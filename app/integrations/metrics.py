"""GA4 <-> Kiboko metric & dimension name mappings.

The analytics dashboards are built on a handful of daily *fundamentals*
(visits, visitors, carts, orders, units, sales); everything else derives from
them (close rate, AOV, $/visit, ...). This module maps GA4's API names onto
those fundamentals so a connector can normalize a GA4 report into the shape
``app/analytics_data.py`` expects.
"""

# GA4 Data API metric name -> canonical Kiboko fundamental key.
FUNDAMENTAL_BY_GA4_METRIC = {
    'sessions':            'visits',
    'totalUsers':          'visitors',
    'newUsers':            'new_visitors',
    'addToCarts':          'carts',
    'ecommercePurchases':  'orders',
    'itemsPurchased':      'units',
    'purchaseRevenue':     'sales',
}

# The GA4 metric names to request (order preserved for row parsing).
GA4_METRIC_NAMES = list(FUNDAMENTAL_BY_GA4_METRIC.keys())

# Dimensions.
DIMENSION_DATE = 'date'                          # YYYYMMDD
DIMENSION_DEVICE = 'deviceCategory'              # desktop / mobile / tablet / (other)
DIMENSION_CHANNEL = 'sessionDefaultChannelGroup'  # Direct / Organic Search / ...

# GA4 deviceCategory -> Kiboko split bucket.
DEVICE_BUCKETS = {
    'desktop': 'desktop',
    'mobile': 'mobile',
    'tablet': 'tablet',
}
DEVICE_OTHER = 'others'

# GA4 default channel group -> Kiboko split bucket.
CHANNEL_BUCKETS = {
    'Direct': 'direct',
    'Organic Search': 'organic',
    'Paid Search': 'paid',
    'Paid Shopping': 'paid',
    'Paid Social': 'paid',
    'Organic Social': 'social',
    'Referral': 'referral',
}
CHANNEL_OTHER = 'others'


def device_bucket(ga4_device_category):
    return DEVICE_BUCKETS.get((ga4_device_category or '').lower(), DEVICE_OTHER)


def channel_bucket(ga4_channel_group):
    return CHANNEL_BUCKETS.get(ga4_channel_group or '', CHANNEL_OTHER)


def empty_fundamentals():
    """A zeroed fundamentals record for one day."""
    return {v: 0.0 for v in FUNDAMENTAL_BY_GA4_METRIC.values()}
