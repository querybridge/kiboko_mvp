"""Org-aware access rules — the single source of truth for what a user may see.

Tiers:
  * Platform superuser (Django is_superuser) -> everything, every org.
  * Org admin (Organization.org_admin) -> every company in their org(s).
  * Company member (CompanyMembership) -> that company, scoped to allowed_bus.
  * Everyone -> the platform demo org (so trial users have something to explore).
"""
from django.db.models import Q


def visible_companies(user):
    """Queryset of companies the user may see (ordered by name)."""
    from business_unit.models import Company
    if not user or not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        return Company.objects.all().order_by('name')
    admin_org_ids = list(user.administered_orgs.values_list('id', flat=True))
    return Company.objects.filter(
        Q(memberships__user=user)
        | Q(organization_id__in=admin_org_ids)
        | Q(organization__is_platform_demo=True)
    ).distinct().order_by('name')


def is_org_admin_of(user, company):
    """True if user administers the company's organization."""
    return bool(
        company.organization_id
        and user.administered_orgs.filter(id=company.organization_id).exists()
    )


def can_access_company(user, company):
    """Whether the user may view the company at all."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or is_org_admin_of(user, company):
        return True
    if company.memberships.filter(user=user).exists():
        return True
    return bool(company.organization and company.organization.is_platform_demo)


def allowed_bu_ids(user, company):
    """Set of BusinessUnit ids the user may see in the company, or None = all.

    Superusers and org admins see all; a plain member is limited by their
    membership's allowed_bus (empty = all)."""
    if user.is_superuser or is_org_admin_of(user, company):
        return None
    m = company.memberships.filter(user=user).first()
    if m is None:
        return None  # platform-demo viewer etc. -> no per-BU restriction
    return m.allowed_bu_ids()
