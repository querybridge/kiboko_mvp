"""Seed demo Projects (the scored unit) for the Demo Account's "GA4 - Google
Merch Shop" business unit so every Project Control view shows activity:

  * Executive Kanban (approved): Ready to Score, Scored, Executive Approval,
    On Deck, WIP, Blocked -- with scores, revenue, t-shirt sizes.
  * Project Intake (approved=False / Pending Revenue / Pending LOE): a few in
    each intake stage, plus incomplete entries.

Each Project gets one child Action (execution task) for the WIP gantt. Clean
reseed: wipes existing Projects on that business unit, then recreates.
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from business_unit.models import Company, Department, Team
from strategy.models import Project, Objective, Measure
from project.models import Action

# (name, status, approved, scored, revenue, effort_size, why, dod, okey)
# okey: volume=Shopper Volume, close=Close Rate, aov=Average Order Value, ''=none
PROJECTS = [
    # -- Executive Kanban (approved) --
    ('Search autocomplete & synonyms',  'Ready to Score',     True,  False, 120000, 'M',  'Faster product discovery', 'Search returns relevant results with synonyms', 'volume'),
    ('Size guide & fit finder',         'Ready to Score',     True,  False,  90000, 'S',  'Reduce sizing uncertainty', 'Fit finder live on all apparel PDPs', 'close'),
    ('Product page video & 360 views',  'Scored',             True,  True,  140000, 'L',  'Richer PDP media', 'Video + 360 on the top 100 PDPs', 'volume'),
    ('Cart abandonment email flow',     'Scored',             True,  True,  200000, 'M',  'Recover abandoned carts', '3-email abandonment series live', 'close'),
    ('Express pay (Google/Apple Pay)',  'Executive Approval', True,  True,  260000, 'L',  'One-tap wallet payment', 'Wallet pay available at checkout', 'close'),
    ('Apparel + accessories bundles',   'Executive Approval', True,  True,  160000, 'S',  'Raise units per order', 'Bundles configured on 20 SKUs', 'aov'),
    ('Post-purchase upsell offers',     'On Deck',            True,  True,  180000, 'M',  'Grow order value', 'Upsell shown on order confirmation', 'aov'),
    ('Homepage bestsellers carousel',   'On Deck',            True,  True,  150000, 'S',  'Lift engagement', 'Bestsellers carousel on the homepage', 'volume'),
    ('Streamline guest checkout',       'WIP',                True,  True,  320000, 'XL', 'Cut checkout drop-off', 'One-page guest checkout', 'close'),
    ('Free shipping threshold at $50',  'WIP',                True,  True,  210000, 'M',  'Encourage bigger baskets', 'Free shipping at $50 live', 'aov'),
    ('Mobile navigation redesign',      'WIP',                True,  True,  130000, 'L',  'Improve mobile UX', 'New mobile navigation shipped', 'volume'),
    ('Restock notifications',           'Blocked',            True,  True,   90000, 'S',  'Return-to-stock alerts', 'Email/SMS when items restock', 'volume'),
    # -- Project Intake: Pending Approval (complete, unapproved) --
    ('Loyalty points program',          'Incomplete Entry',   False, False,      0, '',   'Reward repeat buyers', 'Points earned and redeemable at checkout', 'aov'),
    ('PDP reviews & ratings',           'Incomplete Entry',   False, False,      0, '',   'Add social proof', 'Reviews and star ratings on all PDPs', 'close'),
    # -- Project Intake: Pending Revenue (approved, awaiting Analyst) --
    ('SEO content hub',                 'Pending Revenue',    True,  False,      0, '',   'Grow organic traffic', 'Content hub with 30 buying-guide pages', 'volume'),
    # -- Project Intake: Pending LOE (revenue set, awaiting Developer sizing) --
    ('Wishlist & save-for-later',       'Pending LOE',        True,  False, 110000, '',   'Let shoppers save items', 'Wishlist on PDP and account', 'close'),
    # -- Project Intake: Incomplete (missing fields) --
    ('International shipping options',   'Incomplete Entry',   False, False,      0, '',   '', '', ''),
]

OBJ_KEYWORD = {'volume': 'shopper', 'close': 'close', 'aov': 'order value'}


class Command(BaseCommand):
    help = 'Seed demo Projects for the Demo Account / Google Merch Shop.'

    def handle(self, *args, **opts):
        rng = random.Random(4207)
        today = date.today()
        year = today.year

        demo = Company.objects.filter(name='Demo Account').first()
        if not demo:
            raise CommandError('Demo Account company not found (run seed_organizations first).')
        bu = demo.verticals.filter(name__icontains='Merch Shop').first() or demo.verticals.first()
        if not bu:
            raise CommandError('Demo Account has no business unit to attach projects to.')

        Project.objects.filter(vertical=bu).delete()   # clean reseed (cascades child Actions)

        dept = Department.objects.first() or Department.objects.create(name='General')
        owners = list(User.objects.filter(username__in=['jim', 'amy', 'master', 'sherman@querybridge.com'])) \
            or list(User.objects.all()[:3])
        teams = list(Team.objects.all())
        measures = list(Measure.objects.all())
        objectives = {k: Objective.objects.filter(name__icontains=kw, year=year).first()
                      for k, kw in OBJ_KEYWORD.items()}

        created = 0
        for name, status, approved, scored, revenue, size, why, dod, okey in PROJECTS:
            cv, bv, cs, oc, br, loe = (
                (rng.randint(4, 10), rng.randint(4, 10), rng.randint(1, 8),
                 rng.randint(1, 8), rng.randint(1, 7), rng.randint(2, 9)) if scored
                else (0, 0, 0, 0, 0, 0))
            go_live = date(year, rng.randint(1, min(today.month, 9)), rng.randint(1, 28)) if status == 'WIP' else None

            p = Project(
                name=name[:75], why=why, definition_of_done=dod[:350],
                objective=objectives.get(okey), owner=rng.choice(owners),
                vertical=bu, department=dept, value=revenue, effort_size=size,
                status=status, approved=approved, target_completion=go_live,
                customer_value=cv, business_value=bv, cost_savings=cs,
                operational_cost=oc, business_risk=br, level_of_effort=loe,
                year=year,
            )
            p.save()   # derive_status honors the explicit status; score computed from criteria

            # Execution tasks (Actions). WIP projects get a short dependency chain
            # (Design -> Build -> QA & launch) so the gantt shows start guardrails;
            # other projects get a single task.
            def _mk_action(nm, launch_d, prog, dep=None):
                act = Action(
                    project=p, owner=p.owner, business_unit=dept, vertical=bu,
                    name=nm[:350], why=why, impact=dod, objective=p.objective,
                    launch=launch_d, progress=prog,
                    team=(rng.choice(teams) if teams else None),
                    measure=(rng.choice(measures) if measures else None))
                act.save()
                if dep is not None:
                    act.depends_on.add(dep)
                cdt = date(year, 1, 1) + timedelta(days=rng.randint(0, 45))
                flds = {'date_created': cdt}
                if status == 'WIP' and launch_d:
                    span_end = min(launch_d, today)
                    flds['active_date'] = cdt + timedelta(days=rng.randint(0, max(0, (span_end - cdt).days)))
                Action.objects.filter(pk=act.pk).update(**flds)
                return act

            base = name[:28]
            if status == 'WIP' and go_live:
                d = _mk_action(f'{base} — Design & specs', go_live - timedelta(days=60), 100)
                b = _mk_action(f'{base} — Build', go_live - timedelta(days=25), rng.choice([45, 60, 75]), dep=d)
                _mk_action(f'{base} — QA & launch', go_live, rng.choice([0, 15, 30]), dep=b)
            else:
                _mk_action(f'{name[:40]} — build', go_live, 0)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'seed_demo_projects: {created} projects created on {demo.name} / {bu.name}.'))
