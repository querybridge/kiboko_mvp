from django.db import models
from django.forms import ModelForm
from django import forms
from business_unit.models import Vertical

# Create your all your models here

##############################################################################################################################################################
## DB Models                                                                                                                                                ##
##############################################################################################################################################################

########################################
## Strategy DB Model                  ##
########################################

#Global Strategy List Options

alignment_options = (
		('increase_customers', 'Increase Customers'),
		('increase_aov', 'Increase AOV'),
		('increase_purchase_frequency', 'Increase Purchase Frequency'),
	)

level_options = (
		('corporate', 'Corporate'),
		('business_unit', 'Business Unit'),
		('team', 'Team'),
	)

businessUnit_options = (
		('merchandising', 'Merchandising'),
		('customer_service', 'Customer Service'),
		('innovation', 'Innovation'),
	)

purpose_options = (
		('new_growth', 'New Growth'),
		('hold_position', 'Hold Position'),
		('defend_position', 'Defend Position'),
		('reverse_decay', 'Reverse Decay'),
	)

status_options = (
		('new', 'New'),
		('gathering_requirements', 'Gathering Requirements'),
		('ready_for_dev', 'Ready for Development'),
		('in_development', 'In Development'),
		('uat', 'UAT'),
		('qa', 'QA'),
		('ready_for_prod', 'Ready for Production'),
		('completed_launched', 'Completed - Launched'),
		('blocked', 'Blocked'),

	)

#Strategy Class

class Strategy(models.Model):
	date_created = models.DateField(null=True)
	date_modified = models.DateField(null=True)
	#created_by = models.CharField(max_length=75, null=True)
	#modified_by = models.CharField(max_length=75, null=True)
	sid = models.AutoField(primary_key=True)
	name = models.CharField(max_length=75, null=True)	
	desired_impact = models.CharField(max_length=75, null=True)
	def_of_success = models.CharField(max_length=75, null=True)
	next_launch = models.DateField(null=True)
	alignment = models.CharField(max_length=75, choices=alignment_options, null=True)
	level = models.CharField(max_length=75, choices=level_options, null=True)
	purpose = models.CharField(max_length=75, choices=purpose_options, null=True)
	score = models.IntegerField(null=True)
	value = models.FloatField(null=True)
	status = models.CharField(max_length=75, choices=status_options, null=True)
	progress = models.IntegerField(null=True)
	#business_unit = models.OneToManyField(BusinessUnit)


########################################
## Project DB Model                   ##
########################################

#Global Project List Options

alignment_options = (
		('impress', 'Impress'),
		('enlighten', 'Enlighten'),
		('purchase', 'Purchase'),
	)

locations = (
		('header', 'Header'),
		('footer', 'Footer'),
		('home_page', 'Home Page'),
		('category_page', 'Category Page'),
		('product_list_page', 'Product List Page'),
		('product_detail_page', 'Product Detail Page'),
		('cart_part', 'Cart Page'),
		('order_tracking_page', 'Order Tracking Page'),
		('landing_page', 'Landing Page'),
	)

engagement_options = (
		('click', 'Click'),
		('submit', 'Submit'),
		('view', 'View'),
	)

purpose_options = (
		('new_growth', 'New Growth'),
		('hold_position', 'Hold Position'),
		('defend_position', 'Defend Position'),
		('reverse_decay', 'Reverse Decay'),
	)


#Project Class

class Project(models.Model):
	date_created = models.DateField(blank=True)
	date_modified = models.DateField(blank=True)
	#created_by = models.CharField(max_length=75, blank=True)
	#modified_by = models.ForeignKey('auth.User')
	strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, blank=True)
	name = models.CharField(max_length=75, blank=True)
	desired_impact = models.CharField(max_length=75, blank=True)
	def_of_success = models.CharField(max_length=75, blank=True)
	iep_alignment = models.CharField(max_length=75, choices=alignment_options, blank=True)
	feature_locations = models.CharField(max_length=75, choices=locations, blank=True)
	engagement = models.CharField(max_length=75, choices=engagement_options, blank=True)
	competitive_position = models.IntegerField(blank=True)
	purpose = models.CharField(max_length=75, choices=purpose_options, blank=True)
	why = models.CharField(max_length=75, blank=True)
	#businessUnit = models.OneToManyField(BusinessUnit)

def __str__(self):
    return self.name





########################################
## BusinessUnit DB Model             ##
########################################

class BusinessUnit(models.Model):
	date_created = models.DateField()
	date_modified = models.DateField()
	project = models.ForeignKey(Project, on_delete=models.CASCADE)
	name = models.CharField(max_length=75)
	#members = models.ManyToOneField(Member)


########################################
## Members DB Model                   ##
########################################

#class Member(models.Model):
#	date_created = models.DateField()
#	date_modified = models.DateField()
#	created_by = models.CharField(max_length=75)
#	modified_by = models.CharField(max_length=75)
#	businessunit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE)
#	name = models.CharField(max_length=75)
#	role = models.CharField(max_length=75)
#	email = models.EmailField()
	

########################################
## BigQuery DB Model              ##
########################################
class BigQuery(models.Model):
	date = models.DateField()
	totalAdSpend = models.CharField(max_length=75)
	roas = models.CharField(max_length=75)
	users = models.CharField(max_length=75)
	newUsers = models.CharField(max_length=75)
	sessions = models.CharField(max_length=75)
	sessionsPerUser = models.CharField(max_length=75)
	pageviews = models.CharField(max_length=75)
	revenue = models.CharField(max_length=75)
	avgOrderValue = models.CharField(max_length=75)
	transactions = models.CharField(max_length=75)




##############################################################################################################################################################
## Form DB Models - https://docs.djangoproject.com/en/1.11/topics/forms/modelforms/                                                                         ##
##############################################################################################################################################################

########################################
## Strategy Form DE Model             ##
########################################

#Will error out if HTML Form Field Does Not Exist

class StrategyForm(ModelForm):
    class Meta:
        model = Strategy
        fields = ['name', 'desired_impact', 'def_of_success', 'alignment', 'level', 'purpose']


########################################
## Project Form DB Model              ##
########################################

#class ProjectForm(ModelForm):
#    class Meta:
#       model = Project
#        fields = ['field1', 'field2', 'field3']


########################################
## Business Unit Form DB Model        ##
########################################

#class BusinessUnitForm(ModelForm):
#    class Meta:
#        model = BusinessUnit
#        fields = ['field1', 'field2', 'field3']


########################################
## Member Form DB Model               ##
########################################

#class MemberForm(ModelForm):
#    class Meta:
#        model = Member
#        fields = ['field1', 'field2', 'field3']

##############################################################################################################################################################
## Forms                                                                                                                                                    ##
##############################################################################################################################################################

########################################
## Strategy Form                      ##
########################################
#    name = forms.CharField(max_length=100)
#    title = forms.CharField(max_length=3, widget=forms.Select(choices=TITLE_CHOICES),)
#    birth_date = forms.DateField(required=False)

########################################
## Project Form                       ##
########################################


########################################
## Business Unit Form                 ##
########################################


########################################
## Member Form                        ##
########################################


########################################
## Revenue Models                     ##
########################################

class MonthlyGoal(models.Model):
    month = models.DateField()  # Store as first day of month
    vertical = models.ForeignKey(Vertical, on_delete=models.CASCADE, null=True, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['month']
        unique_together = [['month', 'vertical']]

    def __str__(self):
        v = self.vertical.name if self.vertical else 'Summary'
        return f"{self.month.strftime('%b %Y')} [{v}] - ${self.budget}"

class DailyActual(models.Model):
    date = models.DateField()
    vertical = models.ForeignKey(Vertical, on_delete=models.CASCADE, null=True, blank=True)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    visits = models.IntegerField(default=0)
    orders = models.IntegerField(default=0)

    class Meta:
        ordering = ['date']
        unique_together = [['date', 'vertical']]

    def __str__(self):
        v = self.vertical.name if self.vertical else 'Summary'
        return f"{self.date} [{v}] - ${self.revenue}"