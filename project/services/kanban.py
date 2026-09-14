"""
Kanban board service layer.

Provides lane assignment, grouping, and summary totals for the Kanban view.
All lane logic lives here so it is testable and consistent.
"""
from collections import OrderedDict

# Ordered lane definitions. The Kanban is the weekly EXECUTIVE meeting board; it
# only shows projects a business-unit lead has approved. Incomplete/pending-review
# entries live in the Approve Projects view, not here. Executive Approval sits
# after Scored -- execs move cards from there to On Deck in the weekly meeting.
LANES = OrderedDict([
    ('blocked',             'BLOCKED'),
    ('ready_to_score',      'READY TO SCORE'),
    ('scored',              'SCORED'),
    ('executive_approval',  'EXECUTIVE APPROVAL'),
    ('on_deck',             'ON DECK'),
    ('active',              'WIP'),
])

# The status value stored on an Action for each lane.
LANE_STATUS = {
    'blocked':             'Blocked',
    'ready_to_score':      'Ready to Score',
    'scored':              'Scored',
    'executive_approval':  'Executive Approval',
    'on_deck':             'On Deck',
    'active':              'WIP',
}
STATUS_LANE = {status: lane for lane, status in LANE_STATUS.items()}

# Terminal statuses -- not Kanban columns; they live in the Archive.
TERMINAL_STATUSES = ('Complete', 'Launched')

# Fields required before a project can be scored
REQUIRED_FOR_SCORING = [
    'name', 'project_id', 'business_unit_id', 'owner_id', 'why',
]

# Fields a business-unit lead reviews before approving a project onto the Kanban.
REQUIRED_FOR_REVIEW = ['name', 'owner_id', 'objective_id', 'aee_alignment', 'impact']


def _has_score(project):
    return project.normalized_score is not None and project.normalized_score > 0


def is_ready_for_review(project):
    """Complete enough for a business-unit lead to approve: name, owner, objective,
    AEE alignment, Definition of Done, and a projected value."""
    for field in REQUIRED_FOR_REVIEW:
        val = getattr(project, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            return False
    return (project.value or 0) > 0


def is_executive(user):
    """Interim executive check (superuser or admin/senior_leadership) -- will be
    superseded by the forthcoming user-permission list."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    return getattr(getattr(user, 'profile', None), 'role', '') in ('admin', 'senior_leadership')


def can_approve(user, project):
    """Whether the user may approve this project (business-unit lead). Interim:
    the business unit's general_manager, or a superuser / the org's admin."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    bu = getattr(project, 'vertical', None)
    if bu and bu.general_manager_id == user.id:
        return True
    company = getattr(bu, 'company', None) if bu else None
    if company and company.organization_id:
        from business_unit.access import is_org_admin_of
        return is_org_admin_of(user, company)
    return False


def is_bul_or_higher(user, project):
    """Business-unit lead or above (interim): the BU's lead, an executive, an org
    admin, or a superuser."""
    return is_executive(user) or can_approve(user, project)


# Forward order of the flow lanes (Blocked is out-of-band).
LANE_ORDER = ('ready_to_score', 'scored', 'executive_approval', 'on_deck', 'active')


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

    # Blank / legacy -> infer. Incomplete OR not-yet-approved entries carry
    # 'Incomplete Entry' (a status, no longer a Kanban lane); they live in the
    # Approve Projects view until a business-unit lead approves them.
    if status == 'Pending Assignment':
        return 'On Deck'
    if _is_incomplete(project) or not project.approved:
        return 'Incomplete Entry'
    if _has_score(project):
        return 'Scored'
    return 'Ready to Score'

# Transitions: which lanes can a card be dragged INTO
# None means "any lane can reach it"; a list means those source lanes only.
ALLOWED_TRANSITIONS = {
    'blocked':             None,  # can always block
    'ready_to_score':      None,
    'scored':              None,  # validated server-side for score > 0
    'executive_approval':  None,  # validated server-side for score > 0
    'on_deck':             None,  # only executives, out of Executive Approval
    'active':              None,
}


def get_lane(project):
    """The Kanban lane a project belongs to. The Kanban only shows approved cards
    (callers pre-filter approved=True), so status maps straight to a lane; an
    unmapped status defaults safely to the entry lane."""
    status = (project.status or '').strip()

    if status == 'Blocked' or project.is_blocked:
        return 'blocked'
    if status in STATUS_LANE:
        return STATUS_LANE[status]
    # Off-Kanban / legacy status on an approved card -> default by score.
    return 'scored' if _has_score(project) else 'ready_to_score'


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
    """Summary totals for the cards in one lane -- the impact of completing them
    all. `sales` is the headline: total projected value at stake in the column
    (e.g. how much value is blocked), robust to cards that set `value` but not
    the per-lever breakdown. visits/close_rate/aov are that breakdown.
    """
    visits = close_rate = aov = value = 0
    for p in projects_in_lane:
        visits += p.impact_visits_value or 0
        close_rate += p.impact_close_rate_value or 0
        aov += p.impact_aov_value or 0
        value += (p.value or p.project_value_total or 0)
    return {
        'visits': visits,
        'close_rate': close_rate,
        'aov': aov,
        'sales': value,   # total projected value of the column's cards
    }


def compute_all_lane_totals(grouped):
    """Compute totals for every lane.

    Takes output of group_projects(), returns {lane_key: totals_dict}.
    """
    return {
        lane_key: compute_lane_totals(projects)
        for lane_key, projects in grouped.items()
    }


def validate_move(project, target_lane, user=None):
    """Check whether `user` can move `project` to target_lane.

    Returns (ok: bool, error_message: str|None).
    """
    if target_lane not in LANES:
        return False, f'Unknown lane: {target_lane}'

    # Scoring gate: everything past Ready to Score needs a score.
    if target_lane in ('scored', 'executive_approval', 'on_deck', 'active') and not _has_score(project):
        return False, 'Project must be scored first.'

    # Blocking/unblocking is open; backward moves (send-backs) are open to anyone.
    # Forward promotions are role-gated.
    if target_lane != 'blocked':
        current = get_lane(project)
        ci = LANE_ORDER.index(current) if current in LANE_ORDER else -1
        ti = LANE_ORDER.index(target_lane) if target_lane in LANE_ORDER else -1
        if ti > ci:  # forward promotion
            if target_lane == 'executive_approval' and not is_bul_or_higher(user, project):
                return False, 'Only a business-unit lead (or higher) can promote to Executive Approval.'
            if target_lane == 'on_deck' and not is_executive(user):
                return False, 'Only an executive can move a project to On Deck.'
            if target_lane == 'active' and not is_bul_or_higher(user, project):
                return False, 'Only a business-unit lead (or higher) can move a project to WIP.'

    return True, None


def apply_move(project, target_lane, user=None):
    """Apply lane change to project fields and save.

    Returns (ok: bool, error_message: str|None).
    """
    ok, err = validate_move(project, target_lane, user=user)
    if not ok:
        return False, err

    # Status == the target column (authoritative). save() mirrors is_blocked
    # from the status, so dropping a card is all it takes.
    project.status = LANE_STATUS[target_lane]
    if target_lane in ('on_deck', 'active'):
        project.approved = True

    project.save()
    return True, None
