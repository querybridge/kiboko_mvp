import inspect
import warnings
from functools import partial
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Max, Min, Sum, F, Q
from django.db import models
from django.forms import ModelForm
from django import forms
from django.contrib.auth.models import User
from multiselectfield import MultiSelectField
import datetime
from strategy.models import Strategy
from business_unit.models import BusinessUnit
from computedfields.models import ComputedFieldsModel, computed
from .project_field_options import *
from .scoring import BvmScore

# Create your all your models here

########################################
## Project DB Model                   ##
########################################

#Project Class

class Project(models.Model):
	strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, blank=True, related_name='projects')
	owner = models.ForeignKey(User, on_delete=models.CASCADE)
	date_created = models.DateField(auto_now_add=True, editable=False)
	date_modified = models.DateField(auto_now=True, editable=False)
	name = models.CharField(max_length=350, blank=True)
	impact = models.CharField(max_length=350, blank=True, verbose_name='Definition of Done')
	success = models.CharField(max_length=350, blank=True)
	alignment = models.CharField(max_length=350, choices=alignment_options, blank=False, null=True, default="Impress")
	locations = MultiSelectField(max_length=300, choices=locations, blank=True)
	engagement = models.CharField(max_length=350, choices=engagement_options, blank=False, null=True, default="Click")
	competitive_position = models.IntegerField(choices=competitive_position_dict, null=True, blank=True, default=63 ) #Change to Integer Field
	purpose = models.CharField(max_length=350, choices=purpose_options, blank=False, null=True, default="New Growth")
	why = models.TextField(max_length=500, blank=True, verbose_name='User Story')
	loe = models.CharField(max_length=350, choices=loe, blank=True, null=True, default="NA")
	value = models.IntegerField(blank=True, null=True, default=0)
	progress = models.IntegerField(blank=True, null=True, default=0)
	scored = models.BooleanField(null=True, blank=True, editable=False)
	valued = models.BooleanField(null=True, blank=True, editable=False)
	launch = models.DateField(null=True, blank=True)
	score = models.IntegerField(editable=False, null=True, default=0)
	normalized_score = models.DecimalField(max_digits=4, decimal_places=1, editable=False, null=True, default=0)
	priority = models.IntegerField(editable=False, null=True, default=0)
	approved = models.BooleanField(default=False)
	status = models.CharField(choices=status_options, max_length=350, null=True, default='Pending Approval')
	archived = models.BooleanField(default=False)
	viability = models.CharField(max_length=350, choices=viability_options, blank=False, null=True, default='Steep Climb')
	business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE)

	def save(self, *args, **kwargs):
		strategy_level = 'level'
		strategy_obj = Strategy.objects.first()
		strategy_field_object = Strategy._meta.get_field(strategy_level)
		strategy_level_value = strategy_field_object.value_from_object(strategy_obj)

		strategy_objective = 'objective'
		strategy_field_object_objective = Strategy._meta.get_field(strategy_objective)
		strategy_level_alignment = strategy_field_object_objective.value_from_object(strategy_obj)

		max_score = Project.objects.all().aggregate(Max('score'))
		total_score = Project.objects.all().aggregate(Sum('score'))

		self.score = BvmScore(self.value, self.loe, strategy_level_alignment, self.viability, self.purpose, strategy_level_value).score_project()

		# Auto-archive when status is Launched
		if self.status == 'Launched':
			self.archived = True

		super().save(*args, **kwargs)

		# Recompute normalized scores for all projects
		Project.normalize_all_scores()

	@staticmethod
	def normalize_all_scores():
		"""
		Normalize all project scores to 10-100 range using min-max scaling.
		Lowest score -> 10, highest score -> 100.
		Ties are broken with small epsilon based on pk to ensure uniqueness.
		"""
		projects = list(Project.objects.all().order_by('score', 'pk'))
		if not projects:
			return

		scores = [p.score or 0 for p in projects]
		min_score = min(scores)
		max_score = max(scores)

		# If all scores are the same, assign midpoint (55.0) with epsilon tie-break
		if max_score == min_score:
			for rank, p in enumerate(projects):
				epsilon = Decimal(str(rank * 0.1))
				p.normalized_score = Decimal('55.0') + epsilon
		else:
			score_range = max_score - min_score
			for rank, p in enumerate(projects):
				raw = p.score or 0
				# Min-max scaling to 10-100 range
				normalized = 10 + ((raw - min_score) / score_range) * 90
				# Round to 1 decimal place
				normalized = Decimal(str(normalized)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
				# Add small epsilon based on rank for tie-breaking (0.01 increments won't affect display)
				epsilon = Decimal(str(rank * 0.01))
				p.normalized_score = normalized + epsilon

		# Bulk update to avoid triggering save() recursion
		Project.objects.bulk_update(projects, ['normalized_score'])

	def approve(self):
		self.approved_score = True
		self.save()
	
	class Meta:
		verbose_name_plural = 'Projects'
		ordering = ['-score']

	def __str__(self):
		return self.name

		
class Comment(models.Model):
	project = models.ForeignKey('project.Project', on_delete=models.CASCADE, related_name='comments')
	author = models.ForeignKey(User, on_delete=models.CASCADE)
	text = models.TextField()
	created_date = models.DateTimeField(auto_now_add=True, editable=False)
	approved_comment = models.BooleanField(default=False)
	
	def approve(self):
		self.approved_comment = True
		self.save()
		
	def __str__(self):
		return self.text
