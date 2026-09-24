"""Seed extra Belami projects sitting at Scored / Executive Approval so the
Executive Approval greenlight queue has plenty to test.

Each project is approved, has the estimator inputs (lever + baseline/target +
sales baseline) so it carries a projected value, and has the five voted criteria
filled so recompute_scores() gives it a real normalized score. Idempotent:
projects are matched by name, and recompute is re-run each time.

    python manage.py seed_exec_approval_demo [--count 10]
"""
import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand


# lever + (current, target) per AEE element so the estimate is sensible.
LEVER_SPEC = {
    'attract_traffic':  ('visitors', 3000, 3300),
    'engage_customers': ('cart_completion', 0.30, 0.345),
    'expand_purchase':  ('avg_unit_price', 460, 505),
}
AEE_OBJECTIVES = {
    'attract_traffic': 'Increase Shopper Volume',
    'engage_customers': 'Increase Close Rate',
    'expand_purchase': 'Increase Average Order Value',
}

# (name, business unit, AEE, status, evidence-backed)
SPEC = [
    ('Site-wide search relevance tuning', 'Lighting', 'attract_traffic', 'Scored', False),
    ('Paid-social prospecting for patio', 'Patio', 'attract_traffic', 'Executive Approval', False),
    ('Guided fixture comparison tool', 'Lighting', 'engage_customers', 'Scored', True),
    ('Express guest checkout', 'Bailey Street Home', 'engage_customers', 'Executive Approval', False),
    ('PDP financing badge (Affirm)', 'Lighting', 'expand_purchase', 'Scored', False),
    ('Volume discount on bulk bulb orders', 'Lighting', 'expand_purchase', 'Executive Approval', False),
    ('Heating install-service attach at cart', 'Heating', 'expand_purchase', 'Scored', True),
    ('Category quiz for first-time visitors', 'Patio', 'attract_traffic', 'Executive Approval', False),
    ('Post-purchase review incentive', 'Bailey Street Home', 'engage_customers', 'Scored', False),
    ('Warranty upsell on checkout', 'Heating', 'expand_purchase', 'Executive Approval', True),
    ('Editorial buying-guide hub', 'Lighting', 'attract_traffic', 'Scored', False),
    ('Saved-cart reminder push', 'Patio', 'engage_customers', 'Executive Approval', False),
]


class Command(BaseCommand):
    help = 'Seed extra Belami projects at Scored / Executive Approval for testing the greenlight queue.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=len(SPEC),
                            help=f'How many to create (max {len(SPEC)}; default all).')

    def handle(self, *args, **opts):
        from django.contrib.auth.models import User
        from business_unit.models import Company, Department
        from strategy.models import Objective, Project
        from project.services import impact

        belami = Company.objects.filter(slug='belami').first() or Company.objects.filter(name='Belami').first()
        if belami is None:
            self.stderr.write(self.style.ERROR('Belami company not found — run seed_belami_demo first.'))
            return
        bus = {b.name: b for b in belami.verticals.all()}
        if not bus:
            self.stderr.write(self.style.ERROR('Belami has no business units — run seed_belami_demo first.'))
            return

        # AEE-aligned objectives (reuse/create).
        obj = {}
        for aee, oname in AEE_OBJECTIVES.items():
            o, _ = Objective.objects.get_or_create(
                name=oname, defaults={'aee_alignment': aee, 'year': date.today().year})
            if o.aee_alignment != aee:
                o.aee_alignment = aee
                o.save(update_fields=['aee_alignment'])
            obj[aee] = o

        depts = list(Department.objects.all())
        owners = list(User.objects.filter(is_superuser=True)) or list(User.objects.all()[:3])
        rng = random.Random(4242)
        today = date.today()

        created = 0
        for name, bu_name, aee, status, evidence in SPEC[:opts['count']]:
            if Project.objects.filter(name=name).exists():
                continue
            bu = bus.get(bu_name) or next(iter(bus.values()))
            lever, lo, hi = LEVER_SPEC[aee]
            s0 = self._bu_real_s0(bu, today) or 5_000_000
            p = Project(
                name=name, owner=(rng.choice(owners) if owners else None), vertical=bu,
                department=rng.choice(depts) if depts else None, objective=obj.get(aee),
                why=f'As a shopper, I want {name.lower()}, so that Belami {bu_name} grows.'[:400],
                definition_of_done='Shipped to all users; success metric tracked; no P1 defects.',
                status=status, approved=True, archived=False,
                target_completion=date(today.year, rng.randint(1, 12), rng.randint(1, 28)),
                year=today.year,
                effort_size=rng.choice(['S', 'M', 'L']), capability=rng.choice(['fully', 'mostly']),
                # Five voted criteria (nonzero so a normalized score computes) + LOE.
                customer_value=rng.randint(5, 10), business_value=rng.randint(5, 10),
                cost_savings=rng.randint(2, 8), operational_cost=rng.randint(2, 8),
                business_risk=rng.randint(1, 6), level_of_effort=rng.randint(2, 8),
                ramp_days=rng.choice([30, 45, 60]), direct_expense=rng.choice([0, 20000, 50000]),
                plausibility_factor=1.0,
                lever=lever, target_from=Decimal(str(lo)), target_to=Decimal(str(hi)),
                s0_annual=Decimal(str(s0)),
            )
            if evidence:
                p.evidence_backed = True
                p.evidence_kind = 'prior_level'
                p.evidence_prior_level = Decimal(str(hi))
                p.evidence_note = 'Restoring the level sustained before the recent site regression.'
            p.save()
            created += 1

        # Blend the final normalized scores across the company so the queue ranks.
        impact.recompute_scores(company=belami)
        n_scored = Project.objects.filter(
            vertical__company=belami, approved=True,
            status__in=('Scored', 'Executive Approval')).count()
        self.stdout.write(self.style.SUCCESS(
            f'seed_exec_approval_demo: {created} created; '
            f'{n_scored} Belami projects now at Scored / Executive Approval.'))

    def _bu_real_s0(self, bu, today):
        """Annualized actual revenue from the BU's DailyActuals (mirrors the estimator)."""
        from app.models import DailyActual
        recs = list(DailyActual.objects.filter(vertical=bu, date__lte=today)
                    .order_by('-date').values_list('revenue', flat=True)[:365])
        if not recs:
            return None
        return round(float(sum(recs)) / len(recs) * 365.0, 2)
