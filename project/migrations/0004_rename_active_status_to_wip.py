from django.db import migrations


def to_wip(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    Action.objects.filter(status='Active').update(status='WIP')


def to_active(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    Action.objects.filter(status='WIP').update(status='Active')


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0003_seed_aee_alignment'),
    ]

    operations = [
        migrations.RunPython(to_wip, to_active),
    ]
