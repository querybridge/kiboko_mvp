"""Realized Performance verdict: it worked only if the project drove the gain AND
moved its lever by at least half of what it planned."""
from django.test import SimpleTestCase

from project.services import impact

BEFORE = {'visitors': 1000, 'visits': 1500, 'carts': 150, 'orders': 50, 'units': 100, 'sales': 10000}
# Only cart completion moves (+10%): more orders, same units per order and unit price.
AFTER = dict(BEFORE, orders=55, units=110, sales=11000)


class RealizedVerdictTests(SimpleTestCase):
    def verdict(self, planned):
        return impact.realized_performance(BEFORE, AFTER, 'cart_completion', planned_pct=planned)

    def test_delivered_as_planned_is_meaningful(self):
        r = self.verdict(0.10)
        self.assertEqual(r['verdict'], 'meaningful')
        self.assertAlmostEqual(r['attainment'], 1.0, places=3)

    def test_drove_the_gain_but_far_below_plan_fell_short(self):
        r = self.verdict(0.50)                      # planned +50%, got +10%
        self.assertEqual(r['verdict'], 'short')
        self.assertAlmostEqual(r['attainment'], 0.2, places=3)

    def test_without_a_plan_the_attribution_verdict_stands(self):
        r = self.verdict(None)
        self.assertEqual(r['verdict'], 'meaningful')
        self.assertIsNone(r['attainment'])
