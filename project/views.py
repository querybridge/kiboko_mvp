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
    validate_move, apply_move, is_ready_for_review, can_approve, can_set_loe, can_set_revenue,
    intake_ready,
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
def _quarter_end(d):
    """Last calendar day of the quarter containing date `d`."""
    import datetime
    q_end_month = ((d.month - 1) // 3) * 3 + 3            # 3, 6, 9, or 12
    if q_end_month == 12:
        return datetime.date(d.year, 12, 31)
    # First day of the month AFTER the quarter, minus one day.
    return datetime.date(d.year, q_end_month + 1, 1) - datetime.timedelta(days=1)


def _business_days_out(start, n):
    """The date `n` business days (Mon–Fri) after `start`."""
    import datetime
    d, added = start, 0
    while added < n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:                              # 0=Mon … 4=Fri
            added += 1
    return d


@login_required
def project(request):
    """Add a new Project. It enters the intake pipeline (Incomplete -> BU-lead
    approval -> Developer effort + capability -> Ready to Score -> team vote).
    Revenue is auto-estimated from the impact estimator, not entered by hand."""
    if request.method == 'POST':
        form = ProjectForm(request.POST, user=request.user, company_id=_get_company_id(request))
        if form.is_valid():
            p = form.save()
            # Audit trail: record an evidence-backed claim as a comment for voters.
            if p.evidence_backed and p.evidence_note:
                from strategy.models import ProjectComment
                kind = dict(p.EVIDENCE_KIND_CHOICES).get(p.evidence_kind, 'Evidence')
                ProjectComment.objects.create(
                    project=p, author=request.user, approved_comment=True,
                    text=f'Evidence-backed target ({kind}): {p.evidence_note}')
            from project.services import impact
            impact.recompute_scores(company=p._company())
            from django.utils.html import format_html
            # "Save progress" saves the draft and returns to it so the user can
            # finish the Impact Estimator; "Submit for approval" resets for a new one.
            if request.POST.get('action') == 'save_progress':
                messages.success(request, format_html(
                    'Progress saved for “{}”. Now complete the Impact Estimator, then submit for approval.',
                    p.name))
                return redirect('project:project_edit', project_id=p.id)
            messages.success(request, format_html(
                'Project “{}” submitted. Next: a business-unit lead approves it, a '
                'developer sizes effort &amp; capability, then the team scores it. '
                '<a href="{}">View project</a>',
                p.name, reverse('project:project_detail', kwargs={'project_id': p.id})))
            # Back to a fresh Add form so the fields reset for the next project.
            return redirect('project:project')
        else:
            # Surface why it didn't submit (a blank required field, an AEE mismatch)
            # as an error toast, so the failure is never silent.
            problems = []
            for field, errs in form.errors.items():
                if field == '__all__':
                    problems.extend(errs)
                    continue
                fld = form.fields.get(field)
                label = (fld.label if fld and fld.label else field.replace('_', ' ').title())
                problems.append(f'{label}: {errs[0]}')
            messages.error(request, 'Couldn’t submit — ' + ' · '.join(problems[:6]))
    else:
        # Convenience defaults (all still editable on the form).
        initial = {
            'owner': request.user.pk,                        # default to the creator
            'target_completion': _business_days_out(timezone.localdate(), 30),
            'plausibility_factor': 1.0,
        }
        # Default the Business Unit to the one selected in the top nav (its GET
        # param or the persisted scope), so the estimator can auto-fill GA4
        # baselines on load. Uses the canonical scope helper for consistency.
        vid = _get_vertical_id(request)
        if vid:
            initial['vertical'] = vid
        # Department defaults to the creator's own (Profile.department), else the first.
        profile = getattr(request.user, 'profile', None)
        default_dept = getattr(profile, 'department', None) or Department.objects.first()
        if default_dept:
            initial['department'] = default_dept.pk
        form = ProjectForm(initial=initial, user=request.user, company_id=_get_company_id(request))
    ctx = _project_form_context(form, title='Add Project')
    return render(request, 'project/add.html', ctx)


def _project_form_context(form, title, is_edit=False, next_url=''):
    """Shared context for the rich Project form template (used by Add + Edit) so
    an incomplete entry can be completed — estimator included — from either."""
    from project.services import impact
    aee_color = {'attract_traffic': '#3FC9E0', 'engage_customers': '#ECB752',
                 'expand_purchase': '#55C892'}
    lever_aee = {k: {'aee': aee, 'color': aee_color.get(aee, '#9B7FE0'),
                     'label': lbl} for k, (lbl, aee) in impact.LEVERS.items()}
    objective_aee = {str(o.pk): o.aee_alignment      # objective -> AEE (scopes the lever)
                     for o in form.fields['objective'].queryset}
    return {
        'form': form, 'title': title, 'is_edit': is_edit, 'next': next_url,
        'lever_aee': lever_aee, 'objective_aee': objective_aee,
        'baseline_url': reverse('project:estimator_baseline'),
        'baseline_windows': BASELINE_WINDOWS,
        'default_baseline_window': DEFAULT_BASELINE_WINDOW,
        'plaus_min_weeks': impact.PLAUSIBILITY_MIN_WEEKS,
        'plaus_min_days': impact.PLAUSIBILITY_MIN_WEEKS * 7}


# Baseline / plausibility window options (days). Default is 52 weeks so the
# baseline levels are computed over the same span as the plausibility history.
BASELINE_WINDOWS = (90, 180, 365)
DEFAULT_BASELINE_WINDOW = 365


@login_required
def estimator_baseline(request):
    """JSON: GA4-derived estimator baselines for the intake form's chosen Business
    Unit, over the requested window (?window=90|180|365, default 365 = 52 weeks).
    Both the baseline levels and the plausibility weekly history use this span.
    {connected, levels{lever:level}, s0_annual, weekly{lever:[...]}, window_days,
    min_weeks} or {connected: False, reason}."""
    from app.integrations import ga4_dashboard
    from project.services import impact
    from business_unit.models import BusinessUnit
    bu_id = request.GET.get('vertical')
    bu = (BusinessUnit.objects.filter(pk=bu_id).select_related('company').first()
          if bu_id else None)
    if not bu:
        return JsonResponse({'connected': False, 'reason': 'no-business-unit'})
    try:
        window = int(request.GET.get('window', DEFAULT_BASELINE_WINDOW))
    except (TypeError, ValueError):
        window = DEFAULT_BASELINE_WINDOW
    if window not in BASELINE_WINDOWS:
        window = DEFAULT_BASELINE_WINDOW
    status = ga4_dashboard.baseline_status(request, bu)
    if status not in ('premium', 'standard', 'dailyactual'):
        return JsonResponse({'connected': False, 'reason': status})
    daily = ga4_dashboard.baseline_daily_for_bu(request, bu, window)
    if daily is None:
        return JsonResponse({'connected': False, 'reason': 'fetch-failed'})
    b = impact.baselines_from_daily(daily, window)
    if not b:
        return JsonResponse({'connected': False, 'reason': 'no-data'})
    return JsonResponse({
        'connected': True,
        'source': {'premium': 'BigQuery', 'standard': 'GA4', 'dailyactual': 'actuals'}[status],
        'window_days': b['window_days'],
        's0_annual': round(b['s0_annual']),
        'levels': {k: round(v, 6) for k, v in b['levels'].items()},
        'weekly': {k: [round(x, 6) for x in v] for k, v in b['weekly'].items()},
        'min_weeks': impact.PLAUSIBILITY_MIN_WEEKS})


@login_required
def project_detail(request, project_id):
    """A Project with its execution Actions and an add-action form."""
    project = get_object_or_404(Project, pk=project_id)
    actions = (project.actions.select_related('owner', 'team', 'measure')
               .prefetch_related('depends_on').order_by('launch', 'name'))
    # Post-launch back-half: Realized Performance on completed projects.
    realized = None
    if project.status in COMPLETED_STATUSES:
        from app.integrations import ga4_dashboard
        realized = ga4_dashboard.realized_perf_for_project(request, project)
    # Analyst review audit: the auto value + delta vs the analyst's projected value.
    analyst_auto = analyst_delta = None
    if project.analyst_reviewed and project.analyst_value is not None:
        est = project._estimate()
        analyst_auto = int(round(est['gross_annual'])) if est else 0
        analyst_delta = int(project.analyst_value) - analyst_auto
    return render(request, 'project/detail.html', {
        'project': project,
        'actions': actions,
        'action_form': ActionTaskForm(project=project),
        'realized': realized,
        'completed': project.status in COMPLETED_STATUSES,
        'analyst_auto': analyst_auto,
        'analyst_delta': analyst_delta,
    })


@login_required
@require_POST
def add_action(request, project_id):
    """Add an execution Action to a Project."""
    project = get_object_or_404(Project, pk=project_id)
    if project.status in COMPLETED_STATUSES:
        messages.error(request, 'Actions can’t be added to a completed project.')
        return redirect('project:project_detail', project_id=project.id)
    form = ActionTaskForm(request.POST, project=project)
    if form.is_valid():
        action = form.save(commit=False)
        action.project = project
        action.business_unit = project.department or Department.objects.first()
        action.vertical = project.vertical
        action.objective = project.objective
        action.save()
        form.save_m2m()   # persist depends_on
        messages.success(request, f'Added action "{action.name}".')
    else:
        messages.error(request, 'Could not add the action — check the fields.')
    return redirect('project:project_detail', project_id=project.id)


@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    next_url = (request.POST.get('next') or request.GET.get('next')
                or reverse('project:project_detail', kwargs={'project_id': project.id}))
    edit_company_id = (project.vertical.company_id if project.vertical_id and project.vertical
                       else _get_company_id(request))
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project, user=request.user, company_id=edit_company_id)
        if form.is_valid():
            p = form.save()
            from project.services import impact
            impact.recompute_scores(company=p._company())
            if request.POST.get('action') == 'save_progress':
                messages.success(request, f'Progress saved for “{p.name}”. Complete the Impact Estimator, then submit.')
                return redirect('project:project_edit', project_id=p.id)
            messages.success(request, f'Saved “{p.name}”.')
            return HttpResponseRedirect(next_url)
        else:
            problems = []
            for field, errs in form.errors.items():
                if field == '__all__':
                    problems.extend(errs); continue
                fld = form.fields.get(field)
                label = (fld.label if fld and fld.label else field.replace('_', ' ').title())
                problems.append(f'{label}: {errs[0]}')
            messages.error(request, 'Couldn’t save — ' + ' · '.join(problems[:6]))
    else:
        form = ProjectForm(instance=project, user=request.user, company_id=edit_company_id)
    return render(request, 'project/add.html',
                  _project_form_context(form, title='Edit Project', is_edit=True, next_url=next_url))


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
    INTAKE = ('In Intake', 'Pending LOE', 'Pending Revenue')
    qs = _scope(Project.objects.filter(archived=False).filter(
        Q(approved=False) | Q(status__in=INTAKE)
    ).select_related('owner', 'objective', 'vertical', 'department'),
        vertical_id, _get_company_id(request))

    pending, incomplete, pending_loe, pending_analyst = [], [], [], []
    for p in qs:
        if p.status in INTAKE:
            # Parallel gates: a project needs an analyst value sign-off AND a
            # developer LOE. It shows in each section until that gate is done.
            p.can_analyst = can_set_revenue(request.user, p)
            p.can_loe = can_set_loe(request.user, p)
            if not p.analyst_reviewed:
                pending_analyst.append(p)
            if not (p.effort_size and p.capability):
                pending_loe.append(p)
        elif is_ready_for_review(p):
            p.user_can_act = can_approve(request.user, p)
            pending.append(p)
        else:
            incomplete.append(p)
    from project.project_field_options import EFFORT_SIZE_CHOICES, CAPABILITY_CHOICES
    return render(request, 'project/approve_projects.html', {
        'title': 'Approve Projects',
        'pending_projects': pending,
        'incomplete_projects': incomplete,
        'pending_loe_projects': pending_loe,
        'pending_analyst_projects': pending_analyst,
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
        messages.error(request, 'This entry is incomplete — finish the impact estimate (lever, '
                                'current/target level, sales baseline) via Edit before approving.')
    else:
        project.approved = True
        project.status = 'In Intake'
        project.save()
        messages.success(request, f'Approved "{project.name}" — awaiting analyst value sign-off '
                                  f'and developer effort + capability.')
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
        # Ready to Score only when the analyst has also signed off (parallel gate).
        ready = bool(project.analyst_reviewed)
        project.status = LANE_STATUS['ready_to_score'] if ready else 'In Intake'
        project.save()
        impact.recompute_scores(company=project._company())
        if ready:
            messages.success(request, f'Set effort {size} + capability for "{project.name}" — now Ready to Score.')
        else:
            messages.success(request, f'Set effort {size} + capability for "{project.name}" — '
                                      f'still awaiting the analyst value sign-off.')
    return redirect('project:approve_projects')


# Display units for the six levers on the analyst review screen.
_LEVER_UNITS = {
    'visitors': 'integer', 'visits_per_visitor': 'decimal', 'cart_creation': 'percent',
    'cart_completion': 'percent', 'units_per_order': 'decimal', 'avg_unit_price': 'currency',
}


def _analyst_baselines(request, project):
    """(current_levels{lever:val}, s0_annual, source) for the project's BU, from the
    data tier; falls back to the project's own stored baseline for the primary lever."""
    from app.integrations import ga4_dashboard
    from project.services import impact
    levels, s0, source = {}, float(project.s0_annual or 0), None
    bu = project.vertical
    if bu:
        status = ga4_dashboard.baseline_status(request, bu)
        if status in ('premium', 'standard', 'dailyactual'):
            daily = ga4_dashboard.baseline_daily_for_bu(request, bu, DEFAULT_BASELINE_WINDOW)
            b = impact.baselines_from_daily(daily, DEFAULT_BASELINE_WINDOW) if daily else None
            if b:
                levels = dict(b['levels'])
                s0 = b['s0_annual']
                source = {'premium': 'BigQuery', 'standard': 'GA4', 'dailyactual': 'actuals'}[status]
    # The primary lever's current level is the intake baseline (keeps the auto
    # value reproducible from the composition).
    if project.lever and project.target_from is not None:
        levels[project.lever] = float(project.target_from)
    # Base the composition on the PROJECT's own annual sales baseline (the same
    # base the auto value uses), so an unchanged review yields zero delta. The
    # freshly-fetched baselines are only used for the other levers' current levels.
    if project.s0_annual:
        s0 = float(project.s0_annual)
    return levels, s0, source


def _analyst_metrics(project, levels):
    """Build the per-lever rows for the analyst screen: current, planned, expected."""
    from project.services import impact
    adj = project.analyst_adjustments or {}
    rows = []
    for k in impact.LEVER_KEYS:
        label = impact.LEVERS[k][0]
        current = levels.get(k)
        is_primary = (k == project.lever)
        planned = float(project.target_to) if (is_primary and project.target_to is not None) else current
        if k in adj and adj[k] not in (None, ''):
            expected = float(adj[k])
        else:
            expected = planned
        rows.append({'key': k, 'label': label, 'unit': _LEVER_UNITS.get(k, 'decimal'),
                     'current': current, 'planned': planned, 'expected': expected,
                     'is_primary': is_primary})
    return rows


@login_required
def analyst_review(request, project_id):
    """Analyst screen: verify or adjust the projected value by setting expected
    post-launch levels for one or more of the six levers (parallel intake gate)."""
    from project.services import impact
    project = get_object_or_404(Project, pk=project_id)
    if not can_set_revenue(request.user, project):
        messages.error(request, 'Only an analyst can review the projected value.')
        return redirect('project:project_detail', project_id=project.id)
    levels, s0, source = _analyst_baselines(request, project)
    metrics = _analyst_metrics(project, levels)
    est = project._estimate()
    auto_value = int(round(est['gross_annual'])) if est else 0
    has_baselines = bool(s0 and any(m['current'] for m in metrics))
    return render(request, 'project/analyst_review.html', {
        'project': project, 'metrics': metrics, 's0_annual': s0, 'source': source,
        'auto_value': auto_value, 'has_baselines': has_baselines,
        'current_value': project.analyst_value if project.analyst_reviewed else auto_value,
        'lever_keys': impact.LEVER_KEYS,
    })


@login_required
@require_POST
def set_analyst_review(request, project_id):
    """Save the analyst's value sign-off / adjustments (parallel intake gate)."""
    from django.utils import timezone as _tz
    from project.services import impact
    project = get_object_or_404(Project, pk=project_id)
    if not can_set_revenue(request.user, project):
        messages.error(request, 'Only an analyst can review the projected value.')
        return redirect('project:project_detail', project_id=project.id)

    est = project._estimate()
    auto_value = int(round(est['gross_annual'])) if est else 0
    s0 = float(project.s0_annual or 0)

    # Value is computed RELATIVE to the planned state (the auto value), so any
    # lever left unchanged contributes exactly x1 and an untouched review yields
    # exactly the auto value (no rounding residual). Each lever posts its planned
    # and expected levels in the same display units, so the ratio cancels units.
    multiplier, adjustments = 1.0, {}
    for k in impact.LEVER_KEYS:
        try:
            exp = float(request.POST.get(f'expected_{k}'))
            pl = float(request.POST.get(f'planned_{k}'))
        except (TypeError, ValueError):
            continue
        if pl and abs(exp / pl - 1.0) > 1e-6:            # a real change to this lever
            multiplier *= exp / pl
            adjustments[k] = (exp / 100.0) if _LEVER_UNITS.get(k) == 'percent' else exp

    note = (request.POST.get('analyst_note') or '').strip()
    if s0:
        analyst_value = int(round((s0 + auto_value) * multiplier - s0))
    else:
        # No sales baseline to compose from: accept the auto value unless overridden.
        try:
            analyst_value = int(round(float(request.POST.get('manual_value') or auto_value)))
        except (TypeError, ValueError):
            analyst_value = auto_value

    # A note is required whenever the analyst changes the value.
    if analyst_value != auto_value and not note:
        messages.error(request, 'Add a note justifying the adjustment before saving.')
        return redirect('project:analyst_review', project_id=project.id)

    project.analyst_reviewed = True
    project.analyst_value = analyst_value
    project.analyst_adjustments = adjustments
    project.analyst_note = note[:500]
    project.analyst_reviewed_by = request.user
    project.analyst_reviewed_at = _tz.now()
    ready = bool(project.effort_size and project.capability)
    project.status = LANE_STATUS['ready_to_score'] if ready else 'In Intake'
    project.save()
    impact.recompute_scores(company=project._company())
    delta = analyst_value - auto_value
    if delta:
        messages.success(request, f'Value set to ${analyst_value:,} for "{project.name}" '
                                  f'({"+" if delta > 0 else "−"}${abs(delta):,} vs auto-estimate)'
                                  + ('' if not ready else ' — now Ready to Score.'))
    else:
        messages.success(request, f'Value signed off (${analyst_value:,}) for "{project.name}"'
                                  + ('.' if not ready else ' — now Ready to Score.'))
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
# Project Review — Completed Projects + Archive
# ---------------------------------------------------------------------------
# Completed = terminal statuses; they stay in Completed Projects until archived.
COMPLETED_STATUSES = ('Complete', 'Launched')


def _parse_ymd(s):
    import datetime
    try:
        return datetime.date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


@login_required
def completed_projects(request):
    """Project Review: completed (non-archived) projects with a go-live date filter,
    paginated. Each shows its post-launch Realized Performance on the detail page
    and can be archived from here."""
    import datetime
    vertical_id = _get_vertical_id(request)
    qs = _scope(Project.objects.filter(status__in=COMPLETED_STATUSES, archived=False)
                .select_related('owner', 'objective', 'vertical', 'vertical__company', 'department'),
                vertical_id, _get_company_id(request))
    today = datetime.date.today()
    d_from = _parse_ymd(request.GET.get('from')) or datetime.date(today.year - 1, 1, 1)
    d_to = _parse_ymd(request.GET.get('to')) or today
    qs = qs.filter(target_completion__range=(d_from, d_to)).order_by('-target_completion', '-date_modified')
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'project/completed_projects.html', {
        'title': 'Completed Projects', 'page_obj': page_obj,
        'd_from': d_from.isoformat(), 'd_to': d_to.isoformat()})


@login_required
def archive(request):
    """Project Review: archived projects (paginated)."""
    vertical_id = _get_vertical_id(request)
    qs = _scope(Project.objects.filter(archived=True)
                .select_related('owner', 'objective', 'vertical', 'department')
                .order_by('-date_modified'), vertical_id, _get_company_id(request))
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'project/archive.html', {'page_obj': page_obj, 'title': 'Archive'})


@login_required
@require_POST
def archive_project(request, project_id):
    """Archive a completed project. Anyone can archive; it then leaves Completed
    Projects for the Archive."""
    p = get_object_or_404(Project, pk=project_id)
    Project.objects.filter(pk=p.pk).update(archived=True)   # bypass save()/recompute
    messages.success(request, f'Archived “{p.name}”.')
    return redirect(request.POST.get('next') or 'project:completed_projects')


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
