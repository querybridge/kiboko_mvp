from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateField, DateInput, NumberInput
from .models import Project, Comment
from strategy.models import Metric, KPI
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


class ProjectAdd(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metric'].queryset = Metric.objects.filter(active=True)
        self.fields['kpi'].queryset = KPI.objects.filter(active=True)

    class Meta:
        model = Project
        fields = [
            'annual_rock', 'strategy', 'business_unit', 'vertical',
            'owner', 'name', 'why', 'impact', 'metric', 'kpi',
        ]
        labels = {
            'strategy': 'Quarterly Rock',
            'business_unit': 'Department',
            'annual_rock': 'Annual Rock',
            'vertical': 'Vertical',
            'name': 'Project Name',
            'metric': 'Metric',
            'kpi': 'KPI',
        }
        help_texts = {
            'metric': 'Quantifiable data points and performance indicators such as conversion rates, customer acquisition costs, or average order value',
            'kpi': 'Quantifiable data points measuring performance against strategic goals, such as profitability, growth, and customer satisfaction',
        }
        widgets = {
            'annual_rock': Select(attrs={}),
            'strategy': Select(attrs={}),
            'business_unit': Select(attrs={}),
            'vertical': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'metric': Select(attrs={}),
            'kpi': Select(attrs={}),
        }


class ProjectEdit(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metric'].queryset = Metric.objects.filter(active=True)
        self.fields['kpi'].queryset = KPI.objects.filter(active=True)

    class Meta:
        model = Project
        fields = [
            'name', 'strategy', 'owner', 'status', 'progress', 'launch',
            'impact', 'success', 'why', 'value',
            'business_unit', 'annual_rock', 'vertical', 'metric', 'kpi',
            'customer_value', 'business_value', 'cost_savings',
            'operational_cost', 'business_risk', 'level_of_effort',
        ]
        labels = {
            'strategy': 'Quarterly Rock',
            'business_unit': 'Department',
            'annual_rock': 'Annual Rock',
            'vertical': 'Vertical',
            'metric': 'Metric',
            'kpi': 'KPI',
        }
        help_texts = {
            'metric': 'Quantifiable data points and performance indicators such as conversion rates, customer acquisition costs, or average order value',
            'kpi': 'Quantifiable data points measuring performance against strategic goals, such as profitability, growth, and customer satisfaction',
        }
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'launch': DateInput(attrs={'class': 'datepicker', 'id': 'datepicker', 'type': 'date'}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'status': Select(attrs={}),
            'value': NumberInput(attrs={}),
            'business_unit': Select(attrs={}),
            'annual_rock': Select(attrs={}),
            'vertical': Select(attrs={}),
            'metric': Select(attrs={}),
            'kpi': Select(attrs={}),
            'customer_value': NumberInput(attrs={'min': 0, 'max': 10}),
            'business_value': NumberInput(attrs={'min': 0, 'max': 10}),
            'cost_savings': NumberInput(attrs={'min': 0, 'max': 10}),
            'operational_cost': NumberInput(attrs={'min': 0, 'max': 10}),
            'business_risk': NumberInput(attrs={'min': 0, 'max': 10}),
            'level_of_effort': NumberInput(attrs={'min': 0, 'max': 10}),
        }

class ProjectEditManager(ModelForm):
    class Meta:
        model = Project
        fields = ['strategy', 'owner', 'name', 'impact', 'success', 'why', 'annual_rock']
        labels = {
            'strategy': 'Quarterly Rock',
            'annual_rock': 'Annual Rock',
        }
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'annual_rock': Select(attrs={}),
        }

class ProjectValue(ModelForm):
	class Meta:
	    model = Project
	    fields = ['strategy', 'name', 'impact', 'value']
	    labels = {
	        'strategy': 'Quarterly Rock',
	    }
	    widgets = {
	        'strategy': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'value': NumberInput(attrs={}),
	    }

class ProjectLoe(ModelForm):
	class Meta:
	    model = Project
	    fields = ['strategy', 'name', 'impact', 'value', 'level_of_effort']
	    labels = {
	        'strategy': 'Quarterly Rock',
	    }
	    widgets = {
	        'strategy': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'value': NumberInput(attrs={'readonly':'readonly'}),
	        'level_of_effort': NumberInput(attrs={'min': 0, 'max': 10}),
	    }


class CommentForm(forms.ModelForm):
	class Meta:
		model = Comment
		fields = ('text',)
		widgets = {
			'text': Textarea(attrs={})
		}
