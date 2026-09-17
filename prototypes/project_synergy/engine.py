"""Project-to-project compounding / synergy — engine.

Grounded in the same identity the impact estimator uses:

    Sales = Visitors x Visits/Visitor x Cart Creation x Cart Completion
            x Units/Order x Avg Unit Price          (a PRODUCT of six levers)

Because sales is a product, a *set* of projects is worth more (or less) than the
sum of the individual estimates:
  * different levers  -> multiplicative COMPOUNDING (the a*b cross-term)
  * same lever        -> sub-additive OVERLAP (diminishing returns)
  * enables/depends   -> a dependent's value is gated until its enabler ships

See docs/project_synergy_spec.md. This is a standalone prototype (no Django).
"""
from functools import reduce
from itertools import combinations

LEVERS = {
    'visitors':           ('Visitors',             'Attract', '#3FC9E0'),
    'visits_per_visitor': ('Visits per Visitor',   'Attract', '#3FC9E0'),
    'cart_creation':      ('Cart Creation Rate',   'Engage',  '#ECB752'),
    'cart_completion':    ('Cart Completion Rate', 'Engage',  '#ECB752'),
    'units_per_order':    ('Units per Order',      'Expand',  '#55C892'),
    'avg_unit_price':     ('Avg Unit Price',       'Expand',  '#55C892'),
}
LOE_COST = {'XXS': 0.5, 'XS': 0.7, 'S': 1.0, 'M': 1.4, 'L': 2.0, 'XL': 2.8, 'XXL': 3.6}

# How much of a dependent project's lift survives before its enabler ships.
GATE_WHEN_ENABLER_ABSENT = 0.30


def _prod(xs):
    return reduce(lambda a, b: a * b, xs, 1.0)


def standalone_value(project, s0):
    """The project's value estimated ALONE (what the pipeline sums today)."""
    return s0 * project['pct']


def _effective_pcts(projects, committed_names):
    """Per-project lift after dependency gating: a project that depends on an
    enabler NOT in `committed_names` contributes at a reduced rate."""
    out = []
    for p in projects:
        pct = p['pct']
        dep = p.get('depends_on')
        if dep and dep not in committed_names:          # enabler not committed -> gate
            pct *= GATE_WHEN_ENABLER_ABSENT
        out.append((p['lever'], pct))
    return out


def combined_uplift(projects, s0, committed_names=None):
    """$ sales uplift of the WHOLE set. Within a lever, lifts are sub-additive
    (1 - prod(1-pct)); across levers they multiply -> the compounding bonus."""
    if not projects:
        return 0.0
    committed_names = committed_names if committed_names is not None else {p['name'] for p in projects}
    by_lever = {}
    for lever, pct in _effective_pcts(projects, committed_names):
        by_lever.setdefault(lever, []).append(pct)
    factor = 1.0
    for pcts in by_lever.values():
        combined_pct = 1 - _prod(1 - x for x in pcts)     # sub-additive within a lever
        factor *= (1 + combined_pct)                      # multiplicative across levers
    return s0 * (factor - 1)


def standalone_sum(projects, s0):
    return sum(standalone_value(p, s0) for p in projects)


def compounding_bonus(projects, s0):
    """Portfolio value minus the naive sum. Positive = net compounding; negative
    = net overlap."""
    return combined_uplift(projects, s0) - standalone_sum(projects, s0)


def marginal_contributions(projects, s0):
    """Leave-one-out marginal: what each project adds GIVEN the others. This is the
    portfolio-fit number — a project's worth in the company it keeps."""
    total = combined_uplift(projects, s0)
    out = {}
    for p in projects:
        rest = [q for q in projects if q is not p]
        out[p['name']] = total - combined_uplift(rest, s0)
    return out


def pair_synergies(projects, s0):
    """Every same-BU pair, with its compound (gain) or overlap (loss) strength.
    Both scale with s0 * pct_i * pct_j; sign depends on same vs different lever."""
    out = []
    for a, b in combinations(projects, 2):
        strength = s0 * a['pct'] * b['pct']
        if a['lever'] == b['lever']:
            kind, value = 'overlap', -strength
        else:
            kind, value = 'compound', strength
        out.append({'a': a['name'], 'b': b['name'], 'kind': kind, 'value': value,
                    'lever_a': a['lever'], 'lever_b': b['lever']})
    return sorted(out, key=lambda x: x['value'])


# --------------------------------------------------------------------------
# Phase 3 — pick the best COMBINATION under a budget (not the best items).
# --------------------------------------------------------------------------
def effort(project):
    return LOE_COST.get(project.get('effort', 'M'), 1.4)


def best_portfolio(projects, s0, budget):
    """Subset with the highest combined uplift whose total effort <= budget.
    Brute force for small backlogs (<=18); greedy-by-marginal above that."""
    if len(projects) <= 18:
        best, best_val = [], 0.0
        idx = list(range(len(projects)))
        for r in range(1, len(projects) + 1):
            for combo in combinations(idx, r):
                sel = [projects[i] for i in combo]
                if sum(effort(p) for p in sel) <= budget:
                    v = combined_uplift(sel, s0)
                    if v > best_val:
                        best, best_val = sel, v
        return best, best_val
    # greedy: repeatedly add the project with the best marginal-uplift-per-effort
    chosen, spent = [], 0.0
    remaining = list(projects)
    while remaining:
        base = combined_uplift(chosen, s0)
        scored = [((combined_uplift(chosen + [p], s0) - base) / effort(p), p)
                  for p in remaining if spent + effort(p) <= budget]
        if not scored:
            break
        scored.sort(reverse=True, key=lambda t: t[0])
        pick = scored[0][1]
        chosen.append(pick); spent += effort(pick); remaining.remove(pick)
    return chosen, combined_uplift(chosen, s0)


def top_by_score(projects, s0, budget):
    """Baseline selection: greedily take the highest STANDALONE-value projects
    until the budget is spent (what 'rank projects individually' does)."""
    ranked = sorted(projects, key=lambda p: standalone_value(p, s0), reverse=True)
    chosen, spent = [], 0.0
    for p in ranked:
        if spent + effort(p) <= budget:
            chosen.append(p); spent += effort(p)
    return chosen, combined_uplift(chosen, s0)
