# Roles & Permissions

Authoritative spec for Kiboko access control. Enforcement is being wired via a
user-permission list; interim code checks are placeholders until then.

## Roles
Roles are **not mutually exclusive** — a user can hold several (e.g. a Chief
Analytics Officer = Executive + Analyst). Enforcement should therefore be
role-flags / many-to-many, not a single `profile.role`.

| Role | Code mapping |
|---|---|
| Account Owner / Org Admin | `Organization.org_admin` |
| Executive (Account Admin) | `senior_leadership` |
| Business Unit Leader (BUL) | `general_manager` (+ `BusinessUnit.general_manager` for the specific unit) |
| Business Unit User | `staff` |
| Analyst | new role |
| Developer | new role |
| Super User | Django `is_superuser` |

`supervisor` is retired (redundant with Business Unit Leader).

## Scope legend
Each permission operates at a level; a role's *reach* depends on assignment (a
BUL acts within their business unit; an Executive across the org).
**Self · Business Unit · Company (Client) · Org · Global**

## Permission matrix
✓ = allowed. (Owner=Account Owner/Org Admin, Exec=Executive, BUL=Business Unit
Leader, BUU=Business Unit User, Ana=Analyst, Dev=Developer, Sup=Super User.)

| Permission | Owner | Exec | BUL | BUU | Ana | Dev | Sup | Scope |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| View Project Pipeline Value | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| View Analytics (all dashboards) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| View Insights | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| View Projects | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| Update own profile | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Self |
| Send feedback | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Self |
| Comment on projects | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| Update project progress | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| Create a project (direct or via Insights) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| Send a project back (any backward move) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
| Edit other users | ✓ | ✓ | ✓* | | | | ✓ | Org / *BUL: their BU |
| Add user | ✓ | ✓ | ✓* | | | | ✓ | Org / *BUL: their BU |
| Remove user | ✓ | ✓ | ✓* | | | | ✓ | Org / *BUL: their BU |
| Assign roles | ✓ | ✓ | ✓* | | | | ✓ | Org / *BUL: their BU |
| Approve / deny projects (onto the Kanban) | ✓ | ✓ | ✓ | | | | ✓ | Business Unit |
| Edit any project | ✓ | ✓ | | | | | ✓ | Org |
| Update owned business-unit projects | | | ✓ | | | | ✓ | Business Unit |
| Change project owner | ✓ | ✓ | ✓ | | | | ✓ | Org / BU |
| Archive projects | ✓ | ✓ | ✓ | | | | ✓ | Org / BU |
| Promote Scored → Executive Approval | ✓ | ✓ | ✓ | | | | ✓ | Business Unit |
| Promote Executive Approval → On Deck | ✓ | ✓ | | | | | ✓ | Org |
| Move On Deck → WIP | ✓ | ✓ | ✓ | | | | ✓ | Business Unit |
| Move WIP → Complete / Launched | ✓ | ✓ | ✓ | | | | ✓ | Business Unit |
| Move a project to/from Blocked | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ | Business Unit |
| Estimate project value ($) | | | | | ✓ | | ✓ | Business Unit |
| Estimate level of effort | | | | | | ✓ | ✓ | Business Unit |
| Score: customer value | ✓ | ✓ | | | | | ✓ | Company / BU |
| Score: business value | ✓ | ✓ | | | ✓ | | ✓ | Company / BU |
| Score: cost savings | ✓ | ✓ | | | | | ✓ | Company / BU |
| Score: operational cost | ✓ | ✓ | | | | | ✓ | Company / BU |
| Score: business risk | ✓ | ✓ | | | | | ✓ | Company / BU |
| Score: level of effort | ✓ | ✓ | | | | ✓ | ✓ | Company / BU |
| Enter goals | ✓ | ✓ | ✓ | | | | ✓ | Company / BU |<!-- enforced: access.can_manage_goals -->
| Upload revenue actuals | | | ✓ | ✓ | ✓ | | | Business Unit |
| Connect / manage a Standard GA4 connection | ✓ | ✓ | ✓ | | | | ✓ | Company |
| Update BigQuery service-account credentials | ✓ | ✓ | | | | ✓ | ✓ | Company |<!-- enforced: access.can_manage_bigquery -->
<!-- Settings edit-permission enforcement: Goals -> access.can_manage_goals (Owner/Exec/BUL/Super);
     BigQuery connect -> access.can_manage_bigquery (Owner/Exec/Dev/Super); Billing -> org admin/super;
     Score Weights -> is_executive + administered company. Standard GA4 import is self-limited by the
     user's own Google access. -->
| Create a Company / Client | ✓ | ✓ | ✓ | | | | ✓ | Org |
| Create / edit Business Units | ✓ | ✓ | ✓ | | | | ✓ | Company |
| Assign the Business Unit Leader | ✓ | ✓ | ✓ | | | | ✓ | Company |
| Configure the strategy hierarchy (objectives/metrics/measures) | ✓ | ✓ | | | | | ✓ | Org / Company |
| Edit organization settings | ✓ | | | | | | ✓ | Org |
| Manage billing details | ✓ | | | | | | ✓ | Org |
| Upgrade account to Premium | ✓ | | | | | | ✓ | Org |
| Downgrade account | ✓ | | | | | | ✓ | Org |
| Deactivate account | ✓ | | | | | | ✓ | Org |
| Manage the Insights recommendation library | | | | | | | ✓ | Global |
| Manage SendGrid / feedback settings | | | | | | | ✓ | Global |
| Django admin access | | | | | | | ✓ | Global |

## Workflow rules (behaviors, not role cells)
- **Lanes:** Blocked · Ready to Score · Scored · Executive Approval · On Deck · WIP.
- **BUL promotes Scored → Executive Approval.** Scoring lands a project in Scored;
  a business-unit lead (or higher) then promotes the ones worth executive review,
  keeping the Executive Approval lane clean.
- **Forward promotions are gated; send-backs (any backward move) are open to anyone.**
  Blocking/unblocking is open (Analysts excepted — see below).
- **Kanban move audit.** Every Kanban move auto-creates a project comment recording
  the transition and the logged-in user.
- **Comments** always record the logged-in author; anyone can comment.
- **Projects are archived, never deleted** (the delete path is disabled).
- **Business-unit data access is governed by GA4** (a user's own Google access for
  Standard). ⚠️ Caveat: Premium uses a *shared* service account with no per-user
  GA4 scoping — if a Premium client needs per-user business-unit visibility, that
  still requires Kiboko-side scoping (`CompanyMembership.allowed_bus`).

## Scoring (Score Projects view) — anonymous, all-hands voting
Scoring is a **vote**, not a single edit. Every *pertinent* user scores each
approved project in the **Ready to Score** lane, and the project's consensus
score is the **average** of all votes. This deliberately dilutes the
highest-paid person's opinion so vanity/squirrel projects can't run wild.

- **Who votes (eligible voters):** the members of the project's business unit
  (company members scoped to that unit) **plus** the company's executives, plus
  the unit's general manager (`voting.eligible_scorer_ids`). A user only sees the
  projects they're a voter on; individual votes are never shown (anonymous).
- **Each user submits their own vote** on the six criteria (0–10). They can
  update it until the project finalizes. A per-project progress bar shows how
  many eligible voters have submitted (`voting.vote_progress`).
- **Finalize:** once *every* eligible voter has voted, each criterion is set to
  the average across votes and the project moves to **Scored**
  (`voting.finalize_if_complete`). Until then it stays in Ready to Score with no
  score. A BU lead then promotes it to Executive Approval from the Kanban.
- Votes live in `project.ScoreVote` (one row per action+user); the averaged
  criteria on the `Action` are weighted by the company's model to produce the
  0–10 `normalized_score`.

**Score weights (Settings › Score Weights).** The six criteria weights are set
**per company** (`project.ScoringWeights`, one row per Company; unset companies
use `scoring.DEFAULT_WEIGHTS`). Weights are percentages that must sum to 100 and
are applied by `Action.save()` via the action's company. **Only executives and
org admins** may edit them: a superuser (all companies), an org admin (their
orgs' companies), or an Executive-role holder (companies they belong to). A
project re-scores under its company's current weights the next time it is saved.

## Open items
- **Per-criterion scoring** — the current view scores all six criteria together
  (single weighted save). The per-criterion table above (who may set which
  criterion) is not yet individually gated.
- **Analyst block restriction + full role gating** land incrementally on the
  multi-role model (Track B). Interim checks still approximate a few cells.
