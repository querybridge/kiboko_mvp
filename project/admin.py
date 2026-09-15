from django.contrib import admin

from .models import ScoringWeights, ScoreVote
from .scoring import CRITERIA, VOTED_CRITERIA


@admin.register(ScoringWeights)
class ScoringWeightsAdmin(admin.ModelAdmin):
    list_display = ('company', *CRITERIA, 'updated')
    search_fields = ('company__name',)


@admin.register(ScoreVote)
class ScoreVoteAdmin(admin.ModelAdmin):
    list_display = ('project', 'user', *VOTED_CRITERIA, 'updated')
    search_fields = ('project__name', 'user__username', 'user__email')
    list_select_related = ('project', 'user')
