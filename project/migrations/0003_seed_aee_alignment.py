from django.db import migrations


# Map an objective name to an AEE lever; fall back to a round-robin so the
# demo data shows a realistic spread across the three levers.
OBJECTIVE_TO_AEE = [
    (('shopper', 'visit', 'traffic'), 'attract_traffic'),
    (('close', 'conversion', 'engage'), 'engage_customers'),
    (('order value', 'aov', 'purchase', 'expand'), 'expand_purchase'),
]
CYCLE = ['attract_traffic', 'engage_customers', 'expand_purchase']


def seed(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    Objective = apps.get_model('strategy', 'Objective')

    for i, action in enumerate(Action.objects.all().order_by('id')):
        aee = ''
        name = ''
        if action.objective_id:
            obj = Objective.objects.filter(pk=action.objective_id).first()
            name = (obj.name if obj else '').lower()
        for keywords, value in OBJECTIVE_TO_AEE:
            if any(k in name for k in keywords):
                aee = value
                break
        if not aee:
            aee = CYCLE[i % len(CYCLE)]
        action.aee_alignment = aee
        action.save(update_fields=['aee_alignment'])


def unseed(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    Action.objects.update(aee_alignment='')


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0002_action_aee_alignment'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
