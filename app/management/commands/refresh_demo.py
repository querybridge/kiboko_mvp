"""Keep the Home Products Company demo realistic as the calendar moves.

Run it any time (ideally once a day as a scheduled task); every step is
idempotent and only touches the demo company:

1. Daily actuals through --through (default: the end of this month). Days up to
   today are only ever added, never changed. Days after today are regenerated
   on each run so they follow the current plan (go-lives, budgets); they stay
   invisible until their date arrives, because every page reads actuals through
   today only. Sales continue each business unit's recent weekday pattern,
   scale to ~96% of budget in a new month, double on Black Friday and Cyber
   Monday (app.seasonality), and pick up the ramped lift of projects as they go
   live. Visits, orders, visitors, carts and units follow the unit's recent
   ratios, with event-day shifts (higher close rate, lower order value).
2. Holiday-season projects timed around Black Friday (added once, by name).
3. Go-live dates that have passed for projects not yet started move forward, so the approval and gap views show plausible dates.
4. In-flight (WIP) projects: each action's progress follows its schedule
   (never moving backwards), and a project whose go-live has arrived with all
   actions done becomes Complete.

    python manage.py refresh_demo [--through 2026-11-30] [--dry-run]
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from app import seasonality
from business_unit.email import quiet as quiet_emails

DEMO_SLUG = 'belami'
NEW_MONTH_ACHIEVEMENT = 0.96     # share of budget a newly generated month lands at
TRAILING_DAYS = 28               # recent window the weekday pattern and ratios come from
NOISE = 0.06                     # +/- daily revenue noise
LIVE_ATTAINMENT = 0.6            # share of a launched project's value that shows up in sales

# Funnel shifts on event days: (close rate, order value, cart rate) multipliers.
EVENT_FUNNEL = {
    seasonality.THANKSGIVING: (1.05, 0.97, 1.05),
    seasonality.BLACK_FRIDAY: (1.35, 0.90, 1.25),
    seasonality.CYBER_WEEKEND: (1.15, 0.94, 1.10),
    seasonality.CYBER_MONDAY: (1.35, 0.90, 1.25),
}

PRE_WIP = ('Incomplete Entry', 'In Intake', 'Pending LOE', 'Pending Revenue', 'Ready to Score',
           'Scored', 'Executive Approval', 'On Deck', 'Blocked')

# Holiday-season projects, timed relative to Black Friday (BF).
#   name, business unit, AEE, lever, (current, target), status, go-live offset from BF
HOLIDAY_PROJECTS = [
    ('Black Friday doorbuster landing page', 'Lighting', 'attract_traffic', 'visitors',
     (3000, 3150), 'WIP', -7),
    ('Cyber Monday email & SMS countdown', 'Home Decor', 'engage_customers', 'cart_completion',
     (0.30, 0.315), 'WIP', -1),
    ('Holiday shipping-cutoff banner', 'Heating', 'engage_customers', 'cart_completion',
     (0.30, 0.312), 'On Deck', -3),
    ('Fixtures + bulbs Black Friday bundle', 'Lighting', 'expand_purchase', 'avg_unit_price',
     (460, 478), 'Executive Approval', -2),
    ('Gift-card upsell at checkout', 'Home Decor', 'expand_purchase', 'avg_unit_price',
     (460, 472), 'Scored', -4),
    ('Post-holiday exchange-instead-of-refund flow', 'Home Decor', 'engage_customers',
     'cart_completion', (0.30, 0.309), 'Ready to Score', 49),
]
# Actions for the holiday WIP projects: (name, team, start, end) as days before go-live.
HOLIDAY_ACTIONS = [
    ('Discovery & specs', 'Marketing', 24, 17),
    ('Design & build', 'IT', 16, 5),
    ('QA & launch', 'Content', 4, 0),
]
AEE_OBJECTIVES = {
    'attract_traffic': 'Increase Shopper Volume',
    'engage_customers': 'Increase Close Rate',
    'expand_purchase': 'Increase Average Order Value',
}


def _month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


class Command(BaseCommand):
    help = 'Advance the Home Products Company demo: daily actuals, holiday projects, go-lives, progress.'

    def add_arguments(self, parser):
        parser.add_argument('--through', help='Last day of actuals to generate (YYYY-MM-DD; default: end of this month).')
        parser.add_argument('--dry-run', action='store_true', help='Report what would change, change nothing.')

    @quiet_emails  # demo upkeep never sends project notifications
    def handle(self, *args, **opts):
        from business_unit.models import Company
        self.company = Company.objects.filter(slug=DEMO_SLUG).first()
        if self.company is None:
            raise CommandError('Home Products Company (slug "belami") not found.')
        self.today = timezone.localdate()
        try:
            self.through = date.fromisoformat(opts['through']) if opts['through'] else _month_end(self.today)
        except ValueError:
            raise CommandError('--through must be YYYY-MM-DD.')
        self.dry = opts['dry_run']

        with transaction.atomic():
            self._holiday_projects()
            self._roll_stale_go_lives()
            self._advance_wip()
            self._actuals()
            if self.dry:
                transaction.set_rollback(True)
        if not self.dry:
            from project.services import impact
            impact.recompute_scores(company=self.company)
        self.stdout.write(self.style.SUCCESS(
            ('Dry run — nothing saved. ' if self.dry else '') + f'Demo refreshed through {self.through}.'))

    # ------------------------------------------------------------------ actuals
    def _actuals(self):
        from app.models import DailyActual
        for bu in self.company.verticals.all().order_by('name'):
            rows = list(DailyActual.objects.filter(vertical=bu, date__lte=self.today).order_by('date'))
            if not rows:
                self.stdout.write(f'  {bu.name}: no history to continue from; skipped')
                continue
            last_seen = rows[-1].date
            recent = [r for r in rows if r.date > last_seen - timedelta(days=TRAILING_DAYS)]
            pattern = self._weekday_pattern(recent)
            ratios = self._ratios(recent)
            launches = self._launches(bu, last_seen)

            # Past/today: add only the missing days. Future: rebuild from the plan.
            start = last_seen + timedelta(days=1)
            removed = DailyActual.objects.filter(vertical=bu, date__gt=max(self.today, last_seen)).delete()[0]
            added = 0
            d = start
            while d <= self.through:
                month_end = _month_end(d)
                seg_end = min(month_end, self.through)
                days = [d + timedelta(days=i) for i in range((seg_end - d).days + 1)]
                revenue = self._month_revenue(bu, d, days, pattern, rows)
                for day in days:
                    rev = revenue[day] + self._project_lift(launches, day)
                    DailyActual.objects.create(vertical=bu, date=day, **self._funnel(bu, day, rev, ratios))
                    added += 1
                d = seg_end + timedelta(days=1)
            self.stdout.write(f'  {bu.name}: {added} days written ({start} → {self.through}); '
                              f'{removed} unseen future days rebuilt')

    def _weekday_pattern(self, recent):
        """Typical event-free revenue per weekday over the recent window."""
        by_dow = {i: [] for i in range(7)}
        for r in recent:
            by_dow[r.date.weekday()].append(float(r.revenue) / seasonality.day_factor(r.date))
        overall = [v for vals in by_dow.values() for v in vals]
        mean = sum(overall) / len(overall)
        return {dow: (sum(v) / len(v) if v else mean) for dow, v in by_dow.items()}

    def _ratios(self, recent):
        rev = sum(float(r.revenue) for r in recent)
        orders = sum(r.orders for r in recent) or 1
        visits = sum(r.visits for r in recent) or 1
        with_funnel = [r for r in recent if r.visitors and r.carts and r.units]
        f_visits = sum(r.visits for r in with_funnel) or 1
        f_orders = sum(r.orders for r in with_funnel) or 1
        return {
            'aov': rev / orders,
            'close_rate': orders / visits,
            'visitors_per_visit': (sum(r.visitors for r in with_funnel) / f_visits) if with_funnel else 0.82,
            'carts_per_visit': (sum(r.carts for r in with_funnel) / f_visits) if with_funnel else 0.043,
            'units_per_order': (sum(r.units for r in with_funnel) / f_orders) if with_funnel else 1.75,
        }

    def _month_revenue(self, bu, first, days, pattern, history):
        """{day: revenue} for the days of one month. A month already under way
        keeps its recent pace; a new month lands near its budget, with the same
        weekday shape and event days carrying their factor of the total."""
        from app.models import MonthlyGoal

        def shape(day):
            return pattern[day.weekday()] * seasonality.day_factor(day)

        month_start = date(first.year, first.month, 1)
        under_way = any(r.date >= month_start for r in history)
        scale = 1.0
        if not under_way:
            goal = MonthlyGoal.objects.filter(vertical=bu, month=month_start).first()
            full = [month_start + timedelta(days=i) for i in range(_month_end(first).day)]
            if goal and goal.budget:
                scale = float(goal.budget) * NEW_MONTH_ACHIEVEMENT / sum(shape(x) for x in full)
        out = {}
        for day in days:
            rng = random.Random(f'{bu.id}:{day.isoformat()}')
            out[day] = shape(day) * scale * rng.uniform(1 - NOISE, 1 + NOISE)
        return out

    def _launches(self, bu, last_seen):
        """(go-live, daily value, ramp days) of this unit's projects that go live
        after the last real day, so their lift isn't already in the trend."""
        from strategy.models import Project
        out = []
        for p in Project.objects.filter(vertical=bu, status__in=('WIP', 'Complete', 'Launched'),
                                        target_completion__gt=last_seen, value__gt=0):
            out.append((p.target_completion, p.value / 365.0, max(1, p.ramp_days or 30)))
        return out

    def _project_lift(self, launches, day):
        lift = 0.0
        for go_live, daily, ramp in launches:
            if day >= go_live:
                lift += daily * min(1.0, ((day - go_live).days + 1) / ramp) * LIVE_ATTAINMENT
        return lift

    def _funnel(self, bu, day, revenue, ratios):
        rng = random.Random(f'{bu.id}:{day.isoformat()}:funnel')
        cr_m, aov_m, cart_m = EVENT_FUNNEL.get(seasonality.event_for(day), (1.0, 1.0, 1.0))
        aov = ratios['aov'] * aov_m * rng.uniform(0.96, 1.04)
        close_rate = ratios['close_rate'] * cr_m * rng.uniform(0.95, 1.05)
        orders = max(1, round(revenue / aov))
        visits = max(orders, round(orders / close_rate))
        return {
            'revenue': Decimal(str(round(revenue, 2))),
            'orders': orders,
            'visits': visits,
            'visitors': max(1, round(visits * ratios['visitors_per_visit'] * rng.uniform(0.98, 1.02))),
            'carts': max(orders, round(visits * ratios['carts_per_visit'] * cart_m * rng.uniform(0.96, 1.04))),
            'units': max(orders, round(orders * ratios['units_per_order'] * rng.uniform(0.97, 1.03))),
        }

    # ----------------------------------------------------------------- projects
    def _holiday_projects(self):
        from django.contrib.auth.models import User
        from business_unit.models import Department, Team
        from project.models import Action
        from strategy.models import Objective, Project

        bf = seasonality.black_friday(self.today.year)
        bus = {b.name: b for b in self.company.verticals.all()}
        objectives = {aee: Objective.objects.filter(company=self.company, aee_alignment=aee).order_by('-year').first()
                      for aee in AEE_OBJECTIVES}
        demo_projects = Project.objects.filter(vertical__company=self.company)
        owner_ids = list(demo_projects.exclude(owner=None).values_list('owner_id', flat=True).distinct())
        owners = (list(User.objects.filter(id__in=owner_ids).order_by('id'))
                  or list(User.objects.filter(company_memberships__company=self.company).order_by('id'))
                  or ([self.company.organization.org_admin] if self.company.organization_id
                      and self.company.organization.org_admin_id else []))
        depts = list(Department.objects.order_by('id'))
        teams = {t.name: t for t in Team.objects.all()}

        created = 0
        for i, (name, bu_name, aee, lever, (lo, hi), status, offset) in enumerate(HOLIDAY_PROJECTS):
            bu = bus.get(bu_name)
            if bu is None or demo_projects.filter(name__iexact=name).exists():
                continue
            rng = random.Random(f'holiday:{name}')
            go_live = bf + timedelta(days=offset)
            s0 = self._annual_sales(bu)
            p = Project(
                name=name, owner=owners[i % len(owners)] if owners else None, vertical=bu,
                department=depts[i % len(depts)] if depts else None, objective=objectives.get(aee),
                why=f'As a holiday shopper, I want {name[0].lower() + name[1:]}, so that I find the deal and order in time.'[:400],
                definition_of_done='Live before the holiday peak; success metric tracked; no P1 defects.',
                status=status, approved=status not in ('Incomplete Entry',), archived=False,
                target_completion=go_live, year=go_live.year,
                effort_size=rng.choice(['XS', 'S', 'M']), capability=rng.choice(['fully', 'mostly']),
                customer_value=rng.randint(6, 10), business_value=rng.randint(6, 10),
                cost_savings=rng.randint(2, 6), operational_cost=rng.randint(3, 7),
                business_risk=rng.randint(1, 4), level_of_effort=rng.randint(5, 9),
                ramp_days=7, direct_expense=rng.choice([0, 5000, 15000]), plausibility_factor=1.0,
                lever=lever, target_from=Decimal(str(lo)), target_to=Decimal(str(hi)),
                s0_annual=Decimal(str(round(s0, 2))),
            )
            p.save()
            created += 1
            if status == 'WIP' and p.owner and depts:     # an Action needs an owner and a department
                for a_name, team, start_before, end_before in HOLIDAY_ACTIONS:
                    a = Action(project=p, owner=p.owner, name=a_name,
                               business_unit=p.department or depts[0], vertical=bu,
                               objective=p.objective, team=teams.get(team),
                               launch=go_live - timedelta(days=end_before), progress=0)
                    a.save()
                    Action.objects.filter(pk=a.pk).update(active_date=go_live - timedelta(days=start_before))
        self.stdout.write(f'  Holiday projects: {created} added (Black Friday {bf})')

    def _annual_sales(self, bu):
        from app.models import DailyActual
        recs = list(DailyActual.objects.filter(vertical=bu, date__lte=self.today)
                    .order_by('-date').values_list('revenue', flat=True)[:365])
        return float(sum(recs)) / len(recs) * 365.0 if recs else 5_000_000.0

    def _roll_stale_go_lives(self):
        """Not-yet-started projects whose go-live has passed get a plausible new
        date 4-16 weeks out, spread by project."""
        from strategy.models import Project
        moved = 0
        for p in Project.objects.filter(vertical__company=self.company, archived=False, status__in=PRE_WIP):
            if p.target_completion and p.target_completion >= self.today:
                continue
            p.target_completion = self.today + timedelta(days=28 + (p.id * 17) % 85)
            p.save()
            moved += 1
        self.stdout.write(f'  Go-live dates moved forward: {moved}')

    def _advance_wip(self):
        """Action progress follows each action's schedule; a project whose go-live
        has arrived with every action done is Complete."""
        from project.models import Action
        from strategy.models import Project
        advanced = completed = 0
        for p in Project.objects.filter(vertical__company=self.company, archived=False, status='WIP'):
            actions = list(p.actions.filter(archived=False).order_by('launch', 'id'))
            prev_end = None
            for a in actions:
                end = a.launch or p.target_completion
                start = a.active_date or prev_end or (end - timedelta(days=21) if end else None)
                prev_end = end
                if not (start and end):
                    continue
                if self.today >= end:
                    due = 100
                elif self.today <= start:
                    due = 0
                else:
                    due = int(5 * round(20 * (self.today - start).days / max(1, (end - start).days)))
                if due > (a.progress or 0):
                    Action.objects.filter(pk=a.pk).update(progress=due)
                    advanced += 1
            done = all((x.progress or 0) >= 100 for x in Action.objects.filter(pk__in=[a.pk for a in actions]))
            if actions and done and p.target_completion and p.target_completion <= self.today:
                p.status = 'Complete'
                p.save()
                completed += 1
        self.stdout.write(f'  WIP: {advanced} action(s) advanced, {completed} project(s) completed')
