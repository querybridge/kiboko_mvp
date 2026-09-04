from django.db import migrations


REQUIRED_FOR_SCORING = ['name', 'project_id', 'business_unit_id', 'owner_id', 'why']
TERMINAL = ('Complete', 'Launched')


def _is_incomplete(action):
    for field in REQUIRED_FOR_SCORING:
        val = getattr(action, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            return True
    return False


def _canonical_status(action):
    """Mirror services.kanban.derive_status for the migration."""
    status = (action.status or '').strip()
    if status in TERMINAL:
        return status
    if action.is_blocked:
        return 'Blocked'
    if status == 'WIP':
        return 'WIP'
    if status in ('On Deck', 'Pending Assignment'):
        return 'On Deck'
    if _is_incomplete(action):
        return 'Incomplete Entry'
    if action.normalized_score is not None and action.normalized_score > 0:
        return 'Scored'
    return 'Ready to Score'


def forwards(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    for action in Action.objects.all():
        new_status = _canonical_status(action)
        if new_status != action.status:
            action.status = new_status
            action.save(update_fields=['status'])


def backwards(apps, schema_editor):
    # Best-effort reverse: fold the new Kanban statuses back to the old set.
    Action = apps.get_model('project', 'Action')
    reverse_map = {
        'Blocked': 'Pending Approval',
        'Incomplete Entry': 'Pending Approval',
        'Ready to Score': 'Pending Approval',
        'Scored': 'Pending Approval',
        'On Deck': 'Pending Assignment',
    }
    for action in Action.objects.all():
        if action.status in reverse_map:
            action.status = reverse_map[action.status]
            action.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0007_detail_lever_measures'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
