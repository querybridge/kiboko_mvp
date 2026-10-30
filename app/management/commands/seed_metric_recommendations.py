"""Seed the starter set of CRO / UX recommendations (4 per lead metric per direction).
Idempotent: (metric, direction, text) is the natural key. Goal: trigger ideas for
teams less familiar with ecommerce conversion-rate optimization."""
from django.core.management.base import BaseCommand
from app.models import MetricRecommendation

# {metric: {'loss': [...mitigate...], 'win': [...amplify...]}}
RECS = {
    'visitors': {
        'loss': ['Invest in top-of-funnel awareness (social, content)',
                 'Launch a referral incentive to attract new shoppers',
                 'Run influencer/partner campaigns to reach new audiences',
                 'Improve the first-visit landing experience'],
        'win': ['Scale the awareness channels fueling new visitors',
                'Add email/SMS capture to convert new visitors later',
                'Offer a first-purchase incentive for new shoppers',
                'Build lookalike audiences from recent new visitors'],
    },
    'visits_per_visitor': {
        'loss': ['Send browse- and cart-abandonment reminders to bring shoppers back',
                 'Add wishlist and save-for-later so shoppers have a reason to return',
                 'Retarget recent visitors with the products they viewed',
                 'Grow email/SMS capture so you can invite shoppers back'],
        'win': ['Expand the return-visit triggers (reminders, back-in-stock alerts) that work',
                'Add a loyalty or rewards hook to keep repeat visits coming',
                'Personalize the homepage for returning shoppers',
                'Send new-arrival and restock emails to frequent visitors'],
    },
    'cart_creation': {
        'loss': ['Make the Add-to-Cart button more prominent and sticky',
                 'Show clear pricing, stock and shipping on the product page',
                 'Add product reviews and richer imagery/video',
                 'Speed up PDP load and simplify variant selection'],
        'win': ['Apply the winning product-page layout to more products',
                'Add "recently viewed" and recommendations to lift more carts',
                'Test scarcity/urgency cues on high-interest products',
                'Feature the high-add-to-cart products more prominently'],
    },
    'cart_completion': {
        'loss': ['Simplify the checkout process (fewer steps and fields)',
                 'Add express/one-click and alternative payment methods',
                 'Show total cost (incl. shipping and tax) early',
                 'Trigger a cart-abandonment email/SMS within the hour'],
        'win': ['Roll out the streamlined checkout to all flows',
                'Add an order-bump upsell at the high-completing checkout',
                'Offer saved payment/address for returning buyers',
                'Reassure with guarantees and easy returns to hold completion'],
    },
    'units_per_order': {
        'loss': ['Add quantity incentives (buy-more-save-more)',
                 'Recommend complementary items in the cart',
                 'Create multipack or bundle SKUs',
                 'Offer a free gift above a unit threshold'],
        'win': ['Expand the bundles/multipacks lifting units',
                'Promote "complete the set" cross-sells',
                'Test volume discounts to push units higher',
                'Feature bundles in email and on the homepage'],
    },
    'avg_unit_price': {
        'loss': ['Feature premium and higher-margin products',
                 'Reduce reliance on deep discounting and clearance',
                 'Improve merchandising of premium tiers',
                 'Add good-better-best options so shoppers trade up'],
        'win': ['Promote the premium lines lifting unit price',
                'Test modest price increases on strong sellers',
                'Add premium add-ons and warranties',
                'Reduce discount depth while demand supports it'],
    },
}


class Command(BaseCommand):
    help = 'Seed starter CRO/UX recommendations for each metric (win/loss).'

    def handle(self, *args, **opts):
        created = 0
        for metric, by_dir in RECS.items():
            for direction, texts in by_dir.items():
                for i, text in enumerate(texts):
                    _, made = MetricRecommendation.objects.get_or_create(
                        metric=metric, direction=direction, text=text,
                        defaults={'order': i})
                    created += int(made)
        self.stdout.write(self.style.SUCCESS(
            f'seed_metric_recommendations: {created} created, '
            f'{MetricRecommendation.objects.count()} total.'))
