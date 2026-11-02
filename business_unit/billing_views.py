"""Stripe endpoints behind the Billing page: start Checkout, open the Customer
Portal, and receive webhooks."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from business_unit import billing

log = logging.getLogger(__name__)


def _admin_org(request):
    return request.user.administered_orgs.first()


@login_required
@require_POST
def checkout(request):
    org = _admin_org(request)
    if org is None:
        return HttpResponseForbidden('Billing is available to organization admins only.')
    if not billing.is_configured():
        messages.error(request, 'Payments aren’t set up yet. Please contact Kiboko support.')
        return redirect('app:billing')
    if not billing.line_items(org):
        messages.error(request, 'Your plan isn’t available for online payment yet. Please contact Kiboko support.')
        return redirect('app:billing')
    back = request.build_absolute_uri(reverse('app:billing'))
    try:
        return redirect(billing.checkout_url(org, success_url=back, cancel_url=back))
    except Exception:
        log.exception('Stripe Checkout failed for org %s', org.id)
        messages.error(request, 'We couldn’t open the payment page. Please try again in a moment.')
        return redirect('app:billing')


@login_required
@require_POST
def portal(request):
    org = _admin_org(request)
    if org is None or not org.stripe_customer_id or not billing.is_configured():
        return redirect('app:billing')
    try:
        return redirect(billing.portal_url(org, request.build_absolute_uri(reverse('app:billing'))))
    except Exception:
        log.exception('Stripe portal failed for org %s', org.id)
        messages.error(request, 'We couldn’t open payment settings. Please try again in a moment.')
        return redirect('app:billing')


@csrf_exempt
@require_POST
def webhook(request):
    """Stripe -> Kiboko. Verifies the signature with the webhook secret."""
    from business_unit.models import IntegrationSettings
    s = IntegrationSettings.current()
    sc = billing.client()
    if sc is None or not s.stripe_webhook_secret:
        return HttpResponse(status=503)
    try:
        event = sc.construct_event(request.body, request.headers.get('Stripe-Signature'),
                                   s.stripe_webhook_secret)
    except Exception:
        return HttpResponse(status=400)
    try:
        billing.handle_event(event)
    except Exception:
        log.exception('Stripe webhook %s failed', getattr(event, 'type', '?'))
        return HttpResponse(status=500)          # Stripe retries
    return HttpResponse(status=200)
