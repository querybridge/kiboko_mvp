import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from app.models import DailyActual, MonthlyGoal, RateGoal
from business_unit.models import BusinessUnit, Company, CompanyMembership, Organization


class PerformanceTargetTests(TestCase):
    """Close Rate / AOV targets: the unit's own prior-12-month average unless a BU
    lead set goals; Visits target = budget / AOV / close rate."""

    def setUp(self):
        self.today = datetime.date.today()
        org = Organization.objects.create(name='Acme', slug='acme', billing_exempt=True, plan_status='active')
        self.co = Company.objects.create(organization=org, name='Acme', slug='acme')
        self.lead = User.objects.create_user('lead', 'lead@acme.test', 'pw')
        self.member = User.objects.create_user('mem', 'mem@acme.test', 'pw')
        self.bu = BusinessUnit.objects.create(name='Lighting', company=self.co, general_manager=self.lead)
        self.bu2 = BusinessUnit.objects.create(name='Patio', company=self.co)
        CompanyMembership.objects.create(company=self.co, user=self.lead, role='member')
        CompanyMembership.objects.create(company=self.co, user=self.member, role='member')
        # 400 days of history: $200 AOV, 2% close rate in Lighting.
        DailyActual.objects.bulk_create(
            DailyActual(date=self.today - datetime.timedelta(days=d), vertical=self.bu,
                        revenue=2000, visits=500, orders=10) for d in range(1, 401))
        MonthlyGoal.objects.create(month=self.today.replace(day=1), vertical=self.bu, budget=Decimal('31000'))

    def _cards(self, vertical_id=None, period='mtd'):
        from app.views import _build_performance_data
        return _build_performance_data(self.today, vertical_id=vertical_id, company_id=self.co.id)[period]

    def test_targets_default_to_the_units_own_12_month_average(self):
        cards = self._cards(self.bu.id)
        self.assertEqual(cards['aov']['goal_label'], 'vs 12-mo avg')
        self.assertAlmostEqual(cards['aov']['delta_goal'], 0.0, places=6)          # $200 vs $200
        self.assertAlmostEqual(cards['close_rate']['delta_goal'], 0.0, places=6)   # 2% vs 2%
        future = self._cards(self.bu.id, 'nmo')
        self.assertAlmostEqual(future['aov']['value'], 200.0)
        self.assertAlmostEqual(future['close_rate']['value'], 0.02)

    def test_set_goals_replace_the_average(self):
        RateGoal.objects.create(vertical=self.bu, year=self.today.year, aov=Decimal('250'), close_rate=Decimal('0.025'))
        cards = self._cards(self.bu.id)
        self.assertEqual(cards['aov']['goal_label'], 'vs Goal')
        self.assertAlmostEqual(cards['aov']['delta_goal'], (200 - 250) / 250)
        self.assertAlmostEqual(cards['close_rate']['delta_goal'], (0.02 - 0.025) / 0.025)

    def test_company_rollup_needs_goals_on_every_unit(self):
        RateGoal.objects.create(vertical=self.bu, year=self.today.year, aov=Decimal('250'), close_rate=Decimal('0.025'))
        self.assertEqual(self._cards()['aov']['goal_label'], 'vs 12-mo avg')     # Patio has none
        RateGoal.objects.create(vertical=self.bu2, year=self.today.year, aov=Decimal('100'), close_rate=Decimal('0.05'))
        cards = self._cards()
        self.assertEqual(cards['aov']['goal_label'], 'vs Goal')
        # No budgets next month: units weigh equally, AOV = sales / orders = 2 / (1/250 + 1/100).
        self.assertAlmostEqual(self._cards(period='nmo')['aov']['value'], 2 / (1 / 250 + 1 / 100))
        # Budget only in Lighting: Patio adds no orders, so the roll-up is Lighting's goal.
        nm = (self.today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        MonthlyGoal.objects.create(month=nm, vertical=self.bu, budget=Decimal('31000'))
        self.assertAlmostEqual(self._cards(period='nmo')['aov']['value'], 250.0)

    def _post_goals(self, user, **data):
        self.client.force_login(user)
        return self.client.post(f'/app/goals/?company={self.co.id}&vertical={self.bu.id}',
                                {'action': 'save_rate_goals', **data})

    def test_bu_lead_saves_goals_as_dollars_and_percent(self):
        self._post_goals(self.lead, aov_goal='$1,250.50', close_rate_goal='1.5%')
        goal = RateGoal.objects.get(vertical=self.bu, year=self.today.year)
        self.assertEqual((goal.aov, goal.close_rate), (Decimal('1250.50'), Decimal('0.01500')))
        self._post_goals(self.lead, aov_goal='', close_rate_goal='')                 # blank = back to average
        goal.refresh_from_db()
        self.assertEqual((goal.aov, goal.close_rate), (None, None))

    def test_plain_member_cannot_set_goals(self):
        resp = self._post_goals(self.member, aov_goal='300', close_rate_goal='3')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(RateGoal.objects.exists())

    def test_budget_page_shows_goal_panel(self):
        self.client.force_login(self.lead)
        resp = self.client.get(f'/app/goals/?company={self.co.id}&vertical={self.bu.id}')
        self.assertContains(resp, 'Close Rate &amp; AOV Goals')
        self.assertContains(resp, 'Blank = 12-month avg, $200.00')
