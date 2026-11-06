"""Black Friday / Cyber Monday in the forecast, and the demo refresher."""
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from app import seasonality
from app.models import DailyActual, MonthlyGoal
from business_unit.models import BusinessUnit, Company, Organization
from django.contrib.auth.models import User


class CalendarTests(TestCase):
    def test_dates(self):
        self.assertEqual(seasonality.thanksgiving(2026), date(2026, 11, 26))
        self.assertEqual(seasonality.black_friday(2026), date(2026, 11, 27))
        self.assertEqual(seasonality.thanksgiving(2025), date(2025, 11, 27))
        self.assertEqual(seasonality.day_factor(date(2026, 11, 27)), 2.0)       # Black Friday
        self.assertEqual(seasonality.day_factor(date(2026, 11, 30)), 2.0)       # Cyber Monday
        self.assertEqual(seasonality.day_factor(date(2026, 11, 20)), 1.0)


class ForecastTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('o', 'o@x.test', 'pw')
        org = Organization.objects.create(name='o', slug='o', org_admin=owner, plan_status='active')
        self.co = Company.objects.create(organization=org, name='Co', slug='co')
        self.units = [BusinessUnit.objects.create(name=n, company=self.co) for n in ('A', 'B')]
        for bu in self.units:                         # Nov 1-7: $1,000/day per unit
            for day in range(1, 8):
                DailyActual.objects.create(vertical=bu, date=date(2026, 11, day), revenue=Decimal('1000'))

    def forecast(self):
        from app.views import calculate_forecast
        with mock.patch('app.views.timezone.localdate', return_value=date(2026, 11, 7)):
            return calculate_forecast(2026, 11, return_components=True, company_id=self.co.id)[0]

    def test_company_rollup_projects_daily_totals_with_event_days(self):
        # 7 seen days at $2,000 + 23 remaining days at $2,000, where Thanksgiving
        # counts 0.85, Black Friday and Cyber Monday 2, and the Cyber weekend 1.3 each.
        extra = (0.85 - 1) + (2 - 1) + 2 * (1.3 - 1) + (2 - 1)
        self.assertAlmostEqual(float(self.forecast()), 2000 * (30 + extra), places=0)


class RefreshDemoTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('o', 'o@x.test', 'pw')
        org = Organization.objects.create(name='o', slug='o', org_admin=owner, plan_status='active')
        self.co = Company.objects.create(organization=org, name='Home Products Company', slug='belami')
        self.bu = BusinessUnit.objects.create(name='Lighting', company=self.co)
        d = date(2026, 10, 1)
        while d <= date(2026, 10, 22):
            DailyActual.objects.create(vertical=self.bu, date=d, revenue=Decimal('40000'), visits=6000, orders=90,
                                       visitors=5000, carts=260, units=160)
            d += timedelta(days=1)
        MonthlyGoal.objects.create(vertical=self.bu, month=date(2026, 11, 1), budget=Decimal('1300000'))

    def run_on(self, today):
        with mock.patch('app.management.commands.refresh_demo.timezone.localdate', return_value=today):
            call_command('refresh_demo', stdout=open('/dev/null', 'w'))

    def test_fills_month_lands_near_budget_and_doubles_black_friday(self):
        self.run_on(date(2026, 11, 6))
        rows = {r.date: r for r in DailyActual.objects.filter(vertical=self.bu)}
        self.assertIn(date(2026, 11, 30), rows)
        nov = sum(float(r.revenue) for d, r in rows.items() if d.month == 11)
        self.assertAlmostEqual(nov / 1_300_000, 0.96, delta=0.03)
        fridays = [float(rows[date(2026, 11, d)].revenue) for d in (6, 13, 20)]
        self.assertGreater(float(rows[date(2026, 11, 27)].revenue), 1.7 * max(fridays))

    def test_seen_days_never_change_and_rerun_is_stable(self):
        self.run_on(date(2026, 11, 6))
        seen = {r.date: r.revenue for r in DailyActual.objects.filter(vertical=self.bu, date__lte=date(2026, 11, 6))}
        self.run_on(date(2026, 11, 10))
        after = {r.date: r.revenue for r in DailyActual.objects.filter(vertical=self.bu, date__lte=date(2026, 11, 6))}
        self.assertEqual(seen, after)
        self.assertEqual(DailyActual.objects.filter(vertical=self.bu, date__month=11).count(), 30)

    def test_only_touches_the_demo_company(self):
        other = BusinessUnit.objects.create(name='Other', company=Company.objects.create(
            organization=self.co.organization, name='Real client', slug='real'))
        DailyActual.objects.create(vertical=other, date=date(2026, 10, 1), revenue=Decimal('5'))
        self.run_on(date(2026, 11, 6))
        self.assertEqual(DailyActual.objects.filter(vertical=other).count(), 1)
