from django.db import migrations

LEGACY = {
    'admin': 'executive', 'senior_leadership': 'executive',
    'general_manager': 'business_unit_leader', 'supervisor': 'business_unit_leader',
    'staff': 'business_unit_user',
}


def backfill(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    for p in UserProfile.objects.all():
        if not p.roles:
            mapped = LEGACY.get(p.role)
            if mapped:
                p.roles = [mapped]
                p.save(update_fields=['roles'])


class Migration(migrations.Migration):
    dependencies = [('users', '0005_userprofile_roles')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
