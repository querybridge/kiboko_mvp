"""Give every Objective a company.

- An objective used by one company's projects/actions goes to that company.
- One used by several companies stays with the first; each other company gets
  its own copy and its projects/actions are repointed to it.
- Unused objectives go to the platform demo company (or stay blank, which only
  superusers see).
- Any company left with no objectives gets the three default AEE objectives.
"""
import datetime

from django.db import migrations

DEFAULTS = [
    ('Increase Shopper Volume', 'attract_traffic'),
    ('Increase Close Rate', 'engage_customers'),
    ('Increase Average Order Value', 'expand_purchase'),
]


def assign(apps, schema_editor):
    Objective = apps.get_model('strategy', 'Objective')
    Project = apps.get_model('strategy', 'Project')
    Action = apps.get_model('project', 'Action')
    Company = apps.get_model('business_unit', 'Company')

    demo = Company.objects.filter(organization__is_platform_demo=True).order_by('id').first()
    for o in Objective.objects.filter(company__isnull=True).order_by('id'):
        used = sorted(
            set(Project.objects.filter(objective=o, vertical__isnull=False)
                .values_list('vertical__company_id', flat=True))
            | set(Action.objects.filter(objective=o, vertical__isnull=False)
                  .values_list('vertical__company_id', flat=True)))
        if not used:
            o.company_id = demo.id if demo else None
            o.save(update_fields=['company'])
            continue
        o.company_id = used[0]
        o.save(update_fields=['company'])
        for company_id in used[1:]:
            copy = Objective.objects.create(
                company_id=company_id, name=o.name, description=o.description, year=o.year,
                kpi_id=o.kpi_id, aee_alignment=o.aee_alignment)
            Project.objects.filter(objective=o, vertical__company_id=company_id).update(objective=copy)
            Action.objects.filter(objective=o, vertical__company_id=company_id).update(objective=copy)

    year = datetime.date.today().year
    for company in Company.objects.all():
        if not Objective.objects.filter(company=company).exists():
            Objective.objects.bulk_create(
                Objective(company=company, name=name, aee_alignment=aee, year=year) for name, aee in DEFAULTS)


class Migration(migrations.Migration):

    dependencies = [
        ('strategy', '0012_objective_company'),
        ('project', '0018_estimatorsettings'),
    ]

    operations = [
        migrations.RunPython(assign, migrations.RunPython.noop),
    ]
