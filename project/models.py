from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from multiselectfield import MultiSelectField
from strategy.models import Project, Objective, Measure
from business_unit.models import Department, BusinessUnit, Team
from .project_field_options import locations, status_options, STRATEGY_TAG_CHOICES, AEE_ALIGNMENT_CHOICES
from .scoring import CRITERIA, DEFAULT_WEIGHTS, weighted_score

# Create your all your models here

########################################
## Action DB Model                    ##
########################################
#
# An Action is the execution unit. It rolls up to a quarterly Project (which
# rolls up to an annual Objective). An Action is measured by a Measure, owned by
# one accountable Owner, and resourced by a Team -- the Owner/Team distinction
# drives the gantt chart's grouping (Team) and accountability (Owner).

class Action(models.Model):
	project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, related_name='actions')
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
	# Blank by default so a new entry derives its starting Kanban column from its
	# own completeness/score (see services.kanban.derive_status). Once placed, the
	# stored column is authoritative.
	status = models.CharField(choices=status_options, max_length=350, null=True, blank=True, default=None)
	archived = models.BooleanField(default=False)
	business_unit = models.ForeignKey(Department, on_delete=models.CASCADE)

	# Hierarchy + measurement
	objective = models.ForeignKey(Objective, on_delete=models.SET_NULL, null=True, blank=True)
	vertical = models.ForeignKey(BusinessUnit, on_delete=models.SET_NULL, null=True, blank=True)
	measure = models.ForeignKey(Measure, on_delete=models.SET_NULL, null=True, blank=True)
	team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)

	# --- 6 scoring criteria (each 0-10) ---
	customer_value = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_value = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	cost_savings = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	operational_cost = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_risk = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	level_of_effort = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])

	# AEE (Attract / Engage / Expand) alignment
	aee_alignment = models.CharField(max_length=50, choices=AEE_ALIGNMENT_CHOICES, blank=True, default='')

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

	def _company(self):
		"""The Company this action rolls up to (via its BusinessUnit), or None."""
		bu = self.vertical
		return getattr(bu, 'company', None) if bu else None

	def save(self, *args, **kwargs):
		# Compute weighted score from 6 criteria -> 0-10 scale, using this
		# company's configured weights (falls back to the platform defaults).
		values = {c: getattr(self, c, 0) or 0 for c in CRITERIA}
		score = weighted_score(values, weights=ScoringWeights.for_company(self._company()))
		self.normalized_score = Decimal(str(score)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

		# Status is the source of truth for the Kanban column; is_blocked mirrors
		# it so the board, the backlog and the edit form all agree.
		from .services.kanban import derive_status
		self.status = derive_status(self)
		self.is_blocked = (self.status == 'Blocked')

		# Stamp active_date the first time status transitions to Active
		previous_status = getattr(self, '_db_status', None)
		became_active = self.status == 'WIP' and previous_status != 'WIP'
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
		verbose_name = 'Action'
		verbose_name_plural = 'Actions'
		ordering = ['-normalized_score']

	def __str__(self):
		return self.name


class ActionComment(models.Model):
	action = models.ForeignKey('project.Action', on_delete=models.CASCADE, related_name='comments')
	author = models.ForeignKey(User, on_delete=models.CASCADE)
	text = models.TextField()
	created_date = models.DateTimeField(auto_now_add=True, editable=False)
	approved_comment = models.BooleanField(default=False)

	def approve(self):
		self.approved_comment = True
		self.save()

	def __str__(self):
		return self.text


class ScoringWeights(models.Model):
	"""Per-company weights for the six BVM scoring criteria.

	Executives and org admins tune a company's model in Settings -> Score
	Weights. A company without a row uses scoring.DEFAULT_WEIGHTS. Weights are
	percentages and must sum to 100 (the weighted score divides by 100 to land
	on a 0-10 scale)."""
	company = models.OneToOneField('business_unit.Company', on_delete=models.CASCADE,
	                               related_name='scoring_weights')
	customer_value = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['customer_value'])
	business_value = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['business_value'])
	cost_savings = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['cost_savings'])
	operational_cost = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['operational_cost'])
	business_risk = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['business_risk'])
	level_of_effort = models.PositiveSmallIntegerField(default=DEFAULT_WEIGHTS['level_of_effort'])
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'Scoring Weights'
		verbose_name_plural = 'Scoring Weights'

	def as_dict(self):
		return {c: getattr(self, c) for c in CRITERIA}

	@classmethod
	def for_company(cls, company):
		"""The weight dict for a company -- its saved row, or the defaults."""
		if company is not None:
			row = cls.objects.filter(company=company).first()
			if row:
				return row.as_dict()
		return dict(DEFAULT_WEIGHTS)

	def __str__(self):
		return f'Score weights for {self.company}'


class ScoreVote(models.Model):
	"""One user's anonymous BVM vote on a project.

	Every pertinent user -- the members of the project's business unit plus the
	company's executives -- scores each project. The project's consensus score is
	the average of all eligible voters' ratings, and it only advances to Scored
	once everyone has voted. Individual votes are never shown (anonymous), which
	keeps the highest-paid person's opinion from dominating."""
	action = models.ForeignKey('project.Action', on_delete=models.CASCADE, related_name='score_votes')
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='score_votes')
	customer_value = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_value = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	cost_savings = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	operational_cost = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	business_risk = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	level_of_effort = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
	created = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = [['action', 'user']]

	def as_values(self):
		return {c: getattr(self, c) for c in CRITERIA}

	def __str__(self):
		return f'{self.user} scored {self.action}'
