"""Impact estimation — the auto-derived "Kiboko estimated impact" + algorithmic
priority, folded in from prototypes/impact_estimation (backtest excluded).

A project targets ONE lever, moving it From -> To. Because Sales is the product
of the six levers, that raises Sales by the same %. We discount for speed (ramp +
in-year timing), certainty (capability), plausibility (how far the target sits
outside the lever's own history), and effort, into a rank-able raw priority.

The final project score = average of the anonymous VOTE (5 value/risk criteria)
and the ALGORITHMIC score (this raw, normalized 0-10 relative to the backlog).
The two are never shown separately (blended so a HiPPO can't pressure the vote up
to rescue a low-impact vanity project). See docs/impact_estimation_spec.md.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

# lever key -> (label, AEE element, GA4-metric description)
LEVERS = {
    'visitors':           ('Visitors',             'attract_traffic'),
    'visits_per_visitor': ('Visits per Visitor',   'attract_traffic'),
    'cart_creation':      ('Cart Creation Rate',   'engage_customers'),
    'cart_completion':    ('Cart Completion Rate', 'engage_customers'),
    'units_per_order':    ('Units per Order',      'expand_purchase'),
    'avg_unit_price':     ('Avg Unit Price',       'expand_purchase'),
}
LEVER_KEYS = list(LEVERS)
LEVERS_BY_AEE = {}
for _k, (_lbl, _aee) in LEVERS.items():
    LEVERS_BY_AEE.setdefault(_aee, []).append(_k)

# Capability to Complete (developer) -> confidence multiplier.
CAPABILITY = {
    'fully':   ('Fully capable in-house', 1.00),
    'mostly':  ('Mostly capable',         0.85),
    'stretch': ('Partially / stretch',    0.65),
    'new':     ('Needs new capability',   0.40),
    'unable':  ('Not currently capable',  0.20),
}
CAPABILITY_KEYS = list(CAPABILITY)
# Effort t-shirt size -> cost proxy (score divisor).
LOE_COST = {'XXS': 0.5, 'XS': 0.7, 'S': 1.0, 'M': 1.4, 'L': 2.0, 'XL': 2.8, 'XXL': 3.6}

DAYS_IN_YEAR = 365
DEFAULT_MARGIN = 0.35

# Minimum weekly history needed before the plausibility gauge is meaningful.
PLAUSIBILITY_MIN_WEEKS = 3


def levers_from_metrics(m):
    """Derive the six lever levels + sales from raw GA4 aggregates."""
    users = float(m.get('users') or 0) or 1e-9
    sessions = float(m.get('sessions') or 0) or 1e-9
    carts = float(m.get('add_to_carts') or 0) or 1e-9
    orders = float(m.get('transactions') or 0) or 1e-9
    items = float(m.get('items') or 0) or 1e-9
    revenue = float(m.get('revenue') or 0)
    return {
        'visitors': users, 'visits_per_visitor': sessions / users,
        'cart_creation': carts / sessions, 'cart_completion': orders / carts,
        'units_per_order': items / orders, 'avg_unit_price': revenue / items,
        'sales': revenue,
    }


_FUND_KEYS = ('visits', 'visitors', 'new_visitors', 'carts', 'orders', 'units', 'sales')


def _metrics_from_fund(f):
    """Adapt a GA4 'fundamentals' dict to levers_from_metrics' expected keys."""
    return {'users': f.get('visitors', 0), 'sessions': f.get('visits', 0),
            'add_to_carts': f.get('carts', 0), 'transactions': f.get('orders', 0),
            'items': f.get('units', 0), 'revenue': f.get('sales', 0)}


def _sum_fund(recs):
    tot = {k: 0.0 for k in _FUND_KEYS}
    for r in recs:
        for k in _FUND_KEYS:
            tot[k] += float(r.get(k, 0) or 0)
    return tot


def _perday_levers(recs):
    """Per-day lever levels for a set of daily fundamentals. Counts/flows are
    averaged per day so flow levers (visitors, visits) are window-invariant and
    comparable across a 90-day baseline vs 7-day weekly buckets; ratio levers are
    unchanged (per-day cancels in the ratio)."""
    n = len(recs) or 1
    agg = _sum_fund(recs)
    perday = {k: v / n for k, v in agg.items()}
    return levers_from_metrics(_metrics_from_fund(perday))


def baselines_from_daily(daily, window_days):
    """Turn {'YYYY-MM-DD': fundamentals} into estimator baselines:
      levels     -- {lever: current level} over the last `window_days`
      s0_annual  -- annualized sales from that window
      weekly     -- {lever: [weekly levels, oldest->newest]} for plausibility
      window_days-- actual days used
    Returns None if there's no data."""
    items = sorted(daily.items())                 # (iso, fund) oldest -> newest
    if not items:
        return None
    recs = [r for _iso, r in items]
    win = recs[-window_days:] if window_days else recs
    ndays = len(win) or 1
    levers = _perday_levers(win)                          # per-day baseline levels
    s0_annual = (_sum_fund(win)['sales'] / ndays) * DAYS_IN_YEAR

    # 7-day buckets aligned to the most recent day, up to 52 weeks, oldest->newest.
    weeks, i = [], len(recs)
    while i > 0 and len(weeks) < 52:
        weeks.append(recs[max(0, i - 7):i])
        i -= 7
    weeks.reverse()
    weekly = {k: [] for k in LEVER_KEYS}
    for chunk in weeks:
        lv = _perday_levers(chunk)                        # per-day -> same scale as baseline
        for k in LEVER_KEYS:
            weekly[k].append(lv[k])

    return {'levels': {k: levers[k] for k in LEVER_KEYS},
            's0_annual': s0_annual, 'weekly': weekly, 'window_days': ndays}


def realized_fraction(launch, ramp_days, today=None, year_end=None):
    """Average effectiveness across the fiscal year with a linear ramp."""
    today = today or date.today()
    year_end = year_end or date(today.year, 12, 31)
    if launch is None:
        launch = today
    start = max(launch, today)
    if start > year_end:
        return 0.0
    ramp = max(1, int(ramp_days or 1))
    total = 0.0
    d = start
    while d <= year_end:
        total += min(1.0, max(0, (d - launch).days) / ramp)
        d += timedelta(days=1)
    return total / DAYS_IN_YEAR


def plausibility(target, levels):
    """How plausible is `target` given the lever's recent weekly `levels`?
    Returns z-score, weeks reached, band, gauge position, and a risk factor P
    (used to auto-discount the algorithmic score). Empty history -> neutral P=1."""
    vals = [float(x) for x in (levels or []) if x == x]
    if len(vals) < PLAUSIBILITY_MIN_WEEKS:
        return {'ok': False, 'factor': 1.0}
    import statistics as _s
    mean = _s.fmean(vals)
    std = (_s.stdev(vals) if len(vals) > 1 else 0.0) or 1e-9
    z = (target - mean) / std
    reached = sum(1 for v in vals if v >= target)
    if z <= 1.0:
        band, color = 'Plausible', '#2b83ba'
    elif z <= 2.0:
        band, color = 'A stretch', '#7fbf7b'
    elif z <= 3.0:
        band, color = 'Aggressive', '#fdae61'
    else:
        band, color = 'Implausible', '#d7191c'
    P = 1.0 if z <= 1.0 else max(0.15, 1.0 - (z - 1.0) / 3.0)
    return {'ok': True, 'z': z, 'mean': mean, 'std': std, 'n': len(vals),
            'reached': reached, 'hist_max': max(vals), 'hist_min': min(vals),
            'band': band, 'color': color, 'position': min(1.0, max(0.0, (z + 1) / 5)),
            'factor': P}


def estimate(*, target_from, target_to, s0_annual, launch, ramp_days,
             capability='mostly', effort='M', direct_expense=0.0,
             margin_factor=DEFAULT_MARGIN, plausibility_factor=1.0, fit=1.0, today=None):
    """Return the impact components + raw algorithmic priority for one project."""
    target_from = float(target_from or 0) or 1e-9
    pct = (float(target_to or 0) - target_from) / target_from
    gross_annual = float(s0_annual or 0) * pct
    rf = realized_fraction(launch, ramp_days, today=today)
    realized_annual = gross_annual * rf
    C = CAPABILITY.get(capability, ('', 0.85))[1]
    expected_realized = realized_annual * C * float(plausibility_factor)
    net_annual = gross_annual * margin_factor - float(direct_expense or 0)
    effort_cost = LOE_COST.get(effort, 1.4)
    kiboko_raw = (expected_realized * margin_factor - float(direct_expense or 0)) * fit / effort_cost
    return {
        'pct_delta': pct, 'gross_annual': gross_annual, 'realized_fraction': rf,
        'realized_annual': realized_annual, 'expected_realized': expected_realized,
        'net_annual': net_annual, 'kiboko_raw': kiboko_raw,
    }


def algo_score_0_10(raw, backlog_raws):
    """Normalize a raw algorithmic priority to 0-10 relative to the backlog."""
    vals = [float(v) for v in backlog_raws if v is not None]
    if raw is not None:
        vals = vals + [float(raw)]
    if not vals or raw is None:
        return 0.0
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return 5.0
    return round(10 * (float(raw) - lo) / (hi - lo), 1)


def blended_score(voted_0_10, algo_0_10):
    """Final score = simple average of the vote and the algorithmic score.
    (Shown as a single number so neither side can be gamed in isolation.)"""
    return round((float(voted_0_10 or 0) + float(algo_0_10 or 0)) / 2.0, 1)


# Statuses whose projects carry a final (scored) blended score.
SCORED_STATUSES = {'Scored', 'Executive Approval', 'On Deck', 'WIP'}


_PRE_SCORING = ('Incomplete Entry', 'Pending Revenue', 'Pending LOE', 'Ready to Score')


def recompute_scores(company=None, vertical=None):
    """Recompute each project's estimate (value + algo_raw, applying current
    settings) and the blended normalized_score across the scope's backlog, since
    the algorithmic component is relative to the backlog. Call after a vote
    finalizes or an estimate input/settings change. Scored projects get the
    blend; pre-scoring ones get 0; Blocked/terminal are left untouched."""
    from strategy.models import Project
    qs = Project.objects.filter(archived=False)
    if vertical is not None:
        qs = qs.filter(vertical=vertical)
    elif company is not None:
        qs = qs.filter(vertical__company=company)
    projs = list(qs)
    ests = {p.pk: p._estimate() for p in projs}
    raws = [e['kiboko_raw'] for e in ests.values() if e is not None]
    for p in projs:
        est = ests[p.pk]
        upd = {}
        if est is not None:
            upd['algo_raw'] = est['kiboko_raw']
            upd['value'] = int(round(est['gross_annual']))
        if p.status in SCORED_STATUSES:
            if est is not None:                          # blend vote + algorithmic
                a10 = algo_score_0_10(est['kiboko_raw'], raws)
                upd['normalized_score'] = blended_score(float(p.voted_score or 0), a10)
            else:                                        # no estimate -> vote only
                upd['normalized_score'] = float(p.voted_score or 0)
        elif p.status in _PRE_SCORING:
            upd['normalized_score'] = 0.0
        if upd:
            Project.objects.filter(pk=p.pk).update(**upd)

