"""GA4 Data API -> Kiboko daily fundamentals.

Fetches per-day metrics for a GA4 property (on the user's behalf) and normalizes
them into the fundamentals the dashboards are built on. A property maps to a
Kiboko Vertical; summing across a Vertical's websites / a Company's verticals is
done upstream (roll-ups) once these per-property rows are collected.

Lazy import of the Data API client. Requires (add to requirements):
    google-analytics-data
"""
from . import metrics as M


def run_report(credentials, property_id, start_date, end_date, dimensions,
               metric_names, stream_id=None):
    """Thin wrapper over Data API runReport. Dates are 'YYYY-MM-DD' or GA4
    relative dates like 'yesterday' / 'NdaysAgo'. When stream_id is given, the
    report is filtered to that data stream (a single Website)."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient  # lazy
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter,
    )
    dimension_filter = None
    if stream_id:
        dimension_filter = FilterExpression(filter=Filter(
            field_name='streamId',
            string_filter=Filter.StringFilter(value=str(stream_id))))
    from app.integrations._retry import transient_retry
    client = BetaAnalyticsDataClient(credentials=credentials)
    request = RunReportRequest(
        property=f'properties/{property_id}',
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metric_names],
        dimension_filter=dimension_filter,
    )
    return client.run_report(request, retry=transient_retry())


def fetch_daily_fundamentals(credentials, property_id, start_date, end_date, stream_id=None):
    """Return {'YYYYMMDD': {visits, visitors, new_visitors, carts, orders, units,
    sales}} for the property (optionally one data stream) over the date range."""
    resp = run_report(
        credentials, property_id, start_date, end_date,
        dimensions=[M.DIMENSION_DATE], metric_names=M.GA4_METRIC_NAMES,
        stream_id=stream_id)
    out = {}
    for row in resp.rows:
        day = row.dimension_values[0].value
        rec = M.empty_fundamentals()
        for i, ga4_metric in enumerate(M.GA4_METRIC_NAMES):
            rec[M.FUNDAMENTAL_BY_GA4_METRIC[ga4_metric]] = float(row.metric_values[i].value or 0)
        out[day] = rec
    return out


def fetch_daily_split(credentials, property_id, start_date, end_date, split):
    """Return {'YYYYMMDD': {bucket: {fundamentals}}} split by 'device' or
    'channel'. Buckets are Kiboko's normalized names (desktop/mobile/... or
    direct/organic/paid/...)."""
    if split == 'device':
        dim, bucketer = M.DIMENSION_DEVICE, M.device_bucket
    elif split == 'channel':
        dim, bucketer = M.DIMENSION_CHANNEL, M.channel_bucket
    else:
        raise ValueError(f'unknown split: {split!r}')

    resp = run_report(
        credentials, property_id, start_date, end_date,
        dimensions=[M.DIMENSION_DATE, dim], metric_names=M.GA4_METRIC_NAMES)
    out = {}
    for row in resp.rows:
        day = row.dimension_values[0].value
        bucket = bucketer(row.dimension_values[1].value)
        rec = out.setdefault(day, {}).setdefault(bucket, M.empty_fundamentals())
        for i, ga4_metric in enumerate(M.GA4_METRIC_NAMES):
            rec[M.FUNDAMENTAL_BY_GA4_METRIC[ga4_metric]] += float(row.metric_values[i].value or 0)
    return out


def sum_fundamentals(records):
    """Sum a list of fundamentals dicts -- used for 'All Websites' / 'All
    Verticals' roll-ups (total business performance across streams)."""
    total = M.empty_fundamentals()
    for rec in records:
        for key, val in rec.items():
            total[key] = total.get(key, 0.0) + (val or 0)
    return total
