from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateField, DateInput, NumberInput
from .models import Action, ActionComment
from strategy.models import Measure, Project
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


class ProjectForm(ModelForm):
    """Add / edit a Project (the scored unit). AEE is inherited from the
    objective, so it isn't set here."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_completion'].required = False

    class Meta:
        model = Project
        fields = ['name', 'objective', 'owner', 'vertical', 'department',
                  'target_completion', 'why', 'definition_of_done']
        labels = {
            'vertical': 'Business Unit',
            'department': 'Department',
            'target_completion': 'Target go-live date',
            'definition_of_done': 'Definition of Done',
            'why': 'User Story',
        }
        help_texts = {
            'objective': 'The annual objective this supports (its AEE element is inherited).',
            'vertical': 'The business unit / GA4 property this rolls up to.',
            'target_completion': 'When it goes live — drives the value-pipeline forecast timing.',
        }
        widgets = {
            'name': TextInput(attrs={}),
            'objective': Select(attrs={}),
            'owner': Select(attrs={}),
            'vertical': Select(attrs={}),
            'department': Select(attrs={}),
            'target_completion': DateInput(attrs={'class': 'datepicker', 'type': 'date'}),
            'why': Textarea(attrs={'rows': 3}),
            'definition_of_done': TextInput(attrs={}),
        }


class ActionTaskForm(ModelForm):
    """Add / edit an execution task (Action) under a Project."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measure'].queryset = Measure.objects.filter(active=True)
        for f in ('team', 'measure', 'launch', 'progress', 'value'):
            self.fields[f].required = False

    class Meta:
        model = Action
        fields = ['name', 'owner', 'value', 'launch', 'progress', 'team', 'measure']
        labels = {'team': 'Team', 'measure': 'Measure', 'launch': 'Target date',
                  'value': 'Value unlocked ($)'}
        help_texts = {'value': 'The revenue this task unlocks; sums to the Total Project Value.'}
        widgets = {
            'name': TextInput(attrs={}),
            'owner': Select(attrs={}),
            'value': NumberInput(attrs={'min': 0}),
            'launch': DateInput(attrs={'class': 'datepicker', 'type': 'date'}),
            'progress': NumberInput(attrs={'min': 0, 'max': 100}),
            'team': Select(attrs={}),
            'measure': Select(attrs={}),
        }


class ProjectAdd(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measure'].queryset = Measure.objects.filter(active=True)

    class Meta:
        model = Action
        fields = [
            'objective', 'aee_alignment', 'project', 'business_unit', 'team', 'vertical',
            'owner', 'name', 'why', 'impact', 'measure',
        ]
        labels = {
            'project': 'Project',
            'business_unit': 'Department',
            'team': 'Team',
            'objective': 'Objective',
            'aee_alignment': 'AEE Alignment',
            'vertical': 'Business Unit',
            'name': 'Action Name',
            'measure': 'Measure',
        }
        help_texts = {
            'measure': 'Quantifiable data points used to track progress and performance against the parent metric',
            'team': 'Functional team executing the action (e.g. Marketing, IT, Merchandising)',
            'aee_alignment': 'Which lever this action pulls: Attract Traffic, Engage Customers, or Expand Purchase',
        }
        widgets = {
            'objective': Select(attrs={}),
            'aee_alignment': Select(attrs={}),
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
            'business_unit', 'team', 'objective', 'aee_alignment', 'vertical', 'measure',
            'customer_value', 'business_value', 'cost_savings',
            'operational_cost', 'business_risk', 'level_of_effort',
        ]
        labels = {
            'project': 'Project',
            'business_unit': 'Department',
            'team': 'Team',
            'objective': 'Objective',
            'aee_alignment': 'AEE Alignment',
            'vertical': 'Business Unit',
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
            'aee_alignment': Select(attrs={}),
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
