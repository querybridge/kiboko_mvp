"""Project emails (SendGrid, via business_unit.email):

  * Project added to a business unit -> that unit's owner, to approve or comment.
  * Project moves to a new phase      -> the project owner.
  * Project reaches Ready to Score    -> everyone expected to score it.

Driven by Project save signals, so every path (Add Project, Insights, Kanban
drag, approvals, voting) is covered. Emails go out after the transaction
commits, and never for the platform demo org or while seeding.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from strategy.models import Project

log = logging.getLogger(__name__)


def _enabled(project):
    from business_unit.models import IntegrationSettings
    from business_unit import email as mail
    if mail.is_suppressed() or not IntegrationSettings.current().notifications_enabled:
        return False
    org = getattr(getattr(getattr(project, 'vertical', None), 'company', None), 'organization', None)
    return not (org and org.is_platform_demo)


def _url(project, tab=''):
    from django.urls import reverse
    from business_unit.email import site_url
    if tab:
        return site_url() + reverse('project:project_tab', args=[project.id, tab])
    return site_url() + reverse('project:project_detail', args=[project.id])


def _phase(status):
    """Phase name for a stored status (statuses are already human-readable)."""
    return {'WIP': 'Work In Progress'}.get(status or '', status or 'No status')


def bu_owners(bu):
    """Who owns a business unit: its general manager, else the company's Business
    Unit Leaders who can see that unit."""
    if bu is None:
        return []
    if bu.general_manager_id and bu.general_manager:
        return [bu.general_manager]
    if bu.company_id is None:
        return []
    leads = []
    for m in bu.company.memberships.select_related('user', 'user__profile').prefetch_related('allowed_bus'):
        prof = getattr(m.user, 'profile', None)
        allowed = m.allowed_bu_ids()
        if prof and prof.has_role('business_unit_leader') and (allowed is None or bu.id in allowed):
            leads.append(m.user)
    return leads


def _name(user):
    return (user.get_full_name() or user.username) if user else ''


def notify_new_project(project):
    from business_unit import email as mail
    from django.urls import reverse
    owners = bu_owners(project.vertical)
    for owner in owners:
        mail.send(owner.email, f'New project for {project.vertical}: {project.name}', 'project_added', {
            'recipient': _name(owner), 'project': project, 'bu': project.vertical,
            'proposer': _name(project.owner), 'project_url': _url(project),
            'approve_url': mail.site_url() + reverse('project:approve_projects'),
            'comment_url': _url(project, 'activity'),
        }, category='project_updates')


def notify_phase_change(project, old_status):
    from business_unit import email as mail
    owner = project.owner
    if owner is None:
        return
    mail.send(owner.email, f'{project.name} moved to {_phase(project.status)}', 'project_phase', {
        'recipient': _name(owner), 'project': project,
        'from_phase': _phase(old_status), 'to_phase': _phase(project.status),
        'project_url': _url(project),
    }, category='project_updates')


def notify_needs_scoring(project):
    from django.contrib.auth.models import User
    from django.urls import reverse
    from business_unit import email as mail
    from project.services.voting import eligible_scorer_ids
    scorers = User.objects.filter(id__in=eligible_scorer_ids(project), is_active=True)
    for u in scorers:
        mail.send(u.email, f'Score this project: {project.name}', 'project_needs_scoring', {
            'recipient': _name(u), 'project': project, 'bu': project.vertical,
            'score_url': mail.site_url() + reverse('app:score_projects'),
            'project_url': _url(project),
        }, category='project_updates')


@receiver(pre_save, sender=Project)
def _remember_previous(sender, instance, raw=False, **kwargs):
    instance._prev = None
    if raw or not instance.pk:
        return
    instance._prev = (Project.objects.filter(pk=instance.pk)
                      .values('status', 'vertical_id').first())


@receiver(post_save, sender=Project)
def _project_saved(sender, instance, created, raw=False, **kwargs):
    if raw or not _enabled(instance):
        return
    prev = getattr(instance, '_prev', None) or {}
    pk = instance.pk

    def run(fn, *args):
        def _go():
            try:
                project = Project.objects.select_related('vertical__company', 'owner').get(pk=pk)
                fn(project, *args)
            except Exception:
                log.exception('Project notification %s failed for project %s', fn.__name__, pk)
        transaction.on_commit(_go)

    if instance.vertical_id and (created or prev.get('vertical_id') != instance.vertical_id):
        run(notify_new_project)
    moved = not created and prev and prev.get('status') != instance.status and instance.status
    if moved:
        run(notify_phase_change, prev.get('status'))
    if instance.status == 'Ready to Score' and (created or moved):
        run(notify_needs_scoring)
