from django.db import migrations


def create_default(apps, schema_editor):
    """Create one SendGridSettings row (using field defaults, incl.
    feedback_to=feedback@kibokomethod.com) so an admin can paste the API key in
    Django admin without creating a record first."""
    SendGridSettings = apps.get_model('app', 'SendGridSettings')
    if not SendGridSettings.objects.exists():
        SendGridSettings.objects.create()


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0007_sendgridsettings'),
    ]

    operations = [
        migrations.RunPython(create_default, migrations.RunPython.noop),
    ]
