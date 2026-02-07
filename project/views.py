from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from .models import Project, Strategy
from .forms import ProjectAdd, ProjectEdit, CommentForm, ProjectValue, ProjectLoe, ProjectEditManager
from business_unit.models import BusinessUnit
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q

#from .models import Project
@login_required
# Create your views here.

# View All Projects Page
def view(request):
    context = {}
    title = ""
    # Exclude archived projects
    # Projects that are approved OR have status Pending Assignment/Active go in the approved table
    approved_projects = Project.objects.filter(
        archived=False,
    ).filter(
        Q(approved=True) | Q(status__in=['Pending Assignment', 'Active'])
    )
    owned_bus = BusinessUnit.objects.filter(owner=request.user)
    # Pending = not approved AND not Pending Assignment/Active status
    pending_filter = Q(approved=False, archived=False) & ~Q(status__in=['Pending Assignment', 'Active'])
    if owned_bus.exists():
        pending_projects = Project.objects.filter(pending_filter, business_unit__in=owned_bus)
    else:
        pending_projects = Project.objects.filter(pending_filter)
    return render(request, 'project/view.html', {
        'approved_projects': approved_projects,
        'pending_projects': pending_projects,
        'title': title,
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

#Edit Strategy
@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    return render(request, 'project/detail.html', {'project': project})

#Edit Project
@login_required
def get_absolute_url(self):
    return reverse('Project.views.project_edit', args=[str(self.id)])	

@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    ref_url = request.META['HTTP_REFERER']
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
    project = get_object_or_404(Project, pk=project_id)
    ref_url = request.META['HTTP_REFERER']
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
    project = get_object_or_404(Project, pk=project_id)
    ref_url = request.META['HTTP_REFERER']
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = ProjectValue(request.POST, instance=project)
        form.fields['strategy'].disabled = True
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
        form.fields['strategy'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
    return render(request, 'project/add_value.html', {'form': form, 'title': title})



@login_required
def project_loe(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    ref_url = request.META['HTTP_REFERER']
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = ProjectLoe(request.POST, instance=project)
        form.fields['strategy'].disabled = True
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
        form.fields['strategy'].disabled = True
        form.fields['name'].disabled = True
        form.fields['impact'].disabled = True
        form.fields['value'].disabled = True
    return render(request, 'project/add_loe.html', {'form': form, 'title': title})



# Projects that need Valued
@login_required
def value(request):
    context = {}
    projects = Project.objects.filter(value = 0)
    title = "Assign Value"
    return render(request, 'project/value.html', {'projects': projects, 'title': title})
    
# Projects that need LOE
@login_required
def loe(request):
    context = {}
    projects = Project.objects.filter(level_of_effort=0)
    title = "Assign Level of Effort"
    return render(request, 'project/loe.html', {'projects': projects, 'title': title})

# Projects that need LOE
@login_required
def approve(request):
    context = {}
    projects = Project.objects.filter(approved__exact='False', normalized_score__gt=0)
    title = "Approve and Prioritize"
    return render(request, 'project/approvals.html', {'projects': projects, 'title': title})
    
    
@login_required
def add_comment_to_project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    ref_url = request.META['HTTP_REFERER']
    next = request.POST.get('next', '/')
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.project = project
            comment.save()
        #return redirect(ref_url, {'project': project})    
    #return render(request, 'project/detail.html', {'project': project})
        return HttpResponseRedirect(next)

    else:
        form = CommentForm()
    return render(request, 'project/add_comment_to_project.html', {'form': form})


def approve_project(request, project_id):
    project = Project.objects.get(pk=project_id)
    next_url = request.GET.get('next', request.POST.get('next', '/project/approvals.html'))
    project.approved = not project.approved
    project.save()
    return HttpResponseRedirect(next_url)

def delete(request, project_id):
    object = Project.objects.get(pk=project_id)
    object.delete()
    return redirect("view.html")


@login_required
def archive(request):
    """View archived (launched) projects with pagination."""
    archived_projects = Project.objects.filter(archived=True).order_by('-launch', '-date_modified')
    paginator = Paginator(archived_projects, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'project/archive.html', {
        'page_obj': page_obj,
        'title': 'Archived Projects',
    })