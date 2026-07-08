from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.utils import timezone
from .forms import StrategyAdd, StrategyEdit, CommentForm
from .models import Project, Objective, Metric, KPI
from django.contrib.auth.decorators import login_required
from django.db.models import Sum

# Create your views here.
@login_required

#Add New Quarterly Rock
def strategy(request):
    form = StrategyAdd(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return HttpResponseRedirect("view.html")
    else:
        form = StrategyAdd()

    return render(request, 'strategy/add.html', {
        'form': form
    })

#Edit Quarterly Rock
@login_required
def strategy_edit(request, strategy_id):
    strategy = get_object_or_404(Project, pk=strategy_id)
    if request.method == "POST":
        form = StrategyEdit(request.POST, instance=strategy)
        if form.is_valid():
            strategy = form.save(commit=False)
            strategy.modified_date = timezone.now()
            strategy.save()
            return redirect('strategy:strategy_detail', strategy_id=strategy.pk)
    else:
        form = StrategyEdit(instance=strategy)
    return render(request, 'strategy/edit.html', {'form': form})

# View All Quarterly Rocks Page
@login_required
def strategy_view(request):
    context = {}
    strategies = Project.objects.all()
    return render(request, 'strategy/view.html', {'strategies': strategies})


#View Quarterly Rock Detail
@login_required
def strategy_detail(request, strategy_id):
	strategy = get_object_or_404(Project, pk=strategy_id)
	return render(request, 'strategy/detail.html', {'strategy': strategy})

@login_required
def add_comment_to_strategy(request, strategy_id):
    strategy = get_object_or_404(Project, pk=strategy_id)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.project = strategy
            comment.save()
            return render(request, 'strategy/detail.html', {'strategy': strategy})
    else:
        form = CommentForm()
    return render(request, 'strategy/add_comment_to_strategy.html', {'form': form})


@login_required
def edit_rocks(request):
    """SuperUser-only view to manage Annual Rocks and Quarterly Rocks."""
    if not request.user.is_superuser and not request.user.groups.filter(name='A-Team').exists():
        return redirect('app:index')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_annual_rock':
            name = request.POST.get('ar_name', '').strip()
            description = request.POST.get('ar_description', '').strip()
            year = request.POST.get('ar_year', '').strip()
            if name:
                Objective.objects.create(
                    name=name,
                    description=description,
                    year=int(year) if year else None,
                )

        elif action == 'delete_annual_rock':
            rock_id = request.POST.get('rock_id')
            Objective.objects.filter(pk=rock_id).delete()

        elif action == 'edit_annual_rock':
            rock_id = request.POST.get('rock_id')
            rock = get_object_or_404(Objective, pk=rock_id)
            rock.name = request.POST.get('ar_name', rock.name).strip()
            rock.description = request.POST.get('ar_description', rock.description).strip()
            year = request.POST.get('ar_year', '').strip()
            rock.year = int(year) if year else None
            rock.save()

        return redirect('strategy:edit_rocks')

    annual_rocks = Objective.objects.all()
    quarterly_rocks = Project.objects.all()
    return render(request, 'strategy/edit_rocks.html', {
        'annual_rocks': annual_rocks,
        'quarterly_rocks': quarterly_rocks,
    })


@login_required
def measurement(request):
    """SuperUser-only view to manage Metrics and KPIs via transfer lists."""
    if not request.user.is_superuser:
        return redirect('app:index')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_metric':
            name = request.POST.get('name', '').strip()
            if name:
                Metric.objects.create(name=name, active=True)

        elif action == 'add_kpi':
            name = request.POST.get('name', '').strip()
            if name:
                KPI.objects.create(name=name, active=True)

        elif action == 'activate_metric':
            item_id = request.POST.get('item_id')
            Metric.objects.filter(pk=item_id).update(active=True)

        elif action == 'deactivate_metric':
            item_id = request.POST.get('item_id')
            Metric.objects.filter(pk=item_id).update(active=False)

        elif action == 'activate_kpi':
            item_id = request.POST.get('item_id')
            KPI.objects.filter(pk=item_id).update(active=True)

        elif action == 'deactivate_kpi':
            item_id = request.POST.get('item_id')
            KPI.objects.filter(pk=item_id).update(active=False)

        return redirect('strategy:measurement')

    active_metrics = Metric.objects.filter(active=True)
    inactive_metrics = Metric.objects.filter(active=False)
    active_kpis = KPI.objects.filter(active=True)
    inactive_kpis = KPI.objects.filter(active=False)

    return render(request, 'strategy/measurement.html', {
        'active_metrics': active_metrics,
        'inactive_metrics': inactive_metrics,
        'active_kpis': active_kpis,
        'inactive_kpis': inactive_kpis,
    })
