from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateInput, NumberInput
from .models import Strategy, StrategyComment
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .model_field_options import *


class StrategyAdd(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['level'].required = False
        self.fields['purpose'].required = False

    class Meta:
        model = Strategy
        fields = [
            'name', 'annual_rock', 'department', 'year', 'quarter',
            'impact', 'goal', 'definition_of_done', 'target_completion',
            'level', 'competitive_position', 'purpose', 'why',
        ]
        labels = {
            'annual_rock': 'Annual Rock',
            'department': 'Department',
            'definition_of_done': 'Definition of Done',
            'target_completion': 'Target Completion',
        }
        widgets = {
            'name': TextInput(attrs={}),
            'annual_rock': Select(attrs={}),
            'department': Select(attrs={}),
            'year': NumberInput(attrs={}),
            'quarter': Select(attrs={}),
            'impact': TextInput(attrs={}),
            'goal': TextInput(attrs={}),
            'definition_of_done': TextInput(attrs={}),
            'target_completion': DateInput(attrs={'type': 'date'}),
            'level': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'competitive_position': Select(attrs={}),
            'purpose': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'why': Textarea(attrs={}),
        }


class StrategyEdit(ModelForm):
    class Meta:
        model = Strategy
        fields = [
            'name', 'annual_rock', 'department', 'year', 'quarter',
            'impact', 'goal', 'definition_of_done', 'target_completion',
            'level', 'competitive_position', 'purpose', 'why',
        ]
        labels = {
            'annual_rock': 'Annual Rock',
            'department': 'Department',
            'definition_of_done': 'Definition of Done',
            'target_completion': 'Target Completion',
        }
        widgets = {
            'target_completion': DateInput(attrs={'type': 'date'}),
        }
        helper = FormHelper()


class CommentForm(forms.ModelForm):
    class Meta:
        model = StrategyComment
        fields = ('text',)
        widgets = {
        'text': Textarea(attrs={}),
        }
