from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateField, DateInput, NumberInput
from .models import Project, Comment
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


class ProjectAdd(ModelForm):
    class Meta:
        model = Project
        fields = ['strategy', 'owner', 'name', 'impact', 'success', 'why', 'business_unit']
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'business_unit': Select(attrs={}),
        }


class ProjectEdit(ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'strategy', 'owner', 'status', 'progress', 'launch',
            'impact', 'success', 'why', 'value',
            'customer_value', 'business_value', 'cost_savings',
            'operational_cost', 'business_risk', 'level_of_effort',
        ]
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
        fields = ['strategy', 'owner', 'name', 'impact', 'success', 'why']
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
        }

class ProjectValue(ModelForm):
	class Meta:
	    model = Project
	    fields = ['strategy', 'name', 'impact', 'value']
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
