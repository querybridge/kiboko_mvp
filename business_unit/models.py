from django.db import models
from django.forms import ModelForm
from django import forms
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime

# Create your models here.


business_unit_names = (
		('Merchandising', 'Merchandising'),
		('Customer Service', 'Customer Service'),
		('Innovation', 'Innovation'),
		('Marketing', 'Marketing'),				
	)

class BusinessUnit(models.Model):
	name = models.CharField(max_length=140, choices=business_unit_names)
	owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

	class Meta:
			verbose_name_plural = 'Business Units'

	def __str__(self):
		return self.name