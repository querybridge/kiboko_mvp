"""The phone experience: a short list of what a busy executive does on the go.

Home (forecast vs budget + what needs you), Forecast (closing the budget gap
with project value), Approve, Score, Projects (status), Performance Story and
Add Project. Data comes from the same builders the desktop pages use, and every
change posts to the desktop endpoints (with ?next= back here), so the two
experiences can never disagree."""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from business_unit.scope import scoped_company_id, scoped_vertical_id
from strategy.models import Project

AEE_ELEMENT = {'attract_traffic': 'Attract', 'engage_customers': 'Engage', 'expand_purchase': 'Expand'}

PERIODS = [
    ('month', 'This month'),
    ('quarter', 'This quarter'),
    ('year', 'This year'),
    ('next_quarter', 'Next quarter'),
]
PERIOD_TABS = [('month', 'Month'), ('quarter', 'Quarter'), ('year', 'Year'), ('next_quarter', 'Next Qtr')]
# Gap closers shown before "Show all": enough to close the gap, at least this many.
CLOSERS_SHOWN = 5

GREENLIGHT_STATUSES = ('Scored', 'Executive Approval')
INTAKE_STATUSES = ('In Intake', 'Pending LOE', 'Pending Revenue')
DONE_STATUSES = ('Complete', 'Launched')

# Projects list filters: key -> (label, statuses)
PROJECT_FILTERS = [
    ('active', 'WIP', ('WIP',)),
    ('on_deck', 'On Deck', ('On Deck',)),
    ('review', 'In review', ('Incomplete Entry', 'In Intake', 'Pending LOE', 'Pending Revenue',
                             'Ready to Score', 'Scored', 'Executive Approval', 'Blocked')),
    ('done', 'Done', DONE_STATUSES),
]

STATUS_LABEL = {
    'WIP': 'WIP', 'On Deck': 'On Deck', 'Incomplete Entry': 'Draft',
    'In Intake': 'In intake', 'Pending LOE': 'Sizing', 'Pending Revenue': 'Value review',
    'Ready to Score': 'Scoring', 'Scored': 'Awaiting approval',
    'Executive Approval': 'Awaiting approval', 'Blocked': 'Blocked',
    'Complete': 'Complete', 'Launched': 'Launched',
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _scope(qs, request):
    from app.views import _scope_to
    return _scope_to(qs, scoped_vertical_id(request), scoped_company_id(request))


def _decorate(p, today=None):
    """Display attributes the mobile templates share."""
    today = today or timezone.localdate()
    aee = p.objective.aee_alignment if p.objective_id and p.objective else ''
    p.aee_key = aee.split('_')[0] if aee else ''
    p.aee_name = AEE_ELEMENT.get(aee, '')
    p.status_label = STATUS_LABEL.get(p.status or '', p.status or 'Draft')
    p.late = bool(p.target_completion and p.target_completion < today
                  and p.status not in DONE_STATUSES)
    return p


def _greenlight(request):
    """Scored projects awaiting an executive's go (same as Executive Approval)."""
    qs = _scope(Project.objects.filter(archived=False, approved=True, status__in=GREENLIGHT_STATUSES)
                .select_related('owner', 'objective', 'vertical'), request)
    return sorted(qs, key=lambda p: -(p.value or 0))


def _intake(request):
    """Complete entries awaiting a business-unit lead's approval that this user may give."""
    from project.services.kanban import can_approve, is_ready_for_review
    qs = _scope(Project.objects.filter(archived=False, approved=False)
                .exclude(status__in=INTAKE_STATUSES)
                .select_related('owner', 'objective', 'vertical', 'vertical__company'), request)
    return sorted((p for p in qs if is_ready_for_review(p) and can_approve(request.user, p)),
                  key=lambda p: -(p.value or 0))


def _score_queue(request):
    cached = getattr(request, '_m_score_queue', None)
    if cached is None:
        from app.views import score_queue
        cached = request._m_score_queue = score_queue(request)
    return cached


def _latest_activity(p):
    """The newest comment on the project or any of its actions: (comment, action name or '')."""
    from project.models import ActionComment
    pc = p.comments.select_related('author').order_by('-created_date').first()
    ac = (ActionComment.objects.filter(action__project=p, action__archived=False)
          .select_related('author', 'action').order_by('-created_date').first())
    if ac and (not pc or ac.created_date > pc.created_date):
        return ac, ac.action.name
    return pc, ''


def _blocked(request, start, end, today):
    """Blocked projects, largest first, each with what it would add to the period if
    unblocked now (from its go-live, never before tomorrow), its blocked actions and
    its latest activity, so an executive can see why and ask."""
    from business_unit.access import can_edit_project
    from project.services.impact import forecast_value_between
    tomorrow = today + timedelta(days=1)
    rows = []
    for p in _scope(Project.objects.filter(archived=False)
                    .filter(Q(status='Blocked') | Q(is_blocked=True))
                    .select_related('owner', 'objective', 'vertical'), request):
        live = max(start, tomorrow, p.target_completion or tomorrow)
        p.target_completion, planned = live, p.target_completion
        p.at_stake = forecast_value_between(p, live, end)
        p.target_completion = planned
        p.blocked_actions = [a.name or 'Action' for a in p.actions.filter(archived=False)
                             .filter(Q(status='Blocked') | Q(is_blocked=True))]
        p.last_comment, p.last_comment_on = _latest_activity(p)
        p.can_ask = can_edit_project(request.user, p)
        rows.append(_decorate(p, today))
    rows.sort(key=lambda p: (-(p.value or 0), -p.at_stake))
    return rows


def _nav(request, tab, **extra):
    """Context every mobile page shares: the active tab and the tab badges."""
    from project.services.kanban import is_executive
    exec_ = is_executive(request.user)
    approvals = (len(_greenlight(request)) if exec_ else 0) + len(_intake(request))
    to_score = sum(1 for p in _score_queue(request) if not p.has_voted)
    ctx = {'tab': tab, 'badge_approve': approvals, 'badge_score': to_score, 'is_exec': exec_}
    ctx.update(extra)
    return ctx


def _add_months(year, month, n):
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def _period(key, today):
    """(months, statuses counted in the forecast) for a period key."""
    y, m = today.year, today.month
    qstart = ((m - 1) // 3) * 3 + 1
    if key == 'quarter':
        return [(y, qstart + i) for i in range(3)], ('WIP',)
    if key == 'year':
        return [(y, i) for i in range(1, 13)], ('WIP',)
    if key == 'next_quarter':
        ny, nm = _add_months(y, qstart, 3)
        return [_add_months(ny, nm, i) for i in range(3)], ('WIP', 'On Deck')
    return [(y, m)], ('WIP',)


def _period_bounds(key, today):
    """(first day, last day) of a period key."""
    import calendar
    months, _ = _period(key, today)
    (fy, fm), (ly, lm) = months[0], months[-1]
    return date(fy, fm, 1), date(ly, lm, calendar.monthrange(ly, lm)[1])


def _forecast(request, key):
    """Budget vs forecast for one period, with the projects that could close the gap.

    Landing = trending forecast + value of the projects already counted (WIP, plus
    On Deck for a future period), the same numbers as the Pipeline page. Each
    candidate's contribution is what the forecast would count for it from its
    go-live (never before tomorrow) to the period's end: ramped and discounted
    by expected attainment, as for counted projects."""
    import calendar
    from app import views as av
    from app.integrations import ga4_dashboard

    today = timezone.localdate()
    months, statuses = _period(key, today)
    vid, cid = scoped_vertical_id(request), scoped_company_id(request)
    actuals = ga4_dashboard.ga4_daily_actuals(request, date(today.year - 1, 1, 1), today)
    series = av._month_series(months, today, vid, actuals, cid, statuses)
    s = series['summary']

    start = date(months[0][0], months[0][1], 1)
    ly, lm = months[-1]
    end = date(ly, lm, calendar.monthrange(ly, lm)[1])
    budget, landing = s['budget_total'], s['end_total']
    actual = s['actual'] if start <= today else 0
    gap = budget - landing                       # > 0: short of budget

    from project.services.impact import forecast_value_between
    counted = []
    for p in _scope(Project.objects.filter(status__in=statuses).select_related('objective'), request):
        v = forecast_value_between(p, start, end)
        if v > 0:
            counted.append((_decorate(p, today), v))
    counted.sort(key=lambda t: -t[1])

    cand_statuses = [st for st in ('On Deck',) + GREENLIGHT_STATUSES if st not in statuses]
    tomorrow = today + timedelta(days=1)
    candidates = []
    for p in _scope(Project.objects.filter(archived=False, status__in=cand_statuses)
                    .select_related('objective', 'vertical'), request):
        # Valued as if it went live on its planned date, but not before tomorrow.
        live = max(start, tomorrow, p.target_completion or tomorrow)
        p.target_completion, planned = live, p.target_completion
        p.contribution = forecast_value_between(p, live, end)
        p.target_completion, p.live_from = planned, live
        if p.contribution > 0:            # going live after the period adds nothing to it
            candidates.append(_decorate(p, today))
    candidates.sort(key=lambda p: (-p.contribution, -(p.value or 0)))
    running = 0.0
    shown_until = None
    for i, p in enumerate(candidates):
        running += p.contribution
        p.cumulative = running
        p.covers_pct = min(100, round(100 * running / gap)) if gap > 0 else 100
        if shown_until is None and gap > 0 and running >= gap:
            shown_until = i + 1
        p.extra = i >= max(CLOSERS_SHOWN, shown_until or CLOSERS_SHOWN)
    closers_total = running

    def pct(v):
        return round(100 * v / budget, 1) if budget else 0

    scale = max(budget, landing + max(0.0, closers_total if gap > 0 else 0), 1)
    return {
        'key': key,
        'label': dict(PERIODS)[key],
        'range': f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}",
        'budget': budget, 'landing': landing, 'actual': actual,
        'forecast_base': s['forecast'], 'project_value': s['project_value'],
        'gap': gap, 'ahead': gap <= 0, 'gap_abs': abs(gap),
        'pct_of_budget': pct(landing),
        'has_budget': budget > 0,
        # Landing bar segments as % of the bar's scale.
        'bar': {
            'actual': 100 * actual / scale,
            'forecast': 100 * max(0.0, s['forecast'] - actual) / scale,
            'projects': 100 * s['project_value'] / scale,
            'closers': 100 * (min(closers_total, gap) if gap > 0 else 0) / scale,
            'budget': 100 * budget / scale,
        },
        'counted_statuses': statuses,
        'counted': counted,
        'candidates': candidates,
        'extra_count': sum(1 for p in candidates if p.extra),
        'closers_total': closers_total,
        'closes_gap': gap > 0 and closers_total >= gap,
        'after_closers_gap': max(0.0, gap - closers_total),
        'end': end,
        'chart': {k: series[k] for k in ('labels', 'budget', 'forecast_base', 'project_value_add', 'actual')},
        'multi_month': len(months) > 1,
    }


def _period_key(request, default='month'):
    key = request.GET.get('p') or request.session.get('m_period') or default
    if key not in dict(PERIODS):
        key = default
    request.session['m_period'] = key
    return key


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
# The user's default home page (Profile, or their role's default) -> the mobile
# page that serves the same purpose.
LANDER_PAGES = {
    'pipeline': 'mobile:home',
    'kanban': 'mobile:projects',
    'grow_sales': 'mobile:story',
    'storyboard': 'mobile:story',
}


@login_required
def start(request):
    """Post-login dispatcher, the mobile twin of app.views.home."""
    prof = getattr(request.user, 'profile', None)
    key = prof.resolved_lander_key() if prof else 'pipeline'
    return redirect(LANDER_PAGES.get(key, 'mobile:home'))


@login_required
def home(request):
    today = timezone.localdate()
    fc = _forecast(request, _period_key(request))
    nav = _nav(request, 'home')

    in_flight = list(_scope(Project.objects.filter(archived=False, status='WIP')
                            .select_related('objective'), request)
                     .annotate(avg_progress=Avg('actions__progress', filter=Q(actions__archived=False))))
    for p in in_flight:
        _decorate(p, today)
        p.progress = int(round(p.avg_progress or 0))
    in_flight.sort(key=lambda p: -(p.value or 0))
    soon = [p for p in in_flight if p.target_completion and today <= p.target_completion <= today + timedelta(days=30)]
    soon.sort(key=lambda p: p.target_completion)

    greenlight = _greenlight(request) if nav['is_exec'] else []
    intake = _intake(request)
    to_score = [p for p in _score_queue(request) if not p.has_voted]
    blocked = _blocked(request, *_period_bounds(fc['key'], today), today)
    return render(request, 'mobile/home.html', dict(nav, **{
        'title': 'Home',
        'fc': fc,
        'periods': PERIOD_TABS,
        'greenlight_count': len(greenlight),
        'greenlight_value': sum(p.value or 0 for p in greenlight),
        'intake_count': len(intake),
        'score_count': len(to_score),
        'score_value': sum(p.value or 0 for p in to_score),
        'blocked_count': len(blocked),
        'blocked_value': sum(p.value or 0 for p in blocked),
        'in_flight': in_flight[:4],
        'in_flight_count': len(in_flight),
        'in_flight_value': sum(p.value or 0 for p in in_flight),
        'late_count': sum(1 for p in in_flight if p.late),
        'soon': soon[:3],
    }))


@login_required
def forecast(request):
    fc = _forecast(request, _period_key(request))
    from project.services.kanban import is_executive
    return render(request, 'mobile/forecast.html', dict(_nav(request, 'home'), **{
        'title': 'Forecast',
        'back': reverse('mobile:home'),
        'fc': fc,
        'periods': PERIOD_TABS,
        'can_greenlight': is_executive(request.user),
        'here': request.get_full_path(),
    }))


@login_required
def blocked(request):
    """Blocked projects with the value each holds up and why, so an executive can ask."""
    today = timezone.localdate()
    key = _period_key(request)
    start, end = _period_bounds(key, today)
    rows = _blocked(request, start, end, today)
    return render(request, 'mobile/blocked.html', dict(_nav(request, 'home'), **{
        'title': 'Blocked',
        'back': reverse('mobile:home') + f'?p={key}',
        'fc': {'key': key, 'label': dict(PERIODS)[key], 'end': end},
        'periods': PERIOD_TABS,
        'blocked': rows,
        'blocked_value': sum(p.value or 0 for p in rows),
        'blocked_at_stake': sum(p.at_stake for p in rows),
        'here': request.get_full_path(),
    }))


@login_required
def approve(request):
    nav = _nav(request, 'approve')
    today = timezone.localdate()
    greenlight = [_decorate(p, today) for p in _greenlight(request)]
    intake = [_decorate(p, today) for p in _intake(request)]
    return render(request, 'mobile/approve.html', dict(nav, **{
        'title': 'Approve',
        'greenlight': greenlight,
        'greenlight_value': sum(p.value or 0 for p in greenlight),
        'intake': intake,
        'here': reverse('mobile:approve'),
    }))


@login_required
def score(request):
    today = timezone.localdate()
    queue = [_decorate(p, today) for p in _score_queue(request)]
    return render(request, 'mobile/score_list.html', dict(_nav(request, 'score'), **{
        'title': 'Score',
        'pending': [p for p in queue if not p.has_voted],
        'voted': [p for p in queue if p.has_voted],
    }))


@login_required
def score_project(request, project_id):
    queue = _score_queue(request)
    p = next((x for x in queue if x.id == project_id), None)
    if p is None:
        messages.info(request, 'That project isn’t waiting for your score.')
        return redirect('mobile:score')
    _decorate(p)
    pending = [x for x in queue if not x.has_voted and x.id != p.id]
    return render(request, 'mobile/score.html', dict(_nav(request, 'score'), **{
        'title': 'Score',
        'back': reverse('mobile:score'),
        'p': p,
        'next_project': pending[0] if pending else None,
    }))


@login_required
def projects(request):
    today = timezone.localdate()
    filters = [(k, label) for k, label, _ in PROJECT_FILTERS]
    key = request.GET.get('f') or 'active'
    statuses = next((st for k, _, st in PROJECT_FILTERS if k == key), None)
    if statuses is None:
        key, statuses = 'active', PROJECT_FILTERS[0][2]
    qs = Project.objects.filter(status__in=statuses).select_related('objective', 'owner', 'vertical')
    if key != 'done':
        qs = qs.filter(archived=False)
    qs = _scope(qs, request).annotate(
        avg_progress=Avg('actions__progress', filter=Q(actions__archived=False)))
    if key == 'done':
        rows = list(qs.order_by('-date_modified')[:60])
    else:
        rows = sorted(qs, key=lambda p: -(p.value or 0))
    for p in rows:
        _decorate(p, today)
        p.progress = int(round(p.avg_progress or 0))
    counts = {k: _scope(Project.objects.filter(status__in=st, **({} if k == 'done' else {'archived': False})),
                        request).count()
              for k, _, st in PROJECT_FILTERS}
    return render(request, 'mobile/projects.html', dict(_nav(request, 'projects'), **{
        'title': 'Projects',
        'filters': [(k, label, counts[k]) for k, label in filters],
        'filter': key,
        'rows': rows,
        'total_value': sum(p.value or 0 for p in rows),
        'late_count': sum(1 for p in rows if p.late),
    }))


def _activity(p, actions, limit=20):
    """Project and action comments, newest first; action comments carry `on`, the action's name."""
    from project.models import ActionComment
    feed = list(p.comments.select_related('author').order_by('-created_date')[:limit])
    for c in (ActionComment.objects.filter(action__in=actions).select_related('author', 'action')
              .order_by('-created_date')[:limit]):
        c.on = c.action.name or 'Action'
        feed.append(c)
    feed.sort(key=lambda c: c.created_date, reverse=True)
    return feed[:limit]


@login_required
def project(request, project_id):
    from business_unit.access import can_edit_project
    from project.services import voting
    from project.services.kanban import can_approve, is_executive, is_ready_for_review
    from project.views import _project_or_404, action_progress
    p = _decorate(_project_or_404(request, project_id))
    actions = list(p.actions.filter(archived=False).select_related('owner', 'team').order_by('launch', 'name'))
    editable = can_edit_project(request.user, p)
    here = reverse('mobile:project', kwargs={'project_id': p.id})
    est = p._estimate()
    return render(request, 'mobile/project.html', dict(_nav(request, 'projects'), **{
        'title': 'Project',
        'back': request.GET.get('back') or reverse('mobile:projects'),
        'p': p,
        'actions': actions,
        'progress': action_progress(actions),
        'comments': _activity(p, actions),
        'blocked': p.status == 'Blocked' or p.is_blocked,
        'blocked_actions': [a for a in actions if a.status == 'Blocked' or a.is_blocked],
        'expected': int(round(est['expected_realized'])) if est else None,
        'can_comment': editable,
        'can_greenlight': editable and p.status in GREENLIGHT_STATUSES and p.approved and is_executive(request.user),
        'can_intake': (editable and not p.approved and p.status not in INTAKE_STATUSES
                       and is_ready_for_review(p) and can_approve(request.user, p)),
        'can_score': p.status == 'Ready to Score' and voting.is_eligible(p, request.user),
        'here': here,
        'desktop_url': f'/project/{p.id}/?ui=desktop',
    }))


@login_required
def story(request):
    from app import performance_story as ps
    from app.integrations import ga4_dashboard
    from app.views import _analytics_filter
    primary, compare, ctx = _analytics_filter(request)
    fundamentals = ga4_dashboard.ga4_story_fundamentals(request, primary, compare)
    ctx.update(ps.build_performance_story(primary, compare, fundamentals=fundamentals))
    ctx['primary_options'] = [o for o in ctx['primary_options'] if o[0] != 'CUSTOM']
    ctx['groups'] = ps.aee_groups(ctx['sections'])
    return render(request, 'mobile/story.html', dict(_nav(request, 'story'), **ctx, title='Performance'))


@login_required
def add(request):
    from business_unit.models import Department
    from project.forms import ProjectForm
    from project.services import impact
    from project.views import _business_days_out
    company_id = scoped_company_id(request)
    if request.method == 'POST':
        form = ProjectForm(request.POST, user=request.user, company_id=company_id)
        if form.is_valid():
            p = form.save()
            impact.recompute_scores(company=p._company())
            messages.success(request, f'Added “{p.name}”.')
            return redirect('mobile:project', project_id=p.id)
        messages.error(request, 'Please fix the highlighted fields.')
    else:
        initial = {'owner': request.user.pk,
                   'target_completion': _business_days_out(timezone.localdate(), 30)}
        vid = scoped_vertical_id(request)
        if vid:
            initial['vertical'] = vid
        form = ProjectForm(initial=initial, user=request.user, company_id=company_id)
    form.fields['objective'].empty_label = 'Choose an objective'
    form.fields['vertical'].empty_label = 'Choose a business unit'
    profile = getattr(request.user, 'profile', None)
    dept = getattr(profile, 'department', None) or Department.objects.first()
    verticals = list(form.fields['vertical'].queryset)
    return render(request, 'mobile/add.html', dict(_nav(request, 'projects'), **{
        'title': 'Add project',
        'back': reverse('mobile:projects'),
        'form': form,
        'department_id': dept.pk if dept else '',
        'single_vertical': verticals[0] if len(verticals) == 1 else None,
        'levers': [{'key': k, 'label': lbl, 'aee': aee} for k, (lbl, aee) in impact.LEVERS.items()],
        'objective_aee': {str(o.pk): o.aee_alignment for o in form.fields['objective'].queryset},
        'baseline_url': reverse('project:estimator_baseline'),
        'min_weeks': impact.PLAUSIBILITY_MIN_WEEKS,
    }))
