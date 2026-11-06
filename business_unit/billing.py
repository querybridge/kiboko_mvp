"""Stripe billing for an Organization.

The free trial is Kiboko's own (45 days, started by an emailed trial code, no card).
Adding payment opens Stripe Checkout in subscription mode; the subscription's own
trial is set to end on the org's trial end date, so nothing is charged until then.
The Stripe Customer Portal handles card changes and cancellation afterwards, and
the webhook keeps Organization.plan_status in step with Stripe.

Keys live in IntegrationSettings (Django admin). Prices live on each Plan
(stripe_price_id), so the admin sets them up in Stripe and pastes the ids in.
"""
import datetime
import logging
import random
import string

log = logging.getLogger(__name__)

# Stripe subscription status -> Organization.plan_status
_STATUS = {
    'trialing': 'active', 'active': 'active',
    'past_due': 'past_due', 'unpaid': 'past_due', 'incomplete_expired': 'past_due',
    'paused': 'past_due', 'canceled': 'past_due',
}


def client():
    """A StripeClient, or None when the secret key isn't set."""
    from business_unit.models import IntegrationSettings
    key = IntegrationSettings.current().stripe_secret_key
    if not key:
        return None
    import stripe
    return stripe.StripeClient(key)


def is_configured():
    return client() is not None


def line_items(org):
    """Checkout line items for the org's plan (+ the Premium Connection add-on on
    Standard). Returns [] when a needed Stripe price id is missing."""
    from business_unit.models import Plan
    plan = org.plan
    if plan is None or not plan.stripe_price_id:
        return []
    items = [{'price': plan.stripe_price_id, 'quantity': 1}]
    if org.premium_connection and plan.tier == 'standard':
        addon = Plan.objects.filter(active=True, is_addon=True).order_by('sort_order').first()
        if addon is None or not addon.stripe_price_id:
            return []
        items.append({'price': addon.stripe_price_id, 'quantity': 1})
    return items


def premium_addon():
    """The Premium Connection add-on Plan (price shown on Billing), or None."""
    from business_unit.models import Plan
    return Plan.objects.filter(active=True, is_addon=True).order_by('sort_order').first()


def add_premium(org):
    """Turn on the Premium Connection add-on for `org`. Returns (ok, message).

    Without a subscription yet (free trial), it's switched on now and billed with
    the plan once payment is added (line_items includes it). With a subscription,
    the add-on is added to it in Stripe first, prorated for the current period;
    if Stripe refuses, nothing changes."""
    if org.has_premium:
        return True, 'Premium Connection is already on.'
    if org.is_canceled:
        return False, 'Reactivate the account before adding Premium Connection.'
    addon = premium_addon()
    if org.stripe_subscription_id:
        sc = client()
        if sc is None or addon is None or not addon.stripe_price_id:
            log.error('Premium add-on for org %s: Stripe or the add-on price id is not set up', org.id)
            return False, 'Premium Connection can’t be added online right now. Please try again later.'
        try:
            sc.v1.subscription_items.create(params={
                'subscription': org.stripe_subscription_id, 'price': addon.stripe_price_id,
                'quantity': 1, 'proration_behavior': 'create_prorations'})
        except Exception:
            log.exception('Stripe could not add the Premium add-on to subscription %s (org %s)',
                          org.stripe_subscription_id, org.id)
            return False, 'Our payment provider didn’t accept the change. Nothing was charged; please try again.'
        msg = 'Premium Connection is on and added to your subscription (prorated for this billing period).'
    else:
        msg = ('Premium Connection is on. It’s included in your free trial and billed with your plan '
               'once you add a payment method.')
    org.premium_connection = True
    org.save(update_fields=['premium_connection'])
    return True, msg


def premium_removable(org):
    """True when Premium came from the add-on (not a Premium/Enterprise plan or a
    comped account, which include it)."""
    if not org.premium_connection or org.is_platform_demo or org.billing_exempt:
        return False
    return not (org.plan and org.plan.tier in ('premium', 'enterprise'))


def remove_premium(org):
    """Turn off the Premium Connection add-on. Returns (ok, message).

    With a subscription, the add-on line is removed in Stripe first (prorated);
    if Stripe refuses, nothing changes. Then every company in the org loses its
    BigQuery connection: the stored service-account key and the daily summary
    table are deleted, and dashboards fall back to the Standard (GA4 API) data."""
    from business_unit.models import BigQueryConnection, GA4DailyRollup
    if not premium_removable(org):
        return False, 'Premium Connection is included in your plan, so there’s nothing to remove.'
    if org.stripe_subscription_id:
        sc = client()
        addon = premium_addon()
        if sc is None or addon is None or not addon.stripe_price_id:
            log.error('Remove Premium for org %s: Stripe or the add-on price id is not set up', org.id)
            return False, 'Premium Connection can’t be removed online right now. Please try again later.'
        try:
            items = sc.v1.subscription_items.list(params={'subscription': org.stripe_subscription_id})
            for item in items.data:
                if item.price.id == addon.stripe_price_id:
                    sc.v1.subscription_items.delete(item.id, params={'proration_behavior': 'create_prorations'})
        except Exception:
            log.exception('Stripe could not remove the Premium add-on from subscription %s (org %s)',
                          org.stripe_subscription_id, org.id)
            return False, 'Our payment provider didn’t accept the change. Premium is still on; please try again.'
    companies = org.companies.all()
    GA4DailyRollup.objects.filter(company__in=companies).delete()
    BigQueryConnection.objects.filter(company__in=companies).delete()
    org.premium_connection = False
    org.save(update_fields=['premium_connection'])
    return True, ('Premium Connection is removed. Kiboko deleted the BigQuery service-account key and the daily '
                  'summary table, and your dashboards now use the Standard Google Analytics connection.')


def _address(org):
    return {'line1': org.billing_address1, 'line2': org.billing_address2 or None,
            'city': org.billing_city, 'state': org.billing_state,
            'postal_code': org.billing_postal, 'country': _country_code(org.billing_country)}


def _country_code(value):
    """Stripe wants a 2-letter country code; accept common names too."""
    v = (value or '').strip()
    names = {'united states': 'US', 'usa': 'US', 'united states of america': 'US',
             'canada': 'CA', 'united kingdom': 'GB', 'uk': 'GB', 'mexico': 'MX'}
    if len(v) == 2:
        return v.upper()
    return names.get(v.lower())


def ensure_customer(sc, org):
    """The org's Stripe Customer id, creating it (with the billing address) if needed."""
    params = {'name': org.billing_legal_name or org.name,
              'email': org.billing_email or (org.org_admin.email if org.org_admin else None)}
    if org.has_billing_address():
        params['address'] = _address(org)
    if org.stripe_customer_id:
        sc.v1.customers.update(org.stripe_customer_id, params=params)
        return org.stripe_customer_id
    cust = sc.v1.customers.create(params={**params, 'metadata': {'kiboko_org_id': str(org.id)}})
    org.stripe_customer_id = cust.id
    org.save(update_fields=['stripe_customer_id'])
    return cust.id


def sync_customer(org):
    """Push the billing address to Stripe after it's edited (no-op until the org
    has a Stripe customer)."""
    sc = client()
    if sc is None or not org.stripe_customer_id:
        return
    try:
        ensure_customer(sc, org)
    except Exception:
        log.exception('Stripe customer sync failed for org %s', org.id)


def checkout_url(org, success_url, cancel_url):
    """Create a subscription Checkout Session and return its URL."""
    sc = client()
    items = line_items(org)
    customer = ensure_customer(sc, org)
    sub = {'metadata': {'kiboko_org_id': str(org.id)}}
    # Carry the remaining free trial into Stripe so the first charge lands when the
    # Kiboko trial ends. Stripe needs trial_end at least 48 hours out.
    end = org.trial_end_date
    if end and org.plan_status == 'trial':
        end_ts = int(datetime.datetime.combine(end, datetime.time(12, 0),
                                               tzinfo=datetime.timezone.utc).timestamp())
        if end_ts > datetime.datetime.now(datetime.timezone.utc).timestamp() + 49 * 3600:
            sub['trial_end'] = end_ts
    suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
    session = sc.v1.checkout.sessions.create(params={
        'mode': 'subscription',
        'customer': customer,
        'client_reference_id': str(org.id),
        'line_items': items,
        'subscription_data': sub,
        'billing_address_collection': 'auto',
        'customer_update': {'address': 'auto', 'name': 'auto'},
        'success_url': success_url + '?checkout=success&session_id={CHECKOUT_SESSION_ID}',
        'cancel_url': cancel_url + '?checkout=canceled',
        'integration_identifier': f'kiboko_billing_{suffix}',
    })
    return session.url


def portal_url(org, return_url):
    """Stripe Customer Portal link for updating the card or canceling."""
    sc = client()
    return sc.v1.billing_portal.sessions.create(params={
        'customer': org.stripe_customer_id, 'return_url': return_url}).url


def set_cancel_at_period_end(org, cancel):
    """Stop (cancel=True) or resume (False) renewal of the org's Stripe
    subscription. Cancelling keeps it paid up to the end of the current period;
    Stripe then deletes it and the webhook clears stripe_subscription_id, which
    locks the account. Returns True if Stripe accepted the change (or there is
    no subscription to change)."""
    if not org.stripe_subscription_id:
        return True
    sc = client()
    if sc is None:
        log.error('Stripe not configured; could not %s subscription %s for org %s',
                  'cancel' if cancel else 'resume', org.stripe_subscription_id, org.id)
        return False
    try:
        sc.v1.subscriptions.update(org.stripe_subscription_id, params={'cancel_at_period_end': bool(cancel)})
        return True
    except Exception:
        log.exception('Stripe could not update subscription %s for org %s', org.stripe_subscription_id, org.id)
        return False


def confirm_checkout(org, session_id):
    """On return from Checkout, record the subscription right away (the webhook
    does the same; this just avoids a lag before the page reflects it)."""
    sc = client()
    if sc is None or not session_id:
        return False
    try:
        session = sc.v1.checkout.sessions.retrieve(session_id)
    except Exception:
        log.exception('Could not retrieve Checkout Session %s', session_id)
        return False
    if session.customer != org.stripe_customer_id or session.status != 'complete':
        return False
    _activate(org, session.subscription)
    return True


def _activate(org, subscription_id):
    from business_unit.models import Organization
    org.stripe_subscription_id = subscription_id or org.stripe_subscription_id
    org.plan_status = 'active'
    org.save(update_fields=['stripe_subscription_id', 'plan_status'])
    return org


def _org_for_customer(customer_id):
    from business_unit.models import Organization
    if not customer_id:
        return None
    return Organization.objects.filter(stripe_customer_id=customer_id).first()


def handle_event(event):
    """Apply one verified webhook event. Events are resolved to an org through the
    Stripe Customer id stored on the Organization."""
    obj = event.data.object
    kind = event.type
    org = _org_for_customer(getattr(obj, 'customer', None))
    if org is None:
        log.info('Stripe %s for unknown customer %s', kind, getattr(obj, 'customer', None))
        return

    if kind in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
        # Subscription Checkout with a trial has payment_status 'no_payment_required'.
        if obj.mode == 'subscription' and obj.status == 'complete':
            _activate(org, obj.subscription)
    elif kind in ('customer.subscription.created', 'customer.subscription.updated',
                  'customer.subscription.deleted'):
        status = 'canceled' if kind.endswith('deleted') else obj.status
        new = _STATUS.get(status)
        if new:
            org.stripe_subscription_id = '' if status == 'canceled' else obj.id
            if org.plan_status != 'canceled':        # a Kiboko-side cancel stays canceled
                org.plan_status = new
            org.save(update_fields=['stripe_subscription_id', 'plan_status'])
    elif kind == 'invoice.paid':
        if org.plan_status == 'past_due':
            org.plan_status = 'active'
            org.save(update_fields=['plan_status'])
    elif kind == 'invoice.payment_failed':
        org.plan_status = 'past_due'
        org.save(update_fields=['plan_status'])
    elif kind in ('charge.dispute.created', 'charge.refunded', 'radar.early_fraud_warning.created'):
        log.warning('Stripe %s for org %s (%s) — review in the Stripe Dashboard', kind, org.id, org.name)
