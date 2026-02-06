from django.db import models
from django.forms import ModelForm
from django import forms
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime

# Create your models here.


class Vertical(models.Model):
    name = models.CharField(max_length=140)

    class Meta:
        verbose_name = 'Vertical'
        verbose_name_plural = 'Verticals'

    def __str__(self):
        return self.name


class BusinessUnit(models.Model):
	name = models.CharField(max_length=140)
	owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

	class Meta:
		verbose_name = 'Department'
		verbose_name_plural = 'Departments'

	def __str__(self):
		return self.name
