"""Give every company an objective for each AEE element this year.

0013 seeded the three default objectives only for companies with no objectives
at all, so a company whose projects used one objective kept just that one, and
the Project Pipeline Value page showed one tile instead of Attract, Engage and
Expand. This adds the missing defaults; existing objectives are untouched.
"""
import datetime

from django.db import migrations

DEFAULTS = [
    ('Increase Shopper Volume', 'attract_traffic'),
    ('Increase Close Rate', 'engage_customers'),
    ('Increase Average Order Value', 'expand_purchase'),
]


def complete(apps, schema_editor):
    Objective = apps.get_model('strategy', 'Objective')
    Company = apps.get_model('business_unit', 'Company')
    year = datetime.date.today().year
    for company in Company.objects.all():
        have = set(Objective.objects.filter(company=company, year=year).values_list('aee_alignment', flat=True))
        Objective.objects.bulk_create(Objective(company=company, name=name, aee_alignment=aee, year=year)
                                      for name, aee in DEFAULTS if aee not in have)


class Migration(migrations.Migration):

    dependencies = [
        ('strategy', '0013_assign_objectives_to_companies'),
    ]

    operations = [
        migrations.RunPython(complete, migrations.RunPython.noop),
    ]
