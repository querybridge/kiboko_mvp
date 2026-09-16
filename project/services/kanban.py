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

# Fields required before a project is complete enough to enter the pipeline.
REQUIRED_FOR_SCORING = [
    'name', 'owner_id', 'vertical_id', 'why',
]

# Fields a business-unit lead reviews before approving a project into the
# pipeline. AEE is inherited from the objective, so requiring the objective (with
# an AEE) covers it. Revenue and LOE are set later (Analyst, then Developer).
# Ready for a BU lead to approve: identity + objective + a completed impact
# estimate (lever it moves, current/target level, sales baseline). An idea with no
# estimate (e.g. a raw Insights recommendation) stays an Incomplete Entry until the
# estimator is filled in via Edit.
REQUIRED_FOR_REVIEW = ['name', 'owner_id', 'objective_id', 'definition_of_done',
                       'lever', 'target_from', 'target_to', 's0_annual']


def _has_score(project):
    return project.normalized_score is not None and project.normalized_score > 0


def is_ready_for_review(project):
    """Complete enough for a business-unit lead to approve: name, owner, an
    objective (which carries the AEE element), and a Definition of Done."""
    for field in REQUIRED_FOR_REVIEW:
        val = getattr(project, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            return False
    return True


def is_executive(user):
    """Executive or above: superuser, an Account Owner (org admin), or a user
    holding the Executive role."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.administered_orgs.exists():
        return True
    prof = getattr(user, 'profile', None)
    return bool(prof and prof.has_role('executive'))


def can_approve(user, project):
    """Business-unit lead (or higher) for this project: a user with the Business
    Unit Leader role, the BU's general_manager, a superuser, or the org admin."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    prof = getattr(user, 'profile', None)
    if prof and prof.has_role('business_unit_leader'):
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
    """Business-unit lead or above: BU lead, executive, org admin, or superuser."""
    return is_executive(user) or can_approve(user, project)


def _has_role(user, role):
    prof = getattr(user, 'profile', None)
    return bool(prof and prof.has_role(role))


def can_set_revenue(user, project):
    """Set the projected revenue during intake -- an Analyst (or exec/super)."""
    return is_executive(user) or _has_role(user, 'analyst')


def can_set_loe(user, project):
    """Set the level of effort during intake -- a Developer (or exec/super)."""
    return is_executive(user) or _has_role(user, 'developer')


# Scoring itself is anonymous, all-hands voting -- see project.services.voting.
# A project's eligible voters are its business-unit members plus company execs,
# and it advances to Scored only once everyone has voted.


# Forward order of the flow lanes (Blocked is out-of-band).
LANE_ORDER = ('ready_to_score', 'scored', 'executive_approval', 'on_deck', 'active')


# The six Kanban columns a card can be placed into. Any of these set on a
# project is authoritative -- a move or an edit-form change sticks as-is.
COLUMN_STATUSES = set(LANE_STATUS.values())

# Intake pipeline (pre-Kanban): a project is approved by a BU lead, then an
# Analyst sets revenue, then a Developer sets LOE, then it's Ready to Score.
PIPELINE_STATUSES = ('Incomplete Entry', 'Pending Revenue', 'Pending LOE')


def derive_status(project):
    """The canonical status a project should carry.

    `status` is the single source of truth: an explicitly-set Kanban column,
    intake stage, or terminal state is honored as-is. Only a blank / legacy
    status gets an initial stage inferred from completeness, approval, revenue,
    and LOE (the intake sequence: Incomplete -> Pending Revenue -> Pending LOE
    -> Ready to Score).
    """
    status = (project.status or '').strip()

    # Explicit column / intake / terminal states are authoritative.
    if (status in TERMINAL_STATUSES or status in COLUMN_STATUSES
            or status in PIPELINE_STATUSES):
        return status

    if status == 'Pending Assignment':
        return 'On Deck'
    # Blank / legacy -> infer the intake stage. Revenue is auto-estimated at Add
    # Project, so there's no Analyst stage: after BU-lead approval a Developer
    # sets the effort size + capability, then it's Ready to Score.
    if _is_incomplete(project) or not project.approved:
        return 'Incomplete Entry'
    if not (getattr(project, 'effort_size', '') and getattr(project, 'capability', '')):
        return 'Pending LOE'
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
    """Summary totals for the cards in one lane -- `sales` is the total projected
    revenue at stake in the column (e.g. how much value is blocked)."""
    value = 0
    for p in projects_in_lane:
        value += (p.value or 0)
    return {'sales': value}


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
