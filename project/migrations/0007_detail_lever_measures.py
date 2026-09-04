from django.db import migrations


# Detail-dashboard "main metric" cards that aren't already Grow Sales measures.
# Adding them as active measures lets a card like NEW VISITORS click through to
# a Backlog filtered by an exact-matching measure (rather than falling back to
# the AEE pillar).
EXTRA_MEASURES = [
    'New Visitors',
    'Returning Visitors',
]


def add_measures(apps, schema_editor):
    Measure = apps.get_model('strategy', 'Measure')
    for name in EXTRA_MEASURES:
        m, _ = Measure.objects.get_or_create(name=name)
        if not m.active:
            m.active = True
            m.save(update_fields=['active'])


def remove_measures(apps, schema_editor):
    Measure = apps.get_model('strategy', 'Measure')
    Measure.objects.filter(name__in=EXTRA_MEASURES).update(active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0006_grow_sales_measures'),
    ]

    operations = [
        migrations.RunPython(add_measures, remove_measures),
    ]
