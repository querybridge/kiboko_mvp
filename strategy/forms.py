from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select
from .models import Strategy, StrategyComment
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .model_field_options import *

#level_options = (
#        ('corporate', 'Corporate'),
#        ('business_unit', 'Business Unit'),
#        ('team', 'Team'),
#    )

class StrategyAdd(ModelForm):

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super().__init__(*args, **kwargs)
        # there's a `fields` property now
        self.fields['level'].required = False
        self.fields['purpose'].required = False

    class Meta:
        model = Strategy
        fields = ['name', 'impact', 'goal', 'objective', 'level', 'business_unit', 'competitive_position', 'purpose', 'why']
        widgets = {
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={}),
            'goal': TextInput(attrs={}),
            'objective': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'level': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'business_unit': Select(attrs={}),
            'competitive_position': Select(attrs={}),
            'purpose': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'why': Textarea(attrs={}),                        
        }

class StrategyEdit(ModelForm):
    class Meta:
        model = Strategy
        fields = ['name', 'impact', 'goal', 'objective', 'level', 'business_unit', 'competitive_position', 'purpose', 'why']
        helper = FormHelper()


class StrategyForm(forms.Form):
	name = forms.CharField(max_length=30)	
	desired_impact = forms.CharField(max_length=30)
	def_of_success = forms.CharField(max_length=30)

class StrategyAdd2(forms.Form):
    name = forms.CharField(max_length=75)
    impact = forms.CharField(max_length=75)
    goal = forms.CharField(max_length=75)
    objective = forms.ChoiceField(choices=objective_options, widget=forms.RadioSelect())
    level = forms.ChoiceField(choices=level_options, widget=forms.RadioSelect())
    business_unit = forms.ChoiceField(choices=businessUnit_options, widget=forms.SelectMultiple())
    competitive_position = forms.ChoiceField(choices=competitive_position_dict)
    purpose = forms.ChoiceField(choices=purpose_options, widget=forms.RadioSelect())
    why = forms.CharField(max_length=500, widget=forms.Textarea())

class CommentForm(forms.ModelForm):
    class Meta:
        model = StrategyComment
        fields = ('text',)
        widgets = {
        'text': Textarea(attrs={}),
        }