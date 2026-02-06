from django.forms import ModelForm
from .models import Strategy
from django import forms


class Strategy(ModelForm):
    class Meta:
        model = Strategy
        fields = ['name', 'desired_impact', 'def_of_success', 'alignment', 'level', 'purpose']

class StrategyForm(forms.Form):
	name = forms.CharField(max_length=30)	
	desired_impact = forms.CharField(max_length=30)
	def_of_success = forms.CharField(max_length=30)