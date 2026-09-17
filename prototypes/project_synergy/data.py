"""Sample backlog for one business unit (Lighting). Each project targets one lever
with a fractional lift, has a t-shirt effort, and may depend on another. Numbers
are illustrative — the point is the shape, not precision."""

S0_ANNUAL = 12_000_000   # Lighting annual sales run-rate

# name, lever, pct (fractional lift), effort, depends_on
PROJECTS = [
    {'name': 'Homepage hero + category relight', 'lever': 'visitors',           'pct': 0.08, 'effort': 'L',  'depends_on': None},
    {'name': 'SEO buying-guide hub',             'lever': 'visitors',           'pct': 0.06, 'effort': 'M',  'depends_on': None},
    {'name': 'Email/SMS re-engagement',          'lever': 'visits_per_visitor', 'pct': 0.05, 'effort': 'M',  'depends_on': None},
    {'name': 'Fixture finder quiz',              'lever': 'cart_creation',      'pct': 0.07, 'effort': 'XL', 'depends_on': None},
    {'name': 'One-page checkout redesign',       'lever': 'cart_completion',    'pct': 0.09, 'effort': 'L',  'depends_on': None},
    {'name': 'Express wallet pay',               'lever': 'cart_completion',    'pct': 0.05, 'effort': 'M',  'depends_on': None},
    {'name': 'Bundle shades + bulbs',            'lever': 'units_per_order',    'pct': 0.06, 'effort': 'S',  'depends_on': None},
    {'name': 'Post-purchase upsell',             'lever': 'units_per_order',    'pct': 0.04, 'effort': 'S',  'depends_on': None},
    {'name': 'Premium-tier merchandising',       'lever': 'avg_unit_price',     'pct': 0.05, 'effort': 'M',  'depends_on': None},
    # depends on the recommendation data pipeline shipping first
    {'name': 'Recommendation engine',            'lever': 'cart_creation',      'pct': 0.08, 'effort': 'XL', 'depends_on': 'Product data pipeline'},
    {'name': 'Product data pipeline',            'lever': 'visits_per_visitor', 'pct': 0.02, 'effort': 'L',  'depends_on': None},
]
