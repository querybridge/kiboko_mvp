"""Seed the Belami company for a comprehensive demo:

  1. Projects across every intake / Kanban / terminal status, with real estimator
     inputs (lever + baseline/target + sales baseline) so values, estimates and
     scores populate, spread over the four business units and the objectives.
  2. Performance data (MonthlyGoal budgets + DailyActual) shaped like a retail
     calendar: category seasonality (patio peaks in summer, heating in winter)
     plus event spikes — Valentine's, Presidents/Memorial/Labor Day, July-4 /
     Prime week, Black Friday, Cyber Monday, and the December holiday run. Traffic
     (visits) spikes a little harder than sales on event days, so engagement and
     sales both jump around, e.g., Labor Day.

Idempotent-ish: projects are matched by name; actuals + budgets for Belami are
rebuilt in the requested range. Demo data only — safe to re-run.

    python manage.py seed_belami_demo [--from 2024-01-01] [--to today]
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from app.models import DailyActual, MonthlyGoal
from business_unit.models import Company, BusinessUnit, Department
from strategy.models import Objective, Project


# --- BU demo profile: category (seasonal shape) + annual sales run-rate --------
BU_PROFILE = {
    'Lighting':            {'cat': 'lighting', 'annual': 12_000_000},
    'Patio':               {'cat': 'patio',    'annual': 6_000_000},
    'Bailey Street Home':  {'cat': 'home',     'annual': 8_000_000},
    'Heating':             {'cat': 'heating',  'annual': 4_000_000},
}

# Monthly seasonal shape per category (Jan..Dec); normalized to mean 1.0 in code.
CATEGORY_MONTHLY = {
    'patio':    [0.55, 0.60, 0.85, 1.25, 1.55, 1.65, 1.55, 1.30, 1.00, 0.75, 0.60, 0.55],
    'heating':  [1.55, 1.45, 1.10, 0.80, 0.60, 0.50, 0.50, 0.60, 0.95, 1.30, 1.55, 1.65],
    'lighting': [0.90, 0.88, 0.95, 1.00, 1.00, 0.98, 0.98, 1.00, 1.05, 1.12, 1.35, 1.40],
    'home':     [0.92, 0.90, 1.00, 1.05, 1.05, 1.00, 1.00, 1.00, 1.05, 1.08, 1.25, 1.35],
}
YOY_GROWTH = {2024: 1.00, 2025: 1.08, 2026: 1.16, 2027: 1.24}
DOW_MULT = {0: 1.05, 1: 1.10, 2: 1.10, 3: 1.05, 4: 0.95, 5: 0.85, 6: 0.90}
AOV, CLOSE_RATE = 460.0, 0.0152


def _norm(seq):
    m = sum(seq) / len(seq)
    return [x / m for x in seq]


def _nth_weekday(year, month, weekday, n):
    """n-th `weekday` (Mon=0) of month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date(year, month, 1 + offset + (n - 1) * 7)


def _last_weekday(year, month, weekday):
    last = calendar.monthrange(year, month)[1]
    d = date(year, month, last)
    return date(year, month, last - ((d.weekday() - weekday) % 7))


def retail_event_mult(d):
    """Sales multiplier for a retail-calendar day (1.0 = ordinary)."""
    y = d.year
    presidents = _nth_weekday(y, 2, 0, 3)
    memorial = _last_weekday(y, 5, 0)
    labor = _nth_weekday(y, 9, 0, 1)
    thanks = _nth_weekday(y, 11, 3, 4)
    black_fri, cyber_mon = thanks + timedelta(days=1), thanks + timedelta(days=4)
    windows = [
        (date(y, 2, 10), date(y, 2, 14), 1.15),                      # Valentine's
        (presidents - timedelta(days=2), presidents, 1.12),          # Presidents Day
        (memorial - timedelta(days=3), memorial, 1.28),              # Memorial Day
        (date(y, 7, 1), date(y, 7, 12), 1.30),                       # July 4 / Prime week
        (labor - timedelta(days=3), labor, 1.35),                    # Labor Day
        (date(y, 8, 20), date(y, 9, 5), 1.12),                       # back to school
        (date(y, 10, 25), date(y, 10, 31), 1.10),                    # Halloween
        (thanks, thanks, 1.20),                                      # Thanksgiving
        (black_fri - timedelta(days=1), black_fri, 1.90),            # Black Friday
        (cyber_mon, cyber_mon, 2.00),                                # Cyber Monday
        (cyber_mon + timedelta(days=1), date(y, 12, 23), 1.45),      # holiday shopping
        (date(y, 12, 26), date(y, 12, 31), 1.20),                    # post-Christmas
    ]
    m = 1.0
    for start, end, mult in windows:
        if start <= d <= end:
            m = max(m, mult)
    if d == date(y, 12, 25):
        m = 0.45                                                     # Christmas Day dip
    if d == date(y, 1, 1):
        m = 0.60
    return m


class Command(BaseCommand):
    help = 'Seed Belami with demo projects (all statuses) + retail-calendar performance data.'

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='start', default='2024-01-01')
        parser.add_argument('--to', dest='end', default=None)

    def handle(self, *args, **opts):
        rng = random.Random(1128)
        belami = Company.objects.filter(slug='belami').first()
        if not belami:
            raise CommandError('Belami company not found.')
        bus = {b.name: b for b in belami.verticals.all()}
        try:
            start = date.fromisoformat(opts['start'])
        except ValueError as e:
            raise CommandError(str(e))
        end = date.fromisoformat(opts['end']) if opts['end'] else date.today()

        self._seed_performance(belami, bus, start, end, rng)
        self._seed_projects(belami, bus, rng)
        from project.services import impact
        impact.recompute_scores(company=belami)
        self.stdout.write(self.style.SUCCESS('seed_belami_demo: done.'))

    # ---- performance: budgets + seasonal daily actuals ----------------------
    def _seed_performance(self, belami, bus, start, end, rng):
        from django.db.models import Q
        MonthlyGoal.objects.filter(vertical__in=bus.values()).delete()
        DailyActual.objects.filter(vertical__in=bus.values()).delete()

        months = []
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            months.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

        budgets = {}   # (bu_id, y, m) -> Decimal
        goals = []
        for name, bu in bus.items():
            prof = BU_PROFILE.get(name, {'cat': 'home', 'annual': 5_000_000})
            shape = _norm(CATEGORY_MONTHLY[prof['cat']])
            for (yy, mm) in months:
                base = prof['annual'] / 12.0 * shape[mm - 1] * YOY_GROWTH.get(yy, 1.24)
                budgets[(bu.id, yy, mm)] = Decimal(str(round(base, 2)))
                goals.append(MonthlyGoal(month=date(yy, mm, 1), vertical=bu, budget=budgets[(bu.id, yy, mm)]))
        MonthlyGoal.objects.bulk_create(goals)

        actuals = []
        for name, bu in bus.items():
            # distribute each month's budget across its days, weighted by DOW x event.
            for (yy, mm) in months:
                dim = calendar.monthrange(yy, mm)[1]
                days = [date(yy, mm, dd) for dd in range(1, dim + 1)
                        if start <= date(yy, mm, dd) <= end]
                if not days:
                    continue
                weights = [DOW_MULT[d.weekday()] * retail_event_mult(d) for d in days]
                wsum = sum(weights)
                # actuals land ~97% of budget with mild noise
                month_actual = float(budgets[(bu.id, yy, mm)]) * 0.97
                for d, w in zip(days, weights):
                    rev = month_actual * (w / wsum) * rng.uniform(0.93, 1.07)
                    orders = max(0, int(round(rev / (AOV * rng.uniform(0.95, 1.05)))))
                    visits = int(round(orders / CLOSE_RATE)) if orders else 0
                    # engagement spikes a touch harder than sales on event days
                    ev = retail_event_mult(d)
                    if ev > 1.0:
                        visits = int(round(visits * (1 + (ev - 1) * 0.45)))
                    actuals.append(DailyActual(date=d, vertical=bu, revenue=Decimal(str(round(rev, 2))),
                                               visits=visits, orders=orders))
        DailyActual.objects.bulk_create(actuals, batch_size=2000)
        self.stdout.write(f'  performance: {len(goals)} monthly budgets, {len(actuals)} daily actuals '
                          f'({start} → {end}) with retail seasonality.')

    # ---- projects across all statuses ---------------------------------------
    def _seed_projects(self, belami, bus, rng):
        from project.services import impact
        obj = {o.aee_alignment: o for o in Objective.objects.all() if o.aee_alignment}
        # a couple of engage objectives exist; prefer "Close Rate"/"Shopping Activity"
        depts = list(Department.objects.all())
        from django.contrib.auth.models import User
        owners = list(User.objects.filter(is_superuser=True)) or list(User.objects.all()[:3])

        # lever + baseline/target per AEE so the estimate is sensible
        LEVER_SPEC = {
            'attract_traffic':  ('visitors', 3000, 3300),
            'engage_customers': ('cart_completion', 0.30, 0.345),
            'expand_purchase':  ('avg_unit_price', 460, 505),
        }
        # (name, bu, aee, status, effort, capability, progress, evidence)
        SPEC = [
            ('Relight the homepage hero & category tiles', 'Lighting', 'attract_traffic', 'WIP', 'L', 'fully', 60, False),
            ('Patio collection landing pages for spring', 'Patio', 'attract_traffic', 'On Deck', 'M', 'mostly', 0, False),
            ('Fixture finder quiz (guided selling)', 'Lighting', 'engage_customers', 'WIP', 'XL', 'stretch', 35, False),
            ('One-page checkout redesign', 'Lighting', 'engage_customers', 'Executive Approval', 'L', 'mostly', 0, False),
            ('Bundle shades + bulbs at the PDP', 'Lighting', 'expand_purchase', 'Scored', 'S', 'fully', 0, False),
            ('Free-shipping threshold at $99', 'Bailey Street Home', 'expand_purchase', 'WIP', 'M', 'fully', 45, False),
            ('Heating pre-season email/SMS win-back', 'Heating', 'engage_customers', 'Scored', 'M', 'mostly', 0, True),
            ('Outdoor lighting how-to content hub', 'Patio', 'attract_traffic', 'Ready to Score', 'L', 'stretch', 0, False),
            ('Restore PDP reviews after the migration', 'Bailey Street Home', 'engage_customers', 'Executive Approval', 'S', 'fully', 0, True),
            ('Cart abandonment retargeting', 'Lighting', 'engage_customers', 'On Deck', 'M', 'mostly', 0, False),
            ('Patio heater cross-sell on cart', 'Patio', 'expand_purchase', 'Scored', 'S', 'mostly', 0, False),
            ('Live chat for high-consideration fixtures', 'Lighting', 'engage_customers', 'Ready to Score', 'M', 'stretch', 0, False),
            ('Ceiling-fan configurator', 'Lighting', 'expand_purchase', 'Pending LOE', '', '', 0, False),
            ('Bailey Street loyalty program', 'Bailey Street Home', 'expand_purchase', 'Pending LOE', '', '', 0, False),
            ('Heating buyer’s guide SEO push', 'Heating', 'attract_traffic', 'Incomplete Entry', '', '', 0, False),
            ('AR “see the light in your room”', 'Lighting', 'engage_customers', 'Incomplete Entry', '', '', 0, False),
            ('Same-day-ship badge on eligible SKUs', 'Bailey Street Home', 'engage_customers', 'Blocked', 'L', 'new', 20, False),
            ('Warehouse relight energy retrofit', 'Lighting', 'expand_purchase', 'Complete', 'L', 'fully', 100, False),
            ('Launched Q2 patio clearance engine', 'Patio', 'expand_purchase', 'Launched', 'XL', 'fully', 100, False),
        ]

        today = date.today()
        created = 0
        for i, (name, bu_name, aee, status, effort, cap, prog, evidence) in enumerate(SPEC):
            if Project.objects.filter(name=name).exists():
                continue
            bu = bus.get(bu_name)
            objective = obj.get(aee)
            lever, lo, hi = LEVER_SPEC[aee]
            s0 = BU_PROFILE.get(bu_name, {'annual': 5_000_000})['annual']
            scored_now = status in ('Scored', 'Executive Approval', 'On Deck', 'WIP', 'Complete', 'Launched')
            approved = status != 'Incomplete Entry'
            has_estimate = status != 'Incomplete Entry'   # incomplete entries stay bare
            # 5 voted criteria + LOE (0 until voted)
            cv, bv, cs, oc, br, loe = (
                (rng.randint(5, 10), rng.randint(5, 10), rng.randint(2, 8),
                 rng.randint(2, 8), rng.randint(1, 6), rng.randint(2, 8)) if scored_now
                else (0, 0, 0, 0, 0, 0))
            go = date(today.year, rng.randint(1, 12), rng.randint(1, 28))

            p = Project(
                name=name, owner=rng.choice(owners), vertical=bu,
                department=rng.choice(depts) if depts else None, objective=objective,
                why=f'As a shopper, I want {name.lower()}, so that Belami {bu_name} grows.'[:400],
                definition_of_done='Shipped to all users; success metric tracked; no P1 defects.',
                status=status, approved=approved, archived=(status == 'Launched'),
                target_completion=go, year=today.year,
                effort_size=effort, capability=cap,
                customer_value=cv, business_value=bv, cost_savings=cs,
                operational_cost=oc, business_risk=br, level_of_effort=loe,
                ramp_days=rng.choice([30, 45, 60]), direct_expense=rng.choice([0, 20000, 50000]),
                plausibility_factor=1.0,
            )
            if has_estimate:
                p.lever, p.target_from, p.target_to, p.s0_annual = lever, Decimal(str(lo)), Decimal(str(hi)), Decimal(str(s0))
            if evidence:
                p.evidence_backed = True
                p.evidence_kind = 'prior_level'
                p.evidence_prior_level = Decimal(str(hi))
                p.evidence_note = 'Restoring the level sustained before the recent site regression.'
            p.save()   # explicit status is honored; save computes voted_score
            created += 1
        self.stdout.write(f'  projects: {created} created across statuses / business units.')
