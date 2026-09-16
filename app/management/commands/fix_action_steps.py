"""Replace migration-artifact actions with real step chains.

The Action->Project promotion left each migrated project with a single child
action named identically to the project. This command finds those (a lone action
whose name matches its project) and replaces them with a named step chain
(Design -> Build -> Launch ...), so actions read as steps toward completing the
project rather than repeating its name. Multi-action projects (e.g. reseeded
demo) are left untouched.
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from strategy.models import Project
from project.models import Action

STEP_SETS = [
    ['Discovery & specs', 'Design', 'Build', 'QA & launch'],
    ['Requirements', 'Build', 'Test & QA', 'Rollout'],
    ['Design mockups', 'Implementation', 'Launch'],
    ['Data model', 'Build integration', 'QA', 'Go live'],
]


class Command(BaseCommand):
    help = 'Replace 1:1 migration-artifact actions (named like their project) with step chains.'

    def handle(self, *args, **opts):
        rng = random.Random(7)
        fixed = 0
        for p in Project.objects.all():
            acts = list(p.actions.all())
            if len(acts) != 1:
                continue
            old = acts[0]
            if (old.name or '').strip() != (p.name or '').strip():
                continue  # not an artifact -- leave real single-task projects alone

            owner, team, measure = old.owner, old.team, old.measure
            vertical = old.vertical or p.vertical
            dept = old.business_unit
            base_launch = old.launch or p.target_completion
            base_progress = old.progress or 0
            is_wip = p.status == 'WIP'

            steps = rng.choice(STEP_SETS)
            n = len(steps)
            if base_launch:
                spans = [base_launch - timedelta(days=int(25 * (n - 1 - i))) for i in range(n)]
            else:
                spans = [None] * n
            progs = ([100] * (n - 2) + [max(base_progress, 40), 0]) if is_wip else [0] * n

            old.delete()
            prev = None
            for step_name, launch_d, prog in zip(steps, spans, progs):
                a = Action(
                    project=p, owner=owner, business_unit=dept, vertical=vertical,
                    objective=p.objective, name=step_name, why=p.why or '',
                    impact=p.definition_of_done or '', launch=launch_d, progress=prog,
                    team=team, measure=measure)
                a.save()
                if prev is not None:
                    a.depends_on.add(prev)
                if launch_d:
                    cdt = max(date(launch_d.year, 1, 1), launch_d - timedelta(days=20))
                    flds = {'date_created': cdt}
                    if is_wip:
                        flds['active_date'] = cdt
                    Action.objects.filter(pk=a.pk).update(**flds)
                prev = a
            fixed += 1

        self.stdout.write(self.style.SUCCESS(
            f'fix_action_steps: replaced {fixed} artifact action(s) with step chains.'))
