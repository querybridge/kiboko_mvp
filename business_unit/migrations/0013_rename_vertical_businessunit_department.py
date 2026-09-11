from django.db import migrations


class Migration(migrations.Migration):
    """Safe rename: PPM BusinessUnit -> Department (frees the name), then tenancy
    Vertical -> BusinessUnit. Order matters so the tenancy model can take the
    'businessunit' table name once the PPM model has vacated it. RenameModel
    preserves data and updates FK references (incl. cross-app) automatically.
    """

    # Depend on each app's pre-rename head so their FK references to the old
    # model names already exist in the state when RenameModel rewrites them
    # (otherwise the cross-app lazy references dangle after the rename).
    dependencies = [
        ('business_unit', '0012_organization_company_organization'),
        ('app', '0004_rename_purchase_frequency_alignment'),
        ('project', '0010_alter_action_status'),
        ('users', '0003_userprofile_department_alter_userprofile_role'),
        ('strategy', '0002_seed_reference_data'),
    ]

    operations = [
        migrations.RenameModel(old_name='BusinessUnit', new_name='Department'),
        migrations.RenameModel(old_name='Vertical', new_name='BusinessUnit'),
        migrations.AlterModelOptions(
            name='businessunit',
            options={'verbose_name': 'Business Unit', 'verbose_name_plural': 'Business Units'},
        ),
        migrations.AlterModelOptions(
            name='department',
            options={'verbose_name': 'Department', 'verbose_name_plural': 'Departments'},
        ),
    ]
