"""Permanently delete a disabled organization's data (Privacy Policy section 7,
Terms section 7): 90 days after an account is cancelled or locked for
non-payment, everything Kiboko stores for it goes.

What goes, in one transaction:
  - its companies and everything under them: business units, websites,
    memberships, objectives, budgets, rate goals, daily actuals, the BigQuery
    connection and the daily summary table, score weights, estimator settings;
  - every project and action in its business units (these don't cascade from
    the business unit, so they are deleted explicitly), with their comments and
    votes;
  - its trial codes;
  - its people, when they belong to no other organization. Someone with records
    elsewhere (an action or comment in another company) is scrubbed instead:
    name, email and Google link removed, sign-in disabled;
  - the organization itself.

Never touched: platform demo and comped (billing_exempt) organizations,
superusers, the shared catalog (departments, teams, KPIs), and email opt-outs
(kept so an unsubscribe is still honored).
"""
from collections import Counter

from django.db import transaction


class _DryRun(Exception):
    pass


def org_users(org):
    """Users tied to the org: members of its companies plus its account owner."""
    from django.contrib.auth.models import User
    from django.db.models import Q
    return User.objects.filter(
        Q(company_memberships__company__organization=org) | Q(pk=org.org_admin_id)).distinct()


def _has_records_elsewhere(user, bu_ids, project_ids):
    """True if deleting this user would cascade into another organization's data."""
    from project.models import Action, ActionComment, ScoreVote
    from strategy.models import ProjectComment
    return (Action.objects.filter(owner=user).exclude(vertical_id__in=bu_ids)
            .exclude(project_id__in=project_ids).exists()
            or ProjectComment.objects.filter(author=user).exclude(project_id__in=project_ids).exists()
            or ActionComment.objects.filter(author=user).exclude(action__project_id__in=project_ids).exists()
            or ScoreVote.objects.filter(user=user).exclude(project_id__in=project_ids).exists())


def _scrub(user):
    """Remove someone's personal details without deleting rows other orgs depend on."""
    from business_unit.models import GoogleIdentity
    GoogleIdentity.objects.filter(user=user).delete()
    user.username = f'deleted-user-{user.pk}'
    user.email = ''
    user.first_name = user.last_name = ''
    user.is_active = False
    user.set_unusable_password()
    user.save()


def purge_organization(org, dry_run=False):
    """Delete the org's data as described above. Returns {label: count}. With
    dry_run, the same work runs and is rolled back, so the counts are exact."""
    from django.contrib.auth.models import User
    from business_unit.models import BusinessUnit, Company, Department, Organization, TrialCode
    from project.models import Action
    from strategy.models import Project

    if org.is_platform_demo or org.billing_exempt:
        raise ValueError(f'{org} is a demo or comped organization and is never purged.')

    counts = Counter()

    def add(result):
        for label, n in result[1].items():
            counts[label] += n

    try:
        with transaction.atomic():
            companies = Company.objects.filter(organization=org)
            bu_ids = list(BusinessUnit.objects.filter(company__in=companies).values_list('id', flat=True))
            project_ids = list(Project.objects.filter(vertical_id__in=bu_ids).values_list('id', flat=True))

            other_orgs = Organization.objects.exclude(pk=org.pk)
            people = [u for u in org_users(org)
                      if not u.is_superuser
                      and not u.company_memberships.exclude(company__organization=org).exists()
                      and not u.administered_orgs.filter(pk__in=other_orgs).exists()]
            to_scrub = [u for u in people if _has_records_elsewhere(u, bu_ids, project_ids)]
            to_delete = [u for u in people if u not in to_scrub]
            emails = [u.email for u in people if u.email]

            add(Project.objects.filter(pk__in=project_ids).delete())
            add(Action.objects.filter(vertical_id__in=bu_ids).delete())
            # Departments are a shared list; deleting their owner would delete them.
            Department.objects.filter(owner__in=people).update(owner=None)
            add(companies.delete())
            add(TrialCode.objects.filter(organization=org).delete())
            add(TrialCode.objects.filter(email__in=emails).delete())
            for u in to_scrub:
                _scrub(u)
            counts['users scrubbed'] = len(to_scrub)
            add(User.objects.filter(pk__in=[u.pk for u in to_delete]).delete())
            add(Organization.objects.filter(pk=org.pk).delete())
            if dry_run:
                raise _DryRun
    except _DryRun:
        pass
    return dict(counts)
