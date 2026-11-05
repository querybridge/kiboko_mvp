from django.db import models
from django.forms import ModelForm
from django import forms
from multiselectfield import MultiSelectField
from django.contrib.auth.models import User
import datetime

# Create your models here.


class BusinessUnit(models.Model):
    """A business unit that maps to one GA4 property. Belongs to a Company."""
    name = models.CharField(max_length=140)
    general_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # GA4 tenancy: Company -> BusinessUnit (GA4 property) -> Website (data stream)
    company = models.ForeignKey('Company', on_delete=models.CASCADE, null=True, blank=True, related_name='verticals')
    ga4_property_id = models.CharField(max_length=50, blank=True, help_text='Numeric GA4 property id')
    timezone = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=8, blank=True)

    class Meta:
        verbose_name = 'Business Unit'
        verbose_name_plural = 'Business Units'

    def __str__(self):
        return self.name


class Department(models.Model):
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

class Organization(models.Model):
	"""Top tenant / billing entity. An agency org has many companies ("clients");
	a direct org has one (org and company usually share a name). Exactly one org
	admin. Billing defines the organization (wired later)."""
	KIND_CHOICES = [('agency', 'Agency'), ('direct', 'Direct')]
	name = models.CharField(max_length=200)
	slug = models.SlugField(max_length=200, unique=True)
	kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='direct')
	org_admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
	                              related_name='administered_orgs')
	is_platform_demo = models.BooleanField(default=False, help_text='Demo org shown to all trial orgs')
	trial_started = models.DateField(null=True, blank=True,
	                                 help_text='Trial clock start; null once on a paid plan or internal')
	plan_status = models.CharField(max_length=20, default='trial',
	                               help_text='trial | active | past_due | paused | canceled')
	# The plan the org signed up on. FK so a price change on the Plan flows through;
	# the actual charge is Stripe's job once billing is wired.
	plan = models.ForeignKey('Plan', on_delete=models.SET_NULL, null=True, blank=True,
	                         related_name='organizations')
	premium_connection = models.BooleanField(default=False,
	                                         help_text='Standard add-on: warehouse-grade BigQuery connection')
	billing_exempt = models.BooleanField('Comped (no payment required)', default=False,
	                                     help_text='Demo, sales, or internal account: never locked for payment')
	trial_ends = models.DateField(null=True, blank=True,
	                              help_text='Last day of the free trial (set when the trial code is redeemed)')
	# Stripe: the customer + subscription created when the admin adds payment.
	stripe_customer_id = models.CharField(max_length=80, blank=True)
	stripe_subscription_id = models.CharField(max_length=80, blank=True)
	# Billing address (the billing entity of record; Stripe holds the card later).
	billing_legal_name = models.CharField(max_length=200, blank=True)
	billing_email = models.EmailField(blank=True)
	billing_address1 = models.CharField('Billing address', max_length=200, blank=True)
	billing_address2 = models.CharField('Billing address line 2', max_length=200, blank=True)
	billing_city = models.CharField(max_length=120, blank=True)
	billing_state = models.CharField('State / Region', max_length=120, blank=True)
	billing_postal = models.CharField('Postal code', max_length=40, blank=True)
	billing_country = models.CharField(max_length=120, blank=True)
	# Lifecycle. Cancel = self-serve; the org admin ends the account and data is
	# retained for 90 days (purge_after) then hard-deleted. Pause = admin-side hold.
	paused_at = models.DateTimeField(null=True, blank=True, help_text='Admin paused this account')
	canceled_at = models.DateTimeField(null=True, blank=True, help_text='Account canceled by the org admin')
	purge_after = models.DateField(null=True, blank=True,
	                               help_text='Canceled data is deleted forever on/after this date (canceled_at + 90 days)')
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name

	@property
	def client_noun(self):
		"""What this org calls its companies in the UI."""
		return 'Client' if self.kind == 'agency' else 'Company'

	TRIAL_DAYS = 45
	PURGE_DAYS = 90

	@property
	def trial_end_date(self):
		"""Last day of the trial, or None if the org has no trial clock (internal)."""
		if self.trial_ends:
			return self.trial_ends
		if self.trial_started:
			import datetime
			return self.trial_started + datetime.timedelta(days=self.TRIAL_DAYS)
		return None

	@property
	def trial_days_left(self):
		"""Days remaining in the trial (>=0), or None if not on a trial."""
		end = self.trial_end_date
		if self.plan_status != 'trial' or end is None:
			return None
		import datetime
		return max(0, (end - datetime.date.today()).days)

	@property
	def has_payment(self):
		return bool(self.stripe_subscription_id)

	@property
	def is_locked(self):
		"""True when the org may not use the app until payment is set up: the trial
		ran out with no payment on file, or Stripe reports the payment past due.
		Platform demo and internal orgs (no trial clock) are never locked."""
		if self.is_platform_demo or self.billing_exempt:
			return False
		if self.plan_status == 'past_due':
			return True
		return self.plan_status == 'trial' and self.trial_days_left == 0 and not self.has_payment

	@property
	def is_canceled(self):
		return self.plan_status == 'canceled'

	def billing_address_lines(self):
		"""Billing address as a list of non-blank lines (for display / reuse)."""
		parts = [self.billing_address1, self.billing_address2,
		         ', '.join(p for p in [self.billing_city, self.billing_state, self.billing_postal] if p),
		         self.billing_country]
		return [p for p in parts if p]

	def has_billing_address(self):
		return bool(self.billing_address1 and self.billing_city)


class Plan(models.Model):
	"""A subscription product/tier shown on the Get Started + Billing pages and
	(later) synced to Stripe. Price is editable in Django admin; the Stripe ids
	are placeholders until billing is wired. An add-on (is_addon=True, e.g. the
	Premium Connection) is purchasable alongside a base plan."""
	TIER_CHOICES = [
		('standard', 'Standard'),
		('premium', 'Premium'),
		('enterprise', 'Enterprise'),
		('addon', 'Add-on'),
	]
	slug = models.SlugField(max_length=60, unique=True)
	name = models.CharField(max_length=120)
	tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='standard')
	tagline = models.CharField(max_length=200, blank=True,
	                           help_text='The question this plan answers for the buyer')
	price = models.DecimalField(max_digits=8, decimal_places=2, default=0,
	                            help_text='Price in USD for the interval below')
	interval = models.CharField(max_length=10, default='month',
	                            help_text='Billing interval (month / year)')
	features = models.TextField(blank=True, help_text='One feature per line')
	is_addon = models.BooleanField(default=False,
	                               help_text='Purchasable alongside a base plan (e.g. Premium Connection)')
	highlighted = models.BooleanField(default=False,
	                                  help_text='Visually feature this plan as "most popular"')
	active = models.BooleanField(default=True)
	sort_order = models.PositiveIntegerField(default=0)
	# Placeholders — populated when Stripe is wired; the price above is the source
	# of truth until then and is pushed to Stripe at that point.
	stripe_product_id = models.CharField(max_length=80, blank=True)
	stripe_price_id = models.CharField(max_length=80, blank=True)
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['sort_order', 'price']

	def __str__(self):
		return self.name

	def feature_list(self):
		"""Features as a clean list (one per non-blank line)."""
		return [ln.strip() for ln in self.features.splitlines() if ln.strip()]


class Company(models.Model):
	"""Top tenant -- a customer company (a Kiboko Account). Maps loosely to a
	GA4 Account, but Kiboko groups by company, not by GA4 account."""
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True,
	                                 related_name='companies')
	name = models.CharField(max_length=200)
	slug = models.SlugField(max_length=200, unique=True)
	ga4_account_id = models.CharField(max_length=50, blank=True, help_text='GA4 account id this company was imported from')
	# Company details (entered by the org admin on the Company Details page).
	legal_name = models.CharField(max_length=200, blank=True)
	website = models.CharField(max_length=255, blank=True)
	address1 = models.CharField('Address', max_length=200, blank=True)
	address2 = models.CharField('Address line 2', max_length=200, blank=True)
	city = models.CharField(max_length=120, blank=True)
	state = models.CharField('State / Region', max_length=120, blank=True)
	postal = models.CharField('Postal code', max_length=40, blank=True)
	country = models.CharField(max_length=120, blank=True)
	same_as_billing = models.BooleanField(default=False,
	                                      help_text='Reuse the organization billing address for this company')
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = 'Company'
		verbose_name_plural = 'Companies'
		ordering = ['name']

	def __str__(self):
		return self.name

	def details_complete(self):
		"""True once the org admin has filled the core company details."""
		return bool(self.legal_name and (self.same_as_billing or (self.address1 and self.city)))


class CompanyMembership(models.Model):
	"""Links a Kiboko user (a Google account) to a Company."""
	ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]
	company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='company_memberships')
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
	# Business units this user may see in the company; empty = all of the company's.
	# The service account can read every GA4 property, so an admin scopes visibility here.
	allowed_bus = models.ManyToManyField('BusinessUnit', blank=True, related_name='scoped_memberships')
	created = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = [['company', 'user']]

	def __str__(self):
		return f'{self.user} @ {self.company} ({self.role})'

	def allowed_bu_ids(self):
		"""Set of BusinessUnit ids this membership may see; None = all."""
		ids = set(self.allowed_bus.values_list('id', flat=True))
		return ids or None


class Website(models.Model):
	"""Data Stream == one website within a GA4 property (BusinessUnit)."""
	vertical = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, null=True, blank=True, related_name='websites')
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
	# Maps a standard GA4 event name -> the name this company actually fires
	# (e.g. {'view_cart': 'View Cart'}). Empty/missing means use the standard name.
	event_map = models.JSONField(default=dict, blank=True)
	# Latest complete day of data in the export. Relative periods (This Month,
	# QTD, ...) are anchored to this so historical clients' dashboards land on
	# their data instead of on 'today' (which may be past the export).
	data_through = models.DateField(null=True, blank=True)
	created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
	created = models.DateTimeField(auto_now_add=True)
	last_tested_at = models.DateTimeField(null=True, blank=True)

	# Standard GA4 event names the connector uses; the map lets a company override
	# any of them if they fire custom names.
	STANDARD_EVENTS = ['add_to_cart', 'view_cart', 'begin_checkout', 'add_shipping_info',
	                   'view_item', 'view_item_list', 'purchase']

	class Meta:
		verbose_name = 'BigQuery connection'

	def event_name(self, standard):
		"""The company's actual event name for a standard one (map or passthrough)."""
		return (self.event_map or {}).get(standard) or standard

	def __str__(self):
		return f'BigQuery connection ({self.company})'


class GA4DailyRollup(models.Model):
	"""Pre-aggregated one-day slice of a Premium company's GA4 export, so Premium
	dashboards + the value pipeline read from here instead of scanning events_* on
	every request. One row per (company, property, date); populated by the
	`sync_ga4_rollups` management command. See docs/daily_rollup_cache_plan.md."""
	FUND_KEYS = ('visits', 'visitors', 'new_visitors', 'carts', 'orders', 'units', 'sales')

	company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ga4_rollups')
	property_id = models.CharField(max_length=50)
	date = models.DateField()

	# Daily fundamentals (hot path: fundamentals + derived cards).
	visits = models.FloatField(default=0)
	visitors = models.FloatField(default=0)
	new_visitors = models.FloatField(default=0)
	carts = models.FloatField(default=0)
	orders = models.FloatField(default=0)
	units = models.FloatField(default=0)
	sales = models.FloatField(default=0)

	# GA4-style period totals for Engage/Storyboard (sessions, engagedSessions,
	# funnel event counts, ...), keyed exactly like fetch_period_totals.
	totals = models.JSONField(default=dict, blank=True)
	# {bucket: {fundamentals}} for device / channel splits.
	device = models.JSONField(default=dict, blank=True)
	channel = models.JSONField(default=dict, blank=True)
	# {item_category: {orders, units, sales}}.
	categories = models.JSONField(default=dict, blank=True)

	# Item/order-level (unique_skus_weighted = per-order avg * orders, so summing
	# across days/properties and dividing by total orders recovers the weighted avg).
	item_orders = models.FloatField(default=0)
	unique_skus_weighted = models.FloatField(default=0)
	single_sku_orders = models.FloatField(default=0)

	synced_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'GA4 daily rollup'
		unique_together = [['company', 'property_id', 'date']]
		indexes = [models.Index(fields=['company', 'property_id', 'date'])]
		ordering = ['date']

	def fundamentals(self):
		return {k: getattr(self, k) for k in self.FUND_KEYS}

	def __str__(self):
		return f'{self.company} / {self.property_id} / {self.date}'


class IntegrationSettings(models.Model):
	"""Platform-wide API keys for SendGrid (email) and Stripe (billing). One row,
	edited in Django admin. Until a key is filled in, the matching feature stays
	off: emails are skipped (logged) and the Billing page hides payment."""
	sendgrid_api_key = models.CharField('SendGrid API key', max_length=200, blank=True)
	email_from_address = models.EmailField('From address', blank=True, default='no-reply@kibokomethod.com',
	                                       help_text='A sender verified in SendGrid')
	email_from_name = models.CharField('From name', max_length=100, blank=True, default='Kiboko')
	site_url = models.URLField('App URL', blank=True,
	                           help_text='Base address used for links in emails, e.g. https://kiboko.pythonanywhere.com')
	feedback_to = models.EmailField('Feedback goes to', default='info@kibokomethod.com',
	                                help_text='Where the in-app Feedback button delivers')
	notifications_enabled = models.BooleanField(default=True,
	                                            help_text='Untick to pause all project notification emails')
	stripe_secret_key = models.CharField('Stripe secret key', max_length=200, blank=True,
	                                     help_text='sk_test_... or sk_live_...')
	stripe_publishable_key = models.CharField('Stripe publishable key', max_length=200, blank=True,
	                                          help_text='pk_test_... or pk_live_...')
	stripe_webhook_secret = models.CharField('Stripe webhook signing secret', max_length=200, blank=True,
	                                         help_text='whsec_... from the webhook endpoint in Stripe')
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'Integration Settings'
		verbose_name_plural = 'Integration Settings'

	def __str__(self):
		return 'API keys (SendGrid, Stripe)'

	@classmethod
	def current(cls):
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj

	def save(self, *args, **kwargs):
		self.pk = 1                       # singleton
		super().save(*args, **kwargs)


class TrialCode(models.Model):
	"""A one-time code emailed to a prospective customer. Redeeming it at signup
	starts the 45-day free trial; no trial begins without one."""
	email = models.EmailField()
	code = models.CharField(max_length=12, unique=True)
	created = models.DateTimeField(auto_now_add=True)
	expires = models.DateTimeField()
	used_at = models.DateTimeField(null=True, blank=True)
	organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True,
	                                 related_name='trial_codes')

	VALID_DAYS = 7

	class Meta:
		ordering = ['-created']

	def __str__(self):
		return f'{self.code} ({self.email})'

	@classmethod
	def issue(cls, email):
		import datetime, secrets
		from django.utils import timezone
		alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'          # no I O 0 1
		while True:
			code = ''.join(secrets.choice(alphabet) for _ in range(8))
			if not cls.objects.filter(code=code).exists():
				break
		return cls.objects.create(email=email, code=code,
		                          expires=timezone.now() + datetime.timedelta(days=cls.VALID_DAYS))

	@classmethod
	def redeemable(cls, email, code):
		"""The unused, unexpired code issued to this email, or None."""
		from django.utils import timezone
		return cls.objects.filter(email__iexact=email, code=(code or '').strip().upper(),
		                          used_at__isnull=True, expires__gt=timezone.now()).first()


class EmailOptOut(models.Model):
	"""An address that unsubscribed from one category of automatic email. Service
	emails (invites, trial codes, password resets, billing) ignore this; see
	business_unit.email.OPTIONAL_CATEGORIES."""
	CATEGORY_CHOICES = [
		('project_updates', 'Project updates'),
		('marketing', 'Trial follow-ups and product news'),
	]
	SOURCE_CHOICES = [
		('link', 'Unsubscribe link'),
		('one_click', 'One-click (mail app)'),
		('settings', 'User Settings'),
		('admin', 'Admin'),
	]
	email = models.EmailField(db_index=True)  # stored lowercase
	category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
	source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='link')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = 'email opt-out'
		unique_together = [['email', 'category']]
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.email} ({self.get_category_display()})'
