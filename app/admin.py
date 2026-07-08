from django.contrib import admin
from strategy.models import Project, ProjectComment, AnnualGoals, Objective, Metric, KPI, Measure
from project.models import Action, ActionComment
from business_unit.models import BusinessUnit, Vertical

# Register your models here.

admin.site.register(Objective)
admin.site.register(Project)
admin.site.register(ProjectComment)
admin.site.register(AnnualGoals)
admin.site.register(Metric)
admin.site.register(KPI)
admin.site.register(Measure)
admin.site.register(Action)
admin.site.register(ActionComment)
admin.site.register(BusinessUnit)
admin.site.register(Vertical)
