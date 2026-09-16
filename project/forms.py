from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, SelectMultiple, DateField, DateInput, NumberInput
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
        for f in ('target_completion', 'target_from', 's0_annual', 'direct_expense',
                  'ramp_days', 'plausibility_factor'):
            self.fields[f].required = False
        self.fields['plausibility_factor'].initial = 1.0

    class Meta:
        model = Project
        fields = ['name', 'objective', 'owner', 'vertical', 'department',
                  'target_completion', 'why', 'definition_of_done',
                  'lever', 'target_from', 'target_to', 's0_annual', 'ramp_days',
                  'direct_expense', 'plausibility_factor']
        labels = {
            'vertical': 'Business Unit',
            'department': 'Department',
            'target_completion': 'Target go-live date',
            'definition_of_done': 'Definition of Done',
            'why': 'User Story',
            'lever': 'Lever it moves',
            'target_from': 'Current level (baseline)',
            'target_to': 'Target level',
            's0_annual': 'Annual sales baseline ($)',
            'ramp_days': 'Ramp to full effect (days)',
            'direct_expense': 'Direct expense ($)',
        }
        help_texts = {
            'objective': 'The annual objective this supports (its AEE element is inherited).',
            'vertical': 'The business unit / GA4 property this rolls up to.',
            'target_completion': 'When it goes live — drives the forecast + realized timing.',
            'lever': 'Which of the six sales levers this project improves.',
            'target_from': 'Auto-filled from GA4 when available; enter manually otherwise.',
            's0_annual': 'The business unit’s annual sales run-rate (auto from GA4 when available).',
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
            'lever': Select(attrs={}),
            'target_from': NumberInput(attrs={'step': 'any'}),
            'target_to': NumberInput(attrs={'step': 'any'}),
            's0_annual': NumberInput(attrs={'step': '1000'}),
            'ramp_days': NumberInput(attrs={'min': 1}),
            'direct_expense': NumberInput(attrs={'min': 0}),
            'plausibility_factor': forms.HiddenInput(),
        }


class ActionTaskForm(ModelForm):
    """Add / edit an execution task (Action) under a Project. Dependencies can
    only reference other actions in the same project; a dependent action can't
    start before its dependencies' end (launch) dates."""
    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measure'].queryset = Measure.objects.filter(active=True)
        for f in ('team', 'measure', 'launch', 'progress', 'depends_on'):
            self.fields[f].required = False
        if project is not None:
            qs = project.actions.all()
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['depends_on'].queryset = qs
        else:
            self.fields['depends_on'].queryset = Action.objects.none()

    class Meta:
        model = Action
        fields = ['name', 'owner', 'launch', 'progress', 'team', 'measure', 'depends_on']
        labels = {'team': 'Team', 'measure': 'Measure', 'launch': 'Target date',
                  'depends_on': 'Depends on'}
        help_texts = {'depends_on': "Other tasks that must finish first; this task can't start until they end."}
        widgets = {
            'name': TextInput(attrs={}),
            'owner': Select(attrs={}),
            'launch': DateInput(attrs={'class': 'datepicker', 'type': 'date'}),
            'progress': NumberInput(attrs={'min': 0, 'max': 100}),
            'team': Select(attrs={}),
            'measure': Select(attrs={}),
            'depends_on': SelectMultiple(attrs={'size': 4}),
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
