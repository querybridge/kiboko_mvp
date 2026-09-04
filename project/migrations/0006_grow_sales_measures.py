from django.db import migrations


# The measures a project can impact = the metrics shown on the Grow Sales
# dashboard (AEE funnel order).
GROW_SALES_MEASURES = [
    'Visits',
    'Visitors',
    'Visits per Visitor',
    'Close Rate',
    'Cart Creation',
    'Cart Completion',
    'Orders',
    'Avg Order Value',
    'Units per Order',
    'Avg Unit Price',
    '$/Visit',
    'Sales',
]


def set_measures(apps, schema_editor):
    Measure = apps.get_model('strategy', 'Measure')
    Action = apps.get_model('project', 'Action')

    created = []
    for name in GROW_SALES_MEASURES:
        m, _ = Measure.objects.get_or_create(name=name)
        if not m.active:
            m.active = True
            m.save(update_fields=['active'])
        created.append(m)

    # Hide any non-Grow-Sales measure from the picker.
    Measure.objects.exclude(name__in=GROW_SALES_MEASURES).update(active=False)

    # Re-point existing actions at a Grow Sales measure (deterministic) so demo
    # data and the edit form's active-only queryset stay consistent.
    for i, action in enumerate(Action.objects.all().order_by('id')):
        action.measure_id = created[i % len(created)].id
        action.save(update_fields=['measure'])


def unset_measures(apps, schema_editor):
    Measure = apps.get_model('strategy', 'Measure')
    Measure.objects.filter(name__in=GROW_SALES_MEASURES).update(active=False)
    Measure.objects.exclude(name__in=GROW_SALES_MEASURES).update(active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0005_alter_action_status'),
        ('strategy', '0002_seed_reference_data'),
    ]

    operations = [
        migrations.RunPython(set_measures, unset_measures),
    ]
