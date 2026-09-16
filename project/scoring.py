# Default weights for the 6 BVM criteria (must sum to 100). An organization can
# override these via ScoringWeights (Settings -> Score Weights); this dict is the
# fallback when an org hasn't customized its model.
DEFAULT_WEIGHTS = {
    'customer_value': 25,
    'business_value': 40,
    'cost_savings': 10,
    'operational_cost': 10,
    'business_risk': 5,
    'level_of_effort': 10,
}
# Back-compat alias (older imports referenced WEIGHTS).
WEIGHTS = DEFAULT_WEIGHTS

CRITERIA = list(DEFAULT_WEIGHTS.keys())

# The criteria decided by the anonymous all-hands vote. level_of_effort is NOT
# voted -- effort is a developer input (t-shirt size) that feeds the algorithmic
# score. Revenue is auto-derived by the impact estimator, not voted.
VOTED_CRITERIA = [c for c in CRITERIA if c != 'level_of_effort']


def voted_weights(weights):
    """The voted criteria's weights, renormalized to sum to 100 (LOE's weight is
    excluded since it isn't voted) so the voted score stays on a clean 0-10."""
    sub = {c: weights.get(c, 0) for c in VOTED_CRITERIA}
    total = sum(sub.values()) or 1
    return {c: w * 100.0 / total for c, w in sub.items()}

# Human labels + a one-line hint for each criterion (used by the scoring UI and
# the Score Weights settings page, so both stay in sync).
CRITERIA_META = {
    'customer_value':  ('Customer Value',   'Impact on the customer experience'),
    'business_value':  ('Business Value',   'Revenue / strategic value to the business'),
    'cost_savings':    ('Cost Savings',     'Direct cost the project removes'),
    'operational_cost':('Operational Cost', 'Efficiency it adds to operations'),
    'business_risk':   ('Business Risk',    'How risky it is to take on — unproven tech, no in-house expertise (higher lowers the score)'),
    'level_of_effort': ('Level of Effort',  'Impact to the resource/team, weighed against the lead dev’s size (10 = easy)'),
}

# Criteria the user rates as a *magnitude* where a higher rating is WORSE, so it
# should pull the weighted score DOWN. business_risk = how risky the project is
# for the business to take on (e.g. building an LLM with no LLM expertise): the
# riskier it is, the lower the score. These are inverted (10 - value) before
# weighting, so 0 risk = full credit and 10 risk = none.
INVERTED = {'business_risk'}


def weighted_score(values, weights=None):
    """Return the weighted BVM score on a 0-10 scale.

    *values* maps criterion name -> int (0-10). *weights* maps criterion name ->
    weight (defaults to DEFAULT_WEIGHTS). Positive criteria contribute their
    value; INVERTED criteria (business_risk) contribute (10 - value), so higher
    risk lowers the score. An unscored project (all zeros) scores 0 -- the
    inversion only applies once something is rated.
    """
    weights = weights or DEFAULT_WEIGHTS
    if not any(values.get(k, 0) for k in weights):
        return 0.0
    total = 0
    for k, w in weights.items():
        v = values.get(k, 0)
        if k in INVERTED:
            v = 10 - v
        total += v * w
    return total / 100
