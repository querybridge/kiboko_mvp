"""Turn a discovered GA4 hierarchy into Kiboko tenancy records + membership.

GA4 Account  -> Company
GA4 Property -> BusinessUnit
GA4 Stream   -> Website

Idempotent: re-importing updates in place (keyed on the GA4 ids), so a user can
re-run discovery to pick up new properties/streams without creating duplicates.
"""
from django.db import transaction
from django.utils.text import slugify

from business_unit.models import Company, CompanyMembership, BusinessUnit, Website


def _get_or_create_company(account):
    acct_id = str(account.get('account_id') or '')
    name = account.get('account_name') or f'Account {acct_id}'
    company = Company.objects.filter(ga4_account_id=acct_id).first() if acct_id else None
    if company is None:
        company = Company.objects.filter(name=name).first()
    if company is None:
        base = slugify(name) or f'account-{acct_id}'
        slug, i = base, 1
        while Company.objects.filter(slug=slug).exists():
            i += 1
            slug = f'{base}-{i}'
        company = Company.objects.create(name=name, slug=slug, ga4_account_id=acct_id)
    elif acct_id and not company.ga4_account_id:
        company.ga4_account_id = acct_id
        company.save(update_fields=['ga4_account_id'])
    return company


def _get_or_create_vertical(company, prop):
    prop_id = str(prop.get('property_id') or '')
    vertical = BusinessUnit.objects.filter(company=company, ga4_property_id=prop_id).first()
    if vertical is None:
        # Adopt a same-named company-less vertical if one exists (e.g. from PPM).
        vertical = BusinessUnit.objects.filter(company=company, name=prop['display_name']).first()
    if vertical is None:
        vertical = BusinessUnit.objects.create(
            company=company, name=prop['display_name'], ga4_property_id=prop_id,
            timezone=prop.get('time_zone', ''), currency=prop.get('currency', ''))
    else:
        vertical.ga4_property_id = prop_id
        vertical.timezone = prop.get('time_zone', '') or vertical.timezone
        vertical.currency = prop.get('currency', '') or vertical.currency
        vertical.save(update_fields=['ga4_property_id', 'timezone', 'currency'])
    return vertical


def _get_or_create_website(vertical, stream):
    stream_id = str(stream.get('stream_id') or '')
    site, _ = Website.objects.update_or_create(
        vertical=vertical, ga4_stream_id=stream_id,
        defaults={
            'name': stream.get('display_name') or stream.get('default_uri') or 'Website',
            'measurement_id': stream.get('measurement_id', ''),
            'domain': stream.get('default_uri', ''),
        })
    return site


@transaction.atomic
def import_hierarchy(user, hierarchy, property_ids):
    """Import the selected GA4 property ids from ``hierarchy`` for ``user``.

    Creates/updates Company/BusinessUnit/Website and grants the user admin
    membership on each affected company. Returns a summary dict.
    """
    wanted = {str(pid) for pid in property_ids}
    summary = {'companies': 0, 'verticals': 0, 'websites': 0}

    for account in hierarchy:
        props = [p for p in account.get('properties', []) if str(p['property_id']) in wanted]
        if not props:
            continue
        company = _get_or_create_company(account)
        CompanyMembership.objects.get_or_create(
            company=company, user=user, defaults={'role': 'admin'})
        summary['companies'] += 1
        for prop in props:
            vertical = _get_or_create_vertical(company, prop)
            summary['verticals'] += 1
            for stream in prop.get('data_streams', []):
                _get_or_create_website(vertical, stream)
                summary['websites'] += 1
    return summary


def imported_property_ids(user):
    """GA4 property ids already imported into companies the user belongs to."""
    return set(
        BusinessUnit.objects
        .filter(company__memberships__user=user)
        .exclude(ga4_property_id='')
        .values_list('ga4_property_id', flat=True)
    )
