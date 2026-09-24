import datetime

from django.contrib import admin
from django.utils import timezone

from .models import Plan, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Manage accounts: pause (temporary hold), resume, cancel (90-day retention),
    or delete permanently (the built-in 'Delete selected' action)."""
    list_display = ('name', 'kind', 'plan', 'plan_status', 'trial_started',
                    'paused_at', 'purge_after', 'org_admin')
    list_filter = ('kind', 'plan_status', 'plan')
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
    """Manage the subscription products. Price is editable inline; it is the
    source of truth until Stripe is wired (then it's pushed to Stripe)."""
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
        ('Stripe (wired later)', {'fields': ('stripe_product_id', 'stripe_price_id'),
                                  'classes': ('collapse',)}),
    )
