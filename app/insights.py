"""Insights: turn period-over-period lever movement into Wins / Losses, each with
recommended actions (admin-editable) that can be promoted into projects.

A lever is a win or loss when its move versus the comparison period is unusual for
that lever: |z| >= Z_THRESHOLD, where z is the % move divided by the lever's normal
week-to-week variation (coefficient of variation of its weekly levels). It's the
same yardstick the estimator's plausibility gauge uses, so a 5% swing in a steady
lever can count while a 20% swing in a noisy one doesn't. Without enough weekly
history it falls back to a flat +/-WIN_THRESHOLD%. Values + deltas come from
app.analytics_data.build_metrics, so Insights honors the current scope + period
and works for Standard and Premium alike.
"""
Z_THRESHOLD = 1.0     # normal weekly swings; matches where Score starts discounting
WIN_THRESHOLD = 10.0  # percent, fallback when there's no weekly history

DIRECTION_CHOICES = [('win', 'Win'), ('loss', 'Loss')]

# The six lead metrics (levers) of the sales model: Visitors x Visits per Visitor x
# Cart Creation x Cart Completion x Units per Order x Avg Unit Price = Sales.
# Lag metrics (Sales, Visits, Orders, Close Rate, AOV) are left out on purpose:
# they are products of the levers, so a win or loss there can't be pinned on the
# work that moved it. Keeping insights on the levers keeps each project close to
# the metric it can actually move, which keeps its impact argument honest.
# value_key -> build_metrics['primary']; pct_key -> build_metrics['pct'];
# kind -> app.analytics_data.fmt; obj -> Objective name keyword the 'Add Project'
# draft links to. All are "higher is better".
INSIGHT_METRICS = [
    {'key': 'visitors',           'label': 'Visitors',             'value_key': 'visitors',          'pct_key': 'total_visitor',     'kind': 'integer',    'obj': 'shopper'},
    {'key': 'visits_per_visitor', 'label': 'Visits per Visitor',   'value_key': 'visit_per_visitor', 'pct_key': 'visit_per_visitor', 'kind': 'normal',     'obj': 'shopper'},
    {'key': 'cart_creation',      'label': 'Cart Creation Rate',   'value_key': 'cart_creation_pct', 'pct_key': 'cart_creation',     'kind': 'percentage', 'obj': 'close'},
    {'key': 'cart_completion',    'label': 'Cart Completion Rate', 'value_key': 'cart_completion',   'pct_key': 'cart_completion',   'kind': 'percentage', 'obj': 'close'},
    {'key': 'units_per_order',    'label': 'Units per Order',      'value_key': 'units_per_order',   'pct_key': 'units_per_order',   'kind': 'normal',     'obj': 'order value'},
    {'key': 'avg_unit_price',     'label': 'Average Unit Price',   'value_key': 'avg_unit_price',    'pct_key': 'avg_unit_price',    'kind': 'currency',   'obj': 'order value'},
]
METRIC_CHOICES = [(m['key'], m['label']) for m in INSIGHT_METRICS]
_BY_KEY = {m['key']: m for m in INSIGHT_METRICS}


def objective_keyword(metric_key):
    spec = _BY_KEY.get(metric_key)
    return spec['obj'] if spec else ''


def _swing(delta_pct, weekly):
    """The move in normal weekly swings (z), or None without enough history."""
    import statistics
    from project.services.impact import PLAUSIBILITY_MIN_WEEKS
    vals = [float(x) for x in (weekly or []) if x == x]
    if len(vals) < PLAUSIBILITY_MIN_WEEKS:
        return None
    mean = statistics.fmean(vals)
    cv = statistics.stdev(vals) / mean if mean else 0.0
    return (delta_pct / 100.0) / cv if cv else None


def classify(metrics, weekly=None):
    """From a build_metrics() result and the scope's weekly lever levels
    ({lever: [levels, oldest->newest]}), return (wins, losses). Each item:
    {key, label, value, delta, z, direction, recommendations:[{id, text}]}."""
    from app.analytics_data import fmt
    from app.models import MetricRecommendation

    p, pct = metrics['primary'], metrics['pct']
    by_group = {}
    for r in MetricRecommendation.objects.filter(active=True).order_by('order', 'id'):
        by_group.setdefault((r.metric, r.direction), []).append(r)

    wins, losses = [], []
    for spec in INSIGHT_METRICS:
        raw = pct.get(spec['pct_key'], 0) or 0
        delta = round(raw, 1)
        z = _swing(raw, (weekly or {}).get(spec['key']))
        if z is not None:
            unusual = abs(z) >= Z_THRESHOLD
        else:
            unusual = abs(delta) >= WIN_THRESHOLD
        if not unusual or delta == 0:
            continue
        direction = 'win' if delta > 0 else 'loss'
        recs = by_group.get((spec['key'], direction), [])
        item = {
            'key': spec['key'], 'label': spec['label'],
            'value': fmt(p.get(spec['value_key'], 0) or 0, spec['kind'])[0],
            'delta': delta, 'z': round(abs(z), 1) if z is not None else None,
            'direction': direction,
            'recommendations': [{'id': r.id, 'text': r.text} for r in recs],
        }
        (wins if direction == 'win' else losses).append(item)

    # Most unusual first.
    rank = lambda x: -(x['z'] if x['z'] is not None else abs(x['delta']) / WIN_THRESHOLD)
    wins.sort(key=rank)
    losses.sort(key=rank)
    return wins, losses
