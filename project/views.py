import json

from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader
from django.http import HttpResponse, JsonResponse
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from .models import Action
from .forms import ProjectAdd, ProjectEdit, CommentForm, ProjectValue, ProjectLoe, ProjectEditManager
from business_unit.models import BusinessUnit
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from .services.kanban import (
    LANES, group_projects, compute_all_lane_totals, validate_move, apply_move,
)


def _get_vertical_id(request):
    """Read vertical filter from query string, return int or None."""
    v = request.GET.get('vertical', '')
    try:
        return int(v) if v else None
    except (ValueError, TypeError):
        return None


#from .models import Project
@login_required
# Create your views here.

# View All Projects Page
def view(request):
    from .project_field_options import AEE_ALIGNMENT_CHOICES

    context = {}
    title = ""
    vertical_id = _get_vertical_id(request)
    # Optional AEE-alignment filter (from the analytics "Related Projects" links)
    aee = request.GET.get('aee', '')
    aee_labels = dict(AEE_ALIGNMENT_CHOICES)
    if aee not in aee_labels or aee == '':
        aee = ''
    # Exclude archived projects
    # Projects that are approved OR have status Pending Assignment/Active go in the approved table
    approved_projects = Action.objects.filter(
        archived=False,
    ).filter(
        Q(approved=True) | Q(status__in=['Pending Assignment', 'WIP'])
    )
    if vertical_id:
        approved_projects = approved_projects.filter(vertical_id=vertical_id)
    owned_bus = BusinessUnit.objects.filter(owner=request.user)
    # Pending = not approved AND not Pending Assignment/Active status
    pending_filter = Q(approved=False, archived=False) & ~Q(status__in=['Pending Assignment', 'WIP'])
    if owned_bus.exists():
        pending_projects = Action.objects.filter(pending_filter, business_unit__in=owned_bus)
    else:
        pending_projects = Action.objects.filter(pending_filter)
    if vertical_id:
        pending_projects = pending_projects.filter(vertical_id=vertical_id)
    if aee:
        approved_projects = approved_projects.filter(aee_alignment=aee)
        pending_projects = pending_projects.filter(aee_alignment=aee)
    return render(request, 'project/view.html', {
        'approved_projects': approved_projects,
        'pending_projects': pending_projects,
        'title': title,
        'aee_filter': aee,
        'aee_filter_label': aee_labels.get(aee, ''),
    })
    
#Add New Project
#https://stackoverflow.com/questions/18806668/django-form-showing-no-input-fields
#https://simpleisbetterthancomplex.com/article/2017/08/19/how-to-render-django-form-manually.html

@login_required
def project(request):
    form = ProjectAdd(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            #strategy.save()
            return HttpResponseRedirect("view.html")
    else:
        form = ProjectAdd()

    return render(request, 'project/add.html', {
        'form': form 
    })

#Action Detail
@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    return render(request, 'project/detail.html', {'project': project})

#Edit Project
@login_required
def get_absolute_url(self):
    return reverse('Project.views.project_edit', args=[str(self.id)])	

@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    ref_url = request.META.get('HTTP_REFERER', '/')
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = ProjectEdit(request.POST, instance=project)
        if form.is_valid():
            project = form.save(commit=False)
            project.modified_date = timezone.now()
            if 'approve' in request.POST:
                project.approved = True
                project.status = 'Pending Assignment'
            project.save()
            if 'approve' in request.POST:
                return redirect('project:all')
            return HttpResponseRedirect(next)
    else:
        title = "Edit Project"
        form = ProjectEdit(instance=project)
    return render(request, 'project/edit.html', {'form': form, 'title': title})

@login_required
def project_edit_manager(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    ref_url = request.META.get('HTTP_REFERER', '/')
    next = request.POST.get('next', '/')
    is_admin = getattr(getattr(request.user, 'profile', None), 'role', '') == 'admin'
    if request.method == "POST":
        form = ProjectEditManager(request.POST, instance=project)
        if not is_admin:
            form.fields['value'].disabled = True
        if form.is_valid():
            project = form.save(commit=False)
            #project.author = request.user
            project.modified_date = timezone.now()
            project.save()
            return HttpResponseRedirect(next)
    else:
        title = "Edit Project"
        form = ProjectEditManager(instance=project)
        if not is_admin:
            form.fields['value'].disabled = True
    return render(request, 'project/edit_manager.html', {'form': form, 'title': title})


   
@login_required
def project_value(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    ref_url = request.META.get('HTTP_REFERER', '/')
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = ProjectValue(request.POST, instance=project)
        form.fields['project'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
        if form.is_valid():
            project = form.save(commit=False)
            project.modified_date = timezone.now()
            project.save()
            return HttpResponseRedirect(next)
    else:
        title = "Value Project"
        form = ProjectValue(instance=project)
        form.fields['project'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
    return render(request, 'project/add_value.html', {'form': form, 'title': title})



@login_required
def project_loe(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    ref_url = request.META.get('HTTP_REFERER', '/')
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = ProjectLoe(request.POST, instance=project)
        form.fields['project'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
        form.fields['value'].disabled = True
        if form.is_valid():
            project = form.save(commit=False)
            project.modified_date = timezone.now()
            project.save()
            return HttpResponseRedirect(next)
    else:
        title = "Estimate Level of Effort"
        form = ProjectLoe(instance=project)
        form.fields['project'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
        form.fields['value'].disabled = True
    return render(request, 'project/add_loe.html', {'form': form, 'title': title})



# Projects that need Valued
@login_required
def value(request):
    vertical_id = _get_vertical_id(request)
    projects = Action.objects.filter(value=0)
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)
    title = "Assign Value"
    return render(request, 'project/value.html', {'projects': projects, 'title': title})

# Projects that need LOE
@login_required
def loe(request):
    vertical_id = _get_vertical_id(request)
    projects = Action.objects.filter(level_of_effort=0)
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)
    title = "Assign Level of Effort"
    return render(request, 'project/loe.html', {'projects': projects, 'title': title})

# Projects that need approval
@login_required
def approve(request):
    vertical_id = _get_vertical_id(request)
    projects = Action.objects.filter(approved__exact='False', normalized_score__gt=0).exclude(status__in=['WIP', 'Pending Assignment'])
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)
    title = "Approve and Prioritize"
    return render(request, 'project/approvals.html', {'projects': projects, 'title': title})
    
    
@login_required
def add_comment_to_project(request, project_id):
    project = get_object_or_404(Action, pk=project_id)
    ref_url = request.META.get('HTTP_REFERER', '/')
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.action = project
            comment.save()
        #return redirect(ref_url, {'project': project})    
    #return render(request, 'project/detail.html', {'project': project})
        return HttpResponseRedirect(next)

    else:
        form = CommentForm()
    return render(request, 'project/add_comment_to_project.html', {'form': form})


def approve_project(request, project_id):
    project = Action.objects.get(pk=project_id)
    next_url = request.GET.get('next', request.POST.get('next', '/project/approvals.html'))
    project.approved = not project.approved
    project.save()
    return HttpResponseRedirect(next_url)

def delete(request, project_id):
    object = Action.objects.get(pk=project_id)
    object.delete()
    return redirect("view.html")


@login_required
def archive(request):
    """View archived (launched) projects with pagination."""
    vertical_id = _get_vertical_id(request)
    archived_projects = Action.objects.filter(archived=True).order_by('-launch', '-date_modified')
    if vertical_id:
        archived_projects = archived_projects.filter(vertical_id=vertical_id)
    paginator = Paginator(archived_projects, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'project/archive.html', {
        'page_obj': page_obj,
        'title': 'Archived Projects',
    })


@login_required
def kanban_view(request):
    """Render the Kanban board."""
    vertical_id = _get_vertical_id(request)
    projects = Action.objects.filter(archived=False).select_related(
        'project', 'business_unit', 'vertical', 'owner',
    )
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)

    grouped = group_projects(projects)
    lane_totals = compute_all_lane_totals(grouped)

    lanes_data = []
    for key, label in LANES.items():
        lanes_data.append({
            'key': key,
            'label': label,
            'projects': grouped[key],
            'totals': lane_totals[key],
            'count': len(grouped[key]),
        })

    return render(request, 'project/kanban.html', {
        'lanes_data': lanes_data,
        'lane_totals_json': json.dumps(lane_totals),
        'title': 'Kanban Board',
    })


@require_POST
@login_required
def kanban_move(request):
    """AJAX endpoint: move a project to a new Kanban lane."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    project_id = data.get('project_id')
    target_lane = data.get('target_lane')

    if not project_id or not target_lane:
        return JsonResponse({'ok': False, 'error': 'Missing project_id or target_lane'}, status=400)

    project = get_object_or_404(Action, pk=project_id)
    ok, err = apply_move(project, target_lane)

    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=422)

    # Recompute all lane totals after the move
    vertical_id = data.get('vertical_id')
    qs = Action.objects.filter(archived=False)
    if vertical_id:
        try:
            qs = qs.filter(vertical_id=int(vertical_id))
        except (ValueError, TypeError):
            pass

    grouped = group_projects(qs)
    lane_totals = compute_all_lane_totals(grouped)
    lane_counts = {key: len(projects) for key, projects in grouped.items()}

    return JsonResponse({
        'ok': True,
        'lane_totals': lane_totals,
        'lane_counts': lane_counts,
    })