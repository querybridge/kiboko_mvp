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

def _resolve_scope(request):
    """(property_ids, stream_id) for the current top-bar scope, or None."""
    from business_unit.models import Vertical, Website
    vertical_id = request.session.get('scope_vertical')
    if vertical_id and vertical_id != 'all':
        vertical = Vertical.objects.filter(pk=vertical_id).first()
        if not vertical or not vertical.ga4_property_id:
            return None
        stream_id = None
        website_id = request.session.get('scope_website')
        if website_id and website_id != 'all':
            site = Website.objects.filter(pk=website_id, vertical=vertical).first()
            stream_id = site.ga4_stream_id if site else None
        return [vertical.ga4_property_id], stream_id
    company_id = request.session.get('scope_company')
    if not company_id:
        return None
    property_ids = list(
        Vertical.objects.filter(company_id=company_id)
        .exclude(ga4_property_id='')
        .values_list('ga4_property_id', flat=True))
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
    from business_unit.models import BigQueryConnection, CompanyMembership
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    company_id = request.session.get('scope_company')
    if not company_id:
        return None
    bq = BigQueryConnection.objects.filter(company_id=company_id).first()
    if not bq or not bq.service_account_json:
        return None
    if not user.is_superuser and not CompanyMembership.objects.filter(
            company_id=company_id, user=user).exists():
        return None
    scope = _resolve_scope(request)
    if not scope:
        return None
    property_ids, _stream = scope
    return bq, property_ids


def is_connected(request):
    """True when the current scope is backed by real data (a GA4 property the user
    can read, or a Premium BigQuery company). Dashboards show real-or-zeros then."""
    return _premium_connection(request) is not None or _connected_scope(request) is not None


def _bq_rows(bq, property_ids, primary_code, compare_code, today):
    """Premium daily rows from BigQuery (summed across the company's datasets),
    aggregated over the full period then bucketed -- mirrors ga4_rows."""
    from app.integrations import bigquery as bqmod
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
    labels = [d.strftime('%m-%d') for d in _range_dates(p_start, p_end)]
    try:
        client = bqmod.connect(bq.service_account_json)

        def merged(start, end):
            acc = {}
            for pid in property_ids:
                ds = bqmod.dataset_for(pid)
                if not ds:
                    continue
                for day, rec in bqmod.fetch_daily_fundamentals(client, ds, start, end).items():
                    a = acc.setdefault(day, {k: 0.0 for k in _FUND_KEYS})
                    for k in _FUND_KEYS:
                        a[k] += rec.get(k, 0.0)
            return acc

        daily_p, dates_p = _order_days(merged(p_start, p_end), p_start, p_end)
        daily_s, _ = _order_days(merged(s_start, s_end), s_start, s_end)
        rows_p, labels = _bucketize(daily_p, dates_p, MAX_POINTS)
        rows_s = _bucketize_to(daily_s, len(rows_p))
        return rows_p, rows_s, labels
    except Exception as e:
        logger.warning('Premium (BigQuery) daily fundamentals unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        z = _zero_rows(len(labels))
        return z, list(z), labels


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


def _date_ranges(primary_code, compare_code, today):
    p_start, p_end = _period_range(primary_code, today)
    s_start, s_end = _comparison_range(compare_code, p_start, p_end)
    return p_start, p_end, s_start, s_end


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
# Providers  (return real-or-zeros when connected, None when not connected)
# --------------------------------------------------------------------------

def ga4_rows(request, primary_code, compare_code, today=None):
    today = today or datetime.date.today()
    bqp = _premium_connection(request)
    if bqp is not None:                      # Premium company -> BigQuery
        return _bq_rows(bqp[0], bqp[1], primary_code, compare_code, today)
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
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


def ga4_splits(request, primary_code, compare_code, today=None):
    today = today or datetime.date.today()
    if _premium_connection(request) is not None:
        logger.info('Premium (BigQuery) device/channel splits not wired yet -- showing zeros')
        p_start, p_end, _s, _e = _date_ranges(primary_code, compare_code, today)
        n = len(_range_dates(p_start, p_end))
        return {split: {b: {'total': 0.0, 'delta': 0.0, 'share': 0.0, 'daily': [0.0] * n}
                        for b in SPLIT_BUCKETS[split]} for split in ('device', 'channel')}
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
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
            grand = sum(prim[b]['visits'] for b in SPLIT_BUCKETS[split]) or 1.0
            out[split] = {}
            for b in SPLIT_BUCKETS[split]:
                p_tot, s_tot = prim[b]['visits'], sec[b]['visits']
                out[split][b] = {
                    'total': p_tot,
                    'delta': round(((p_tot - s_tot) / s_tot * 100) if s_tot else 0.0, 2),
                    'share': p_tot / grand,
                    'daily': [round(by_day[b].get(d.strftime('%Y%m%d'), 0.0), 2) for d in dates_p],
                }
        return out
    except Exception as e:
        logger.warning('GA4 CONNECTED but device/channel splits unavailable (%s: %s) -- showing zeros',
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
    if _premium_connection(request) is not None:
        logger.info('Premium (BigQuery) engage metrics not wired yet -- showing zeros')
        return {**{k: 0.0 for k in _ENGAGE_KEYS}, **{k + '_delta': 0.0 for k in _ENGAGE_KEYS}}
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)

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

        p_c, s_c = _engage_compute(raw(p_start, p_end)), _engage_compute(raw(s_start, s_end))
        out = {}
        for k in _ENGAGE_KEYS:
            out[k] = p_c[k]
            out[k + '_delta'] = round(((p_c[k] - s_c[k]) / s_c[k] * 100) if s_c[k] else 0.0, 2)
        return out
    except Exception as e:
        logger.warning('GA4 CONNECTED but engage metrics unavailable (%s: %s) -- showing zeros',
                       type(e).__name__, e)
        return zeros()


STORY_GA4_METRICS = [
    'sessions', 'totalUsers', 'newUsers', 'engagedSessions', 'userEngagementDuration',
    'screenPageViews', 'addToCarts', 'ecommercePurchases', 'itemsPurchased', 'purchaseRevenue',
]
STORY_EVENT_NAMES = ['view_item', 'view_item_list', 'view_cart', 'begin_checkout', 'add_shipping_info']


def _story_fundamentals(t):
    """Storyboard fundamentals from GA4 totals + event counts. Funnel/PDP/category
    views come from real events; single-SKU stays Premium-approximated."""
    checkouts = t.get('ecommercePurchases', 0.0)
    return dict(
        visitors=t.get('totalUsers', 0.0), new_users=t.get('newUsers', 0.0),
        sessions=t.get('sessions', 0.0),
        engaged=t.get('engagedSessions', 0.0), total_visit_time=t.get('userEngagementDuration', 0.0),
        page_views=t.get('screenPageViews', 0.0), add_to_cart=t.get('addToCarts', 0.0),
        checkouts=checkouts, item_qty=t.get('itemsPurchased', 0.0), revenue=t.get('purchaseRevenue', 0.0),
        category_pv=t.get('view_item_list', 0.0), pdp_pv=t.get('view_item', 0.0),
        cart_views=t.get('view_cart', 0.0), checkout_views=t.get('begin_checkout', 0.0),
        billing_shipping_views=t.get('add_shipping_info', 0.0),
        single_sku=checkouts * 0.30,   # item/order-level -> Premium tier
    )


def ga4_story_fundamentals(request, primary_code, compare_code, today=None):
    if _premium_connection(request) is not None:
        logger.info('Premium (BigQuery) storyboard metrics not wired yet -- showing zeros')
        return _story_fundamentals({}), _story_fundamentals({})
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)

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
    if _premium_connection(request) is not None:
        logger.info('Premium (BigQuery) changeplot segments not wired yet -- showing zeros')
        out = {}
        for split, disp in (('device', DEVICE_DISPLAY), ('channel', CHANNEL_DISPLAY)):
            out[split] = {disp[b]: {'p': {k: 0.0 for k in _FUND_KEYS}, 's': {k: 0.0 for k in _FUND_KEYS}}
                          for b in SPLIT_BUCKETS[split]}
        return out
    sc = _connected_scope(request)
    if sc is None:
        return None
    identity, property_ids, stream_id = sc
    today = today or datetime.date.today()
    p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)

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
