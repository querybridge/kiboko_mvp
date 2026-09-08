from django.db import models
from django.forms import ModelForm
from django import forms
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime

# Create your models here.


class Vertical(models.Model):
    """A business unit that maps to one GA4 property. Belongs to a Company."""
    name = models.CharField(max_length=140)
    general_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # GA4 tenancy: Company -> Vertical (GA4 property) -> Website (data stream)
    company = models.ForeignKey('Company', on_delete=models.CASCADE, null=True, blank=True, related_name='verticals')
    ga4_property_id = models.CharField(max_length=50, blank=True, help_text='Numeric GA4 property id')
    timezone = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=8, blank=True)

    class Meta:
        verbose_name = 'Vertical'
        verbose_name_plural = 'Verticals'

    def __str__(self):
        return self.name


class BusinessUnit(models.Model):
	name = models.CharField(max_length=140)
	owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

	class Meta:
		verbose_name = 'Department'
		verbose_name_plural = 'Departments'

	def __str__(self):
		return self.name


class Team(models.Model):
	name = models.CharField(max_length=140, unique=True)

	class Meta:
		verbose_name = 'Team'
		verbose_name_plural = 'Teams'
		ordering = ['name']

	def __str__(self):
		return self.name


# ---------------------------------------------------------------------------
# GA4 data-connection tenancy (see docs/data_connection_plan.md)
#   Company (Kiboko Account)  ->  Property (Business Unit / GA4 property)
#                             ->  Website (GA4 data stream)
# Users authenticate with Google; a user only sees Properties/Websites their
# Google account can access in GA4 (access is enforced live via their token).
# ---------------------------------------------------------------------------

class Company(models.Model):
	"""Top tenant -- a customer company (a Kiboko Account). Maps loosely to a
	GA4 Account, but Kiboko groups by company, not by GA4 account."""
	name = models.CharField(max_length=200)
	slug = models.SlugField(max_length=200, unique=True)
	ga4_account_id = models.CharField(max_length=50, blank=True, help_text='GA4 account id this company was imported from')
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = 'Company'
		verbose_name_plural = 'Companies'
		ordering = ['name']

	def __str__(self):
		return self.name


class CompanyMembership(models.Model):
	"""Links a Kiboko user (a Google account) to a Company."""
	ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]
	company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='company_memberships')
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = [['company', 'user']]

	def __str__(self):
		return f'{self.user} @ {self.company} ({self.role})'


class Website(models.Model):
	"""Data Stream == one website within a GA4 property (Vertical)."""
	vertical = models.ForeignKey(Vertical, on_delete=models.CASCADE, null=True, blank=True, related_name='websites')
	name = models.CharField(max_length=200)
	ga4_stream_id = models.CharField(max_length=50, blank=True)
	measurement_id = models.CharField(max_length=50, blank=True, help_text='G-XXXXXXX')
	domain = models.CharField(max_length=255, blank=True)
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name


class GoogleIdentity(models.Model):
	"""A Kiboko user's linked Google account. The OAuth token authorizes GA4
	reads on the user's behalf, so their own GA4 access gates what they see.

	NOTE: refresh_token must be encrypted at rest (django-cryptography) before
	real tokens are stored -- see the data-connection plan."""
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_identity')
	google_sub = models.CharField(max_length=255, unique=True, help_text='Stable Google user id (sub)')
	email = models.EmailField()
	picture_url = models.URLField(blank=True)
	refresh_token = models.TextField(blank=True)
	token_expiry = models.DateTimeField(null=True, blank=True)
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = 'Google identity'
		verbose_name_plural = 'Google identities'

	def __str__(self):
		return self.email or str(self.user)


class BigQueryConnection(models.Model):
	"""GA4 PREMIUM connection: read a company's GA4 -> BigQuery export via a
	service account (shared for all members), instead of each user's Google token.
	A Company with one of these is on the Premium tier.

	The dataset for a property is analytics_<vertical.ga4_property_id>; the page
	paths let the SQL derive cart/checkout/billing views (mirrors ITG).

	NOTE: service_account_json holds a GCP service-account key -- HIGHLY sensitive.
	It must be encrypted at rest (django-cryptography / Fernet) before production,
	like GoogleIdentity.refresh_token. Stored plain here only for scaffolding."""
	company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='bigquery')
	gcp_project = models.CharField(max_length=100, blank=True)
	service_account_json = models.JSONField(default=dict, blank=True)
	# Latest complete day of data in the export. Relative periods (This Month,
	# QTD, ...) are anchored to this so historical clients' dashboards land on
	# their data instead of on 'today' (which may be past the export).
	data_through = models.DateField(null=True, blank=True)
	created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
	created = models.DateTimeField(auto_now_add=True)
	last_tested_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		verbose_name = 'BigQuery connection'

	def __str__(self):
		return f'BigQuery connection ({self.company})'
