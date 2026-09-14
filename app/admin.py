from django.contrib import admin
from strategy.models import Project, ProjectComment, AnnualGoals, Objective, Metric, KPI, Measure
from project.models import Action, ActionComment
from business_unit.models import Department, BusinessUnit, Organization, Company, CompanyMembership
from app.models import MetricRecommendation, SendGridSettings


@admin.register(MetricRecommendation)
class MetricRecommendationAdmin(admin.ModelAdmin):
    list_display = ('metric', 'direction', 'order', 'text', 'active')
    list_filter = ('metric', 'direction', 'active')
    list_editable = ('order', 'active')
    search_fields = ('text',)
    ordering = ('metric', 'direction', 'order')


@admin.register(SendGridSettings)
class SendGridSettingsAdmin(admin.ModelAdmin):
    list_display = ('from_email', 'from_name', 'feedback_to', 'active', 'is_configured', 'updated')
    fields = ('api_key', 'from_email', 'from_name', 'feedback_to', 'active')

    @admin.display(boolean=True, description='Configured')
    def is_configured(self, obj):
        return obj.is_configured

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
admin.site.register(Department)
admin.site.register(BusinessUnit)
admin.site.register(Organization)
admin.site.register(Company)
admin.site.register(CompanyMembership)
