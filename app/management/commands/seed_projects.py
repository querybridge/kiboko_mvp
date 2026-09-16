"""
Seed dummy Projects (the scored unit) and their child Actions (execution tasks)
for UX pressure testing -- a spread of Kanban lanes, intake stages, scores,
revenue, t-shirt sizes, and launch dates across objectives / business units.
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from business_unit.models import Department, BusinessUnit, Team
from project.models import Action
from strategy.models import Project, Objective, Measure


def _rand_date(rng, start, end):
    span = (end - start).days
    return start if span <= 0 else start + timedelta(days=rng.randint(0, span))


# (name, status, scored, revenue, size, progress, why)
PROJECTS = [
    ('Redesign Product Detail Pages',    'WIP',                True,  450000, 'XL', 65, 'Improve conversion on high-traffic PDPs'),
    ('Add size/finish filter to PLP',    'WIP',                True,  120000, 'M',  30, 'Narrow results by product attributes'),
    ('Loyalty points dashboard',         'WIP',                True,  800000, 'L',  10, 'Members see points balance and redemption'),
    ('Referral program integration',     'On Deck',            True,  350000, 'M',   0, 'Members refer friends and earn points'),
    ('Headless CMS proof of concept',    'Ready to Score',     False, 200000, 'L',   0, 'Validate headless architecture'),
    ('B2B bulk order CSV upload',        'WIP',                True,  600000, 'L',  45, 'Wholesale customers upload large orders'),
    ('B2B net-30 payment terms',         'Executive Approval', True,  250000, 'S',   0, 'Invoice-based payment for B2B accounts'),
    ('Homepage personalization A/B test','Scored',             True,  500000, 'M',   0, 'Personalized hero banners vs static'),
    ('Recommendation engine pipeline',   'Pending Revenue',    False,      0, '',    0, 'ETL pipeline feeding the ML model'),
    ('Holiday email drip sequences',     'Pending LOE',        False, 200000, '',    0, 'Automated flows for the holiday season'),
    ('Gift guide landing pages',         'Incomplete Entry',   False,      0, '',    0, 'Curated gift guides by price and recipient'),
    ('Site search autocomplete upgrade', 'Scored',             True,  275000, 'M',   0, 'AI-powered autocomplete'),
    ('Mobile checkout redesign',         'Blocked',            True,  180000, 'L',  20, 'Simplify mobile checkout'),
    ('Inventory sync real-time API',     'Complete',           True,  180000, 'M', 100, 'Real-time inventory across channels'),
    ('Launched Q4 promo engine',         'Launched',           True,  900000, 'XL',100, 'Dynamic promo pricing engine'),
    ('Warehouse pick-pack optimization', 'WIP',                True,  400000, 'L',  55, 'Optimize pick routes'),
]


class Command(BaseCommand):
    help = 'Seed dummy Projects (+ child tasks) for UX testing.'

    def handle(self, *args, **options):
        rng = random.Random(42)
        today = date.today()
        year = today.year

        users = list(User.objects.all())
        departments = list(Department.objects.all())
        verticals = list(BusinessUnit.objects.filter(company__isnull=False))
        teams = list(Team.objects.all())
        objectives = list(Objective.objects.all())
        measures = list(Measure.objects.filter(active=True))

        if not users or not departments or not verticals:
            self.stderr.write('Need users, departments, and business units first.')
            return

        created = 0
        for i, (name, status, scored, revenue, size, progress, why) in enumerate(PROJECTS):
            if Project.objects.filter(name=name).exists():
                self.stdout.write(f'  Skip (exists): {name}')
                continue
            cv, bv, cs, oc, br, loe = (
                (rng.randint(3, 10), rng.randint(3, 10), rng.randint(1, 8),
                 rng.randint(1, 8), rng.randint(1, 7), rng.randint(2, 9)) if scored
                else (0, 0, 0, 0, 0, 0))
            go_live = date(year, rng.randint(1, 6), rng.randint(1, 28)) if status in ('WIP', 'Complete', 'Launched') else None
            approved = status not in ('Incomplete Entry',)

            p = Project(
                name=name[:75], why=why, definition_of_done=why[:350],
                objective=objectives[i % len(objectives)] if objectives else None,
                owner=rng.choice(users), vertical=rng.choice(verticals),
                department=rng.choice(departments), value=revenue, effort_size=size,
                status=status, approved=approved, archived=(status == 'Launched'),
                target_completion=go_live, year=year,
                customer_value=cv, business_value=bv, cost_savings=cs,
                operational_cost=oc, business_risk=br, level_of_effort=loe,
            )
            p.save()

            # Steps toward completing the project (named for the work), chained.
            step_set = rng.choice([
                ['Discovery & specs', 'Build', 'QA & launch'],
                ['Design', 'Implementation', 'Rollout'],
                ['Requirements', 'Build integration', 'Go live'],
            ])
            spans = ([go_live - timedelta(days=int(25 * (len(step_set) - 1 - i))) for i in range(len(step_set))]
                     if go_live else [None] * len(step_set))
            progs = [100, progress, 0] if status == 'WIP' else [0] * len(step_set)
            prev = None
            for step_name, launch_d, prog in zip(step_set, spans, progs):
                a = Action(
                    project=p, owner=p.owner, business_unit=p.department or departments[0],
                    vertical=p.vertical, objective=p.objective, name=step_name,
                    why=why, impact=why[:75], launch=launch_d, progress=prog,
                    team=rng.choice(teams) if teams else None,
                    measure=rng.choice(measures) if measures else None,
                )
                a.save()
                if prev is not None:
                    a.depends_on.add(prev)
                created_dt = _rand_date(rng, date(year, 1, 1), launch_d if (launch_d and launch_d < today) else today)
                Action.objects.filter(pk=a.pk).update(date_created=created_dt)
                if status == 'WIP' and launch_d:
                    Action.objects.filter(pk=a.pk).update(
                        active_date=_rand_date(rng, created_dt, min(launch_d, today)))
                prev = a
            created += 1
            self.stdout.write(f'  [{status:18s}] {name} (score={p.normalized_score}, ${revenue:,})')

        self.stdout.write(self.style.SUCCESS(f'Created {created} Projects (+ child tasks).'))
