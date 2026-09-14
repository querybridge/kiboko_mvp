"""Seed demo Actions for the Demo Account's "GA4 - Google Merch Shop" business
unit so every Project Control view (Kanban, WIP, Backlog, Active Projects gantt,
Value Pipeline objective tiles) shows activity. Idempotent: skips an Action that
already exists with the same name on that business unit.
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from business_unit.models import Company, BusinessUnit, Department, Team
from strategy.models import Project, Objective, Measure
from project.models import Action

# (name, status, scored, value, progress, why, objective_key)
# objective_key: volume=Shopper Volume, close=Close Rate, aov=Average Order Value
ACTIONS = [
    ('Streamline guest checkout',        'WIP',            True, 320000, 65, 'One-page guest checkout to cut drop-off', 'close'),
    ('Free shipping threshold at $50',   'WIP',            True, 210000, 40, 'Encourage larger baskets with a free-shipping tier', 'aov'),
    ('Homepage bestsellers carousel',    'WIP',            True, 150000, 80, 'Surface top products to lift engagement', 'volume'),
    ('Express pay (Google/Apple Pay)',   'On Deck',        True, 260000,  0, 'Add one-tap wallet payments at checkout', 'close'),
    ('Post-purchase upsell offers',      'On Deck',        True, 180000,  0, 'Order-confirmation cross-sells to grow AOV', 'aov'),
    ('Product page video & 360 views',   'Scored',         True, 140000,  0, 'Richer PDP media to boost add-to-cart', 'volume'),
    ('Cart abandonment email flow',      'Scored',         True, 200000,  0, 'Automated reminders to recover carts', 'close'),
    ('Apparel + accessories bundles',    'Ready to Score', False,     0,  0, 'Discounted bundles to raise units per order', 'aov'),
    ('Search autocomplete & synonyms',   'Ready to Score', False,     0,  0, 'Faster product discovery in site search', 'volume'),
    ('Size guide & fit finder',          'Ready to Score', False,     0,  0, 'Reduce sizing uncertainty on the product page', 'close'),
    ('Loyalty points program',           'Incomplete Entry', False,   0,  0, '', 'aov'),
    ('Mobile navigation redesign',       'Incomplete Entry', False,   0,  0, '', 'volume'),
    ('Restock notifications',            'Blocked',        True,  90000, 20, 'Email/SMS when out-of-stock items return', 'volume'),
    ('Q2 promo pricing engine',          'Launched',       True, 500000, 100, 'Dynamic promo pricing shipped last quarter', 'aov'),
    ('PDP reviews & ratings',            'Complete',       True, 160000, 100, 'Customer reviews on product pages', 'close'),
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
        for i, (name, status, scored, value, progress, why, okey) in enumerate(ACTIONS):
            if Action.objects.filter(name=name, vertical=bu).exists():
                continue
            cv, bv, cs, oc, br, loe = (
                (rng.randint(4, 10), rng.randint(4, 10), rng.randint(1, 8),
                 rng.randint(1, 8), rng.randint(1, 7), rng.randint(2, 9)) if scored
                else (0, 0, 0, 0, 0, 0))

            launch = None
            if status in ('WIP', 'Launched', 'Complete'):
                launch = date(year, rng.randint(1, min(today.month, 9)), rng.randint(1, 28))

            a = Action(
                project=project, owner=rng.choice(owners), business_unit=dept, vertical=bu,
                name=name, why=why, impact=(why[:75] if why else ''),
                value=value, progress=progress, launch=launch, status=status,
                approved=status in ('WIP', 'On Deck', 'Complete', 'Launched'),
                archived=(status == 'Launched'),
                team=(rng.choice(teams) if teams else None),
                measure=(rng.choice(measures) if measures else None),
                objective=objectives.get(okey), aee_alignment=OBJ_AEE.get(okey, ''),
                # Attribute the card's value to its lever so the Kanban summary
                # tiles show the per-lever impact breakdown, not just the total.
                impact_visits_value=(value if okey == 'volume' else 0),
                impact_close_rate_value=(value if okey == 'close' else 0),
                impact_aov_value=(value if okey == 'aov' else 0),
                customer_value=cv, business_value=bv, cost_savings=cs,
                operational_cost=oc, business_risk=br, level_of_effort=loe,
            )
            a.save()  # derive_status honors the explicit column status

            # Backdate created; give WIP an active_date so the gantt draws a bar.
            created_dt = date(year, 1, 1) + timedelta(days=rng.randint(0, 90))
            fields = {'date_created': created_dt}
            if status == 'WIP':
                span_end = min(launch or today, today)
                fields['active_date'] = created_dt + timedelta(
                    days=rng.randint(0, max(0, (span_end - created_dt).days)))
            Action.objects.filter(pk=a.pk).update(**fields)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'seed_demo_projects: {created} created on {demo.name} / {bu.name} '
            f'({Action.objects.filter(vertical=bu).count()} total).'))
