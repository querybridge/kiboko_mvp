"""Org-aware access rules — the single source of truth for what a user may see.

Tiers:
  * Platform superuser (Django is_superuser) -> everything, every org.
  * Org admin (Organization.org_admin) -> every company in their org(s).
  * Company member (CompanyMembership) -> that company, scoped to allowed_bus.
  * Everyone -> the platform demo org (so trial users have something to explore).
"""
from django.db.models import Q


def real_companies(user):
    """Companies the user genuinely belongs to (member or org admin) -- excludes
    the platform demo."""
    from business_unit.models import Company
    admin_org_ids = list(user.administered_orgs.values_list('id', flat=True))
    return Company.objects.filter(
        Q(memberships__user=user) | Q(organization_id__in=admin_org_ids)
    ).distinct().order_by('name')


def has_real_company(user):
    """True if the user has any company of their own (not just the demo)."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or real_companies(user).exists()


def visible_companies(user):
    """Queryset of companies the user may see (ordered by name). Users with no
    company of their own fall back to the platform demo so there's something to
    explore; provisioned users see only their own (no demo clutter)."""
    from business_unit.models import Company
    if not user or not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        return Company.objects.all().order_by('name')
    real = real_companies(user)
    if real.exists():
        return real
    return Company.objects.filter(organization__is_platform_demo=True).order_by('name')


def contact_admin(user, company=None):
    """The admin a user should contact for access: the scoped company's org admin,
    else any org admin of an org they touch, else a platform superuser."""
    from django.contrib.auth.models import User
    if company and company.organization and company.organization.org_admin:
        return company.organization.org_admin
    for c in real_companies(user) if user and user.is_authenticated else []:
        if c.organization and c.organization.org_admin:
            return c.organization.org_admin
    return User.objects.filter(is_superuser=True).exclude(email='').order_by('id').first()


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


def can_manage_goals(user, vertical):
    """Enter/edit goals for a business unit: Owner / Executive / BU Lead / Super,
    within a company the user can access. (Matrix: 'Enter goals'.)"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    company = getattr(vertical, 'company', None)
    if company is None or not can_access_company(user, company):
        return False
    if is_org_admin_of(user, company):                       # Owner / Org Admin
        return True
    prof = getattr(user, 'profile', None)
    member = company.memberships.filter(user=user).exists()
    if prof and member and prof.has_role('executive'):       # Executive of the company
        return True
    if getattr(vertical, 'general_manager_id', None) == user.id:  # BU Lead of this unit
        return True
    if prof and member and prof.has_role('business_unit_leader'):  # BU Lead role in company
        return True
    return False


def can_manage_bigquery(user):
    """CRUD a company's BigQuery (Premium) connection: Owner / Executive /
    Developer / Super. Connecting provisions a new company, so this is a
    role check rather than a per-company one."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.administered_orgs.exists():  # Super / Owner
        return True
    prof = getattr(user, 'profile', None)
    return bool(prof and (prof.has_role('executive') or prof.has_role('developer')))


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
