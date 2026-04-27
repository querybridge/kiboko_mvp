"""
Kanban board service layer.

Provides lane assignment, grouping, and summary totals for the Kanban view.
All lane logic lives here so it is testable and consistent.
"""
from collections import OrderedDict

# Ordered lane definitions
LANES = OrderedDict([
    ('blocked',          'BLOCKED'),
    ('incomplete_entry', 'INCOMPLETE ENTRY'),
    ('ready_to_score',   'READY TO SCORE'),
    ('scored',           'SCORED'),
    ('on_deck',          'ON DECK'),
    ('active',           'ACTIVE'),
])

# Fields required before a project can be scored
REQUIRED_FOR_SCORING = [
    'name', 'strategy_id', 'business_unit_id', 'owner_id', 'why',
]

# Transitions: which lanes can a card be dragged INTO
# None means "any lane can reach it"; a list means those source lanes only.
ALLOWED_TRANSITIONS = {
    'blocked':          None,  # can always block
    'incomplete_entry': None,
    'ready_to_score':   None,  # validated server-side for required fields
    'scored':           None,  # validated server-side for score > 0
    'on_deck':          None,  # validated server-side for score > 0
    'active':           None,
}


def get_lane(project):
    """Determine which Kanban lane a project belongs to.

    Priority order matters -- is_blocked is checked first, then status-based
    rules, then scoring completeness.
    """
    if project.is_blocked:
        return 'blocked'

    status = (project.status or '').strip()

    if status == 'Active':
        return 'active'

    if status == 'On Deck':
        return 'on_deck'

    if status in ('Pending Assignment',):
        return 'on_deck'

    # Check if scoring is complete
    has_score = project.normalized_score is not None and project.normalized_score > 0

    if has_score and status == 'Pending Approval':
        return 'scored'

    # Check required fields
    if _is_incomplete(project):
        return 'incomplete_entry'

    if not has_score:
        return 'ready_to_score'

    # Fallback for scored but unmatched status
    return 'scored'


def _is_incomplete(project):
    """Return True if project is missing required fields for scoring."""
    for field in REQUIRED_FOR_SCORING:
        val = getattr(project, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            return True
    return False


def group_projects(projects):
    """Group a queryset/list of projects into lane buckets.

    Returns OrderedDict {lane_key: [project, ...]} preserving LANES order.
    """
    groups = OrderedDict((key, []) for key in LANES)
    for project in projects:
        lane = get_lane(project)
        groups[lane].append(project)
    return groups


def compute_lane_totals(projects_in_lane):
    """Compute summary KPI totals for a list of projects in one lane.

    Returns dict with visits, close_rate, aov, sales values.
    """
    visits = 0
    close_rate = 0
    aov = 0
    for p in projects_in_lane:
        visits += p.impact_visits_value or 0
        close_rate += p.impact_close_rate_value or 0
        aov += p.impact_aov_value or 0
    sales = visits + close_rate + aov
    return {
        'visits': visits,
        'close_rate': close_rate,
        'aov': aov,
        'sales': sales,
    }


def compute_all_lane_totals(grouped):
    """Compute totals for every lane.

    Takes output of group_projects(), returns {lane_key: totals_dict}.
    """
    return {
        lane_key: compute_lane_totals(projects)
        for lane_key, projects in grouped.items()
    }


def validate_move(project, target_lane):
    """Check whether a project can be moved to target_lane.

    Returns (ok: bool, error_message: str|None).
    """
    if target_lane not in LANES:
        return False, f'Unknown lane: {target_lane}'

    if target_lane == 'ready_to_score':
        if _is_incomplete(project):
            return False, 'Project is missing required fields. Complete the entry first.'

    if target_lane == 'scored':
        has_score = project.normalized_score is not None and project.normalized_score > 0
        if not has_score:
            return False, 'Project must be scored before moving to SCORED.'

    if target_lane == 'on_deck':
        has_score = project.normalized_score is not None and project.normalized_score > 0
        if not has_score:
            return False, 'Project must be scored before moving to ON DECK.'

    if target_lane == 'active':
        has_score = project.normalized_score is not None and project.normalized_score > 0
        if not has_score:
            return False, 'Project must be scored before moving to ACTIVE.'

    return True, None


def apply_move(project, target_lane):
    """Apply lane change to project fields and save.

    Returns (ok: bool, error_message: str|None).
    """
    ok, err = validate_move(project, target_lane)
    if not ok:
        return False, err

    if target_lane == 'blocked':
        project.is_blocked = True
    else:
        project.is_blocked = False

        if target_lane == 'incomplete_entry':
            project.status = 'Pending Approval'
        elif target_lane == 'ready_to_score':
            project.status = 'Pending Approval'
        elif target_lane == 'scored':
            project.status = 'Pending Approval'
        elif target_lane == 'on_deck':
            project.status = 'On Deck'
            project.approved = True
        elif target_lane == 'active':
            project.status = 'Active'
            project.approved = True

    project.save()
    return True, None
