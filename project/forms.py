from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, SelectMultiple, DateField, DateInput, NumberInput
from .models import Action, ActionComment
from strategy.models import Measure, Project
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from decimal import Decimal, ROUND_HALF_UP


class RoundedDecimalField(forms.DecimalField):
    """Quantize to the field's decimal_places before validation, so GA4-derived
    values with extra precision (e.g. visits/visitor = 1.228734) don't trip the
    'Ensure that there are no more than N decimal places' error."""
    def to_python(self, value):
        value = super().to_python(value)
        if value is not None and self.decimal_places is not None:
            value = value.quantize(Decimal(1).scaleb(-self.decimal_places), rounding=ROUND_HALF_UP)
        return value


class ProjectForm(ModelForm):
    """Add / edit a Project (the scored unit). AEE is inherited from the
    objective, so it isn't set here."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('target_completion', 'target_from', 's0_annual', 'direct_expense',
                  'ramp_days', 'plausibility_factor',
                  'evidence_backed', 'evidence_kind', 'evidence_prior_level', 'evidence_note'):
            self.fields[f].required = False
        self.fields['plausibility_factor'].initial = 1.0

        # Round decimal inputs to their column precision (GA4 levels can carry more).
        for name in ('target_from', 'target_to', 's0_annual', 'evidence_prior_level'):
            f = self.fields[name]
            self.fields[name] = RoundedDecimalField(
                max_digits=f.max_digits, decimal_places=f.decimal_places,
                required=False, widget=forms.HiddenInput())

        # Owner shown as "First L." for quick scanning (falls back to username).
        def _owner_label(u):
            first = (u.first_name or '').strip()
            last = (u.last_name or '').strip()
            if first and last:
                return f'{first} {last[0]}.'
            return first or u.get_username()
        self.fields['owner'].label_from_instance = _owner_label

    def clean(self):
        cleaned = super().clean()
        # Unique project name per company (case-insensitive), so lazy duplicates
        # and re-suggested ideas don't fragment the backlog. Different companies
        # may reuse a name; archived projects don't block reuse.
        name = (cleaned.get('name') or '').strip()
        if name:
            cleaned['name'] = name
            vertical = cleaned.get('vertical')
            dupes = Project.objects.filter(archived=False, name__iexact=name)
            if vertical is not None:
                dupes = dupes.filter(vertical__company=vertical.company)
            else:
                dupes = dupes.filter(vertical__isnull=True)
            if self.instance and self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                self.add_error('name', 'A project with this name already exists — use a distinct name.')
        # Lever must pull the objective's AEE element (AEE > Objective > Project).
        objective, lever = cleaned.get('objective'), cleaned.get('lever')
        if objective and lever:
            from project.services import impact
            lever_aee = impact.LEVERS.get(lever, ('', ''))[1]
            if objective.aee_alignment and lever_aee and lever_aee != objective.aee_alignment:
                self.add_error('lever',
                               f'“{objective.name}” is an {objective.get_aee_alignment_display()} '
                               f'objective — pick a matching lever.')
        if cleaned.get('evidence_backed'):
            if not (cleaned.get('evidence_note') or '').strip():
                self.add_error('evidence_note', 'A note is required for an evidence-backed target.')
            if cleaned.get('evidence_prior_level') in (None, ''):
                self.add_error('evidence_prior_level',
                               'Enter the evidenced prior level the target is anchored to.')
        else:
            # Clear evidence detail when the flag is off, so stale values don't linger.
            cleaned['evidence_kind'] = ''
            cleaned['evidence_prior_level'] = None
            cleaned['evidence_note'] = ''
        return cleaned

    class Meta:
        model = Project
        fields = ['name', 'objective', 'owner', 'vertical', 'department',
                  'target_completion', 'why', 'definition_of_done',
                  'lever', 'target_from', 'target_to', 's0_annual', 'ramp_days',
                  'direct_expense', 'plausibility_factor',
                  'evidence_backed', 'evidence_kind', 'evidence_prior_level', 'evidence_note']
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
            'why': 'Format: As a [user persona], I want [goal/action], so that [benefit/value].',
            'definition_of_done': 'The criteria the project must meet for the team to call it '
                                  'complete and ready for customers.',
        }
        widgets = {
            'name': TextInput(attrs={}),
            'objective': Select(attrs={}),
            'owner': Select(attrs={}),
            'vertical': Select(attrs={}),
            'department': Select(attrs={}),
            'target_completion': DateInput(attrs={'class': 'datepicker', 'type': 'date'}),
            'why': Textarea(attrs={'rows': 3, 'maxlength': 400,
                                   'placeholder': 'As a shopper, I want …, so that …'}),
            'definition_of_done': Textarea(attrs={'rows': 3, 'maxlength': 350,
                                                  'placeholder': 'e.g. Live for all users; success metric tracked; no P1 bugs; …'}),
            'lever': Select(attrs={}),
            # Unit-bearing values are kept raw in hidden inputs; the template shows
            # formatted, per-lever displays (rates as %, counts with commas, $ finance).
            'target_from': forms.HiddenInput(),
            'target_to': forms.HiddenInput(),
            's0_annual': forms.HiddenInput(),
            'direct_expense': forms.HiddenInput(),
            'ramp_days': NumberInput(attrs={'min': 1}),
            'plausibility_factor': forms.HiddenInput(),
            'evidence_backed': forms.CheckboxInput(),
            'evidence_kind': Select(),
            'evidence_prior_level': forms.HiddenInput(),      # raw; formatted display in template
            'evidence_note': Textarea(attrs={'rows': 3, 'maxlength': 300,
                                             'placeholder': 'e.g. restoring the 28% rate sustained before the March checkout regression'}),
        }
        labels = dict(labels, **{
            'evidence_kind': 'Evidence type',
            'evidence_note': 'Evidence note (shown to voters)',
        })


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
