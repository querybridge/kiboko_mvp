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

########################################
## Strategy DB Model                  ##
########################################

#Global Strategy List Options
#Strategy Class

class Strategy(models.Model):
	#modified_by = models.ForeignKey('auth.User', editable=False, null=True)
	date_created = models.DateField(auto_now_add=True, editable=False)
	date_modified = models.DateField(auto_now=True, editable=False)
	name = models.CharField(max_length=75, null=True)	
	impact = models.CharField(max_length=75, null=True)
	goal = models.CharField(max_length=75, null=True)
	#launch = models.DateField(name="Launch Date", null=True)
	objective = models.CharField(max_length=75, choices=objective_options, blank=False, null=True, default="IC")
	level = models.CharField(max_length=75, choices=level_options, blank=False, null=True, default="Corporate")
	business_unit = models.CharField(max_length=75, choices=businessUnit_options, null=True, blank=True)
	competitive_position = models.IntegerField(choices=competitive_position_dict, null=True, blank=True, default=63)
	purpose = models.CharField(max_length=75, choices=purpose_options, blank=False, null=True, default="New Growth")
	why = models.TextField(max_length=400)
	
	class Meta:
		verbose_name_plural = 'Strategies'
	
	def __str__(self):
		return self.name

class StrategyComment(models.Model):
	strategy = models.ForeignKey('strategy.Strategy', on_delete=models.CASCADE, related_name='comments')
	author = models.ForeignKey(User, on_delete=models.CASCADE)
	text = models.TextField()
	created_date = models.DateTimeField(auto_now_add=True, editable=False)
	approved_comment = models.BooleanField(default=False)
	
	def approve(self):
		self.approved_comment = True
		self.save()
		
	def __str__(self):
		return self.text

class StrategyGoals(models.Model):
	ic_goal = models.IntegerField(null=True, blank=True, default=35000000)
	ips_goal = models.IntegerField(null=True, blank=True, default=550)
	ipf_goal = models.FloatField(null=True, blank=True, default=1.5)
	combined_revenue_goal = models.IntegerField(null=True, blank=True, default=350000000)
	
	class Meta:
		verbose_name_plural = 'Strategy Goals'