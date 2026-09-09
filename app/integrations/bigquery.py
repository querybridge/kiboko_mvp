"""GA4 Premium connector: read a company's GA4 -> BigQuery export via a service
account and return the same shapes the GA4 Data API providers emit, so the
dashboards render unchanged.

The SQL follows GA4's standard export schema (event-level `events_YYYYMMDD`
tables in dataset `analytics_<property_id>`). Ecommerce events are referenced by
*standard* name and resolved through an ``events`` map (from
BigQueryConnection.event_map) so non-standard exports (e.g. Autocado's
"View Cart") resolve correctly. google-cloud-bigquery is imported lazily so the
app runs without it until Premium is used.
"""
import logging
import re

logger = logging.getLogger(__name__)

_FUND_KEYS = ('visits', 'visitors', 'new_visitors', 'carts', 'orders', 'units', 'sales')

# Ecommerce events the queries reference by *standard* name. Callers pass an
# ``events`` map {standard: actual_ga4_event_name}; unmapped keys default to the
# standard name.
_EVENT_KEYS = ('add_to_cart', 'purchase', 'view_item', 'view_item_list',
               'view_cart', 'begin_checkout', 'add_shipping_info')

# Reusable SQL fragments over the GA4 export schema.
_SESSION_ID = ("(SELECT value.int_value FROM UNNEST(event_params) "
               "WHERE key = 'ga_session_id')")
_SESSION_KEY = f"CONCAT(user_pseudo_id, '-', CAST({_SESSION_ID} AS STRING))"
_ENGAGEMENT_MS = ("IFNULL((SELECT value.int_value FROM UNNEST(event_params) "
                  "WHERE key = 'engagement_time_msec'), 0)")
_SESSION_ENGAGED = ("(SELECT value.string_value FROM UNNEST(event_params) "
                    "WHERE key = 'session_engaged') = '1'")
# Channel grouping mirrors ITG's proven GA4-standard logic, using first-click
# traffic_source.* (source/medium) and collapsing GA4's channel groups into
# Kiboko's six buckets. Order matters: Paid* is detected before Organic/Social so
# paid social/search land in 'paid'.
_TS_MEDIUM = "LOWER(IFNULL(traffic_source.medium, ''))"
_TS_SOURCE = "LOWER(IFNULL(traffic_source.source, ''))"
_CHANNEL_BUCKET_SQL = f"""CASE
  WHEN {_TS_SOURCE} = '(direct)' AND {_TS_MEDIUM} IN ('(not set)', '(none)', '') THEN 'direct'
  WHEN REGEXP_CONTAINS({_TS_MEDIUM}, r'^(.*cp.*|ppc|paid.*)$')
       OR {_TS_MEDIUM} IN ('display', 'banner', 'expandable', 'interstitial', 'cpm') THEN 'paid'
  WHEN REGEXP_CONTAINS({_TS_SOURCE}, r'badoo|facebook|fb|instagram|linkedin|pinterest|tiktok|twitter|whatsapp|reddit|snapchat')
       OR {_TS_MEDIUM} IN ('social', 'social-network', 'social-media', 'sm', 'social network', 'social media') THEN 'social'
  WHEN REGEXP_CONTAINS({_TS_SOURCE}, r'baidu|bing|duckduckgo|ecosia|google|yahoo|yandex')
       OR {_TS_MEDIUM} = 'organic' THEN 'organic'
  WHEN {_TS_MEDIUM} = 'referral' THEN 'referral'
  ELSE 'others' END"""
_DEVICE_BUCKET_SQL = ("CASE WHEN LOWER(device.category) IN ('desktop', 'mobile', 'tablet') "
                      "THEN LOWER(device.category) ELSE 'others' END")


def is_available():
    """True when google-cloud-bigquery is installed."""
    import importlib.util
    return importlib.util.find_spec('google.cloud.bigquery') is not None


def dataset_for(property_id):
    """GA4 export dataset name for a numeric property id."""
    pid = re.sub(r'[^0-9]', '', str(property_id or ''))
    return f'analytics_{pid}' if pid else ''


def connect(service_account_json):
    """A bigquery.Client authenticated with the service account dict."""
    from google.oauth2 import service_account  # lazy
    from google.cloud import bigquery
    creds = service_account.Credentials.from_service_account_info(service_account_json)
    project = service_account_json.get('project_id')
    return bigquery.Client(credentials=creds, project=project)


def latest_daily_date(client, dataset):
    """Latest complete daily table date (excludes events_intraday_*), or None.
    Free metadata query."""
    import datetime
    q = (f"SELECT MAX(SUBSTR(table_id, 8)) AS d FROM `{dataset}.__TABLES__` "
         f"WHERE table_id LIKE 'events_2%'")
    rows = list(client.query(q).result())
    d = rows[0]['d'] if rows else None
    return datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8])) if d else None


def test_connection(service_account_json, property_id):
    """(ok, message, latest_date) -- verifies the dataset exists and returns the
    latest complete daily date (to anchor relative periods)."""
    dataset = dataset_for(property_id)
    if not dataset:
        return False, 'Missing/invalid GA4 property id for the dataset name.', None
    try:
        client = connect(service_account_json)
        latest = latest_daily_date(client, dataset)
        if latest is None:
            return False, f'No GA4 daily event tables found in `{dataset}`.', None
        return True, f'Connected. Data through {latest.isoformat()}.', latest
    except Exception as e:
        logger.warning('BigQuery test_connection failed (%s: %s)', type(e).__name__, e)
        return False, f'{type(e).__name__}: {e}', None


# --------------------------------------------------------------------------
# Query parameter helpers
# --------------------------------------------------------------------------

def _resolve_events(events):
    """Full {standard: actual} map, defaulting unmapped keys to their standard name."""
    events = events or {}
    return {k: (events.get(k) or k) for k in _EVENT_KEYS}


def _job_config(start_date, end_date, events=None):
    """QueryJobConfig with @start/@end and every @ev_* event-name parameter."""
    from google.cloud import bigquery  # lazy
    params = [
        bigquery.ScalarQueryParameter('start', 'STRING', start_date.strftime('%Y%m%d')),
        bigquery.ScalarQueryParameter('end', 'STRING', end_date.strftime('%Y%m%d')),
        bigquery.ScalarQueryParameter('ev_first_visit', 'STRING', 'first_visit'),
    ]
    for k, v in _resolve_events(events).items():
        params.append(bigquery.ScalarQueryParameter(f'ev_{k}', 'STRING', v))
    return bigquery.QueryJobConfig(query_parameters=params)


def _run(client, query, job_config):
    from app.integrations._retry import transient_retry
    return client.query(query, job_config=job_config, retry=transient_retry()).result()


# --------------------------------------------------------------------------
# Daily fundamentals (Grow Sales + all fundamentals-derived cards)
# --------------------------------------------------------------------------

_DAILY_SQL = f"""
SELECT
  event_date,
  COUNT(DISTINCT {_SESSION_KEY}) AS visits,
  COUNT(DISTINCT user_pseudo_id) AS visitors,
  COUNT(DISTINCT IF(event_name = @ev_first_visit, user_pseudo_id, NULL)) AS new_visitors,
  COUNT(DISTINCT IF(event_name = @ev_add_to_cart, {_SESSION_KEY}, NULL)) AS carts,
  COUNTIF(event_name = @ev_purchase) AS orders,
  SUM(IF(event_name = @ev_purchase, IFNULL(ecommerce.purchase_revenue_in_usd, ecommerce.purchase_revenue), 0)) AS sales,
  SUM(IF(event_name = @ev_purchase, ecommerce.total_item_quantity, 0)) AS units
FROM `{{dataset}}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end
GROUP BY event_date
"""


def fetch_daily_fundamentals(client, dataset, start_date, end_date, events=None):
    """{'YYYYMMDD': {visits, visitors, new_visitors, carts, orders, units, sales}}
    for the dataset over [start_date, end_date] (date objects)."""
    out = {}
    for row in _run(client, _DAILY_SQL.format(dataset=dataset),
                    _job_config(start_date, end_date, events)):
        out[row['event_date']] = {k: float(row[k] or 0) for k in _FUND_KEYS}
    return out


# --------------------------------------------------------------------------
# Period totals (Engage Customers + Performance Story)
# --------------------------------------------------------------------------

# Keys mirror the GA4 Data API metric names + standard event names so the
# ga4_dashboard providers (_engage_compute / _story_fundamentals) consume them
# unchanged.
_TOTALS_KEYS = ('sessions', 'totalUsers', 'newUsers', 'engagedSessions',
                'userEngagementDuration', 'screenPageViews', 'addToCarts',
                'ecommercePurchases', 'itemsPurchased', 'purchaseRevenue',
                'view_item', 'view_item_list', 'view_cart', 'begin_checkout',
                'add_shipping_info')

_TOTALS_SQL = f"""
SELECT
  COUNT(DISTINCT {_SESSION_KEY}) AS sessions,
  COUNT(DISTINCT user_pseudo_id) AS totalUsers,
  COUNT(DISTINCT IF(event_name = @ev_first_visit, user_pseudo_id, NULL)) AS newUsers,
  COUNT(DISTINCT IF({_SESSION_ENGAGED}, {_SESSION_KEY}, NULL)) AS engagedSessions,
  SUM({_ENGAGEMENT_MS}) / 1000 AS userEngagementDuration,
  COUNTIF(event_name = 'page_view') AS screenPageViews,
  COUNTIF(event_name = @ev_add_to_cart) AS addToCarts,
  COUNTIF(event_name = @ev_purchase) AS ecommercePurchases,
  SUM(IF(event_name = @ev_purchase, ecommerce.total_item_quantity, 0)) AS itemsPurchased,
  SUM(IF(event_name = @ev_purchase, IFNULL(ecommerce.purchase_revenue_in_usd, ecommerce.purchase_revenue), 0)) AS purchaseRevenue,
  COUNTIF(event_name = @ev_view_item) AS view_item,
  COUNTIF(event_name = @ev_view_item_list) AS view_item_list,
  COUNTIF(event_name = @ev_view_cart) AS view_cart,
  COUNTIF(event_name = @ev_begin_checkout) AS begin_checkout,
  COUNTIF(event_name = @ev_add_shipping_info) AS add_shipping_info
FROM `{{dataset}}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end
"""


def fetch_period_totals(client, dataset, start_date, end_date, events=None):
    """One row of GA4-style totals + funnel event counts for [start, end]."""
    out = {k: 0.0 for k in _TOTALS_KEYS}
    for row in _run(client, _TOTALS_SQL.format(dataset=dataset),
                    _job_config(start_date, end_date, events)):
        for k in _TOTALS_KEYS:
            out[k] = float(row[k] or 0)
    return out


# --------------------------------------------------------------------------
# Device / channel splits (Attract Traffic + changeplot segments)
# --------------------------------------------------------------------------

_SPLIT_SQL = f"""
SELECT
  event_date,
  {{bucket_sql}} AS bucket,
  COUNT(DISTINCT {_SESSION_KEY}) AS visits,
  COUNT(DISTINCT user_pseudo_id) AS visitors,
  COUNT(DISTINCT IF(event_name = @ev_first_visit, user_pseudo_id, NULL)) AS new_visitors,
  COUNT(DISTINCT IF(event_name = @ev_add_to_cart, {_SESSION_KEY}, NULL)) AS carts,
  COUNTIF(event_name = @ev_purchase) AS orders,
  SUM(IF(event_name = @ev_purchase, IFNULL(ecommerce.purchase_revenue_in_usd, ecommerce.purchase_revenue), 0)) AS sales,
  SUM(IF(event_name = @ev_purchase, ecommerce.total_item_quantity, 0)) AS units
FROM `{{dataset}}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end
GROUP BY event_date, bucket
"""


def fetch_split_daily(client, dataset, start_date, end_date, split, events=None):
    """{'YYYYMMDD': {bucket: {fundamentals}}} split by 'device' or 'channel'.
    Buckets are Kiboko's normalized names (desktop/mobile/... or direct/organic/...)."""
    bucket_sql = _DEVICE_BUCKET_SQL if split == 'device' else _CHANNEL_BUCKET_SQL
    query = _SPLIT_SQL.format(dataset=dataset, bucket_sql=bucket_sql)
    out = {}
    for row in _run(client, query, _job_config(start_date, end_date, events)):
        day = out.setdefault(row['event_date'], {})
        day[row['bucket']] = {k: float(row[k] or 0) for k in _FUND_KEYS}
    return out


# --------------------------------------------------------------------------
# Item / order-level (Expand Purchases: unique SKUs, cherry pick, category AOV)
# --------------------------------------------------------------------------

_ORDER_ITEM_SQL = f"""
WITH orders AS (
  SELECT (SELECT COUNT(DISTINCT i.item_id) FROM UNNEST(items) i) AS skus
  FROM `{{dataset}}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @start AND @end AND event_name = @ev_purchase
)
SELECT
  COUNT(*) AS orders,
  IFNULL(AVG(skus), 0) AS unique_skus_per_order,
  COUNTIF(skus = 1) AS single_sku_orders
FROM orders
"""


def fetch_order_item_metrics(client, dataset, start_date, end_date, events=None):
    """{orders, unique_skus_per_order, single_sku_orders} from purchase item arrays."""
    out = {'orders': 0.0, 'unique_skus_per_order': 0.0, 'single_sku_orders': 0.0}
    for row in _run(client, _ORDER_ITEM_SQL.format(dataset=dataset),
                    _job_config(start_date, end_date, events)):
        out['orders'] = float(row['orders'] or 0)
        out['unique_skus_per_order'] = float(row['unique_skus_per_order'] or 0)
        out['single_sku_orders'] = float(row['single_sku_orders'] or 0)
    return out


_CATEGORY_SQL = f"""
SELECT
  IFNULL(NULLIF(i.item_category, ''), '(not set)') AS category,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST(event_timestamp AS STRING))) AS orders,
  SUM(IFNULL(i.quantity, 0)) AS units,
  SUM(IFNULL(i.item_revenue_in_usd, i.item_revenue)) AS sales
FROM `{{dataset}}.events_*`, UNNEST(items) i
WHERE _TABLE_SUFFIX BETWEEN @start AND @end AND event_name = @ev_purchase
GROUP BY category
"""


def fetch_category_metrics(client, dataset, start_date, end_date, events=None):
    """{category: {orders, units, sales}} from purchase item arrays."""
    out = {}
    for row in _run(client, _CATEGORY_SQL.format(dataset=dataset),
                    _job_config(start_date, end_date, events)):
        out[row['category']] = {
            'orders': float(row['orders'] or 0),
            'units': float(row['units'] or 0),
            'sales': float(row['sales'] or 0),
        }
    return out
