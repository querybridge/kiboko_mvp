from django.db import migrations


# Stored alignment values that should now read "Increase Close Rate".
# The init form historically saved the human-readable label, so cover both
# the display text and the choice key just in case.
OLD_VALUES = ['Increase Purchase Frequency', 'increase_purchase_frequency']
NEW_VALUE = 'Increase Close Rate'


def rename_forward(apps, schema_editor):
    Strategy = apps.get_model('app', 'Strategy')
    Strategy.objects.filter(alignment__in=OLD_VALUES).update(alignment=NEW_VALUE)


def rename_backward(apps, schema_editor):
    Strategy = apps.get_model('app', 'Strategy')
    Strategy.objects.filter(alignment=NEW_VALUE).update(
        alignment='Increase Purchase Frequency'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_add_visits_orders'),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_backward),
    ]
