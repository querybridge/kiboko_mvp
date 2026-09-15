"""Data migration: make Project the scored unit, Action its child task.

For each existing Action we create a 1:1 parent Project carrying the workflow
fields (owner, business unit, revenue, LOE, criteria, score, approval, Kanban
status) and repoint the Action to it as a child execution task. Objective AEE is
backfilled from the Actions that referenced it. Orphaned (now childless) Projects
from the old grouping are removed.
"""
from collections import Counter
from django.db import migrations

CRITERIA_VOTED = ['customer_value', 'business_value', 'cost_savings',
                  'operational_cost', 'business_risk']


def forward(apps, schema_editor):
    Action = apps.get_model('project', 'Action')
    Project = apps.get_model('strategy', 'Project')
    Objective = apps.get_model('strategy', 'Objective')

    # 1. Objective AEE <- most common alignment among its Actions.
    for obj in Objective.objects.all():
        if obj.aee_alignment:
            continue
        aees = [a.aee_alignment for a in Action.objects.filter(objective=obj) if a.aee_alignment]
        if aees:
            obj.aee_alignment = Counter(aees).most_common(1)[0][0]
            obj.save(update_fields=['aee_alignment'])

    # 2. Promote each Action to a 1:1 parent Project; keep the Action as its child.
    for a in Action.objects.all():
        p = Project.objects.create(
            name=(a.name or 'Project')[:75],
            why=a.why or '',
            definition_of_done=(a.impact or '')[:350],
            objective=a.objective,
            department_id=a.business_unit_id,          # Action.business_unit is a Department
            owner_id=a.owner_id,
            vertical_id=a.vertical_id,
            value=a.value or 0,
            level_of_effort=a.level_of_effort or 0,
            normalized_score=a.normalized_score or 0,
            approved=a.approved,
            status=a.status,
            is_blocked=a.is_blocked,
            archived=a.archived,
            **{c: getattr(a, c, 0) or 0 for c in CRITERIA_VOTED},
        )
        a.project_id = p.id
        a.save(update_fields=['project'])

    # 3. Drop old grouping Projects that no longer have any actions.
    for p in Project.objects.all():
        if not Action.objects.filter(project_id=p.id).exists():
            p.delete()


def backward(apps, schema_editor):
    # One-way transform; leave data as-is on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('strategy', '0004_objective_aee_alignment_project_approved_and_more'),
        ('project', '0014_scorevote'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
