import json

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q

from strategy.models import Project, ProjectComment
from .models import Action
from .forms import ProjectForm, ActionTaskForm
from business_unit.models import Department
from .services.kanban import (
    LANES, LANE_STATUS, PIPELINE_STATUSES, get_lane, group_projects, compute_all_lane_totals,
    validate_move, apply_move, is_ready_for_review, can_approve, can_set_loe,
)

# Statuses that are terminal / not represented as a Kanban lane. These never
# appear in the Backlog -- they live in the Archive only.
NON_KANBAN_STATUSES = ['Complete', 'Launched']


def _get_vertical_id(request):
    from business_unit.scope import scoped_vertical_id
    return scoped_vertical_id(request)


def _get_company_id(request):
    from business_unit.scope import scoped_company_id
    return scoped_company_id(request)


def _scope(qs, vertical_id, company_id):
    """Scope to a BusinessUnit, or (on the Summary roll-up) to the selected
    company so project lists never span companies/clients."""
    if vertical_id:
        return qs.filter(vertical_id=vertical_id)
    if company_id:
        return qs.filter(vertical__company_id=company_id)
    return qs


# ---------------------------------------------------------------------------
# Backlog
# ---------------------------------------------------------------------------
@login_required
def view(request):
    """Backlog of approved projects on the executive board, grouped by lane."""
    from project.project_field_options import AEE_ALIGNMENT_CHOICES

    vertical_id = _get_vertical_id(request)
    aee_labels = dict(AEE_ALIGNMENT_CHOICES)
    aee = request.GET.get('aee', '')
    if aee not in aee_labels or aee == '':
        aee = ''

    base = _scope(Project.objects.filter(archived=False, approved=True).exclude(
        status__in=NON_KANBAN_STATUSES + list(PIPELINE_STATUSES)
    ).select_related('owner', 'objective', 'vertical', 'department'),
        vertical_id, _get_company_id(request))
    if aee:
        base = base.filter(objective__aee_alignment=aee)

    buckets = {key: [] for key in LANES}
    for p in base:
        p.kanban_lane_key = get_lane(p)
        p.kanban_lane_label = LANES.get(p.kanban_lane_key, '')
        buckets[p.kanban_lane_key].append(p)

    # Business-unit owners only see their own department's not-yet-in-flight work.
    owned_bus = Department.objects.filter(owner=request.user)
    if owned_bus.exists():
        owned_ids = set(owned_bus.values_list('id', flat=True))
        for key in ('blocked', 'ready_to_score', 'scored', 'executive_approval'):
            buckets[key] = [p for p in buckets[key] if p.department_id in owned_ids]

    approved_projects = buckets['active'] + buckets['on_deck']
    pending_review_projects = buckets['ready_to_score'] + buckets['scored'] + buckets['executive_approval']
    blocked_projects = buckets['blocked']
    lane = request.GET.get('lane', '').strip()
    lane_filter = lane if lane in LANES else ''
    return render(request, 'project/view.html', {
        'approved_projects': approved_projects,
        'pending_review_projects': pending_review_projects,
        'incomplete_projects': [],
        'blocked_projects': blocked_projects,
        'lane_filter': lane_filter,
        'lane_filter_label': LANES.get(lane_filter, ''),
        'lane_filter_projects': buckets.get(lane_filter, []),
        'title': '',
        'aee_filter': aee,
        'aee_filter_label': aee_labels.get(aee, ''),
        'measure_filter': '',
    })


# ---------------------------------------------------------------------------
# Add / edit / detail
# ---------------------------------------------------------------------------
@login_required
def project(request):
    """Add a new Project. It enters the intake pipeline (Incomplete -> BU-lead
    approval -> Developer effort + capability -> Ready to Score -> team vote).
    Revenue is auto-estimated from the impact estimator, not entered by hand."""
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            p = form.save()
            from project.services import impact
            impact.recompute_scores(company=p._company())
            messages.success(request, f'Added "{p.name}" — pending business-unit approval.')
            return redirect('project:project_detail', project_id=p.id)
    else:
        form = ProjectForm()
    from project.services import impact
    aee_color = {'attract_traffic': '#3FC9E0', 'engage_customers': '#ECB752',
                 'expand_purchase': '#55C892'}
    lever_aee = {k: {'aee': aee, 'color': aee_color.get(aee, '#9B7FE0'),
                     'label': lbl} for k, (lbl, aee) in impact.LEVERS.items()}
    return render(request, 'project/add.html', {
        'form': form, 'title': 'Add Project', 'lever_aee': lever_aee})


@login_required
def project_detail(request, project_id):
    """A Project with its execution tasks (Actions) and an add-task form."""
    project = get_object_or_404(Project, pk=project_id)
    actions = (project.actions.select_related('owner', 'team', 'measure')
               .prefetch_related('depends_on').order_by('launch', 'name'))
    return render(request, 'project/detail.html', {
        'project': project,
        'actions': actions,
        'action_form': ActionTaskForm(project=project),
    })


@login_required
@require_POST
def add_action(request, project_id):
    """Add an execution task (Action) to a Project."""
    project = get_object_or_404(Project, pk=project_id)
    form = ActionTaskForm(request.POST, project=project)
    if form.is_valid():
        action = form.save(commit=False)
        action.project = project
        action.business_unit = project.department or Department.objects.first()
        action.vertical = project.vertical
        action.objective = project.objective
        action.save()
        form.save_m2m()   # persist depends_on
        messages.success(request, f'Added task "{action.name}".')
    else:
        messages.error(request, 'Could not add the task — check the fields.')
    return redirect('project:project_detail', project_id=project.id)


@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    next = request.POST.get('next', '/')
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(next)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'project/edit.html', {'form': form, 'title': 'Edit Project'})


@login_required
def add_comment_to_project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    next = request.POST.get('next', '/')
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            ProjectComment.objects.create(project=project, author=request.user, text=text)
        return HttpResponseRedirect(next)
    return redirect('project:project_detail', project_id=project.id)


# ---------------------------------------------------------------------------
# Intake pipeline: approval (BU lead) -> effort + capability (Developer)
# (revenue is auto-estimated at Add Project -- no Analyst stage)
# ---------------------------------------------------------------------------
@login_required
def approve_projects(request):
    """Intake queue: Incomplete -> Pending Approval (BU lead) -> Pending LOE
    (Developer sets effort size + capability) -> Ready to Score."""
    vertical_id = _get_vertical_id(request)
    qs = _scope(Project.objects.filter(archived=False).filter(
        Q(approved=False) | Q(status='Pending LOE')
    ).select_related('owner', 'objective', 'vertical', 'department'),
        vertical_id, _get_company_id(request))

    pending, incomplete, pending_loe = [], [], []
    for p in qs:
        if p.status == 'Pending LOE':
            p.user_can_act = can_set_loe(request.user, p)
            pending_loe.append(p)
        elif is_ready_for_review(p):
            p.user_can_act = can_approve(request.user, p)
            pending.append(p)
        else:
            incomplete.append(p)
    from project.project_field_options import EFFORT_SIZE_CHOICES, CAPABILITY_CHOICES
    return render(request, 'project/approve_projects.html', {
        'title': 'Project Intake',
        'pending_projects': pending,
        'incomplete_projects': incomplete,
        'pending_loe_projects': pending_loe,
        'effort_sizes': EFFORT_SIZE_CHOICES,
        'capability_choices': [c for c in CAPABILITY_CHOICES if c[0]],
    })


@login_required
@require_POST
def approve_action(request, project_id):
    """A business-unit lead approves a project into the pipeline (-> Pending LOE)."""
    project = get_object_or_404(Project, pk=project_id)
    if not can_approve(request.user, project):
        messages.error(request, 'Only a business-unit lead can approve this project.')
    elif not is_ready_for_review(project):
        messages.error(request, 'This project is missing required fields for approval.')
    else:
        project.approved = True
        project.status = 'Pending LOE'
        project.save()
        messages.success(request, f'Approved "{project.name}" — awaiting effort + capability (Developer).')
    return redirect('project:approve_projects')


@login_required
@require_POST
def set_loe(request, project_id):
    """A lead Developer sets the effort size (t-shirt XXS-XXL) and Capability to
    Complete -- both feed the algorithmic score -> Ready to Score."""
    from project.project_field_options import EFFORT_SIZE_CHOICES, CAPABILITY_CHOICES
    from project.services import impact
    project = get_object_or_404(Project, pk=project_id)
    if not can_set_loe(request.user, project):
        messages.error(request, 'Only a developer can set effort and capability.')
        return redirect('project:approve_projects')
    size = (request.POST.get('effort_size') or '').strip().upper()
    cap = (request.POST.get('capability') or '').strip()
    if size not in {c[0] for c in EFFORT_SIZE_CHOICES} or cap not in {c[0] for c in CAPABILITY_CHOICES if c[0]}:
        messages.error(request, 'Pick both an effort size (XXS–XXL) and a capability.')
    else:
        project.effort_size = size
        project.capability = cap
        project.status = LANE_STATUS['ready_to_score']
        project.save()
        impact.recompute_scores(company=project._company())
        messages.success(request, f'Set effort {size} + capability for "{project.name}" — now Ready to Score.')
    return redirect('project:approve_projects')


@login_required
def approve_project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    next_url = request.GET.get('next', request.POST.get('next', '/project/approve/'))
    project.approved = not project.approved
    project.save()
    return HttpResponseRedirect(next_url)


@login_required
def delete(request, project_id):
    """Disabled: projects are archived, never deleted."""
    messages.info(request, 'Projects are archived, not deleted.')
    return redirect('project:all')


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------
@login_required
def archive(request):
    vertical_id = _get_vertical_id(request)
    archived_projects = _scope(Project.objects.filter(
        Q(archived=True) | Q(status='Complete')
    ).order_by('-date_modified'), vertical_id, _get_company_id(request))
    paginator = Paginator(archived_projects, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'project/archive.html', {
        'page_obj': page_obj, 'title': 'Archived Projects'})


# ---------------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------------
@login_required
def kanban_view(request):
    vertical_id = _get_vertical_id(request)
    projects = _scope(Project.objects.filter(archived=False, approved=True).exclude(
        status__in=NON_KANBAN_STATUSES + list(PIPELINE_STATUSES)
    ).select_related('objective', 'department', 'vertical', 'owner'),
        vertical_id, _get_company_id(request))

    grouped = group_projects(projects)
    lane_totals = compute_all_lane_totals(grouped)
    lanes_data = [{
        'key': key, 'label': label, 'projects': grouped[key],
        'totals': lane_totals[key], 'count': len(grouped[key]),
    } for key, label in LANES.items()]

    return render(request, 'project/kanban.html', {
        'lanes_data': lanes_data,
        'lane_totals_json': json.dumps(lane_totals),
        'title': 'Kanban Board',
    })


@require_POST
@login_required
def kanban_move(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    project_id = data.get('project_id')
    target_lane = data.get('target_lane')
    if not project_id or not target_lane:
        return JsonResponse({'ok': False, 'error': 'Missing project_id or target_lane'}, status=400)

    project = get_object_or_404(Project, pk=project_id)
    from_lane = get_lane(project)
    ok, err = apply_move(project, target_lane, user=request.user)
    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=422)

    if from_lane != target_lane:
        who = request.user.get_full_name() or request.user.username
        ProjectComment.objects.create(
            project=project, author=request.user, approved_comment=True,
            text=f'{who} moved this from {LANES.get(from_lane, from_lane)} to {LANES.get(target_lane, target_lane)}.')

    vertical_id = _get_vertical_id(request)
    qs = _scope(Project.objects.filter(archived=False, approved=True).exclude(
        status__in=NON_KANBAN_STATUSES + list(PIPELINE_STATUSES)), vertical_id, _get_company_id(request))
    grouped = group_projects(qs)
    lane_totals = compute_all_lane_totals(grouped)
    lane_counts = {key: len(projects) for key, projects in grouped.items()}
    return JsonResponse({'ok': True, 'lane_totals': lane_totals, 'lane_counts': lane_counts})
