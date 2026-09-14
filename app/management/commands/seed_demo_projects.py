"""Seed demo Actions for the Demo Account's "GA4 - Google Merch Shop" business
unit so every Project Control view shows activity:

  * Executive Kanban (approved=True): Ready to Score, Scored, Executive Approval,
    On Deck, WIP, Blocked -- with scores/values/launch dates.
  * Approve Projects (approved=False): a few complete projects Pending Approval,
    and a couple of Incomplete Entries missing required fields.

Clean reseed: wipes existing Actions on that business unit, then recreates.
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from business_unit.models import Company, Department, Team
from strategy.models import Project, Objective, Measure
from project.models import Action

# (name, status, approved, scored, value, progress, why, dod, okey)
# okey: volume=Shopper Volume, close=Close Rate, aov=Average Order Value, ''=none
ACTIONS = [
    # -- Executive Kanban (approved) --
    ('Search autocomplete & synonyms',  'Ready to Score',     True,  False, 120000,  0, 'Faster product discovery', 'Search returns relevant results with synonyms', 'volume'),
    ('Size guide & fit finder',         'Ready to Score',     True,  False,  90000,  0, 'Reduce sizing uncertainty', 'Fit finder live on all apparel PDPs', 'close'),
    ('Product page video & 360 views',  'Scored',             True,  True,  140000,  0, 'Richer PDP media', 'Video + 360 on the top 100 PDPs', 'volume'),
    ('Cart abandonment email flow',     'Scored',             True,  True,  200000,  0, 'Recover abandoned carts', '3-email abandonment series live', 'close'),
    ('Express pay (Google/Apple Pay)',  'Executive Approval', True,  True,  260000,  0, 'One-tap wallet payment', 'Wallet pay available at checkout', 'close'),
    ('Apparel + accessories bundles',   'Executive Approval', True,  True,  160000,  0, 'Raise units per order', 'Bundles configured on 20 SKUs', 'aov'),
    ('Post-purchase upsell offers',     'On Deck',            True,  True,  180000,  0, 'Grow order value', 'Upsell shown on order confirmation', 'aov'),
    ('Homepage bestsellers carousel',   'On Deck',            True,  True,  150000,  0, 'Lift engagement', 'Bestsellers carousel on the homepage', 'volume'),
    ('Streamline guest checkout',       'WIP',                True,  True,  320000, 65, 'Cut checkout drop-off', 'One-page guest checkout', 'close'),
    ('Free shipping threshold at $50',  'WIP',                True,  True,  210000, 40, 'Encourage bigger baskets', 'Free shipping at $50 live', 'aov'),
    ('Mobile navigation redesign',      'WIP',                True,  True,  130000, 80, 'Improve mobile UX', 'New mobile navigation shipped', 'volume'),
    ('Restock notifications',           'Blocked',            True,  True,   90000, 20, 'Return-to-stock alerts', 'Email/SMS when items restock', 'volume'),
    # -- Approve Projects: Pending Approval (complete, unapproved) --
    ('Loyalty points program',          'Incomplete Entry',   False, False, 220000,  0, 'Reward repeat buyers', 'Points earned and redeemable at checkout', 'aov'),
    ('PDP reviews & ratings',           'Incomplete Entry',   False, False, 160000,  0, 'Add social proof', 'Reviews and star ratings on all PDPs', 'close'),
    ('SEO content hub',                 'Incomplete Entry',   False, False, 140000,  0, 'Grow organic traffic', 'Content hub with 30 buying-guide pages', 'volume'),
    # -- Approve Projects: Incomplete Entries (missing fields) --
    ('Wishlist & save-for-later',       'Incomplete Entry',   False, False,      0,  0, 'Let shoppers save items', '', 'close'),
    ('International shipping options',   'Incomplete Entry',   False, False,      0,  0, '', '', ''),
]

OBJ_KEYWORD = {'volume': 'shopper', 'close': 'close', 'aov': 'order value'}
OBJ_AEE = {'volume': 'attract_traffic', 'close': 'engage_customers', 'aov': 'expand_purchase'}


class Command(BaseCommand):
    help = 'Seed demo projects (Actions) for the Demo Account / Google Merch Shop.'

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

        Action.objects.filter(vertical=bu).delete()   # clean reseed

        project, _ = Project.objects.get_or_create(
            name='Demo — Google Merch Shop',
            defaults={'why': 'Demo initiatives for the Google Merch Shop.', 'year': year})
        dept = Department.objects.first() or Department.objects.create(name='General')
        owners = list(User.objects.filter(username__in=['jim', 'amy', 'master', 'sherman@querybridge.com'])) \
            or list(User.objects.all()[:3])
        teams = list(Team.objects.all())
        measures = list(Measure.objects.all())
        objectives = {k: Objective.objects.filter(name__icontains=kw, year=year).first()
                      for k, kw in OBJ_KEYWORD.items()}

        created = 0
        for name, status, approved, scored, value, progress, why, dod, okey in ACTIONS:
            cv, bv, cs, oc, br, loe = (
                (rng.randint(4, 10), rng.randint(4, 10), rng.randint(1, 8),
                 rng.randint(1, 8), rng.randint(1, 7), rng.randint(2, 9)) if scored
                else (0, 0, 0, 0, 0, 0))
            launch = date(year, rng.randint(1, min(today.month, 9)), rng.randint(1, 28)) if status == 'WIP' else None

            a = Action(
                project=project, owner=rng.choice(owners), business_unit=dept, vertical=bu,
                name=name, why=why, impact=dod,
                value=value, progress=progress, launch=launch, status=status,
                approved=approved, team=(rng.choice(teams) if teams else None),
                measure=(rng.choice(measures) if measures else None),
                objective=objectives.get(okey), aee_alignment=OBJ_AEE.get(okey, ''),
                impact_visits_value=(value if okey == 'volume' else 0),
                impact_close_rate_value=(value if okey == 'close' else 0),
                impact_aov_value=(value if okey == 'aov' else 0),
                customer_value=cv, business_value=bv, cost_savings=cs,
                operational_cost=oc, business_risk=br, level_of_effort=loe,
            )
            a.save()   # derive_status honors explicit Kanban columns; unapproved -> Incomplete Entry

            created_dt = date(year, 1, 1) + timedelta(days=rng.randint(0, 90))
            fields = {'date_created': created_dt}
            if status == 'WIP':
                span_end = min(launch or today, today)
                fields['active_date'] = created_dt + timedelta(days=rng.randint(0, max(0, (span_end - created_dt).days)))
            Action.objects.filter(pk=a.pk).update(**fields)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'seed_demo_projects: {created} created on {demo.name} / {bu.name}.'))
