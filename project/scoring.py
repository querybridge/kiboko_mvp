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


def weighted_score(values):
    """Return weighted average on a 0-10 scale.

    *values* is a dict mapping criterion name -> int (0-10).
    Formula: sum(criterion * weight) / 100
    """
    return sum(values.get(k, 0) * w for k, w in WEIGHTS.items()) / 100
