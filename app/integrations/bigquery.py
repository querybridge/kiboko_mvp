"""GA4 Premium connector: read a company's GA4 -> BigQuery export via a service
account and return the same daily-fundamentals shape the GA4 Data API providers
emit, so the dashboards render unchanged.

Ported from the original Kiboko (ITG) BigQuery layer. The SQL follows GA4's
standard export schema (event-level `events_YYYYMMDD` tables in dataset
`analytics_<property_id>`). google-cloud-bigquery is imported lazily so the app
runs without it until Premium is used.

NOTE: the SQL is faithful to ITG's proven queries but must be validated against a
real dataset once a service account + dataset are provided.
"""
import logging
import re

logger = logging.getLogger(__name__)

_FUND_KEYS = ('visits', 'visitors', 'new_visitors', 'carts', 'orders', 'units', 'sales')


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


def test_connection(service_account_json, property_id):
    """(ok: bool, message: str) -- verifies the dataset exists and has GA4 tables."""
    dataset = dataset_for(property_id)
    if not dataset:
        return False, 'Missing/invalid GA4 property id for the dataset name.'
    try:
        client = connect(service_account_json)
        q = (f"SELECT table_id FROM `{dataset}.__TABLES__` "
             f"WHERE table_id LIKE 'events_%' ORDER BY table_id DESC LIMIT 1")
        rows = list(client.query(q).result())
        if not rows:
            return False, f'No GA4 event tables found in `{dataset}`.'
        return True, f'Connected. Latest table: {rows[0][0]}.'
    except Exception as e:
        logger.warning('BigQuery test_connection failed (%s: %s)', type(e).__name__, e)
        return False, f'{type(e).__name__}: {e}'


# Single conditional-aggregation query over the GA4 export (one row per day).
_DAILY_SQL = """
SELECT
  event_date,
  COUNT(DISTINCT CONCAT(user_pseudo_id, CAST((
    SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING))) AS visits,
  COUNT(DISTINCT user_pseudo_id) AS visitors,
  COUNT(DISTINCT IF(event_name = 'first_visit', user_pseudo_id, NULL)) AS new_visitors,
  COUNT(DISTINCT IF(event_name = 'add_to_cart', CONCAT(user_pseudo_id, CAST((
    SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)), NULL)) AS carts,
  COUNTIF(event_name = 'purchase') AS orders,
  SUM(IF(event_name = 'purchase', IFNULL(ecommerce.purchase_revenue_in_usd, ecommerce.purchase_revenue), 0)) AS sales,
  SUM(IF(event_name = 'purchase', ecommerce.total_item_quantity, 0)) AS units
FROM `{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end
GROUP BY event_date
"""


def fetch_daily_fundamentals(client, dataset, start_date, end_date):
    """{'YYYYMMDD': {visits, visitors, new_visitors, carts, orders, units, sales}}
    for the dataset over [start_date, end_date] (date objects)."""
    from google.cloud import bigquery  # lazy
    from app.integrations._retry import transient_retry
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter('start', 'STRING', start_date.strftime('%Y%m%d')),
        bigquery.ScalarQueryParameter('end', 'STRING', end_date.strftime('%Y%m%d')),
    ])
    query = _DAILY_SQL.format(dataset=dataset)
    out = {}
    for row in client.query(query, job_config=job_config, retry=transient_retry()).result():
        out[row['event_date']] = {k: float(row[k] or 0) for k in _FUND_KEYS}
    return out
