from django.forms import ModelForm, Textarea, TextInput, CheckboxSelectMultiple, RadioSelect, Select, DateField, DateInput, NumberInput
from .models import Project, Comment
from django import forms
from django.forms import widgets
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .project_field_options import *



#class ProjectAdd(ModelForm):
#    class Meta:
#        model = Project
#        exclude = ['Score', 'Value']
#        helper = FormHelper()
        
class ProjectAdd(ModelForm):

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super().__init__(*args, **kwargs)
        # there's a `fields` property now
        self.fields['purpose'].required = False

    class Meta:
        model = Project
        fields = ['strategy', 'owner', 'name', 'impact', 'success', 'alignment', 'engagement', 'purpose', 'why', 'business_unit']
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'alignment': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
			'engagement': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'purpose': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'business_unit': Select(attrs={}),
        }


class ProjectEdit(ModelForm):
    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super().__init__(*args, **kwargs)
        # there's a `fields` property now
        self.fields['purpose'].required = False

    class Meta:
        model = Project
        fields = ['name', 'strategy', 'owner', 'status', 'progress', 'launch', 'impact', 'success', 'alignment', 'engagement', 'purpose', 'why', 'value', 'viability', 'loe']
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'launch': DateInput(attrs={'class': 'datepicker', 'id': 'datepicker', 'type': 'date'}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'goal': TextInput(attrs={'name': 'Definition of Success'}),
            'alignment': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'locations': CheckboxSelectMultiple(),
			'engagement': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'business_unit': Select(attrs={}),
            'viability': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'competitive_position': Select(attrs={'class': 'grid_slider'}),
            'purpose': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'why': Textarea(attrs={'name': 'User Story'}),
            'status': Select(attrs={}),
            #'approved': CheckboxSelect(attrs={})
        }

class ProjectEditManager(ModelForm):
    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super().__init__(*args, **kwargs)
        # there's a `fields` property now
        self.fields['purpose'].required = False

    class Meta:
        model = Project
        fields = ['strategy', 'owner', 'name', 'impact', 'success', 'alignment', 'engagement', 'purpose', 'why']
        widgets = {
            'strategy': Select(attrs={}),
            'owner': Select(attrs={}),
            'name': TextInput(attrs={}),
            'impact': TextInput(attrs={'name': 'Definition of Done'}),
            'success': TextInput(attrs={'name': 'Definition of Success'}),
            'alignment': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
			'engagement': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'purpose': RadioSelect(attrs={'class': 'iradio_flat-green radio flat'}),
            'why': Textarea(attrs={'name': 'User Story'}),                        
        }       

class ProjectValue(ModelForm):      
	class Meta:
	    model = Project
	    fields = ['strategy', 'name', 'impact', 'purpose', 'loe', 'value']
	    widgets = {
	        'strategy': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'purpose': TextInput(attrs={'readonly':'readonly'}),
	        'loe': Select(attrs={'readonly':'readonly'}),	        
	        'value': NumberInput(attrs={}),
	    }
        
class ProjectLoe(ModelForm):      
	class Meta:
	    model = Project
	    fields = ['strategy', 'name', 'impact', 'purpose', 'value', 'loe',]
	    widgets = {
	        'strategy': Select(attrs={'readonly':'readonly'}),
	        'name': TextInput(attrs={'readonly':'readonly'}),
	        'impact': TextInput(attrs={'name': 'Desired Impact', 'readonly':'readonly'}),
	        'purpose': TextInput(attrs={'readonly':'readonly'}),
	        'loe': Select(attrs={'name': 'LOE', 'label': 'LOE'}),	        
	        'value': NumberInput(attrs={'readonly':'readonly'}),
	    }

	
class CommentForm(forms.ModelForm):
	class Meta:
		model = Comment
		fields = ('text',)
		widgets = {
			'text': Textarea(attrs={})
		}