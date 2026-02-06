from django.contrib import admin
from strategy.models import Strategy, StrategyComment, StrategyGoals, AnnualRock, Metric, KPI
from project.models import Project, Comment
from business_unit.models import BusinessUnit, Vertical

# Register your models here.

admin.site.register(Strategy)
admin.site.register(StrategyComment)
admin.site.register(StrategyGoals)
admin.site.register(AnnualRock)
admin.site.register(Metric)
admin.site.register(KPI)
admin.site.register(Project)
admin.site.register(Comment)
admin.site.register(BusinessUnit)
admin.site.register(Vertical)
