"""Seed the Kiboko subscription plans (products shown on Get Started / Billing).

Idempotent: re-running updates copy but preserves any price you changed in the
Django admin (prices are only set on first create). Usage:
    python manage.py seed_plans           # create/update, keep admin-edited prices
    python manage.py seed_plans --reset-prices   # also reset prices to defaults
"""
from django.core.management.base import BaseCommand


# tier -> defaults. Prices per the product positioning:
#   Standard  -> "How do I think about increasing ecommerce revenue?"
#   Premium   -> "Which projects should I work on to improve revenue?"
#   Enterprise-> "What's getting done -- and did what we do work?"
PLANS = [
    {
        'slug': 'standard', 'name': 'Kiboko Standard', 'tier': 'standard',
        'tagline': 'How do I think about increasing ecommerce revenue?',
        'price': '299.00', 'sort_order': 10, 'highlighted': False, 'is_addon': False,
        'features': (
            'Analytics: Grow Sales, Attract Traffic, Engage Customers, Expand Purchases\n'
            'Insights: wins, losses, and what to do about them\n'
            'GA4 data connection\n'
            'Optional add-on: Premium Connection (warehouse-grade BigQuery)'
        ),
    },
    {
        'slug': 'premium', 'name': 'Kiboko Premium', 'tier': 'premium',
        'tagline': 'Which projects should I work on to improve revenue?',
        'price': '599.00', 'sort_order': 20, 'highlighted': True, 'is_addon': False,
        'features': (
            'Everything in Standard\n'
            'Premium Connection included (BigQuery)\n'
            'Project Prioritization: impact estimator, business-value scoring, value pipeline\n'
            'Approvals workflow'
        ),
    },
    {
        'slug': 'enterprise', 'name': 'Kiboko Enterprise', 'tier': 'enterprise',
        'tagline': "What's getting done — and did what we do work?",
        'price': '899.00', 'sort_order': 30, 'highlighted': False, 'is_addon': False,
        'features': (
            'Everything in Premium\n'
            'Project Control: kanban, work in progress, backlog\n'
            'Project Review: realized performance & revenue attribution\n'
            'Priority support'
        ),
    },
    {
        'slug': 'premium-connection', 'name': 'Premium Connection', 'tier': 'addon',
        'tagline': 'Warehouse-grade data via BigQuery',
        'price': '150.00', 'sort_order': 40, 'highlighted': False, 'is_addon': True,
        'features': (
            'BigQuery service-account connection\n'
            'Faster, cached dashboards\n'
            'Add to Standard — included with Premium & Enterprise'
        ),
    },
]


class Command(BaseCommand):
    help = 'Create/update the Kiboko subscription plans (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--reset-prices', action='store_true',
                            help='Also reset prices to the seed defaults (overwrites admin edits).')

    def handle(self, *args, **opts):
        from business_unit.models import Plan
        from decimal import Decimal

        created = updated = 0
        for spec in PLANS:
            defaults = {
                'name': spec['name'], 'tier': spec['tier'], 'tagline': spec['tagline'],
                'features': spec['features'], 'is_addon': spec['is_addon'],
                'highlighted': spec['highlighted'], 'sort_order': spec['sort_order'],
                'active': True, 'interval': 'month',
            }
            obj, was_created = Plan.objects.get_or_create(
                slug=spec['slug'],
                defaults={**defaults, 'price': Decimal(spec['price'])})
            if was_created:
                created += 1
                continue
            # Update copy but keep admin-edited price unless --reset-prices.
            for k, v in defaults.items():
                setattr(obj, k, v)
            if opts['reset_prices']:
                obj.price = Decimal(spec['price'])
            obj.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Plans: {created} created, {updated} updated.'))
