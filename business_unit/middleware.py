"""Lock an organization out of the app once its free trial ends without payment
(or Stripe reports the payment past due). Org admins are sent to Billing to add
payment; everyone else sees a page asking them to contact their admin.
Superusers and comped (demo / sales / internal) orgs are never locked."""
from django.shortcuts import redirect, render
from django.urls import reverse

# Always reachable, even when locked.
_OPEN_PREFIXES = ('/static/', '/media/', '/admin/', '/auth/', '/users/', '/billing/', '/legal/', '/email/')


class BillingLockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_superuser:
            path = request.path
            if not (path.startswith(_OPEN_PREFIXES) or path == reverse('app:billing')):
                from business_unit.access import _effective_org
                org = _effective_org(user)
                if org is not None and org.is_locked:
                    if org.org_admin_id == user.id:
                        return redirect('app:billing')
                    return render(request, 'app/billing_locked.html',
                                  {'title': 'Subscription required', 'organization': org}, status=402)
        return self.get_response(request)


class CompanyTimeZoneMiddleware:
    """Run each request in the selected company's time zone, so "today", period
    boundaries and displayed times follow that company's business day (set on
    Data Connection). Background jobs keep Kiboko's default (settings.TIME_ZONE)."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import timezone
        zone = None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith(_OPEN_PREFIXES[:2]):
            zone = company_zone(request)
        if zone:
            timezone.activate(zone)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()


def company_zone(request):
    """ZoneInfo for the request's scoped company, or None (use the default)."""
    import zoneinfo
    from business_unit.models import Company
    from business_unit.scope import NO_ACCESS, scoped_company_id
    try:
        company_id = scoped_company_id(request)
        if not company_id or company_id == NO_ACCESS:
            return None
        company = Company.objects.filter(pk=company_id).first()
        return zoneinfo.ZoneInfo(company.effective_time_zone) if company else None
    except Exception:          # an unknown zone name must never break a page
        return None
