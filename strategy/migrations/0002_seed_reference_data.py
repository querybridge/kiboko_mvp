from django.db import migrations


# Dashboard objective tiles look for these by year. "Increase Close Rate" is the
# renamed third core objective (formerly "Increase Purchase Frequency").
OBJECTIVES = [
    {'name': 'Increase Shopper Volume', 'year': 2026},
    {'name': 'Increase Average Order Value', 'year': 2026},
    {'name': 'Increase Close Rate', 'year': 2026},
    {'name': 'Increase Shopping Activity', 'year': 2027},
]

KPIS = ['MTS', 'Average Order Value', 'Conversion Rate']
METRICS = ['Users', 'Product Views', 'Add to Carts', 'Begin Checkouts']
MEASURES = ['Sessions', 'Clicks', 'Tasks Completed', 'Tickets Closed']


def seed(apps, schema_editor):
    Objective = apps.get_model('strategy', 'Objective')
    KPI = apps.get_model('strategy', 'KPI')
    Metric = apps.get_model('strategy', 'Metric')
    Measure = apps.get_model('strategy', 'Measure')

    for name in KPIS:
        KPI.objects.get_or_create(name=name, defaults={'active': True})
    for name in METRICS:
        Metric.objects.get_or_create(name=name, defaults={'active': True})
    for name in MEASURES:
        Measure.objects.get_or_create(name=name, defaults={'active': True})

    for obj in OBJECTIVES:
        Objective.objects.get_or_create(name=obj['name'], year=obj['year'])


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('strategy', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
