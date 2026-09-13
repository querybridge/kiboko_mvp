"""Insights: turn period-over-period metric movement into Wins / Losses, each with
recommended actions (admin-editable) that can be promoted into projects.

A win = metric up >= WIN_THRESHOLD% vs the comparison period; a loss = down by the
same. Values + deltas come from app.analytics_data.build_metrics, so Insights
honors the current scope + period and works for Standard and Premium alike.
"""
WIN_THRESHOLD = 10.0  # percent

DIRECTION_CHOICES = [('win', 'Win'), ('loss', 'Loss')]

# The core ecommerce KPIs. value_key -> build_metrics['primary']; pct_key ->
# build_metrics['pct']; kind -> app.analytics_data.fmt; obj -> Objective name
# keyword the 'Add Project' draft links to. All are "higher is better".
INSIGHT_METRICS = [
    {'key': 'sales',           'label': 'Sales',                'value_key': 'sales',             'pct_key': 'total_sales',          'kind': 'currency',   'obj': 'order value'},
    {'key': 'visits',          'label': 'Visits',               'value_key': 'visits',            'pct_key': 'total_visits',         'kind': 'integer',    'obj': 'shopper'},
    {'key': 'visitors',        'label': 'Visitors',             'value_key': 'visitors',          'pct_key': 'total_visitor',        'kind': 'integer',    'obj': 'shopper'},
    {'key': 'orders',          'label': 'Orders',               'value_key': 'orders',            'pct_key': 'attract_engage_order', 'kind': 'integer',    'obj': 'close'},
    {'key': 'close_rate',      'label': 'Close Rate',           'value_key': 'close_rate',        'pct_key': 'close_rate',           'kind': 'percentage', 'obj': 'close'},
    {'key': 'aov',             'label': 'Average Order Value',  'value_key': 'aov',               'pct_key': 'aov',                  'kind': 'currency',   'obj': 'order value'},
    {'key': 'cart_creation',   'label': 'Cart Creation Rate',   'value_key': 'cart_creation_pct', 'pct_key': 'cart_creation',        'kind': 'percentage', 'obj': 'close'},
    {'key': 'cart_completion', 'label': 'Cart Completion Rate', 'value_key': 'cart_completion',   'pct_key': 'cart_completion',      'kind': 'percentage', 'obj': 'close'},
    {'key': 'units_per_order', 'label': 'Units per Order',      'value_key': 'units_per_order',   'pct_key': 'units_per_order',      'kind': 'normal',     'obj': 'order value'},
    {'key': 'avg_unit_price',  'label': 'Average Unit Price',   'value_key': 'avg_unit_price',    'pct_key': 'avg_unit_price',       'kind': 'currency',   'obj': 'order value'},
]
METRIC_CHOICES = [(m['key'], m['label']) for m in INSIGHT_METRICS]
_BY_KEY = {m['key']: m for m in INSIGHT_METRICS}


def objective_keyword(metric_key):
    spec = _BY_KEY.get(metric_key)
    return spec['obj'] if spec else ''


def classify(metrics):
    """From a build_metrics() result, return (wins, losses). Each item:
    {key, label, value, delta, direction, recommendations:[{id, text}]}."""
    from app.analytics_data import fmt
    from app.models import MetricRecommendation

    p, pct = metrics['primary'], metrics['pct']
    by_group = {}
    for r in MetricRecommendation.objects.filter(active=True).order_by('order', 'id'):
        by_group.setdefault((r.metric, r.direction), []).append(r)

    wins, losses = [], []
    for spec in INSIGHT_METRICS:
        delta = round(pct.get(spec['pct_key'], 0) or 0, 1)
        if delta >= WIN_THRESHOLD:
            direction = 'win'
        elif delta <= -WIN_THRESHOLD:
            direction = 'loss'
        else:
            continue
        recs = by_group.get((spec['key'], direction), [])
        item = {
            'key': spec['key'], 'label': spec['label'],
            'value': fmt(p.get(spec['value_key'], 0) or 0, spec['kind'])[0],
            'delta': delta, 'direction': direction,
            'recommendations': [{'id': r.id, 'text': r.text} for r in recs],
        }
        (wins if direction == 'win' else losses).append(item)

    wins.sort(key=lambda x: -x['delta'])
    losses.sort(key=lambda x: x['delta'])
    return wins, losses
