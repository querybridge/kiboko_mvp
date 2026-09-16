from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.forms import ModelForm
from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime
from .model_field_options import *
from project.project_field_options import (AEE_ALIGNMENT_CHOICES, status_options,
                                            EFFORT_SIZE_CHOICES, LEVER_CHOICES, CAPABILITY_CHOICES)

# Create your all your models here

##############################################################################################################################################################
## DB Models                                                                                                                                                ##
##############################################################################################################################################################
#
# Planning hierarchy (top -> bottom):
#   Objective (annual horizon, measured by a KPI)
#     -> Project (quarterly horizon, measured by a Metric)        [this app]
#         -> Action (execution unit, measured by a Measure)       [project app]
#
# NOTE: app directories keep their original names (`strategy`, `project`) to
# avoid churn; the *models* carry the current hierarchy names.

########################################
## KPI / Metric / Measure (reference) ##
########################################

class KPI(models.Model):
    """Annual performance indicator attached to an Objective -- e.g. MTS,
    Average Order Value, Conversion Rate."""
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'KPI'
        verbose_name_plural = 'KPIs'

    def __str__(self):
        return self.name


class Metric(models.Model):
    """Quarterly metric attached to a Project -- e.g. users, product views,
    add to carts."""
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Measure(models.Model):
    """Action-level measure -- the most granular quantity a Action moves."""
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


########################################
## Objective (Annual) DB Model        ##
########################################

class Objective(models.Model):
    """Top-level annual strategic priority, measured by a KPI.

    Every objective aligns to one AEE element (Attract / Engage / Expand); the
    Projects and Actions beneath it inherit that alignment (AEE > Objective >
    Project > Action)."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    year = models.IntegerField(null=True, blank=True)
    kpi = models.ForeignKey(KPI, on_delete=models.SET_NULL, null=True, blank=True)
    aee_alignment = models.CharField(max_length=50, choices=AEE_ALIGNMENT_CHOICES, blank=True, default='')

    class Meta:
        verbose_name = 'Objective'
        verbose_name_plural = 'Objectives'
        ordering = ['-year', 'name']

    def __str__(self):
        if self.year:
            return f"{self.name} ({self.year})"
        return self.name


########################################
## Project (Quarterly) DB Model       ##
########################################

class Project(models.Model):
    """Quarterly project supporting an Objective, measured by a Metric.

    The Project is the prioritized/scored unit: it carries the workflow
    (approval, revenue, level of effort, the BVM score, and the Kanban lane).
    The Actions beneath it (project.Action) are the execution tasks that appear
    on the WIP gantt."""
    date_created = models.DateField(auto_now_add=True, editable=False)
    date_modified = models.DateField(auto_now=True, editable=False)
    name = models.CharField(max_length=75, null=True)
    impact = models.CharField(max_length=75, null=True)
    goal = models.CharField(max_length=75, null=True)
    objective = models.ForeignKey(Objective, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    metric = models.ForeignKey(Metric, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey('business_unit.Department', on_delete=models.SET_NULL, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    quarter = models.IntegerField(choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')], null=True, blank=True)
    level = models.CharField(max_length=75, choices=level_options, blank=False, null=True, default="Corporate")
    competitive_position = models.IntegerField(choices=competitive_position_dict, null=True, blank=True, default=63)
    purpose = models.CharField(max_length=75, choices=purpose_options, blank=False, null=True, default="New Growth")
    why = models.TextField(max_length=400)
    definition_of_done = models.CharField(max_length=350, blank=True)
    target_completion = models.DateField(null=True, blank=True)

    # --- Prioritization workflow (moved up from Action) --------------------
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_projects')
    # Tenancy: which BusinessUnit (GA4 property / company unit) this rolls up to.
    vertical = models.ForeignKey('business_unit.BusinessUnit', on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    value = models.IntegerField(default=0, null=True, blank=True)          # projected gross revenue impact ($/yr) -- computed by the estimator
    # Lead-developer t-shirt sizing -- feeds the algorithmic score (developer only).
    effort_size = models.CharField(max_length=4, choices=EFFORT_SIZE_CHOICES, blank=True, default='')
    level_of_effort = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])  # legacy; no longer voted

    # --- Impact estimation (the auto-derived "Kiboko estimated impact") ---
    lever = models.CharField(max_length=30, choices=LEVER_CHOICES, blank=True, default='')
    target_from = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)  # baseline lever level
    target_to = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)    # proposed level
    s0_annual = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)     # baseline annual sales
    ramp_days = models.PositiveSmallIntegerField(default=30)
    capability = models.CharField(max_length=12, choices=CAPABILITY_CHOICES, blank=True, default='')  # developer only
    direct_expense = models.IntegerField(default=0)
    plausibility_factor = models.FloatField(default=1.0)        # target plausibility risk-adjustment (P)
    algo_raw = models.FloatField(null=True, blank=True)          # raw algorithmic priority (kiboko_raw)
    voted_score = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)  # BVM weighted vote (0-10)
    # Five voted BVM criteria (0-10); level_of_effort above is the 6th, set by a developer.
    customer_value = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    business_value = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    cost_savings = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    operational_cost = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    business_risk = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    normalized_score = models.DecimalField(max_digits=4, decimal_places=1, editable=False, null=True, default=0)
    approved = models.BooleanField(default=False)
    status = models.CharField(choices=status_options, max_length=350, null=True, blank=True, default=None)
    is_blocked = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

    @property
    def aee_alignment(self):
        """Inherited from the objective (single source of truth: AEE > Objective)."""
        return self.objective.aee_alignment if self.objective_id else ''

    def get_aee_alignment_display(self):
        return dict(AEE_ALIGNMENT_CHOICES).get(self.aee_alignment, '')

    def _company(self):
        bu = self.vertical
        return getattr(bu, 'company', None) if bu else None

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._db_status = instance.status
        return instance

    def _estimate(self):
        """Run the impact estimator from the stored inputs; None if incomplete."""
        from project.services import impact
        from project.models import EstimatorSettings
        if not (self.lever and self.target_from and self.target_to and self.s0_annual):
            return None
        return impact.estimate(
            target_from=float(self.target_from), target_to=float(self.target_to),
            s0_annual=float(self.s0_annual), launch=self.target_completion,
            ramp_days=self.ramp_days, capability=self.capability or 'mostly',
            effort=self.effort_size or 'M', direct_expense=self.direct_expense or 0,
            margin_factor=EstimatorSettings.margin_for(self._company()),
            plausibility_factor=self.plausibility_factor or 1.0)

    def save(self, *args, **kwargs):
        # Voted component: BVM weighted average of the voted criteria (LOE dropped
        # -- effort is a developer input on the algorithmic side).
        from project.scoring import weighted_score, voted_weights, VOTED_CRITERIA
        from project.models import ScoringWeights
        from project.services.kanban import derive_status
        values = {c: getattr(self, c, 0) or 0 for c in VOTED_CRITERIA}
        vs = weighted_score(values, weights=voted_weights(ScoringWeights.for_company(self._company())))
        self.voted_score = Decimal(str(vs)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        # Algorithmic side: gross revenue impact -> `value`, raw priority -> algo_raw.
        est = self._estimate()
        if est is not None:
            self.value = int(round(est['gross_annual']))
            self.algo_raw = est['kiboko_raw']
        # normalized_score (the blended final) is set by impact.recompute_scores()
        # after a vote finalizes / estimate changes -- it needs the backlog.
        self.status = derive_status(self)
        self.is_blocked = (self.status == 'Blocked')
        if self.status == 'Launched':
            self.archived = True
        super().save(*args, **kwargs)
        self._db_status = self.status

    def __str__(self):
        return self.name


class ProjectComment(models.Model):
    project = models.ForeignKey('strategy.Project', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_date = models.DateTimeField(auto_now_add=True, editable=False)
    approved_comment = models.BooleanField(default=False)

    def approve(self):
        self.approved_comment = True
        self.save()

    def __str__(self):
        return self.text


class AnnualGoals(models.Model):
    ic_goal = models.IntegerField(null=True, blank=True, default=35000000)
    ips_goal = models.IntegerField(null=True, blank=True, default=550)
    ipf_goal = models.FloatField(null=True, blank=True, default=1.5)
    combined_revenue_goal = models.IntegerField(null=True, blank=True, default=350000000)

    class Meta:
        verbose_name_plural = 'Annual Goals'
