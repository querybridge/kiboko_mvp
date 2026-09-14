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
| View Project Value Pipeline | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Business Unit |
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
| Enter goals | ✓ | ✓ | ✓ | | | | ✓ | Company / BU |
| Upload revenue actuals | | | ✓ | ✓ | ✓ | | | Business Unit |
| Connect / manage a Standard GA4 connection | ✓ | ✓ | ✓ | | | | ✓ | Company |
| Update BigQuery service-account credentials | ✓ | ✓ | | | | ✓ | ✓ | Company |
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
- **Scoring auto-advances.** When a project is fully scored, it moves automatically
  from Ready to Score to **Executive Approval** (no manual step).
- **Kanban move audit.** Every Kanban move auto-creates a project comment recording
  the transition and the logged-in user.
- **Comments** always record the logged-in author.
- **Projects are archived, never deleted.** (Remove the delete-project path.)
- **Business-unit data access is governed by GA4** (a user's own Google access for
  Standard). ⚠️ Caveat: Premium uses a *shared* service account with no per-user
  GA4 scoping — if a Premium client needs per-user business-unit visibility, that
  still requires Kiboko-side scoping (`CompanyMembership.allowed_bus`).

## Open items
- **Scored lane is now redundant** — since scoring auto-advances to Executive
  Approval, the "Scored" Kanban column would always be empty. Recommend removing
  it → lanes: Blocked · Ready to Score · Executive Approval · On Deck · WIP.
- **Scoring permissions** — per-criterion table above is a first pass (you noted
  you'd revisit); confirm whether BULs score anything and how "estimate value/LOE"
  relate to the criteria.
- **Move to/from Blocked** currently excludes Analyst — confirm (vs. "anyone").
