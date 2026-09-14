from django.contrib import admin

from .models import ScoringWeights
from .scoring import CRITERIA


@admin.register(ScoringWeights)
class ScoringWeightsAdmin(admin.ModelAdmin):
    list_display = ('company', *CRITERIA, 'updated')
    search_fields = ('company__name',)
