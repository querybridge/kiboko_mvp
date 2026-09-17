"""Bridge the top-bar scope + period selection to GA4 data the analytics
dashboards consume.

Connection-aware behaviour:
  * NOT connected (no Google identity, or the scope has no GA4 property) -> each
    provider returns None, and the caller uses illustrative dummy data.
  * CONNECTED (Google identity + a scoped GA4 property) -> providers ALWAYS return
    real data, or **zeros** if a fetch fails/returns nothing. We never fall back
    to dummy for connected data, so any empty/zero chart is a visible, diagnosable
    gap (each is logged).
"""
import datetime
import logging
import math

from app.analytics_data import PRIMARY_OPTIONS, MAX_POINTS
from app.integrations import google_oauth, ga4_data, metrics as M

logger = logging.getLogger(__name__)

# Row fundamentals carried to build_metrics (new_visitors makes new/returning real).
_FUND_KEYS = ('visits', 'visitors', 'new_visitors', 'carts', 'orders', 'units', 'sales')

SPLIT_BUCKETS = {
    'device': ['desktop', 'mobile', 'tablet', 'others'],
    'channel': ['direct', 'organic', 'paid', 'social', 'referral', 'others'],
}
DEVICE_DISPLAY = {'desktop': 'Desktop', 'mobile': 'Mobile', 'tablet': 'Tablet', 'others': 'Other'}
CHANNEL_DISPLAY = {'direct': 'Direct', 'organic': 'Organic Search', 'paid': 'Paid',
                   'social': 'Social', 'referral': 'Referral', 'others': 'Other'}


# --------------------------------------------------------------------------
# Scope / connection
# --------------------------------------------------------------------------

def _scope_ids(request):
    """(company_id, vertical_sel, website_sel) preferring the live URL params over
    the session, so a just-applied scope is used on the SAME request (the session
    is only updated later, at template render, by the tenancy context processor)."""
    def pick(param, key):
        v = request.GET.get(param)
        return v if v is not None else request.session.get(key)
    return (pick('company', 'scope_company'),
            pick('vertical', 'scope_vertical'),
            pick('website', 'scope_website'))


def _resolve_scope(request):
    """(property_ids, stream_id) for the current top-bar scope, or None.

    Enforces org access + per-user business-unit visibility: the user must be
    able to see the company, and only their allowed business units' properties
    are ever returned (defense-in-depth against a forged ?vertical= param)."""
    from business_unit.models import BusinessUnit, Website, Company
    from business_unit.access import can_access_company, allowed_bu_ids
    user = getattr(request, 'user', None)
    company_id, vertical_sel, website_sel = _scope_ids(request)
    if not company_id:
        return None
    company = Company.objects.filter(pk=company_id).first()
    if not company or not can_access_company(user, company):
        return None
    allowed = allowed_bu_ids(user, company)                 # None = all
    bu_qs = BusinessUnit.objects.filter(company_id=company_id).exclude(ga4_property_id='')
    if allowed is not None:
        bu_qs = bu_qs.filter(id__in=allowed)
    # A specific BusinessUnit -> only if it belongs to the company AND is allowed.
    if vertical_sel and vertical_sel != 'all':
        vertical = bu_qs.filter(pk=vertical_sel).first()
        if vertical and vertical.ga4_property_id:
            stream_id = None
            if website_sel and website_sel != 'all':
                site = Website.objects.filter(pk=website_sel, vertical=vertical).first()
                stream_id = site.ga4_stream_id if site else None
            return [vertical.ga4_property_id], stream_id
    # All Business Units -> every allowed GA4 property in the company.
    property_ids = list(bu_qs.values_list('ga4_property_id', flat=True))
    return (property_ids, None) if property_ids else None


def _connected_scope(request):
    """(identity, property_ids, stream_id) when connected to GA4, else None.
    No network calls -- just checks config + scope."""
    if not google_oauth.is_enabled():
        return None
    identity = getattr(request.user, 'google_identity', None)
    if not identity:
        return None
    scope = _resolve_scope(request)
    if not scope:
        return None
    property_ids, stream_id = scope
    return identity, property_ids, stream_id


def _premium_connection(request):
    """(BigQueryConnection, property_ids) when the scoped company is Premium and
    the user is authorized (member/superuser), else None. Access = membership,
    NOT the user's personal Google/GA4 access."""
    from business_unit.models import BigQueryConnection, Company
    from business_unit.access import can_access_company
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    company_id = _scope_ids(request)[0]
    if not company_id:
        return None
    bq = BigQueryConnection.objects.filter(company_id=company_id).first()
    if not bq or not bq.service_account_json:
        return None
    company = Company.objects.filter(pk=company_id).first()
    if not company or not can_access_company(user, company):   # superuser / org admin / member
        return None
    scope = _resolve_scope(request)
    if not scope:
        return None
    property_ids, _stream = scope
    return bq, property_ids


def is_connected(request):
    """True when the current scope is backed by real data: a Premium BigQuery
    company, a GA4 property the user can read, or seeded/uploaded DailyActual.
    Dashboards show real-or-zeros (never dummy) then."""
    return (_premium_connection(request) is not None or _connected_scope(request) is not None
            or _scope_has_actuals(request))


def signin_prompt(request):
    """True when the scoped company has real (Standard/GA4) data but the current
    login can't fetch it because it isn't signed in with Google. Dashboards then
    show a 'Sign in with Google' banner instead of misleading dummy data. Pure
    demo companies (no GA4 property) stay on dummy -> return False."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    if not google_oauth.is_enabled():
        return False                              # can't sign in -> dummy is all we have
    if getattr(user, 'google_identity', None):
        return False                              # already linked a Google account
    if _premium_connection(request) is not None:
        return False                              # Premium fetches via the service account
    company_id = _scope_ids(request)[0]
    if not company_id:
        return False
    from business_unit.models import BusinessUnit
    return BusinessUnit.objects.filter(company_id=company_id).exclude(ga4_property_id='').exists()


def _bq_rows(bq, property_ids, primary_code, compare_code, today, custom=None):
    """Premium daily rows (rollup cache or live BigQuery, summed across the
    company's datasets), aggregated over the full period then bucketed."""
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today, custom)
    labels = [d.strftime('%m-%d') for d in _range_dates(p_start, p_end)]
    try:
        daily_p, dates_p = _order_days(_daily_fundamentals(bq, property_ids, p_start, p_end), p_start, p_end)
        daily_s, _ = _order_days(_daily_fundamentals(bq, property_ids, s_start, s_end), s_start, s_end)
        rows_p, labels = _bucketize(daily_p, dates_p, MAX_POINTS)
        rows_s = _bucketize_to(daily_s, len(rows_p))
        return rows_p, rows_s, labels
    except Exception as e:
        logger.warning('Premium (BigQuery) daily fundamentals unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        z = _zero_rows(len(labels))
        return z, list(z), labels


# --------------------------------------------------------------------------
# Premium (BigQuery) helpers for the detail providers (splits, engage, story,
# segments, item-level). Each mirrors its GA4 counterpart's shape so the
# dashboards render identically whether Standard or Premium.
# --------------------------------------------------------------------------

def _bq_ranges(request, bq, primary_code, compare_code, today):
    """Date ranges for a Premium provider, anchored to the export's data_through."""
    today = _bq_today(bq, today or datetime.date.today())
    custom = _custom_dates(request) if primary_code == 'CUSTOM' else None
    return _date_ranges(primary_code, compare_code, today, custom)


# --- Source dispatchers: rollup cache when it covers the range, else live ----
# Each returns a per-day dict MERGED across the company's properties, in the same
# shape the live bigquery fetch functions emit, so the providers are source-blind.

def _daily_fundamentals(bq, property_ids, start, end):
    from business_unit import rollup as R
    if R.covers(bq.company, property_ids, start, end):
        return R.fundamentals(bq.company, property_ids, start, end)
    from app.integrations import bigquery as bqmod
    client = bqmod.connect(bq.service_account_json)
    out = {}
    for pid in property_ids:
        ds = bqmod.dataset_for(pid)
        if not ds:
            continue
        for day, rec in bqmod.fetch_daily_fundamentals(client, ds, start, end, bq.event_map).items():
            acc = out.setdefault(day, {k: 0.0 for k in _FUND_KEYS})
            for k in _FUND_KEYS:
                acc[k] += rec.get(k, 0.0)
    return out


def _daily_totals(bq, property_ids, start, end):
    from business_unit import rollup as R
    if R.covers(bq.company, property_ids, start, end):
        return R.totals(bq.company, property_ids, start, end)
    from app.integrations import bigquery as bqmod
    client = bqmod.connect(bq.service_account_json)
    out = {}
    for pid in property_ids:
        ds = bqmod.dataset_for(pid)
        if not ds:
            continue
        for day, t in bqmod.fetch_daily_totals(client, ds, start, end, bq.event_map).items():
            acc = out.setdefault(day, {})
            for k, v in t.items():
                acc[k] = acc.get(k, 0.0) + float(v or 0)
    return out


def _daily_split(bq, property_ids, start, end, split):
    from business_unit import rollup as R
    if R.covers(bq.company, property_ids, start, end):
        return R.split_daily(bq.company, property_ids, start, end, split)
    from app.integrations import bigquery as bqmod
    client = bqmod.connect(bq.service_account_json)
    out = {}
    for pid in property_ids:
        ds = bqmod.dataset_for(pid)
        if not ds:
            continue
        for day, bmap in bqmod.fetch_split_daily(client, ds, start, end, split, bq.event_map).items():
            dd = out.setdefault(day, {})
            for bucket, rec in bmap.items():
                acc = dd.setdefault(bucket, {k: 0.0 for k in _FUND_KEYS})
                for k in _FUND_KEYS:
                    acc[k] += float(rec.get(k, 0) or 0)
    return out


def _daily_order_item(bq, property_ids, start, end):
    from business_unit import rollup as R
    if R.covers(bq.company, property_ids, start, end):
        return R.order_item(bq.company, property_ids, start, end)
    from app.integrations import bigquery as bqmod
    client = bqmod.connect(bq.service_account_json)
    out = {}
    for pid in property_ids:
        ds = bqmod.dataset_for(pid)
        if not ds:
            continue
        for day, rec in bqmod.fetch_daily_order_item(client, ds, start, end, bq.event_map).items():
            dd = out.setdefault(day, {'orders': 0.0, '_w': 0.0, 'single_sku_orders': 0.0})
            dd['orders'] += rec['orders']
            dd['_w'] += rec['unique_skus_per_order'] * rec['orders']
            dd['single_sku_orders'] += rec['single_sku_orders']
    for v in out.values():
        v['unique_skus_per_order'] = (v['_w'] / v['orders']) if v['orders'] else 0.0
        del v['_w']
    return out


def _daily_category(bq, property_ids, start, end):
    from business_unit import rollup as R
    if R.covers(bq.company, property_ids, start, end):
        return R.category(bq.company, property_ids, start, end)
    from app.integrations import bigquery as bqmod
    client = bqmod.connect(bq.service_account_json)
    out = {}
    for pid in property_ids:
        ds = bqmod.dataset_for(pid)
        if not ds:
            continue
        for day, cmap in bqmod.fetch_daily_category(client, ds, start, end, bq.event_map).items():
            dd = out.setdefault(day, {})
            for cat, rec in cmap.items():
                acc = dd.setdefault(cat, {'orders': 0.0, 'units': 0.0, 'sales': 0.0})
                for k in ('orders', 'units', 'sales'):
                    acc[k] += float(rec.get(k, 0) or 0)
    return out


def _bq_split_totals(bq, property_ids, start, end, split):
    """{bucket: {fund: total}} over the period (rollup or live)."""
    buckets = {b: {k: 0.0 for k in _FUND_KEYS} for b in SPLIT_BUCKETS[split]}
    for _day, bmap in _daily_split(bq, property_ids, start, end, split).items():
        for bucket, rec in bmap.items():
            if bucket in buckets:
                for k in _FUND_KEYS:
                    buckets[bucket][k] += float(rec.get(k, 0) or 0)
    return buckets


def _bq_split_daily_visits(bq, property_ids, start, end, split):
    """{bucket: {YYYYMMDD: visits}} (split-card sparklines)."""
    out = {b: {} for b in SPLIT_BUCKETS[split]}
    for day, bmap in _daily_split(bq, property_ids, start, end, split).items():
        for bucket, rec in bmap.items():
            if bucket in out:
                out[bucket][day] = out[bucket].get(day, 0.0) + float(rec.get('visits', 0) or 0)
    return out


def _bq_period_totals(bq, property_ids, start, end, keys):
    """Summed GA4-style totals over the period, restricted to `keys`."""
    acc = {k: 0.0 for k in keys}
    for _day, t in _daily_totals(bq, property_ids, start, end).items():
        for k in keys:
            acc[k] += float(t.get(k, 0) or 0)
    return acc


# --------------------------------------------------------------------------
# Date ranges
# --------------------------------------------------------------------------

def _quarter_start(d):
    return d.replace(month=3 * ((d.month - 1) // 3) + 1, day=1)


def _period_range(code, today):
    """(start, end) honoring each period's real semantics. GA4 daily tables lag,
    so 'to-date' periods run through yesterday (the last complete day)."""
    end = today - datetime.timedelta(days=1)
    if code == 'THISMONTH':                       # month-to-date
        start = today.replace(day=1)
    elif code == 'LASTMONTH':
        end = today.replace(day=1) - datetime.timedelta(days=1)
        start = end.replace(day=1)
    elif code == 'THISQT':                         # quarter-to-date
        start = _quarter_start(today)
    elif code == 'ROLLQTR':                        # rolling 13 weeks
        start = end - datetime.timedelta(days=90)
    elif code == 'ROLLYEAR':                       # rolling 12 months
        start = end - datetime.timedelta(days=364)
    elif code in ('THISWEEKSUN', 'THISWEEKMON'):   # week-to-date
        since = (today.weekday() + 1) % 7 if code == 'THISWEEKSUN' else today.weekday()
        start = today - datetime.timedelta(days=since)
    elif code in ('LASTWEEKSUN', 'LASTWEEKMON'):
        since = (today.weekday() + 1) % 7 if code == 'LASTWEEKSUN' else today.weekday()
        end = today - datetime.timedelta(days=since + 1)
        start = end - datetime.timedelta(days=6)
    else:                                          # CUSTOM / fallback -> last 30 days
        start = end - datetime.timedelta(days=29)
    if start > end:
        start = end
    return start, end


def _comparison_range(compare_code, p_start, p_end):
    """The comparison window: same period a year earlier (year-over-year compare
    codes) or the immediately preceding period of the same length."""
    yoy = any(tok in (compare_code or '').upper()
              for tok in ('LY', 'YEAR', 'QTRLY', 'MONLY', 'WEEKLY'))
    if yoy:
        try:
            return p_start.replace(year=p_start.year - 1), p_end.replace(year=p_end.year - 1)
        except ValueError:  # Feb 29
            return (p_start - datetime.timedelta(days=365), p_end - datetime.timedelta(days=365))
    length = (p_end - p_start).days + 1
    s_end = p_start - datetime.timedelta(days=1)
    return s_end - datetime.timedelta(days=length - 1), s_end


def _custom_dates(request):
    """(start, end) date objects for a Custom period from the session, or None."""
    cs, ce = request.session.get('analytics_custom_start'), request.session.get('analytics_custom_end')
    try:
        return datetime.date.fromisoformat(cs), datetime.date.fromisoformat(ce)
    except (TypeError, ValueError):
        return None


def _date_ranges(primary_code, compare_code, today, custom=None):
    if primary_code == 'CUSTOM' and custom:
        p_start, p_end = custom
    else:
        p_start, p_end = _period_range(primary_code, today)
    s_start, s_end = _comparison_range(compare_code, p_start, p_end)
    return p_start, p_end, s_start, s_end


def _ranges(request, primary_code, compare_code, today):
    """Date ranges honoring a Custom period's session start/end when applicable."""
    custom = _custom_dates(request) if primary_code == 'CUSTOM' else None
    return _date_ranges(primary_code, compare_code, today, custom)


def _order_days(by_day, start, end):
    """Ordered, zero-filled daily rows from a {YYYYMMDD: fundamentals} dict."""
    rows, dates, day = [], [], start
    while day <= end:
        rec = by_day.get(day.strftime('%Y%m%d'))
        rows.append({k: float((rec or {}).get(k, 0) or 0) for k in _FUND_KEYS})
        dates.append(day)
        day += datetime.timedelta(days=1)
    return rows, dates


def _daily_rows(creds, property_ids, start, end, stream_id):
    """All daily rows across [start, end] (no cap), zero-filled, + dates."""
    return _order_days(_fetch_by_day(creds, property_ids, start, end, stream_id), start, end)


def _bucketize(rows, dates, count):
    """Sum consecutive days into <= count buckets so long periods (quarter/year)
    stay readable AND totals stay correct. Returns (bucket_rows, labels)."""
    if len(rows) <= count:
        return rows, [d.strftime('%m-%d') for d in dates]
    size = math.ceil(len(rows) / count)
    brows, labels = [], []
    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        brows.append({k: sum(r[k] for r in chunk) for k in _FUND_KEYS})
        labels.append(dates[i].strftime('%m-%d'))
    return brows, labels


def _bucketize_to(rows, count):
    """Sum consecutive days into exactly `count` buckets (comparison series)."""
    if not rows:
        return _zero_rows(count)
    size = max(1, math.ceil(len(rows) / count))
    out = [{k: sum(r[k] for r in rows[i:i + size]) for k in _FUND_KEYS}
           for i in range(0, len(rows), size)]
    out += _zero_rows(count - len(out))
    return out[:count]


def _range_dates(start, end):
    dates, day = [], start
    while day <= end:
        dates.append(day)
        day += datetime.timedelta(days=1)
    return dates[-MAX_POINTS:] if len(dates) > MAX_POINTS else dates


# --------------------------------------------------------------------------
# Fetch helpers
# --------------------------------------------------------------------------

def _fetch_by_day(creds, property_ids, start, end, stream_id):
    merged = {}
    for pid in property_ids:
        by_day = ga4_data.fetch_daily_fundamentals(
            creds, pid, start.isoformat(), end.isoformat(), stream_id=stream_id)
        for day, rec in by_day.items():
            acc = merged.setdefault(day, {k: 0.0 for k in _FUND_KEYS})
            for k in _FUND_KEYS:
                acc[k] += float(rec.get(k, 0) or 0)
    return merged


def _split_funds(creds, property_ids, start, end, split, stream_id):
    """{bucket: {fund: total}} summed across properties for one split."""
    buckets = {b: {k: 0.0 for k in _FUND_KEYS} for b in SPLIT_BUCKETS[split]}
    for pid in property_ids:
        daily = ga4_data.fetch_daily_split(
            creds, pid, start.isoformat(), end.isoformat(), split, stream_id=stream_id)
        for _day, bmap in daily.items():
            for bucket, rec in bmap.items():
                if bucket in buckets:
                    for k in _FUND_KEYS:
                        buckets[bucket][k] += float(rec.get(k, 0) or 0)
    return buckets


def _split_daily_visits(creds, property_ids, start, end, split, stream_id):
    """{bucket: {YYYYMMDD: visits}} for the split-card sparklines."""
    out = {b: {} for b in SPLIT_BUCKETS[split]}
    for pid in property_ids:
        daily = ga4_data.fetch_daily_split(
            creds, pid, start.isoformat(), end.isoformat(), split, stream_id=stream_id)
        for day, bmap in daily.items():
            for bucket, rec in bmap.items():
                if bucket in out:
                    out[bucket][day] = out[bucket].get(day, 0.0) + float(rec.get('visits', 0) or 0)
    return out


def _zero_rows(n):
    return [{k: 0.0 for k in _FUND_KEYS} for _ in range(n)]


# --------------------------------------------------------------------------
# DailyActual fallback — used when a company has neither a Premium (BigQuery)
# nor Standard (GA4) connection but DOES have DailyActual rows (seeded/uploaded).
# DailyActual carries only revenue / visits / orders, so the remaining GA4
# "fundamentals" are best-effort estimates from fixed retail ratios. Dummy data
# is reserved for a scope with no actuals at all.
# --------------------------------------------------------------------------
DA_SESSIONS_PER_VISITOR = 1.3      # sessions (visits) per visitor (user)
DA_NEW_VISITOR_SHARE = 0.40
DA_CART_COMPLETION = 0.35          # orders / carts
DA_UNITS_PER_ORDER = 1.8
# Best-effort device / channel mix for split cards (must sum ~1 per split).
DA_DEVICE_MIX = {'desktop': 0.42, 'mobile': 0.50, 'tablet': 0.05, 'others': 0.03}
DA_CHANNEL_MIX = {'direct': 0.26, 'organic': 0.34, 'paid': 0.18, 'social': 0.10,
                  'referral': 0.08, 'others': 0.04}


def _fund_from_actual(revenue, visits, orders):
    visits = float(visits or 0); orders = float(orders or 0); revenue = float(revenue or 0)
    visitors = visits / DA_SESSIONS_PER_VISITOR if visits else 0.0
    carts = orders / DA_CART_COMPLETION if orders else 0.0
    return {'visits': visits, 'visitors': visitors, 'new_visitors': visitors * DA_NEW_VISITOR_SHARE,
            'carts': carts, 'orders': orders, 'units': orders * DA_UNITS_PER_ORDER, 'sales': revenue}


def _scoped_verticals(request):
    """BusinessUnits for the current top-bar scope (company + optional vertical),
    access-checked, WITHOUT requiring a GA4 property (for the DailyActual tier)."""
    from business_unit.models import BusinessUnit, Company
    from business_unit.access import can_access_company, allowed_bu_ids
    user = getattr(request, 'user', None)
    company_id, vertical_sel, _ = _scope_ids(request)
    if not company_id:
        return []
    company = Company.objects.filter(pk=company_id).first()
    if not company or not can_access_company(user, company):
        return []
    allowed = allowed_bu_ids(user, company)
    qs = BusinessUnit.objects.filter(company_id=company_id)
    if allowed is not None:
        qs = qs.filter(id__in=allowed)
    if vertical_sel and vertical_sel != 'all':
        qs = qs.filter(pk=vertical_sel)
    return list(qs)


def _actual_by_day(verticals, start, end):
    """{'YYYYMMDD': fundamentals} from DailyActual summed over verticals, or None
    when there are no rows in range."""
    from app.models import DailyActual
    if not verticals:
        return None
    agg = {}
    for a in DailyActual.objects.filter(vertical__in=verticals, date__range=(start, end)):
        acc = agg.setdefault(a.date.strftime('%Y%m%d'), {'r': 0.0, 'v': 0, 'o': 0})
        acc['r'] += float(a.revenue or 0); acc['v'] += int(a.visits or 0); acc['o'] += int(a.orders or 0)
    if not agg:
        return None
    return {k: _fund_from_actual(v['r'], v['v'], v['o']) for k, v in agg.items()}


def _scope_has_actuals(request):
    from app.models import DailyActual
    verts = _scoped_verticals(request)
    return bool(verts) and DailyActual.objects.filter(vertical__in=verts).exists()


def _period_totals(by_day):
    """Sum a {day: fundamentals} dict into one fundamentals total."""
    t = {k: 0.0 for k in _FUND_KEYS}
    for rec in (by_day or {}).values():
        for k in _FUND_KEYS:
            t[k] += rec.get(k, 0.0)
    return t


def _actual_split(verts, p_start, p_end, s_start, s_end, split):
    """Best-effort device/channel split of DailyActual, in the shape _split_metrics
    expects: (prim{bucket:fund}, sec{bucket:fund}, by_day{bucket:{YYYYMMDD:visits}})."""
    mix = DA_DEVICE_MIX if split == 'device' else DA_CHANNEL_MIX
    by_p = _actual_by_day(verts, p_start, p_end) or {}
    tp, ts = _period_totals(by_p), _period_totals(_actual_by_day(verts, s_start, s_end) or {})
    prim = {b: {k: tp[k] * frac for k in _FUND_KEYS} for b, frac in mix.items()}
    sec = {b: {k: ts[k] * frac for k in _FUND_KEYS} for b, frac in mix.items()}
    by_day = {b: {d: rec['visits'] * frac for d, rec in by_p.items()} for b, frac in mix.items()}
    return prim, sec, by_day


def _actual_engage_raw(t):
    """Best-effort Engage raw counts from a DailyActual fundamentals total."""
    v, o, carts = t['visits'], t['orders'], t['carts']
    return {'sessions': v, 'engagedSessions': v * 0.58, 'userEngagementDuration': v * 95.0,
            'screenPageViews': v * 4.6, 'addToCarts': carts, 'ecommercePurchases': o,
            'view_item': v * 1.15, 'view_item_list': v * 0.85, 'view_cart': carts * 0.85,
            'begin_checkout': carts * 0.55, 'add_shipping_info': o * 1.2}


# --------------------------------------------------------------------------
# Providers  (return real-or-zeros when connected, None when not connected)
# --------------------------------------------------------------------------

def _bq_today(bq, today):
    """Anchor 'today' to the export's latest data (+1 day) so relative periods
    land on the data rather than on the real calendar today."""
    if bq.data_through:
        return min(today, bq.data_through + datetime.timedelta(days=1))
    return today


def ga4_rows(request, primary_code, compare_code, today=None):
    today = today or datetime.date.today()
    custom = _custom_dates(request) if primary_code == 'CUSTOM' else None
    bqp = _premium_connection(request)
    if bqp is not None:                      # Premium company -> BigQuery
        return _bq_rows(bqp[0], bqp[1], primary_code, compare_code, _bq_today(bqp[0], today), custom)
    sc = _connected_scope(request)
    if sc is None:
        # DailyActual fallback (seeded/uploaded actuals) before dummy.
        verts = _scoped_verticals(request)
        p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)
        by_p = _actual_by_day(verts, p_start, p_end)
        if by_p is None:
            return None
        rows_p, labels = _bucketize(*_order_days(by_p, p_start, p_end), MAX_POINTS)
        by_s = _actual_by_day(verts, s_start, s_end) or {}
        rows_s = _bucketize_to(_order_days(by_s, s_start, s_end)[0], len(rows_p))
        return rows_p, rows_s, labels
    identity, property_ids, stream_id = sc
    p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)
    try:
        creds = google_oauth.credentials_from_identity(identity)
        # Aggregate over the FULL period (correct KPI totals), then bucket the
        # daily series into <= MAX_POINTS points so the chart spans the period
        # with correct dates.
        daily_p, dates_p = _daily_rows(creds, property_ids, p_start, p_end, stream_id)
        daily_s, _ = _daily_rows(creds, property_ids, s_start, s_end, stream_id)
        rows_p, labels = _bucketize(daily_p, dates_p, MAX_POINTS)
        rows_s = _bucketize_to(daily_s, len(rows_p))
        return rows_p, rows_s, labels
    except Exception as e:
        logger.warning('GA4 CONNECTED but daily fundamentals unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        labels = [d.strftime('%m-%d') for d in _range_dates(p_start, p_end)]
        z = _zero_rows(len(labels))
        return z, list(z), labels


def _split_metrics(prim, sec, by_day, dates_p, split):
    """Shared: assemble the per-bucket split card payload from period totals +
    comparison totals + daily visits."""
    grand = sum(prim[b]['visits'] for b in SPLIT_BUCKETS[split]) or 1.0
    out = {}
    for b in SPLIT_BUCKETS[split]:
        p_tot, s_tot = prim[b]['visits'], sec[b]['visits']
        out[b] = {
            'total': p_tot,
            'delta': round(((p_tot - s_tot) / s_tot * 100) if s_tot else 0.0, 2),
            'share': p_tot / grand,
            'daily': [round(by_day[b].get(d.strftime('%Y%m%d'), 0.0), 2) for d in dates_p],
        }
    return out


def ga4_splits(request, primary_code, compare_code, today=None):
    today = today or datetime.date.today()
    bqp = _premium_connection(request)
    if bqp is not None:                            # Premium company -> BigQuery
        return _bq_splits(request, bqp, primary_code, compare_code, today)
    sc = _connected_scope(request)
    if sc is None:
        # DailyActual fallback (best-effort device/channel mix) before dummy.
        verts = _scoped_verticals(request)
        p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)
        if _actual_by_day(verts, p_start, p_end) is None:
            return None
        dates_p = _range_dates(p_start, p_end)
        return {split: _split_metrics(*_actual_split(verts, p_start, p_end, s_start, s_end, split),
                                      dates_p, split) for split in ('device', 'channel')}
    identity, property_ids, stream_id = sc
    p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)
    dates_p = _range_dates(p_start, p_end)

    def zeros():
        return {split: {b: {'total': 0.0, 'delta': 0.0, 'share': 0.0, 'daily': [0.0] * len(dates_p)}
                        for b in SPLIT_BUCKETS[split]} for split in ('device', 'channel')}
    try:
        creds = google_oauth.credentials_from_identity(identity)
        out = {}
        for split in ('device', 'channel'):
            prim = _split_funds(creds, property_ids, p_start, p_end, split, stream_id)
            sec = _split_funds(creds, property_ids, s_start, s_end, split, stream_id)
            by_day = _split_daily_visits(creds, property_ids, p_start, p_end, split, stream_id)
            out[split] = _split_metrics(prim, sec, by_day, dates_p, split)
        return out
    except Exception as e:
        logger.warning('GA4 CONNECTED but device/channel splits unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


def _bq_splits(request, bqp, primary_code, compare_code, today):
    """Premium device/channel splits from BigQuery -- mirrors ga4_splits."""
    bq, property_ids = bqp
    p_start, p_end, s_start, s_end = _bq_ranges(request, bq, primary_code, compare_code, today)
    dates_p = _range_dates(p_start, p_end)

    def zeros():
        return {split: {b: {'total': 0.0, 'delta': 0.0, 'share': 0.0, 'daily': [0.0] * len(dates_p)}
                        for b in SPLIT_BUCKETS[split]} for split in ('device', 'channel')}
    try:
        out = {}
        for split in ('device', 'channel'):
            prim = _bq_split_totals(bq, property_ids, p_start, p_end, split)
            sec = _bq_split_totals(bq, property_ids, s_start, s_end, split)
            by_day = _bq_split_daily_visits(bq, property_ids, p_start, p_end, split)
            out[split] = _split_metrics(prim, sec, by_day, dates_p, split)
        return out
    except Exception as e:
        logger.warning('Premium (BigQuery) device/channel splits unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


# Engage: session metrics + ecommerce events. Funnel views and PDP/category
# views come straight from GA4 events (view_item / view_item_list / view_cart /
# begin_checkout / add_shipping_info) -- no page-path config needed. Engagement
# history cards are computed from raw session counts (which sum across properties).
ENGAGE_METRICS = ['sessions', 'engagedSessions', 'userEngagementDuration',
                  'screenPageViews', 'addToCarts', 'ecommercePurchases']
ENGAGE_EVENT_NAMES = ['view_item', 'view_item_list', 'view_cart', 'begin_checkout', 'add_shipping_info']

_ENGAGE_KEYS = ['pdp_views', 'category_pv', 'carts_per_pdp', 'orders_per_pdp', 'bounce_rate',
                'visit_duration', 'shopper_activity', 'pages_per_visit', 'cat_pdp_per_visit',
                'pdp_per_visit', 'cart_views', 'checkout_views', 'billing_views']


def _engage_compute(a):
    """Derive the Engage card values from one period's raw counts."""
    def sd(x, y):
        return x / y if y else 0.0
    sess, eng, dur = a['sessions'], a['engagedSessions'], a['userEngagementDuration']
    pv, carts, orders = a['screenPageViews'], a['addToCarts'], a['ecommercePurchases']
    vi, vl = a['view_item'], a['view_item_list']
    return {
        'pdp_views': vi,                          # view_item events
        'category_pv': vl,                        # view_item_list events
        'carts_per_pdp': sd(carts, vi) * 100,
        'orders_per_pdp': sd(orders, vi) * 100,
        'bounce_rate': sd(sess - eng, sess) * 100,
        'visit_duration': sd(dur, sess),          # avg engagement seconds / session
        'shopper_activity': sd(eng, sess) * 100,  # engagement rate
        'pages_per_visit': sd(pv, sess),
        'cat_pdp_per_visit': sd(vl, sess),
        'pdp_per_visit': sd(vi, sess),
        'cart_views': a['view_cart'],
        'checkout_views': a['begin_checkout'],
        'billing_views': a['add_shipping_info'],
    }


def ga4_engage_metrics(request, primary_code, compare_code, today=None):
    """Engage card values (+ deltas) from real GA4 events/metrics, or None.
    Keys in _ENGAGE_KEYS, each also with a _delta suffix."""
    bqp = _premium_connection(request)
    if bqp is not None:                            # Premium company -> BigQuery
        return _bq_engage_metrics(request, bqp, primary_code, compare_code, today)
    sc = _connected_scope(request)
    if sc is None:
        # DailyActual fallback (best-effort funnel) before dummy.
        verts = _scoped_verticals(request)
        today = today or datetime.date.today()
        p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)
        by_p = _actual_by_day(verts, p_start, p_end)
        if by_p is None:
            return None
        by_s = _actual_by_day(verts, s_start, s_end) or {}
        return _engage_payload(_engage_compute(_actual_engage_raw(_period_totals(by_p))),
                               _engage_compute(_actual_engage_raw(_period_totals(by_s))))
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)

    def zeros():
        return {**{k: 0.0 for k in _ENGAGE_KEYS}, **{k + '_delta': 0.0 for k in _ENGAGE_KEYS}}
    try:
        creds = google_oauth.credentials_from_identity(identity)

        def raw(start, end):
            acc = {m: 0.0 for m in ENGAGE_METRICS}
            acc.update({e: 0.0 for e in ENGAGE_EVENT_NAMES})
            for pid in property_ids:
                t = ga4_data.fetch_totals(creds, pid, start.isoformat(), end.isoformat(),
                                          ENGAGE_METRICS, stream_id=stream_id)
                for m in ENGAGE_METRICS:
                    acc[m] += t.get(m, 0.0)
                ev = ga4_data.fetch_event_counts(creds, pid, start.isoformat(), end.isoformat(),
                                                 ENGAGE_EVENT_NAMES, stream_id=stream_id)
                for e in ENGAGE_EVENT_NAMES:
                    acc[e] += ev.get(e, 0.0)
            return acc

        return _engage_payload(_engage_compute(raw(p_start, p_end)),
                               _engage_compute(raw(s_start, s_end)))
    except Exception as e:
        logger.warning('GA4 CONNECTED but engage metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


def _engage_payload(p_c, s_c):
    """{key: value, key_delta: pct} for every _ENGAGE_KEYS from two computed periods."""
    out = {}
    for k in _ENGAGE_KEYS:
        out[k] = p_c[k]
        out[k + '_delta'] = round(((p_c[k] - s_c[k]) / s_c[k] * 100) if s_c[k] else 0.0, 2)
    return out


# Period-totals keys the Engage cards need (subset of BigQuery totals).
_ENGAGE_TOTALS_KEYS = ['sessions', 'engagedSessions', 'userEngagementDuration',
                       'screenPageViews', 'addToCarts', 'ecommercePurchases',
                       'view_item', 'view_item_list', 'view_cart', 'begin_checkout',
                       'add_shipping_info']


def _bq_engage_metrics(request, bqp, primary_code, compare_code, today):
    """Premium Engage card values (+ deltas), rollup cache or live -- mirrors ga4_engage_metrics."""
    bq, property_ids = bqp
    p_start, p_end, s_start, s_end = _bq_ranges(request, bq, primary_code, compare_code, today)

    def zeros():
        return {**{k: 0.0 for k in _ENGAGE_KEYS}, **{k + '_delta': 0.0 for k in _ENGAGE_KEYS}}
    try:
        p_c = _engage_compute(_bq_period_totals(bq, property_ids, p_start, p_end, _ENGAGE_TOTALS_KEYS))
        s_c = _engage_compute(_bq_period_totals(bq, property_ids, s_start, s_end, _ENGAGE_TOTALS_KEYS))
        return _engage_payload(p_c, s_c)
    except Exception as e:
        logger.warning('Premium (BigQuery) engage metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


STORY_GA4_METRICS = [
    'sessions', 'totalUsers', 'newUsers', 'engagedSessions', 'userEngagementDuration',
    'screenPageViews', 'addToCarts', 'ecommercePurchases', 'itemsPurchased', 'purchaseRevenue',
]
STORY_EVENT_NAMES = ['view_item', 'view_item_list', 'view_cart', 'begin_checkout', 'add_shipping_info']


def _story_fundamentals(t):
    """Storyboard fundamentals from GA4/BigQuery totals + event counts. Funnel/PDP/
    category views come from real events. single_sku is real on Premium (from the
    item arrays) and a 0.30 approximation on Standard (item-level needs BigQuery)."""
    checkouts = t.get('ecommercePurchases', 0.0)
    single_sku = t.get('single_sku_orders')
    if single_sku is None:
        single_sku = checkouts * 0.30   # item/order-level -> Premium tier
    return dict(
        visitors=t.get('totalUsers', 0.0), new_users=t.get('newUsers', 0.0),
        sessions=t.get('sessions', 0.0),
        engaged=t.get('engagedSessions', 0.0), total_visit_time=t.get('userEngagementDuration', 0.0),
        page_views=t.get('screenPageViews', 0.0), add_to_cart=t.get('addToCarts', 0.0),
        checkouts=checkouts, item_qty=t.get('itemsPurchased', 0.0), revenue=t.get('purchaseRevenue', 0.0),
        category_pv=t.get('view_item_list', 0.0), pdp_pv=t.get('view_item', 0.0),
        cart_views=t.get('view_cart', 0.0), checkout_views=t.get('begin_checkout', 0.0),
        billing_shipping_views=t.get('add_shipping_info', 0.0),
        single_sku=single_sku,
    )


STORY_TOTALS_KEYS = STORY_GA4_METRICS + STORY_EVENT_NAMES


def _bq_story_fundamentals(request, bqp, primary_code, compare_code, today):
    """Premium storyboard fundamentals from BigQuery -- mirrors ga4_story_fundamentals.
    single_sku comes from the real purchase item arrays."""
    bq, property_ids = bqp
    p_start, p_end, s_start, s_end = _bq_ranges(request, bq, primary_code, compare_code, today)

    def zeros():
        return _story_fundamentals({}), _story_fundamentals({})
    try:
        def totals(start, end):
            t = _bq_period_totals(bq, property_ids, start, end, STORY_TOTALS_KEYS)
            t['single_sku_orders'] = sum(
                v['single_sku_orders'] for v in _daily_order_item(bq, property_ids, start, end).values())
            return t

        return _story_fundamentals(totals(p_start, p_end)), _story_fundamentals(totals(s_start, s_end))
    except Exception as e:
        logger.warning('Premium (BigQuery) storyboard metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return _story_fundamentals({}), _story_fundamentals({})


def ga4_story_fundamentals(request, primary_code, compare_code, today=None):
    bqp = _premium_connection(request)
    if bqp is not None:                            # Premium company -> BigQuery
        return _bq_story_fundamentals(request, bqp, primary_code, compare_code, today)
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)

    def zeros():
        return _story_fundamentals({}), _story_fundamentals({})
    try:
        creds = google_oauth.credentials_from_identity(identity)

        def totals(start, end):
            total = {m: 0.0 for m in STORY_GA4_METRICS}
            total.update({e: 0.0 for e in STORY_EVENT_NAMES})
            for pid in property_ids:
                t = ga4_data.fetch_totals(creds, pid, start.isoformat(), end.isoformat(),
                                          STORY_GA4_METRICS, stream_id=stream_id)
                for m in STORY_GA4_METRICS:
                    total[m] += t.get(m, 0.0)
                ev = ga4_data.fetch_event_counts(creds, pid, start.isoformat(), end.isoformat(),
                                                 STORY_EVENT_NAMES, stream_id=stream_id)
                for e in STORY_EVENT_NAMES:
                    total[e] += ev.get(e, 0.0)
            return total

        return _story_fundamentals(totals(p_start, p_end)), _story_fundamentals(totals(s_start, s_end))
    except Exception as e:
        logger.warning('GA4 CONNECTED but storyboard metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


def ga4_segments(request, primary_code, compare_code, today=None):
    """Per-device and per-channel fundamentals for the changeplots, or None.

    {'device': {'Desktop': {'p': {funds}, 's': {funds}}, ...}, 'channel': {...}}
    """
    bqp = _premium_connection(request)
    if bqp is not None:                            # Premium company -> BigQuery
        return _bq_segments(request, bqp, primary_code, compare_code, today)
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _ranges(request, primary_code, compare_code, today)

    def zeros():
        out = {}
        for split, disp in (('device', DEVICE_DISPLAY), ('channel', CHANNEL_DISPLAY)):
            out[split] = {disp[b]: {'p': {k: 0.0 for k in _FUND_KEYS}, 's': {k: 0.0 for k in _FUND_KEYS}}
                          for b in SPLIT_BUCKETS[split]}
        return out
    try:
        creds = google_oauth.credentials_from_identity(identity)
        out = {}
        for split, disp in (('device', DEVICE_DISPLAY), ('channel', CHANNEL_DISPLAY)):
            prim = _split_funds(creds, property_ids, p_start, p_end, split, stream_id)
            sec = _split_funds(creds, property_ids, s_start, s_end, split, stream_id)
            out[split] = {disp[b]: {'p': prim[b], 's': sec[b]} for b in SPLIT_BUCKETS[split]}
        return out
    except Exception as e:
        logger.warning('GA4 CONNECTED but changeplot segments unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


def _accumulate_daily(out, by_day):
    """Fold a {'YYYYMMDD': fundamentals} dict into the pipeline actuals map."""
    for day, rec in by_day.items():
        iso = f'{day[:4]}-{day[4:6]}-{day[6:8]}'
        acc = out.setdefault(iso, {'revenue': 0.0, 'visits': 0, 'orders': 0})
        acc['revenue'] += float(rec.get('sales', 0) or 0)
        acc['visits'] += int(rec.get('visits', 0) or 0)
        acc['orders'] += int(rec.get('orders', 0) or 0)
    return out


def ga4_daily_actuals(request, start, end):
    """{'YYYY-MM-DD': {'revenue': float, 'visits': int, 'orders': int}} of actual
    daily performance for the scoped company over [start, end], or None when the
    scope isn't connected. Used by the Project Value Pipeline so actual revenue
    comes from live analytics instead of uploaded DailyActual rows.

    Source by tier: **Premium -> BigQuery** (faster, no API rate limits; and later
    the daily rollup cache); **Standard -> GA4 Data API** (subject to GA4 API rate
    limits/latency -- the upgrade path to Premium)."""
    bqp = _premium_connection(request)
    if bqp is not None:
        return _bq_daily_actuals(bqp, start, end)
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    try:
        creds = google_oauth.credentials_from_identity(identity)
        out = {}
        for pid in property_ids:
            _accumulate_daily(out, ga4_data.fetch_daily_fundamentals(
                creds, pid, start.isoformat(), end.isoformat(), stream_id=stream_id))
        return out
    except Exception as e:
        logger.warning('PPM pipeline: GA4 daily actuals unavailable (%s: %s) -- using uploaded actuals',
                       type(e).__name__, e)
        return None


def _bq_daily_actuals(bqp, start, end):
    """Premium pipeline actuals -- rollup cache when it covers the range, else a
    live BigQuery scan. Summed across the company's datasets, keyed by iso date."""
    bq, property_ids = bqp
    try:
        out = {}
        for day, rec in _daily_fundamentals(bq, property_ids, start, end).items():
            iso = f'{day[:4]}-{day[4:6]}-{day[6:8]}'
            out[iso] = {'revenue': float(rec.get('sales', 0) or 0),
                        'visits': int(rec.get('visits', 0) or 0),
                        'orders': int(rec.get('orders', 0) or 0)}
        return out
    except Exception as e:
        logger.warning('PPM pipeline: Premium actuals unavailable (%s: %s) -- using uploaded actuals',
                       type(e).__name__, e)
        return None


def baseline_status(request, business_unit):
    """Why a BU can/can't auto-fill baselines, WITHOUT any network call. Connectable:
    'premium' (BigQuery) / 'standard' (GA4) / 'dailyactual' (seeded/uploaded actuals).
    Blocked: 'no-access' / 'no-property' / 'no-oauth' / 'not-signed-in' / 'no-data'."""
    from business_unit.models import BigQueryConnection
    from business_unit.access import can_access_company, allowed_bu_ids
    from app.models import DailyActual
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return 'no-access'
    company = business_unit.company
    if not can_access_company(user, company):
        return 'no-access'
    allowed = allowed_bu_ids(user, company)            # None = all
    if allowed is not None and business_unit.id not in allowed:
        return 'no-access'
    bq = BigQueryConnection.objects.filter(company=company).first()
    if bq and bq.service_account_json:
        return 'premium'
    pid = getattr(business_unit, 'ga4_property_id', '')
    if pid and google_oauth.is_enabled() and getattr(user, 'google_identity', None):
        return 'standard'
    if DailyActual.objects.filter(vertical=business_unit).exists():
        return 'dailyactual'                           # seeded/uploaded actuals
    if not pid:
        return 'no-property'
    if not google_oauth.is_enabled():
        return 'no-oauth'
    return 'not-signed-in'


def baseline_daily_for_bu(request, business_unit, days, end=None):
    """{'YYYY-MM-DD': fundamentals} summed for ONE business unit over the last
    `days` (through `end`, default yesterday), or None when it isn't connected /
    the user can't read it / the fetch fails. Driven by the intake form's chosen
    Business Unit, not the top-bar scope. Fundamentals keys: visits, visitors,
    new_visitors, carts, orders, units, sales."""
    status = baseline_status(request, business_unit)
    if status not in ('premium', 'standard', 'dailyactual'):
        return None
    pid = getattr(business_unit, 'ga4_property_id', '')
    company = business_unit.company
    end = end or (datetime.date.today() - datetime.timedelta(days=1))
    start = end - datetime.timedelta(days=days - 1)

    if status == 'dailyactual':
        by_day = _actual_by_day([business_unit], start, end)   # {'YYYYMMDD': fund}
        if not by_day:
            return None
        return {f'{k[:4]}-{k[4:6]}-{k[6:8]}': rec for k, rec in by_day.items()}

    if status == 'premium':
        from business_unit.models import BigQueryConnection
        bq = BigQueryConnection.objects.filter(company=company).first()
        try:
            out = {}
            for day, rec in _daily_fundamentals(bq, [pid], start, end).items():
                out[f'{day[:4]}-{day[4:6]}-{day[6:8]}'] = rec
            return out
        except Exception as e:
            logger.warning('estimator baseline: Premium fundamentals unavailable (%s: %s)',
                           type(e).__name__, e)
            return None

    identity = getattr(request.user, 'google_identity', None)
    try:
        creds = google_oauth.credentials_from_identity(identity)
        out = {}
        for day, rec in ga4_data.fetch_daily_fundamentals(
                creds, pid, start.isoformat(), end.isoformat()).items():
            out[f'{day[:4]}-{day[4:6]}-{day[6:8]}'] = rec
        return out
    except Exception as e:
        logger.warning('estimator baseline: GA4 fundamentals unavailable (%s: %s)',
                       type(e).__name__, e)
        return None


def realized_perf_for_project(request, project, measure_days=30):
    """Post-launch realized performance for a completed project, or a status dict.
    Compares the project's targeted lever + sales over a post-ramp measurement
    window vs the matching pre-launch window, via the project's data tier
    (BigQuery / GA4 / DailyActual). Returns None when it can't be computed."""
    from project.services import impact
    launch = getattr(project, 'target_completion', None)
    bu = getattr(project, 'vertical', None)
    lever = getattr(project, 'lever', '') or ''
    if not launch or not bu or lever not in impact.LEVER_KEYS:
        return {'ok': False, 'reason': 'no-estimate'}
    ramp = int(getattr(project, 'ramp_days', 30) or 30)
    ramp_end = launch + datetime.timedelta(days=ramp)
    post = (ramp_end, ramp_end + datetime.timedelta(days=measure_days - 1))
    base = (launch - datetime.timedelta(days=measure_days), launch - datetime.timedelta(days=1))
    today = datetime.date.today()
    if post[1] >= today:
        return {'ok': False, 'reason': 'pending', 'ready_on': post[1]}   # window not elapsed yet

    span_days = (post[1] - base[0]).days + 1
    daily = baseline_daily_for_bu(request, bu, span_days, end=post[1])   # {'YYYY-MM-DD': fund}
    if not daily:
        return {'ok': False, 'reason': 'no-data'}

    def _sum(s, e):
        tot = {k: 0.0 for k in _FUND_KEYS}
        for iso, fund in daily.items():
            d = datetime.date.fromisoformat(iso)
            if s <= d <= e:
                for k in _FUND_KEYS:
                    tot[k] += fund.get(k, 0.0)
        return tot

    before, after = _sum(*base), _sum(*post)
    planned = None
    if project.target_from and project.target_to and float(project.target_from) != 0:
        planned = (float(project.target_to) - float(project.target_from)) / float(project.target_from)
    rp = impact.realized_performance(before, after, lever, planned_pct=planned)
    rp.update({'ok': True, 'lever': lever, 'lever_label': impact.LEVERS[lever][0],
               'base_start': base[0], 'base_end': base[1], 'post_start': post[0], 'post_end': post[1],
               # display percentages (the raw values are fractions)
               'perf_pct_disp': rp['perf_pct'] * 100, 'share_disp': rp['share'] * 100,
               'actual_lever_disp': rp['actual_lever_pct'] * 100,
               'planned_disp': (planned * 100) if planned is not None else None})

    # ---- chart-ready data (mirrors the prototype's Realized Performance tab) ----
    aee_color = {'attract_traffic': '#3FC9E0', 'engage_customers': '#ECB752', 'expand_purchase': '#55C892'}
    items = sorted(daily.items())                                # (iso, fundamentals)
    dates = [iso for iso, _ in items]
    sales = [f.get('sales', 0.0) for _, f in items]
    roll = [sum(sales[max(0, i - 6):i + 1]) / len(sales[max(0, i - 6):i + 1]) for i in range(len(sales))]

    def _idx(d):
        for i, iso in enumerate(dates):
            if datetime.date.fromisoformat(iso) >= d:
                return i
        return max(0, len(dates) - 1)

    contrib = sorted(
        ({'label': impact.LEVERS[k][0], 'value': round(rp['contrib'].get(k, 0.0)),
          'color': aee_color.get(impact.LEVERS[k][1], '#9B7FE0'), 'is_target': (k == lever)}
         for k in impact.LEVER_KEYS), key=lambda c: c['value'])
    rp['chart'] = {
        'labels': [d[5:] for d in dates],                        # MM-DD
        'sales': [round(x) for x in roll],
        'baseline': round(before['sales'] / measure_days),       # per-day pre-launch avg
        'launch_i': _idx(launch), 'ramp_i': _idx(ramp_end),
        'post_s_i': _idx(post[0]), 'post_e_i': _idx(post[1]),
        'contrib': contrib,
    }
    return rp


def ga4_item_metrics(request, primary_code, compare_code, today=None):
    """Premium-only item/order-level + per-category metrics for Expand Purchases.

    {'p': {orders, unique_skus_per_order, single_sku_orders}, 's': {...},
     'categories': {'p': {cat: {orders, units, sales}}, 's': {...}}}

    Returns None for Standard/dummy companies (the GA4 Data API can't produce
    item/order-level detail -> those stay Premium-gated)."""
    bqp = _premium_connection(request)
    if bqp is None:
        return None
    bq, property_ids = bqp
    p_start, p_end, s_start, s_end = _bq_ranges(request, bq, primary_code, compare_code, today)
    try:
        def order_item(start, end):
            orders = skus_weighted = single = 0.0
            for v in _daily_order_item(bq, property_ids, start, end).values():
                orders += v['orders']
                single += v['single_sku_orders']
                skus_weighted += v['unique_skus_per_order'] * v['orders']   # re-weight to aggregate
            return {'orders': orders, 'single_sku_orders': single,
                    'unique_skus_per_order': (skus_weighted / orders) if orders else 0.0}

        def categories(start, end):
            acc = {}
            for cmap in _daily_category(bq, property_ids, start, end).values():
                for cat, m in cmap.items():
                    a = acc.setdefault(cat, {'orders': 0.0, 'units': 0.0, 'sales': 0.0})
                    for k in ('orders', 'units', 'sales'):
                        a[k] += m[k]
            return acc

        return {'p': order_item(p_start, p_end), 's': order_item(s_start, s_end),
                'categories': {'p': categories(p_start, p_end), 's': categories(s_start, s_end)}}
    except Exception as e:
        logger.warning('Premium (BigQuery) item/category metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return {'p': {}, 's': {}, 'categories': {'p': {}, 's': {}}}


def _bq_segments(request, bqp, primary_code, compare_code, today):
    """Premium per-device/per-channel changeplot segments (rollup cache or live)."""
    bq, property_ids = bqp
    p_start, p_end, s_start, s_end = _bq_ranges(request, bq, primary_code, compare_code, today)

    def zeros():
        out = {}
        for split, disp in (('device', DEVICE_DISPLAY), ('channel', CHANNEL_DISPLAY)):
            out[split] = {disp[b]: {'p': {k: 0.0 for k in _FUND_KEYS}, 's': {k: 0.0 for k in _FUND_KEYS}}
                          for b in SPLIT_BUCKETS[split]}
        return out
    try:
        out = {}
        for split, disp in (('device', DEVICE_DISPLAY), ('channel', CHANNEL_DISPLAY)):
            prim = _bq_split_totals(bq, property_ids, p_start, p_end, split)
            sec = _bq_split_totals(bq, property_ids, s_start, s_end, split)
            out[split] = {disp[b]: {'p': prim[b], 's': sec[b]} for b in SPLIT_BUCKETS[split]}
        return out
    except Exception as e:
        logger.warning('Premium (BigQuery) changeplot segments unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()
