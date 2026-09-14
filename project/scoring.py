# Scoring weights for the 6 BVM criteria (must sum to 100)
WEIGHTS = {
    'customer_value': 25,
    'business_value': 40,
    'cost_savings': 10,
    'operational_cost': 10,
    'business_risk': 5,
    'level_of_effort': 10,
}

CRITERIA = list(WEIGHTS.keys())

# Criteria the user rates as a *magnitude* where a higher rating is WORSE, so it
# should pull the weighted score DOWN. business_risk = how risky the project is
# for the business to take on (e.g. building an LLM with no LLM expertise): the
# riskier it is, the lower the score. These are inverted (10 - value) before
# weighting, so 0 risk = full credit and 10 risk = none.
INVERTED = {'business_risk'}


def weighted_score(values):
    """Return the weighted BVM score on a 0-10 scale.

    *values* is a dict mapping criterion name -> int (0-10). Positive criteria
    contribute their value; INVERTED criteria (business_risk) contribute
    (10 - value), so higher risk lowers the score. An unscored project (all
    zeros) scores 0 -- the inversion only applies once something is rated.
    """
    if not any(values.get(k, 0) for k in WEIGHTS):
        return 0.0
    total = 0
    for k, w in WEIGHTS.items():
        v = values.get(k, 0)
        if k in INVERTED:
            v = 10 - v
        total += v * w
    return total / 100
