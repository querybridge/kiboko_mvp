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


# ---------------------------------------------------------------------------
# Plan tier / feature gating
#   Standard  -> Analytics + Insights
#   Premium   -> + Project Prioritization (estimator, scoring, value pipeline,
#                approvals incl. the Executive Approval greenlight)
#   Enterprise-> + Project Control (Kanban / WIP / Backlog) and Project Review
# BigQuery is never required — it's the optional "Premium Connection" speed /
# data-integrity upgrade, independent of the plan tier gates below.
# ---------------------------------------------------------------------------
TIER_RANK = {'standard': 1, 'premium': 2, 'enterprise': 3}
ENTERPRISE_FEATURES = frozenset({'project_control', 'project_review'})


def _effective_org(user):
    """The org whose plan governs this user's features: an org they administer,
    else the org of a real company they belong to."""
    org = user.administered_orgs.first()
    if org is not None:
        return org
    c = real_companies(user).first()
    return c.organization if c else None


def plan_tier(user):
    """The plan tier governing this user's feature access. Superusers, platform
    demo orgs, and internal orgs with no explicit plan get full ('enterprise')
    access; self-serve orgs get their chosen plan's tier."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'enterprise'
    org = _effective_org(user)
    if org is None or org.is_platform_demo:
        return 'enterprise'
    plan = getattr(org, 'plan', None)
    if plan is None:
        return 'enterprise'                      # grandfather orgs with no plan
    return plan.tier if plan.tier in TIER_RANK else 'enterprise'


def has_plan_feature(user, feature):
    """Whether the user's plan includes a gated feature (e.g. 'project_control').
    Non-gated features are always available."""
    if feature not in ENTERPRISE_FEATURES:
        return True
    return plan_tier(user) == 'enterprise'


def manageable_companies(user):
    """Companies whose people this user may manage (Manage Users): all for a
    superuser; otherwise companies in organizations they administer plus companies
    where they hold an admin membership. Never another organization's."""
    from django.db.models import Q
    from business_unit.models import Company
    if not user or not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        return Company.objects.all().order_by('name')
    return Company.objects.filter(
        Q(organization__in=user.administered_orgs.all())
        | Q(memberships__user=user, memberships__role='admin')
    ).distinct().order_by('name')


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


def visible_bu_ids(user):
    """BusinessUnit ids the user may see across every company they can view, or
    None for all (superuser). Respects a membership's per-BU limit."""
    from business_unit.models import BusinessUnit
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return None
    ids = set()
    for company in visible_companies(user):
        company_bus = set(BusinessUnit.objects.filter(company=company).values_list('id', flat=True))
        allowed = allowed_bu_ids(user, company)
        ids |= company_bus if allowed is None else (company_bus & set(allowed))
    return ids


def visible_projects(user):
    """Projects the user may open: those in business units they can see."""
    from strategy.models import Project
    ids = visible_bu_ids(user)
    return Project.objects.all() if ids is None else Project.objects.filter(vertical_id__in=ids)


def can_edit_project(user, project):
    """Whether the user may change a project they can see. The shared platform demo
    is read-only to anyone who isn't one of its members; role checks in each view
    still apply on top of this."""
    if user.is_superuser:
        return True
    company = project.vertical.company if project.vertical_id else None
    if company is None:
        return False
    if company.organization and company.organization.is_platform_demo:
        return is_org_admin_of(user, company) or company.memberships.filter(user=user).exists()
    return True


def staff_only(view):
    """Legacy screens that span every organization (old Rocks / Company /
    Measurements settings and the strategy app): Kiboko superusers only. Everyone
    else gets a 404, so the pages don't advertise themselves."""
    import functools
    from django.http import Http404

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper


def can_manage_objectives(user, company):
    """Add / edit a company's objectives: superuser, the company's org admin, or a
    member of the company holding the Executive role."""
    if not user or not user.is_authenticated or company is None:
        return False
    if user.is_superuser or is_org_admin_of(user, company):
        return True
    prof = getattr(user, 'profile', None)
    return bool(prof and prof.has_role('executive') and company.memberships.filter(user=user).exists())
