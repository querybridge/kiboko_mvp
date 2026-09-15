"""Anonymous, all-hands project scoring.

Every pertinent user -- the members of a project's business unit plus the
company's executives -- scores each project on the five voted BVM criteria (the
sixth, level of effort, is a Developer's specialist input). The project's
consensus score is the average of all votes, and it only advances to Scored once
everyone eligible has voted. Averaging anonymously keeps the highest-paid
person's opinion from steering the board toward vanity projects.
"""
from project.scoring import VOTED_CRITERIA


def eligible_scorer_ids(project):
    """User ids expected to vote on `project`: every member of its business unit
    (company members scoped to that unit) plus the company's executives and the
    unit's general manager. Empty if the project has no business unit/company."""
    bu = getattr(project, 'vertical', None)
    if bu is None or bu.company_id is None:
        return set()
    ids = set()
    memberships = (bu.company.memberships
                   .select_related('user', 'user__profile')
                   .prefetch_related('allowed_bus'))
    for m in memberships:
        allowed = m.allowed_bu_ids()          # None = all of the company's units
        prof = getattr(m.user, 'profile', None)
        in_bu = allowed is None or bu.id in allowed
        is_exec = bool(prof and prof.has_role('executive'))
        if in_bu or is_exec:                  # BU members + company execs
            ids.add(m.user_id)
    if bu.general_manager_id:                  # the BU lead
        ids.add(bu.general_manager_id)
    return ids


def is_eligible(project, user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return user.id in eligible_scorer_ids(project)


def vote_progress(project, eligible=None):
    """{'voted', 'total', 'pct'} -- how many eligible voters have scored."""
    if eligible is None:
        eligible = eligible_scorer_ids(project)
    total = len(eligible)
    voted = len(set(project.score_votes.values_list('user_id', flat=True)) & eligible)
    pct = int(round(100 * voted / total)) if total else 0
    return {'voted': voted, 'total': total, 'pct': pct}


def record_vote(project, user, values):
    """Upsert one user's vote (the five voted criteria), then finalize the
    project if everyone has voted. Returns (vote, finalized: bool)."""
    from project.models import ScoreVote
    vote, _ = ScoreVote.objects.update_or_create(
        project=project, user=user,
        defaults={c: max(0, min(10, int(values.get(c, 0) or 0))) for c in VOTED_CRITERIA})
    return vote, finalize_if_complete(project)


def finalize_if_complete(project):
    """If every eligible voter has voted, set the project's five voted criteria to
    the average across votes and move it to Scored (the developer-set LOE is left
    as-is). Returns True if it finalized."""
    from project.services.kanban import LANE_STATUS
    eligible = eligible_scorer_ids(project)
    if not eligible:
        return False
    votes = [v for v in project.score_votes.all() if v.user_id in eligible]
    if len(votes) < len(eligible):
        return False
    n = len(votes)
    for c in VOTED_CRITERIA:
        setattr(project, c, int(round(sum(getattr(v, c) for v in votes) / n)))
    project.status = LANE_STATUS['scored']     # only now does it advance
    project.save()
    return True
