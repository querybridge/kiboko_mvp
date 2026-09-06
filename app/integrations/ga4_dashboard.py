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


def ga4_rows(request, primary_code, compare_code, today=None):
    """(rows_p, rows_s, labels) of real GA4 data for the current scope, or None.

    Uses the selected Vertical's GA4 property (and the selected Website's stream,
    if a specific one is chosen), read with the signed-in user's Google token.
    """
    if not google_oauth.is_enabled():
        return None

    identity = getattr(request.user, 'google_identity', None)
    if not identity:
        return None

    from business_unit.models import Vertical, Website
    vertical_id = request.session.get('scope_vertical')
    stream_id = None

    if vertical_id and vertical_id != 'all':
        # One Vertical = one GA4 property (optionally one Website/data stream).
        vertical = Vertical.objects.filter(pk=vertical_id).first()
        if not vertical or not vertical.ga4_property_id:
            return None
        property_ids = [vertical.ga4_property_id]
        website_id = request.session.get('scope_website')
        if website_id and website_id != 'all':
            site = Website.objects.filter(pk=website_id, vertical=vertical).first()
            stream_id = site.ga4_stream_id if site else None
    else:
        # All Verticals = sum across every GA4 property in the current company.
        company_id = request.session.get('scope_company')
        if not company_id:
            return None
        property_ids = list(
            Vertical.objects.filter(company_id=company_id)
            .exclude(ga4_property_id='')
            .values_list('ga4_property_id', flat=True))
        if not property_ids:
            return None

    try:
        creds = google_oauth.credentials_from_identity(identity)
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
