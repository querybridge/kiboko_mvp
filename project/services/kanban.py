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
    ('active',           'WIP'),
])

# The status value stored on an Action for each lane. Status == the Kanban
# column, so moving a card (or saving one) writes the matching status here.
LANE_STATUS = {
    'blocked':          'Blocked',
    'incomplete_entry': 'Incomplete Entry',
    'ready_to_score':   'Ready to Score',
    'scored':           'Scored',
    'on_deck':          'On Deck',
    'active':           'WIP',
}
STATUS_LANE = {status: lane for lane, status in LANE_STATUS.items()}

# Terminal statuses -- not Kanban columns; they live in the Archive.
TERMINAL_STATUSES = ('Complete', 'Launched')

# Fields required before a project can be scored
REQUIRED_FOR_SCORING = [
    'name', 'project_id', 'business_unit_id', 'owner_id', 'why',
]


def _has_score(project):
    return project.normalized_score is not None and project.normalized_score > 0


# The six Kanban columns a card can be placed into. Any of these set on an
# action is authoritative -- a move or an edit-form change sticks as-is.
COLUMN_STATUSES = set(LANE_STATUS.values())


def derive_status(project):
    """The canonical status (== Kanban column) an Action should carry.

    `status` is the single source of truth: whatever column a move or the edit
    form sets is honored as-is, so cards stay where you drop them. Terminal
    states (Complete / Launched) are likewise kept. Only a blank / legacy status
    -- a brand-new entry or an old Pending Approval/Assignment row -- gets an
    initial column inferred from completeness + score.
    """
    status = (project.status or '').strip()

    # Terminal states and any explicitly-chosen Kanban column are authoritative.
    if status in TERMINAL_STATUSES or status in COLUMN_STATUSES:
        return status

    # Blank / legacy -> infer the starting column from the entry itself.
    if status == 'Pending Assignment':
        return 'On Deck'
    if _is_incomplete(project):
        return 'Incomplete Entry'
    if _has_score(project):
        return 'Scored'
    return 'Ready to Score'

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

    Status mirrors the column (kept in sync by Action.save), so we map the
    stored status straight to its lane. Legacy statuses fall through to a
    completeness/score derivation for safety.
    """
    status = (project.status or '').strip()

    if status == 'Blocked' or project.is_blocked:
        return 'blocked'

    if status in STATUS_LANE:
        return STATUS_LANE[status]

    # Legacy / unsynced statuses (Pending Approval, Pending Assignment, blank).
    if status == 'Pending Assignment':
        return 'on_deck'
    has_score = _has_score(project)
    if has_score and status == 'Pending Approval':
        return 'scored'
    if _is_incomplete(project):
        return 'incomplete_entry'
    if not has_score:
        return 'ready_to_score'
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

    # Status == the target column (authoritative). save() mirrors is_blocked
    # from the status, so dropping a card is all it takes.
    project.status = LANE_STATUS[target_lane]
    if target_lane in ('on_deck', 'active'):
        project.approved = True

    project.save()
    return True, None
