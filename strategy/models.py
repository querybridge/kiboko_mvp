from django.db import models
from django.forms import ModelForm
from django import forms
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime
from .model_field_options import *

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
    """Top-level annual strategic priority, measured by a KPI."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    year = models.IntegerField(null=True, blank=True)
    kpi = models.ForeignKey(KPI, on_delete=models.SET_NULL, null=True, blank=True)

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
    """Quarterly project supporting an Objective, measured by a Metric."""
    date_created = models.DateField(auto_now_add=True, editable=False)
    date_modified = models.DateField(auto_now=True, editable=False)
    name = models.CharField(max_length=75, null=True)
    impact = models.CharField(max_length=75, null=True)
    goal = models.CharField(max_length=75, null=True)
    objective = models.ForeignKey(Objective, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    metric = models.ForeignKey(Metric, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey('business_unit.BusinessUnit', on_delete=models.SET_NULL, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    quarter = models.IntegerField(choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')], null=True, blank=True)
    level = models.CharField(max_length=75, choices=level_options, blank=False, null=True, default="Corporate")
    competitive_position = models.IntegerField(choices=competitive_position_dict, null=True, blank=True, default=63)
    purpose = models.CharField(max_length=75, choices=purpose_options, blank=False, null=True, default="New Growth")
    why = models.TextField(max_length=400)
    definition_of_done = models.CharField(max_length=350, blank=True)
    target_completion = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

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
