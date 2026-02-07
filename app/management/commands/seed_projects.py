"""
Seed dummy Quarterly Rocks and Projects for UX pressure testing.

Creates 6 Quarterly Rocks spread across annual rocks / departments,
then 20 Projects with varying statuses, scores (some zeroed out),
values, progress, launch dates, and verticals.
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from business_unit.models import BusinessUnit, Vertical
from project.models import Project
from strategy.models import Strategy, AnnualRock, Metric, KPI


QUARTERLY_ROCKS = [
    {'name': 'Redesign Product Detail Pages', 'quarter': 1, 'why': 'Improve conversion on high-traffic PDPs'},
    {'name': 'Launch Loyalty Program MVP', 'quarter': 1, 'why': 'Drive repeat purchase frequency'},
    {'name': 'Migrate to Headless CMS', 'quarter': 2, 'why': 'Improve site speed and developer velocity'},
    {'name': 'Expand B2B Portal Features', 'quarter': 2, 'why': 'Increase wholesale order volume'},
    {'name': 'Implement Personalization Engine', 'quarter': 3, 'why': 'Boost AOV through smart recommendations'},
    {'name': 'Holiday Campaign Automation', 'quarter': 3, 'why': 'Scale holiday marketing with less manual effort'},
]

PROJECTS = [
    # (name, status, has_scores, value, progress, why)
    ('PDP image zoom & 360 viewer', 'Active', True, 450000, 65, 'As a shopper I want to zoom and rotate product images so I can inspect details before buying'),
    ('Add size/finish filter to PLP', 'Active', True, 120000, 30, 'Enable shoppers to narrow results by product attributes'),
    ('Loyalty points dashboard', 'Active', True, 800000, 10, 'Show members their points balance, history, and redemption options'),
    ('Referral program integration', 'Active', False, 350000, 5, 'Allow members to refer friends and earn bonus points'),
    ('Headless CMS proof of concept', 'Pending Assignment', True, 0, 0, 'Validate headless architecture with a single landing page'),
    ('Content migration tooling', 'Pending Assignment', False, 0, 0, 'Build scripts to migrate legacy CMS content'),
    ('B2B bulk order CSV upload', 'Active', True, 600000, 45, 'Let wholesale customers upload large orders via CSV'),
    ('B2B net-30 payment terms', 'Active', True, 250000, 80, 'Offer invoice-based payment for approved B2B accounts'),
    ('Homepage personalization A/B test', 'Active', True, 500000, 20, 'Test personalized hero banners vs static content'),
    ('Recommendation engine data pipeline', 'Pending Approval', True, 300000, 0, 'Build ETL pipeline feeding the ML recommendation model'),
    ('Holiday email drip sequences', 'Pending Approval', True, 200000, 0, 'Pre-built automated email flows for Black Friday and holiday season'),
    ('Gift guide landing pages', 'Pending Approval', False, 150000, 0, 'Curated gift guide pages by price range and recipient'),
    ('Cart abandonment retargeting', 'Pending Approval', False, 0, 0, 'Retarget shoppers who abandon carts with personalized ads'),
    ('Site search autocomplete upgrade', 'Pending Approval', True, 275000, 0, 'Replace current search with AI-powered autocomplete'),
    ('Mobile checkout redesign', 'Pending Approval', False, 0, 0, 'Simplify mobile checkout to reduce drop-off'),
    ('Inventory sync real-time API', 'Complete', True, 180000, 100, 'Real-time inventory updates across all channels'),
    ('Returns portal self-service', 'Complete', True, 220000, 100, 'Allow customers to initiate returns without contacting support'),
    ('Launched Q4 promo engine', 'Launched', True, 900000, 100, 'Dynamic promo pricing engine for holiday campaigns'),
    ('Accessibility WCAG 2.1 audit', 'Pending Approval', True, 50000, 0, 'Audit and remediate accessibility issues site-wide'),
    ('Warehouse pick-pack optimization', 'Active', True, 400000, 55, 'Optimize warehouse pick routes to reduce fulfillment time'),
]


class Command(BaseCommand):
    help = 'Seed 6 Quarterly Rocks and 20 dummy Projects for UX testing.'

    def handle(self, *args, **options):
        rng = random.Random(42)

        users = list(User.objects.all())
        departments = list(BusinessUnit.objects.all())
        verticals = list(Vertical.objects.all())
        annual_rocks = list(AnnualRock.objects.filter(year=2026))
        metrics = list(Metric.objects.filter(active=True))
        kpis = list(KPI.objects.filter(active=True))

        if not users:
            self.stderr.write('No users found. Create at least one user first.')
            return
        if not departments:
            self.stderr.write('No departments found. Create at least one department first.')
            return

        # ---- Quarterly Rocks ----
        rocks_created = 0
        strategies = []
        for i, qr in enumerate(QUARTERLY_ROCKS):
            strat, created = Strategy.objects.get_or_create(
                name=qr['name'],
                defaults={
                    'why': qr['why'],
                    'quarter': qr['quarter'],
                    'year': 2026,
                    'annual_rock': annual_rocks[i % len(annual_rocks)] if annual_rocks else None,
                    'department': departments[i % len(departments)],
                },
            )
            strategies.append(strat)
            if created:
                rocks_created += 1
                self.stdout.write(f'  QR: {strat.name}')

        # Include any pre-existing strategies too
        all_strategies = list(Strategy.objects.all())
        self.stdout.write(self.style.SUCCESS(f'Created {rocks_created} Quarterly Rocks ({len(all_strategies)} total).'))

        # ---- Projects ----
        projects_created = 0
        for i, (name, status, has_scores, value, progress, why) in enumerate(PROJECTS):
            if Project.objects.filter(name=name).exists():
                self.stdout.write(f'  Skip (exists): {name}')
                continue

            owner = rng.choice(users)
            dept = rng.choice(departments)
            vert = rng.choice(verticals) if verticals else None
            rock = all_strategies[i % len(all_strategies)]
            ar = annual_rocks[i % len(annual_rocks)] if annual_rocks else None

            # Scores — some projects get full scores, some get zeros
            if has_scores:
                cv = rng.randint(3, 10)
                bv = rng.randint(3, 10)
                cs = rng.randint(1, 8)
                oc = rng.randint(1, 8)
                br = rng.randint(1, 7)
                loe = rng.randint(2, 9)
            else:
                cv = bv = cs = oc = br = loe = 0

            launch = None
            if status in ('Active', 'Launched', 'Complete'):
                launch = date(2026, rng.randint(1, 6), rng.randint(1, 28))
            elif status == 'Pending Assignment':
                launch = date(2026, rng.randint(4, 8), rng.randint(1, 28))

            approved = status in ('Active', 'Complete', 'Launched', 'Pending Assignment')

            p = Project(
                strategy=rock,
                owner=owner,
                name=name,
                why=why,
                impact=why[:75] if why else '',
                value=value,
                progress=progress,
                launch=launch,
                status=status,
                approved=approved,
                archived=(status == 'Launched'),
                business_unit=dept,
                vertical=vert,
                annual_rock=ar,
                metric=rng.choice(metrics) if metrics else None,
                kpi=rng.choice(kpis) if kpis else None,
                customer_value=cv,
                business_value=bv,
                cost_savings=cs,
                operational_cost=oc,
                business_risk=br,
                level_of_effort=loe,
            )
            p.save()
            projects_created += 1
            score_label = f'score={p.normalized_score}' if has_scores else 'NO SCORES'
            self.stdout.write(f'  [{status:20s}] {name} ({score_label}, ${value:,})')

        self.stdout.write(self.style.SUCCESS(f'Created {projects_created} Projects.'))
