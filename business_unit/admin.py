import datetime

from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import Plan, Organization, IntegrationSettings, TrialCode, EmailOptOut


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Manage accounts: pause (temporary hold), resume, cancel (90-day retention),
    or delete permanently (the built-in 'Delete selected' action)."""
    list_display = ('name', 'kind', 'plan', 'plan_status', 'billing_exempt', 'trial_started',
                    'trial_ends', 'paused_at', 'purge_after', 'org_admin')
    list_filter = ('kind', 'plan_status', 'plan', 'billing_exempt')
    list_editable = ('billing_exempt',)
    search_fields = ('name', 'slug', 'org_admin__username', 'org_admin__email')
    readonly_fields = ('paused_at', 'canceled_at', 'purge_after', 'created')
    actions = ('pause_accounts', 'resume_accounts', 'cancel_accounts')

    @admin.action(description='Pause selected accounts (temporary hold)')
    def pause_accounts(self, request, queryset):
        n = queryset.update(plan_status='paused', paused_at=timezone.now())
        self.message_user(request, f'{n} account(s) paused.')

    @admin.action(description='Resume selected accounts')
    def resume_accounts(self, request, queryset):
        n = 0
        for org in queryset:
            org.plan_status = 'trial' if org.trial_started else 'active'
            org.paused_at = None
            org.canceled_at = None
            org.purge_after = None
            org.save(update_fields=['plan_status', 'paused_at', 'canceled_at', 'purge_after'])
            n += 1
        self.message_user(request, f'{n} account(s) resumed.')

    @admin.action(description='Cancel selected accounts (delete data in 90 days)')
    def cancel_accounts(self, request, queryset):
        now = timezone.now()
        purge = datetime.date.today() + datetime.timedelta(days=Organization.PURGE_DAYS)
        n = queryset.update(plan_status='canceled', canceled_at=now, purge_after=purge)
        self.message_user(request, f'{n} account(s) canceled — data is retained until {purge:%b %d, %Y}, '
                                   'then use “Delete selected” to remove permanently.')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Manage the subscription products. The price shown on the pricing table is
    edited here; the amount actually charged is the Stripe Price in stripe_price_id,
    so keep the two in step."""
    list_display = ('name', 'tier', 'price', 'interval', 'is_addon', 'active', 'sort_order')
    list_editable = ('price', 'active', 'sort_order')
    list_filter = ('tier', 'is_addon', 'active')
    search_fields = ('name', 'slug', 'tagline')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'tier', 'tagline', 'highlighted', 'active', 'sort_order')}),
        ('Pricing', {'fields': ('price', 'interval', 'is_addon')}),
        ('Features', {'fields': ('features',),
                      'description': 'One feature per line — shown as bullets on the pricing table.'}),
        ('Stripe', {'fields': ('stripe_product_id', 'stripe_price_id'),
                    'description': 'The recurring Price id (price_...) Checkout charges for this plan.'}),
    )


SECRET_FIELDS = ('sendgrid_api_key', 'stripe_secret_key', 'stripe_webhook_secret')


class IntegrationSettingsForm(forms.ModelForm):
    """Secret keys are never echoed back into the page. Leave a secret blank to
    keep the saved value; tick the matching "clear" box to remove it."""
    clear_sendgrid_api_key = forms.BooleanField(required=False, label='Clear SendGrid API key')
    clear_stripe_secret_key = forms.BooleanField(required=False, label='Clear Stripe secret key')
    clear_stripe_webhook_secret = forms.BooleanField(required=False, label='Clear webhook signing secret')

    class Meta:
        model = IntegrationSettings
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SECRET_FIELDS:
            saved = getattr(self.instance, name, '')
            f = self.fields[name]
            f.widget = forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password', 'size': 60})
            f.required = False
            f.help_text = ((f'Saved (ends in ...{saved[-4:]}). Leave blank to keep it. ' if saved else 'Not set. ')
                           + (f.help_text or ''))

    def clean(self):
        data = super().clean()
        for name in SECRET_FIELDS:
            if data.get(f'clear_{name}'):
                data[name] = ''
            elif not data.get(name):
                data[name] = getattr(self.instance, name, '')
        return data


@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(admin.ModelAdmin):
    """One screen for the SendGrid and Stripe API keys."""
    form = IntegrationSettingsForm
    fieldsets = (
        ('SendGrid (email)', {'fields': ('sendgrid_api_key', 'clear_sendgrid_api_key', 'email_from_address',
                                         'email_from_name', 'site_url', 'feedback_to', 'notifications_enabled'),
                              'description': 'Sends user invites, trial codes, feedback, and project notifications. '
                                             'The From address must be a verified sender in SendGrid.'}),
        ('Stripe (billing)', {'fields': ('stripe_secret_key', 'clear_stripe_secret_key', 'stripe_publishable_key',
                                         'stripe_webhook_secret', 'clear_stripe_webhook_secret'),
                              'description': 'Webhook endpoint to add in Stripe: <code>&lt;App URL&gt;/billing/stripe/webhook/</code>. '
                                             'Each Plan also needs its Stripe price id (Plans admin).'}),
    )
    def has_add_permission(self, request):
        return not IntegrationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = IntegrationSettings.current()
        return redirect(reverse('admin:business_unit_integrationsettings_change', args=[obj.pk]))


@admin.register(TrialCode)
class TrialCodeAdmin(admin.ModelAdmin):
    """Trial codes emailed from the Get Started page (one per request)."""
    list_display = ('code', 'email', 'created', 'expires', 'used_at', 'organization')
    search_fields = ('code', 'email', 'organization__name')
    list_filter = ('used_at',)
    readonly_fields = ('code', 'email', 'created', 'expires', 'used_at', 'organization')

    def has_add_permission(self, request):
        return False


@admin.register(EmailOptOut)
class EmailOptOutAdmin(admin.ModelAdmin):
    """Addresses that turned off a category of automatic email. Delete a row to
    resubscribe someone (only at their request)."""
    list_display = ('email', 'category', 'source', 'created_at')
    search_fields = ('email',)
    list_filter = ('category', 'source')
