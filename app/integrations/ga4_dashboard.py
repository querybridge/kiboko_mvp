"""Bridge the top-bar scope + period selection to GA4 daily rows the analytics
dashboards can consume.

Returns rows in the shape ``build_metrics`` expects — (rows_p, rows_s, labels)
where each row is a dict with visits/visitors/carts/orders/units/sales — so the
existing dashboards render real data with no template changes. Any problem
(no scope, no GA4 property, no Google identity, API error) returns None so the
caller falls back to dummy data.
"""
import datetime
import logging

from app.analytics_data import PRIMARY_OPTIONS, MAX_POINTS
from app.integrations import google_oauth, ga4_data, metrics as M

logger = logging.getLogger(__name__)

_FUND_KEYS = ('visits', 'visitors', 'carts', 'orders', 'units', 'sales')


def _period_days(primary_code):
    return next((d for c, _, d in PRIMARY_OPTIONS if c == primary_code), 30)


def _date_ranges(primary_code, compare_code, today):
    """(p_start, p_end, s_start, s_end) date objects for the primary period and
    its comparison. Primary = last N days ending yesterday. Comparison = same N
    days a year earlier when the compare code implies year-over-year, else the
    immediately preceding N days."""
    days = _period_days(primary_code)
    p_end = today - datetime.timedelta(days=1)
    p_start = p_end - datetime.timedelta(days=days - 1)
    yoy = any(tok in (compare_code or '').upper() for tok in ('LY', 'YEAR', 'QTRLY', 'MONLY', 'WEEKLY'))
    if yoy:
        s_start = p_start.replace(year=p_start.year - 1)
        s_end = p_end.replace(year=p_end.year - 1)
    else:
        s_end = p_start - datetime.timedelta(days=1)
        s_start = s_end - datetime.timedelta(days=days - 1)
    return p_start, p_end, s_start, s_end


def _range_dates(start, end):
    """Ordered list of dates across [start, end], capped to MAX_POINTS (tail)."""
    dates, day = [], start
    while day <= end:
        dates.append(day)
        day += datetime.timedelta(days=1)
    return dates[-MAX_POINTS:] if len(dates) > MAX_POINTS else dates


def _fetch_by_day(creds, property_ids, start, end, stream_id):
    """Merge daily fundamentals across one or more GA4 properties, summed per day
    (the 'All Verticals' / 'All Websites' roll-up = total business performance)."""
    merged = {}
    for pid in property_ids:
        by_day = ga4_data.fetch_daily_fundamentals(
            creds, pid, start.isoformat(), end.isoformat(), stream_id=stream_id)
        for day, rec in by_day.items():
            acc = merged.setdefault(day, {k: 0.0 for k in _FUND_KEYS})
            for k in _FUND_KEYS:
                acc[k] += float(rec.get(k, 0) or 0)
    return merged


def _rows_for_range(creds, property_ids, start, end, stream_id):
    """Ordered list of daily rows (one per day across the range, zero-filled)
    summed across the given properties, plus the ordered date list."""
    by_day = _fetch_by_day(creds, property_ids, start, end, stream_id)
    rows, dates = [], []
    day = start
    while day <= end:
        rec = by_day.get(day.strftime('%Y%m%d'))
        row = {k: float((rec or {}).get(k, 0) or 0) for k in _FUND_KEYS}
        rows.append(row)
        dates.append(day)
        day += datetime.timedelta(days=1)
    # Cap points for long ranges to stay readable (mirrors the dummy path).
    if len(rows) > MAX_POINTS:
        rows = rows[-MAX_POINTS:]
        dates = dates[-MAX_POINTS:]
    return rows, dates


def _resolve_scope(request):
    """(property_ids, stream_id) for the current top-bar scope, or None.

    One Vertical -> [its property] (+ stream if a specific Website is chosen);
    All Verticals -> every GA4 property in the current company.
    """
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


def _scoped_creds(request):
    """(credentials, property_ids, stream_id) or None -- shared preamble."""
    if not google_oauth.is_enabled():
        return None
    identity = getattr(request.user, 'google_identity', None)
    if not identity:
        return None
    scope = _resolve_scope(request)
    if not scope:
        return None
    property_ids, stream_id = scope
    return google_oauth.credentials_from_identity(identity), property_ids, stream_id


def ga4_rows(request, primary_code, compare_code, today=None):
    """(rows_p, rows_s, labels) of real GA4 data for the current scope, or None."""
    try:
        scoped = _scoped_creds(request)
        if not scoped:
            return None
        creds, property_ids, stream_id = scoped
        today = today or datetime.date.today()
        p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
        rows_p, dates_p = _rows_for_range(creds, property_ids, p_start, p_end, stream_id)
        rows_s, _ = _rows_for_range(creds, property_ids, s_start, s_end, stream_id)
        labels = [d.strftime('%m-%d') for d in dates_p]
        # Comparison series must align in length with the primary for the charts.
        if len(rows_s) < len(rows_p):
            rows_s = rows_s + [{k: 0.0 for k in _FUND_KEYS}] * (len(rows_p) - len(rows_s))
        else:
            rows_s = rows_s[:len(rows_p)]
        return rows_p, rows_s, labels
    except Exception as e:
        logger.warning('GA4 dashboard fetch failed (%s: %s) -- falling back to dummy',
                       type(e).__name__, e)
        return None


# Performance Storyboard needs a richer fundamentals set. GA4 provides most of
# these directly; the funnel-view rows it can't (without page-path config) are
# approximated from real metrics in _story_fundamentals below.
STORY_GA4_METRICS = [
    'sessions', 'totalUsers', 'newUsers', 'engagedSessions',
    'userEngagementDuration', 'screenPageViews', 'addToCarts',
    'ecommercePurchases', 'itemsPurchased', 'purchaseRevenue',
]


def _story_totals(creds, property_ids, start, end, stream_id):
    """Summed GA4 story metrics across the properties for the range."""
    total = {m: 0.0 for m in STORY_GA4_METRICS}
    for pid in property_ids:
        t = ga4_data.fetch_totals(creds, pid, start.isoformat(), end.isoformat(),
                                  STORY_GA4_METRICS, stream_id=stream_id)
        for m in STORY_GA4_METRICS:
            total[m] += t.get(m, 0.0)
    return total


def _story_fundamentals(t):
    """Map GA4 metric totals to the storyboard's fundamentals dict. Real where
    GA4 provides it; the funnel-view rows (cart/checkout/billing views, category/
    PDP page views, single-SKU) are approximated from real metrics until the
    page-path/Premium tier lands."""
    sessions = t.get('sessions', 0.0)
    page_views = t.get('screenPageViews', 0.0)
    add_to_cart = t.get('addToCarts', 0.0)
    checkouts = t.get('ecommercePurchases', 0.0)
    return dict(
        visitors=t.get('totalUsers', 0.0),
        new_users=t.get('newUsers', 0.0),
        sessions=sessions,
        engaged=t.get('engagedSessions', 0.0),
        total_visit_time=t.get('userEngagementDuration', 0.0),
        page_views=page_views,
        add_to_cart=add_to_cart,
        checkouts=checkouts,
        item_qty=t.get('itemsPurchased', 0.0),
        revenue=t.get('purchaseRevenue', 0.0),
        # approximated (see docstring)
        category_pv=page_views * 0.45,
        pdp_pv=page_views * 0.60,
        cart_views=add_to_cart * 1.40,
        checkout_views=add_to_cart * 0.60,
        billing_shipping_views=add_to_cart * 0.48,
        single_sku=checkouts * 0.30,
    )


# Bucket order per split (matches the Attract Traffic device/channel cards).
SPLIT_BUCKETS = {
    'device': ['desktop', 'mobile', 'tablet', 'others'],
    'channel': ['direct', 'organic', 'paid', 'social', 'referral', 'others'],
}


def _split_visits(creds, property_ids, start, end, split, stream_id):
    """{bucket: {'total': visits, 'by_day': {YYYYMMDD: visits}}} summed across
    the scope's properties for one split."""
    buckets = {b: {'total': 0.0, 'by_day': {}} for b in SPLIT_BUCKETS[split]}
    for pid in property_ids:
        daily = ga4_data.fetch_daily_split(
            creds, pid, start.isoformat(), end.isoformat(), split, stream_id=stream_id)
        for day, bmap in daily.items():
            for bucket, rec in bmap.items():
                if bucket not in buckets:
                    continue
                v = float(rec.get('visits', 0) or 0)
                buckets[bucket]['total'] += v
                buckets[bucket]['by_day'][day] = buckets[bucket]['by_day'].get(day, 0.0) + v
    return buckets


def ga4_splits(request, primary_code, compare_code, today=None):
    """Real device + channel visit splits for the current scope, or None.

    Returns {'device': {bucket: {total, delta, share, daily}}, 'channel': {...}}
    where `daily` aligns to the primary period's days.
    """
    try:
        scoped = _scoped_creds(request)
        if not scoped:
            return None
        creds, property_ids, stream_id = scoped
        today = today or datetime.date.today()
        p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
        dates_p = _range_dates(p_start, p_end)

        out = {}
        for split in ('device', 'channel'):
            prim = _split_visits(creds, property_ids, p_start, p_end, split, stream_id)
            sec = _split_visits(creds, property_ids, s_start, s_end, split, stream_id)
            grand = sum(b['total'] for b in prim.values()) or 1.0
            out[split] = {}
            for bucket in SPLIT_BUCKETS[split]:
                p_tot = prim[bucket]['total']
                s_tot = sec[bucket]['total']
                delta = ((p_tot - s_tot) / s_tot * 100) if s_tot else 0.0
                out[split][bucket] = {
                    'total': p_tot,
                    'delta': round(delta, 2),
                    'share': p_tot / grand,
                    'daily': [round(prim[bucket]['by_day'].get(d.strftime('%Y%m%d'), 0.0), 2)
                              for d in dates_p],
                }
        return out
    except Exception as e:
        logger.warning('GA4 splits fetch failed (%s: %s) -- falling back to dummy',
                       type(e).__name__, e)
        return None


# Engage funnel-view cards -> GA4 recommended ecommerce events.
ENGAGE_EVENTS = {
    'cart_views': 'view_cart',
    'checkout_views': 'begin_checkout',
    'billing_views': 'add_shipping_info',
}


def ga4_engage_events(request, primary_code, compare_code, today=None):
    """Real cart/checkout/billing view counts (+ deltas) from GA4 events for the
    current scope, or None. Keys: cart_views/checkout_views/billing_views and
    each with a _delta suffix."""
    try:
        scoped = _scoped_creds(request)
        if not scoped:
            return None
        creds, property_ids, stream_id = scoped
        today = today or datetime.date.today()
        p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
        names = list(ENGAGE_EVENTS.values())

        def totals(start, end):
            acc = {n: 0.0 for n in names}
            for pid in property_ids:
                t = ga4_data.fetch_event_counts(
                    creds, pid, start.isoformat(), end.isoformat(), names, stream_id=stream_id)
                for n in names:
                    acc[n] += t.get(n, 0.0)
            return acc

        prim, sec = totals(p_start, p_end), totals(s_start, s_end)
        out = {}
        for key, ev in ENGAGE_EVENTS.items():
            pv, sv = prim[ev], sec[ev]
            out[key] = pv
            out[key + '_delta'] = round(((pv - sv) / sv * 100) if sv else 0.0, 2)
        return out
    except Exception as e:
        logger.warning('GA4 engage events fetch failed (%s: %s) -- falling back to dummy',
                       type(e).__name__, e)
        return None


def ga4_story_fundamentals(request, primary_code, compare_code, today=None):
    """(prim_f, sec_f) storyboard fundamentals for the current scope, or None."""
    try:
        scoped = _scoped_creds(request)
        if not scoped:
            return None
        creds, property_ids, stream_id = scoped
        today = today or datetime.date.today()
        p_start, p_end, s_start, s_end = _date_ranges(primary_code, compare_code, today)
        prim = _story_fundamentals(_story_totals(creds, property_ids, p_start, p_end, stream_id))
        sec = _story_fundamentals(_story_totals(creds, property_ids, s_start, s_end, stream_id))
        return prim, sec
    except Exception as e:
        logger.warning('GA4 storyboard fetch failed (%s: %s) -- falling back to dummy',
                       type(e).__name__, e)
        return None
