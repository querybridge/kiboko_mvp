from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateField, DateInput, NumberInput
from .models import Action, ActionComment
from strategy.models import Measure
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


class ProjectAdd(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measure'].queryset = Measure.objects.filter(active=True)

    class Meta:
        model = Action
        fields = [
            'objective', 'project', 'business_unit', 'team', 'vertical',
            'owner', 'name', 'why', 'impact', 'measure',
        ]
        labels = {
            'project': 'Project',
            'business_unit': 'Department',
            'team': 'Team',
            'objective': 'Objective',
            'vertical': 'Vertical',
            'name': 'Action Name',
            'measure': 'Measure',
        }
        help_texts = {
            'measure': 'Quantifiable data points used to track progress and performance against the parent metric',
            'team': 'Functional team executing the action (e.g. Marketing, IT, Merchandising)',
        }
        widgets = {
            'objective': Select(attrs={}),
            'project': Select(attrs={}),
            'business_unit': Select(attrs={}),
            'team': Select(attrs={}),
            'vertical': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'measure': Select(attrs={}),
        }


class ProjectEdit(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measure'].queryset = Measure.objects.filter(active=True)

    class Meta:
        model = Action
        fields = [
            'name', 'project', 'owner', 'status', 'progress', 'launch',
            'impact', 'success', 'why', 'value',
            'business_unit', 'team', 'objective', 'vertical', 'measure',
            'customer_value', 'business_value', 'cost_savings',
            'operational_cost', 'business_risk', 'level_of_effort',
        ]
        labels = {
            'project': 'Project',
            'business_unit': 'Department',
            'team': 'Team',
            'objective': 'Objective',
            'vertical': 'Vertical',
            'measure': 'Measure',
        }
        help_texts = {
            'measure': 'Quantifiable data points used to track progress and performance against the parent metric',
        }
        widgets = {
            'project': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'launch': DateInput(attrs={'class': 'datepicker', 'id': 'datepicker', 'type': 'date'}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'status': Select(attrs={}),
            'value': NumberInput(attrs={}),
            'business_unit': Select(attrs={}),
            'team': Select(attrs={}),
            'objective': Select(attrs={}),
            'vertical': Select(attrs={}),
            'measure': Select(attrs={}),
            'customer_value': NumberInput(attrs={'min': 0, 'max': 10}),
            'business_value': NumberInput(attrs={'min': 0, 'max': 10}),
            'cost_savings': NumberInput(attrs={'min': 0, 'max': 10}),
            'operational_cost': NumberInput(attrs={'min': 0, 'max': 10}),
            'business_risk': NumberInput(attrs={'min': 0, 'max': 10}),
            'level_of_effort': NumberInput(attrs={'min': 0, 'max': 10}),
        }

class ProjectEditManager(ModelForm):
    class Meta:
        model = Action
        fields = ['project', 'owner', 'name', 'impact', 'success', 'why', 'objective', 'value']
        labels = {
            'project': 'Project',
            'objective': 'Objective',
        }
        widgets = {
            'project': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'objective': Select(attrs={}),
            'value': NumberInput(attrs={}),
        }

class ProjectValue(ModelForm):
	class Meta:
	    model = Action
	    fields = ['project', 'name', 'impact', 'value']
	    labels = {
	        'project': 'Project',
	    }
	    widgets = {
	        'project': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'value': NumberInput(attrs={}),
	    }

class ProjectLoe(ModelForm):
	class Meta:
	    model = Action
	    fields = ['project', 'name', 'impact', 'value', 'level_of_effort']
	    labels = {
	        'project': 'Project',
	    }
	    widgets = {
	        'project': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'value': NumberInput(attrs={'readonly':'readonly'}),
	        'level_of_effort': NumberInput(attrs={'min': 0, 'max': 10}),
	    }


class CommentForm(forms.ModelForm):
	class Meta:
		model = ActionComment
		fields = ('text',)
		widgets = {
			'text': Textarea(attrs={})
		}
