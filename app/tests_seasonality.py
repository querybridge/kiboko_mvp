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


class UnseenWeekdayTests(ForecastTests):
    def test_weekday_not_seen_yet_uses_the_average_not_zero(self):
        from app.views import calculate_forecast
        DailyActual.objects.filter(date=date(2026, 11, 7)).delete()          # no Saturday yet
        with mock.patch('app.views.timezone.localdate', return_value=date(2026, 11, 6)):
            base = calculate_forecast(2026, 11, return_components=True, company_id=self.co.id)[0]
        extra = (0.85 - 1) + (2 - 1) + 2 * (1.3 - 1) + (2 - 1)
        self.assertAlmostEqual(float(base), 2000 * (30 + extra), places=0)


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


class ProjectRampTests(TestCase):
    """A launched project counts in the forecast ramped up from go-live and
    discounted by expected attainment, never at full value from day one."""

    def project(self, **kw):
        from strategy.models import Project
        defaults = dict(value=365000, target_completion=date(2026, 11, 21), ramp_days=10,
                        capability='fully', plausibility_factor=1.0)
        defaults.update(kw)
        return Project(**defaults)

    def test_ramp(self):
        from project.services.impact import forecast_daily_value
        p = self.project()                                   # $1,000/day at full effect
        self.assertEqual(forecast_daily_value(p, date(2026, 11, 20)), 0)
        self.assertEqual(forecast_daily_value(p, date(2026, 11, 21)), 0)     # go-live day: 0%
        self.assertAlmostEqual(forecast_daily_value(p, date(2026, 11, 26)), 500)
        self.assertAlmostEqual(forecast_daily_value(p, date(2026, 12, 15)), 1000)

    def test_discounted_by_capability_and_plausibility(self):
        from project.services.impact import forecast_daily_value
        p = self.project(capability='mostly', plausibility_factor=0.8)
        self.assertAlmostEqual(forecast_daily_value(p, date(2026, 12, 15)), 1000 * 0.85 * 0.8)

    def test_month_forecast_uses_ramp(self):
        from app.views import calculate_forecast
        owner = User.objects.create_user('o', 'o@x.test', 'pw')
        org = Organization.objects.create(name='o', slug='o', org_admin=owner, plan_status='active')
        co = Company.objects.create(organization=org, name='Co', slug='co')
        bu = BusinessUnit.objects.create(name='A', company=co)
        p = self.project(name='Launch', why='x', vertical=bu, status='WIP')
        p.save()
        type(p).objects.filter(pk=p.pk).update(status='WIP', value=365000)
        with mock.patch('app.views.timezone.localdate', return_value=date(2026, 11, 7)):
            uplift = calculate_forecast(2026, 11, return_components=True, company_id=co.id)[1]
        # Nov 21-30 at 0%, 10%, ... 90% of $1,000/day = $4,500 (not $10,000 at face value).
        self.assertAlmostEqual(float(uplift), 4500, places=0)
