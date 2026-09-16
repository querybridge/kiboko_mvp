"""Impact-estimation engine (pure, no Django).

Implements the core of docs/impact_estimation_spec.md so it can be backtested and
UX-prototyped standalone, then ported into project/services/impact.py.

The identity everything hangs on:

    Sales = Visitors x VisitsPerVisitor x CartCreation x CartCompletion
            x UnitsPerOrder x AvgUnitPrice   ==  purchaseRevenue

So Sales is the product of six independent "levers", two per objective:

    Attract (Visits):     visitors, visits_per_visitor
    Engage  (Close Rate): cart_creation, cart_completion
    Expand  (AOV):        units_per_order, avg_unit_price

Because Sales is a product, improving ONE lever by x% (others held) raises Sales
by x% -- that is the estimate. And any *actual* sales change decomposes exactly
into the six levers via LMDI (log-mean divisia index), which is the backtest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import date

# lever key -> (label, objective/AEE)
LEVERS = {
    'visitors':           ('Visitors',            'Attract'),
    'visits_per_visitor': ('Visits per Visitor',  'Attract'),
    'cart_creation':      ('Cart Creation Rate',  'Engage'),
    'cart_completion':    ('Cart Completion Rate','Engage'),
    'units_per_order':    ('Units per Order',     'Expand'),
    'avg_unit_price':     ('Avg Unit Price',      'Expand'),
}
LEVER_KEYS = list(LEVERS)

# Capability to Complete (5-point) -> confidence multiplier.
CAPABILITY = {
    'fully':    ('Fully capable in-house', 1.00),
    'mostly':   ('Mostly capable',         0.85),
    'stretch':  ('Partially / stretch',    0.65),
    'new':      ('Needs new capability',   0.40),
    'unable':   ('Not currently capable',  0.20),
}
# Level of effort (t-shirt) -> cost proxy (divisor in the score).
LOE_COST = {'XXS': 0.5, 'XS': 0.7, 'S': 1.0, 'M': 1.4, 'L': 2.0, 'XL': 2.8, 'XXL': 3.6}

DAYS_IN_YEAR = 365


# --------------------------------------------------------------------------
# Lever derivation
# --------------------------------------------------------------------------
def levers_from_metrics(m):
    """Derive the six lever levels + sales from raw GA4 aggregates.

    `m` maps: users, sessions, add_to_carts, transactions, items, revenue.
    Returns {lever_key: level, ..., 'sales': revenue}.
    """
    users = float(m['users']) or 1e-9
    sessions = float(m['sessions']) or 1e-9
    carts = float(m['add_to_carts']) or 1e-9
    orders = float(m['transactions']) or 1e-9
    items = float(m['items']) or 1e-9
    revenue = float(m['revenue'])
    return {
        'visitors':           users,
        'visits_per_visitor': sessions / users,
        'cart_creation':      carts / sessions,
        'cart_completion':    orders / carts,
        'units_per_order':    items / orders,
        'avg_unit_price':     revenue / items,
        'sales':              revenue,
    }


# --------------------------------------------------------------------------
# Backtest: exact LMDI decomposition of an actual sales change
# --------------------------------------------------------------------------
def _log_mean(a, b):
    """Logarithmic mean; L(a,a)=a. Used by LMDI so contributions sum exactly."""
    if a <= 0 or b <= 0:
        return 0.0
    if abs(a - b) < 1e-12:
        return a
    return (b - a) / (math.log(b) - math.log(a))


def lmdi_decompose(base_metrics, target_metrics):
    """Split the ACTUAL sales change (target - base) into exact per-lever dollar
    contributions (LMDI-I). Sum of contributions == actual sales delta.

    Returns {'delta': total, 'contrib': {lever: $}, 'residual': ~0}.
    """
    lb = levers_from_metrics(base_metrics)
    lt = levers_from_metrics(target_metrics)
    lm = _log_mean(lb['sales'], lt['sales'])
    contrib = {}
    for k in LEVER_KEYS:
        a, b = lb[k], lt[k]
        contrib[k] = lm * math.log(b / a) if (a > 0 and b > 0) else 0.0
    delta = lt['sales'] - lb['sales']
    return {'delta': delta, 'contrib': contrib,
            'residual': delta - sum(contrib.values())}


# --------------------------------------------------------------------------
# Estimate: predicted forward impact of a single lever move
# --------------------------------------------------------------------------
@dataclass
class Estimate:
    lever: str
    objective: str
    target_from: float
    target_to: float
    pct_delta: float
    s0_annual: float
    gross_annual: float        # full run-rate $/yr
    realized_fraction: float   # in-year, after ramp + timing
    realized_annual: float     # $ this fiscal year
    expected_realized: float   # x capability confidence
    net_annual: float          # contribution - direct expense
    kiboko_raw: float          # rank key (speed/certainty/fit/effort-adjusted)

    def as_dict(self):
        return asdict(self)


def realized_fraction(launch, ramp_days, today=None, year_end=None):
    """Average effectiveness across the fiscal year with a linear ramp from
    launch to launch+ramp_days. Only days on/after max(launch, today) count."""
    today = today or date.today()
    year_end = year_end or date(today.year, 12, 31)
    start = max(launch, today)
    if start > year_end:
        return 0.0
    ramp = max(1, int(ramp_days))
    total = 0.0
    d = start
    from datetime import timedelta
    while d <= year_end:
        t = (d - launch).days
        total += min(1.0, max(0.0, t) / ramp)
        d += timedelta(days=1)
    return total / DAYS_IN_YEAR


def plausibility(target, levels):
    """How plausible is reaching `target` for a lever, given its recent history?

    `levels` = the lever's level in each of the trailing weeks. Returns a z-score
    vs. that distribution, how many weeks ever reached the target, a band label +
    heat color, a 0..1 gauge position (blue→red), and a risk multiplier P used to
    optionally discount the expected impact (accountability for big claims).
    """
    vals = [float(x) for x in levels if x == x]          # drop NaN
    if len(vals) < 3:
        return {'ok': False}
    import statistics as _s
    mean = _s.fmean(vals)
    std = _s.pstdev(vals) if len(vals) < 2 else _s.stdev(vals)
    std = std or 1e-9
    z = (target - mean) / std
    n = len(vals)
    reached = sum(1 for v in vals if v >= target)
    if z <= 1.0:
        band, color = 'Plausible', '#2b83ba'             # within normal range
    elif z <= 2.0:
        band, color = 'A stretch', '#7fbf7b'
    elif z <= 3.0:
        band, color = 'Aggressive', '#fdae61'
    else:
        band, color = 'Implausible', '#d7191c'
    position = min(1.0, max(0.0, (z + 1.0) / 5.0))        # z in [-1, 4] -> [0, 1]
    P = 1.0 if z <= 1.0 else max(0.15, 1.0 - (z - 1.0) / 3.0)
    return {'ok': True, 'z': z, 'mean': mean, 'std': std, 'n': n,
            'reached': reached, 'hist_max': max(vals), 'hist_min': min(vals),
            'band': band, 'color': color, 'position': position, 'factor': P}


def estimate(lever, target_from, target_to, s0_annual, *, launch, ramp_days,
             capability='mostly', effort='M', direct_expense=0.0,
             margin_factor=0.35, fit=1.0, plausibility=1.0, today=None):
    """Estimate a project's impact + priority. See the spec for the model.

    `plausibility` (0..1) optionally risk-adjusts the expected impact based on how
    achievable the target level is vs. history (see plausibility())."""
    if lever not in LEVERS:
        raise ValueError(f'unknown lever {lever!r}')
    target_from = float(target_from) or 1e-9
    pct = (float(target_to) - target_from) / target_from
    gross_annual = s0_annual * pct
    rf = realized_fraction(launch, ramp_days, today=today)
    realized_annual = gross_annual * rf
    C = CAPABILITY.get(capability, ('', 0.85))[1]
    expected_realized = realized_annual * C * float(plausibility)
    net_annual = gross_annual * margin_factor - float(direct_expense)
    effort_cost = LOE_COST.get(effort, 1.4)
    kiboko_raw = (expected_realized * margin_factor - float(direct_expense)) * fit / effort_cost
    return Estimate(
        lever=lever, objective=LEVERS[lever][1],
        target_from=target_from, target_to=float(target_to), pct_delta=pct,
        s0_annual=s0_annual, gross_annual=gross_annual,
        realized_fraction=rf, realized_annual=realized_annual,
        expected_realized=expected_realized, net_annual=net_annual,
        kiboko_raw=kiboko_raw)


def display_score(kiboko_raw, backlog_raws):
    """Min-max normalize a raw score to 0-10 across the current backlog."""
    vals = [v for v in backlog_raws if v is not None]
    if not vals:
        return 0.0
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return 5.0
    return round(10 * (kiboko_raw - lo) / (hi - lo), 1)
