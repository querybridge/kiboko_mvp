from django.shortcuts import render, get_object_or_404
from django.template import loader
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from .forms import StrategyAdd, StrategyForm, StrategyEdit, StrategyAdd2, CommentForm
from .models import Strategy
from django.contrib.auth.decorators import login_required
from django.db.models import Sum

# Create your views here.
@login_required
    
#Add New Strategy
def strategy(request):
#https://stackoverflow.com/questions/18806668/django-form-showing-no-input-fields
#https://simpleisbetterthancomplex.com/article/2017/08/19/how-to-render-django-form-manually.html
    form = StrategyAdd(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            #strategy.save()
            return HttpResponseRedirect("view.html")
    else:
        form = StrategyAdd()

    return render(request, 'strategy/add.html', {
        'form': form 
    })

#Edit Strategy
@login_required
def strategy_edit(request, project_id):
    stragety = get_object_or_404(Strategy, pk=strategy_id)
    if request.method == "POST":
        form = StrategyEdit(request.POST, instance=strategy)
        if form.is_valid():
            strategy = form.save(commit=False)
            #project.author = request.user
            strategy.modified_date = timezone.now()
            strategy.save()
            return redirect('strategy_detail', pk=strategy.pk)
    else:
        form = StrategyEdit(instance=strategy)
    return render(request, 'strategy/edit.html', {'form': form})

# View All Strategy Page
@login_required
def strategy_view(request):
    context = {}
    strategies = Strategy.objects.all()
    return render(request, 'strategy/view.html', {'strategies': strategies})


#Edit Strategy
@login_required
def strategy_detail(request, strategy_id):
	strategy = get_object_or_404(Strategy, pk=strategy_id)
	return render(request, 'strategy/detail.html', {'strategy': strategy})

@login_required
def add_comment_to_strategy(request, strategy_id):
    strategy = get_object_or_404(Strategy, pk=strategy_id)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.strategy = strategy
            comment.save()
            return render(request, 'strategy/detail.html', {'strategy': strategy})
    else:
        form = CommentForm()
    return render(request, 'strategy/add_comment_to_strategy.html', {'form': form})  

