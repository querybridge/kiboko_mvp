"""Convert stored plausibility factors from the old straight-line discount to the
log diminishing-returns curve (impact.diminishing_factor).

The old factor was P = max(0.15, 1 - (z - 1) / 3), so z = 1 + 3 * (1 - P) recovers
the target's stretch exactly, except at the 0.15 floor where z was at least 3.55
(we use 3.55, the most conservative reading). Affected companies' scores are then
recomputed so the backlog reflects the new expected values.
"""
import math

from django.db import migrations

OLD_FLOOR = 0.15
K = 1.0   # impact.DIMINISHING_K at the time of this migration


def _new_factor(old):
    z = 1.0 + 3.0 * (1.0 - max(old, OLD_FLOOR))
    return 1.0 if z <= 1.0 else (1.0 + K * math.log1p((z - 1.0) / K)) / z


def forwards(apps, schema_editor):
    Project = apps.get_model('strategy', 'Project')
    companies = set()
    for p in Project.objects.filter(plausibility_factor__lt=0.9999):
        Project.objects.filter(pk=p.pk).update(plausibility_factor=round(_new_factor(p.plausibility_factor), 4))
        if p.vertical_id:
            companies.add(p.vertical.company_id)
    if not companies:
        return
    # Rescore with the live models so value / algo_raw / normalized_score update.
    from business_unit.models import Company
    from project.services import impact
    for c in Company.objects.filter(pk__in=companies):
        impact.recompute_scores(company=c)


class Migration(migrations.Migration):

    dependencies = [
        ('strategy', '0009_project_analyst_adjustments_project_analyst_note_and_more'),
        ('business_unit', '0019_retire_sendgridsettings'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
