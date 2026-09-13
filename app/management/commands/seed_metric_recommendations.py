"""Seed the starter set of CRO / UX recommendations (4 per metric per direction).
Idempotent: (metric, direction, text) is the natural key. Goal: trigger ideas for
teams less familiar with ecommerce conversion-rate optimization."""
from django.core.management.base import BaseCommand
from app.models import MetricRecommendation

# {metric: {'loss': [...mitigate...], 'win': [...amplify...]}}
RECS = {
    'sales': {
        'loss': ['Run a win-back email/SMS campaign to lapsed buyers',
                 'Add urgency with limited-time offers or low-stock badges',
                 'Feature bestsellers and bundles on the homepage',
                 'Review shipping thresholds and pricing that may deter purchases'],
        'win': ['Scale spend on the channels driving the lift',
                'Restock and expand the winning product lines',
                'Launch a loyalty or referral program to capture momentum',
                'Test upsells to raise order value while demand is high'],
    },
    'visits': {
        'loss': ['Audit paid campaign budgets and keywords for drops',
                 'Refresh SEO content and fix indexing/technical issues',
                 'Re-engage your email/SMS list with fresh content',
                 'Check site speed and uptime for friction lowering traffic'],
        'win': ['Increase budget on the best-performing acquisition channels',
                'Create more content/landing pages around winning topics',
                'Retarget new visitors to bring them back',
                'Expand into adjacent keywords and audiences that are working'],
    },
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
    'orders': {
        'loss': ['Simplify and speed up the checkout flow',
                 'Add trust signals: reviews, guarantees, secure-checkout badges',
                 'Offer a free-shipping threshold or first-order discount',
                 'Recover abandoned carts with email/SMS reminders'],
        'win': ['Scale the campaigns and products driving orders',
                'Add post-purchase upsells and subscription options',
                'Shore up inventory so winners don\'t stock out',
                'Add reviews and social proof to sustain conversion'],
    },
    'close_rate': {
        'loss': ['Reduce checkout steps and form fields',
                 'Add guest checkout and express pay (Apple/Google Pay)',
                 'Clarify pricing, shipping and returns earlier',
                 'A/B test product-page CTAs and trust badges'],
        'win': ['Roll out the winning page/flow patterns site-wide',
                'Test higher-value offers while conversion is strong',
                'Reinforce winning pages with reviews and UGC',
                'Remove any remaining checkout friction to push higher'],
    },
    'aov': {
        'loss': ['Add cross-sells and "frequently bought together" on PDP/cart',
                 'Introduce tiered free-shipping or spend-and-save thresholds',
                 'Bundle complementary products at a slight discount',
                 'Surface premium/higher-margin options in recommendations'],
        'win': ['Expand the bundles and cross-sell placements that are working',
                'Raise the free-shipping threshold to nudge basket size',
                'Promote premium tiers and add-ons at checkout',
                'Launch a volume or loyalty incentive to grow baskets'],
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
