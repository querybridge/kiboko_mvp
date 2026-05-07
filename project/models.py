from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from multiselectfield import MultiSelectField
from strategy.models import Strategy, AnnualRock, Metric, KPI
from business_unit.models import BusinessUnit, Vertical, Team
from .project_field_options import locations, status_options, STRATEGY_TAG_CHOICES
from .scoring import CRITERIA, weighted_score

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
	locations = MultiSelectField(max_length=300, choices=locations, blank=True)
	why = models.TextField(max_length=500, blank=True, verbose_name='User Story')
	value = models.IntegerField(blank=True, null=True, default=0)
	progress = models.IntegerField(blank=True, null=True, default=0)
	launch = models.DateField(null=True, blank=True)
	active_date = models.DateField(null=True, blank=True, editable=False)
	normalized_score = models.DecimalField(max_digits=4, decimal_places=1, editable=False, null=True, default=0)
	approved = models.BooleanField(default=False)
	status = models.CharField(choices=status_options, max_length=350, null=True, default='Pending Approval')
	archived = models.BooleanField(default=False)
	business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE)

	# New fields
	annual_rock = models.ForeignKey(AnnualRock, on_delete=models.SET_NULL, null=True, blank=True)
	vertical = models.ForeignKey(Vertical, on_delete=models.SET_NULL, null=True, blank=True)
	metric = models.ForeignKey(Metric, on_delete=models.SET_NULL, null=True, blank=True)
	kpi = models.ForeignKey(KPI, on_delete=models.SET_NULL, null=True, blank=True)
	team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)

	# --- 6 scoring criteria (each 0-10) ---
	customer_value = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_value = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	cost_savings = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	operational_cost = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_risk = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	level_of_effort = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])

	# Kanban fields
	is_blocked = models.BooleanField(default=False)
	strategy_tag = models.CharField(max_length=50, choices=STRATEGY_TAG_CHOICES, blank=True, default='')
	impact_visits_value = models.IntegerField(default=0, null=True, blank=True)
	impact_close_rate_value = models.IntegerField(default=0, null=True, blank=True)
	impact_aov_value = models.IntegerField(default=0, null=True, blank=True)

	@property
	def project_value_total(self):
		return (self.impact_visits_value or 0) + (self.impact_close_rate_value or 0) + (self.impact_aov_value or 0)

	@classmethod
	def from_db(cls, db, field_names, values):
		instance = super().from_db(db, field_names, values)
		instance._db_status = instance.status
		return instance

	def save(self, *args, **kwargs):
		# Compute weighted score from 6 criteria -> 0-10 scale
		values = {c: getattr(self, c, 0) or 0 for c in CRITERIA}
		score = weighted_score(values)
		self.normalized_score = Decimal(str(score)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

		# Stamp active_date the first time status transitions to Active
		previous_status = getattr(self, '_db_status', None)
		became_active = self.status == 'Active' and previous_status != 'Active'
		if became_active and not self.active_date:
			self.active_date = date.today()

		# Auto-archive when status is Launched
		if self.status == 'Launched':
			self.archived = True

		super().save(*args, **kwargs)
		self._db_status = self.status

	def approve(self):
		self.approved_score = True
		self.save()

	class Meta:
		verbose_name_plural = 'Projects'
		ordering = ['-normalized_score']

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
