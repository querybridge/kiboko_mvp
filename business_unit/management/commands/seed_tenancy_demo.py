"""Seed demo GA4 tenancy (Company -> BusinessUnit -> Website) and add every existing
superuser as an admin member, so the top-bar selectors have something to show
before real Google/GA4 connections exist.

Any pre-existing verticals that don't yet belong to a company are folded into the
first demo company. Idempotent: safe to re-run.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.text import slugify

from business_unit.models import Company, CompanyMembership, BusinessUnit, Website

DEMO = {
    'Belami': [
        ('Lighting', [('Lighting.com', 'lighting.example.com'),
                      ('Lighting Canada', 'ca.lighting.example.com')]),
        ('Heating', [('Heating.com', 'heating.example.com')]),
    ],
    'VW Group': [
        ('Lamborghini', [('Lamborghini.com', 'lamborghini.example.com')]),
        ('Audi', [('Audi.com', 'audi.example.com')]),
    ],
}


class Command(BaseCommand):
    help = 'Create demo Company/BusinessUnit/Website tenancy and grant superusers admin access.'

    def handle(self, *args, **options):
        companies = {}
        for company_name, verticals in DEMO.items():
            company, _ = Company.objects.get_or_create(
                slug=slugify(company_name), defaults={'name': company_name})
            companies[company_name] = company
            for vert_name, websites in verticals:
                vert, _ = BusinessUnit.objects.get_or_create(
                    name=vert_name, defaults={'company': company})
                if vert.company_id is None:
                    vert.company = company
                    vert.save(update_fields=['company'])
                for site_name, domain in websites:
                    Website.objects.get_or_create(
                        vertical=vert, name=site_name, defaults={'domain': domain})
            self.stdout.write(f'  {company_name}: {len(verticals)} verticals')

        # Fold any orphan (company-less) verticals into the first demo company.
        default_company = companies['Belami']
        orphans = BusinessUnit.objects.filter(company__isnull=True)
        n = orphans.update(company=default_company)
        if n:
            self.stdout.write(f'  attached {n} existing vertical(s) to {default_company.name}')

        # Grant every superuser admin membership on every demo company.
        supers = User.objects.filter(is_superuser=True)
        for company in Company.objects.all():
            for u in supers:
                CompanyMembership.objects.get_or_create(
                    company=company, user=u, defaults={'role': 'admin'})
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {Company.objects.count()} companies; '
            f'{supers.count()} superuser(s) granted admin.'))
