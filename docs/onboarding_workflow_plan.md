# Onboarding, Organizations & Permissions — Plan

Status: **designed, not yet built.** Companion to `daily_rollup_cache_plan.md`
(which is parked behind this). Captures the decisions from the onboarding design
sessions so we can build in phases.

## Tenancy model (new top level: Organization)
```
Organization   ← NEW. The account / billing entity. Exactly ONE org admin.
   └── Company            (agency: shown as "Client"; direct: "Company")
          └── BusinessUnit   (was "Vertical" = a GA4 property)
                 └── Website  (GA4 data stream)
User ∈ Organization → Company access (membership) → scoped to BusinessUnits (per-user)
```
- **Organization** = billing entity. Agency = many companies; direct = one.
- **One org admin** per organization (single person; a field, not a role list).
- **Company admin** = `CompanyMembership.role = admin` — each company can have its
  own admin (e.g., an agency's per-client leader). Distinct from the org admin.

## Locked decisions
- **C1** — Premium connection requires a company first; Standard connection may
  attach its company later (can sit "unassigned" until an admin attaches it).
- **C2** — Keep the current Google sign-in flow (self-serve; see Trial).
- **C4 / Organization** — New account = Organization. Billing defines it.
- **Org type** — explicit flag `Organization.kind = agency | direct`.
- **Terminology** — agency orgs label Company as **"Client"**; direct orgs keep
  **"Company"**. Everywhere, **"Vertical" → "Business Unit"**.
- **Business Unit rename** — rename the tenancy model `Vertical → BusinessUnit`
  and **retire the PPM `BusinessUnit`** (departments). ⚠️ See risk below.
- **Trial** — self-serve 30-day trial; expiry **locks everything except Billing**
  for the org admin (non-admins see "trial ended — contact your admin").
- **Demo Account** — a **platform demo** org, visible to all trial orgs so new
  users have something to explore before connecting data.
- **Billing** — new Settings link, **visible only to org admins**, blank for now.

## Data migration (target state)
| Organization | kind | Companies (agency: "Clients") | Notes |
|---|---|---|---|
| **Querybridge** | agency | VOLT Lighting, Autocado | org admin: `sherman@querybridge.com` |
| **Belami** | direct | Belami | org + company same name; admin: `belami` user (confirm) |
| **Demo** (platform) | direct/demo | Demo Account | visible to all trial orgs |
| ~~VW Group~~ | — | — | **DELETE** company + its business units/websites/memberships + any GA4/rollup rows exclusive to it |

- Existing `CompanyMembership` admins stay as **company** admins.
- `master` / `kiboko` superusers remain **platform** (see all orgs), not org-bound.

## Permissions — target state
- **Platform superuser** (Django admin only; never mintable via the UI) — sees all
  orgs/companies. Reserved for Querybridge operators.
- **Org admin** (one per org) — manages the org: creates companies, adds users,
  assigns company + business-unit access, sees Billing.
- **Company admin** — manages one company's users/data.
- **Member** — views the companies + business units they're scoped to.
- **New/unprovisioned user** — no access → "contact your admin" banner (shows the
  relevant admin's first/last name + email: company admin for a specific company,
  else the org admin).
- **Cross-org isolation** — every company/business-unit/data query is scoped to the
  viewer's organization. A member of Org A must never see Org B.
- **Per-user business-unit scoping** (was gap G1) — `CompanyMembership.allowed_bus`
  (M2M; empty = all of that company's business units), enforced in the context
  processor **and** every provider/scope resolver. Rationale: a service account
  can see all GA4 properties, so the admin decides which business units each user
  sees.

## Onboarding flows
**Direct client**: New account → (auto-creates trial Organization; user = org
admin) → Add Company → Add Users (≥1 admin) → Connect Data → Set Goals → Add more
users. Billing forced at day 30.

**Agency**: New account → trial Org (agency) → Add Users (agency staff, ≥1 admin)
→ Add Client (Company) → Connect Data → Set Goals → repeat per client → add users.

**Sign-in resolution** (keeps C2): a Google sign-in whose email matches a
pre-provisioned user → link into their existing org (no new org). A brand-new
email → auto-create a trial Organization with that user as org admin.

## ⚠️ Risk: retiring the PPM `BusinessUnit`
The chosen "rename model + retire PPM departments" collides with live PPM code.
`business_unit/models.py:BusinessUnit` (departments) is referenced by:
- `project/models.py:44` — `Project.business_unit` (required FK, CASCADE)
- `users/models.py:21` — `UserProfile.department`
- `strategy/models.py:95` — `department`
- `app/models.py:146` — a **duplicate** legacy `BusinessUnit` class (+ `app/admin.py`)
- assorted views/commands (`app/views.py`, `seed_projects.py`, `project/views.py:70`)

Deleting it outright breaks Projects/Strategy. **Recommended safe path:**
1. Rename the PPM model `BusinessUnit → Department` (it already *is* "departments")
   — frees the name, keeps PPM working; update its FKs/admin/views.
2. Delete the dead duplicate `app/models.py:146 BusinessUnit`.
3. Rename tenancy `Vertical → BusinessUnit` (model, related_names, templates,
   selectors, providers, scope helpers).
4. "Retire PPM departments" = remove them from the customer-facing UI (not the
   data), unless you want the Projects/Strategy features gone too (open question).

## Phased build order
- **Phase 1 — Organization foundation (additive, low risk):** `Organization`
  model (name, slug, kind, org_admin FK, trial_started, plan/status),
  `Company.organization` FK; data migration (create Querybridge/Belami/Demo orgs,
  assign companies, delete VW Group); Billing link in Settings (org-admin-only) +
  blank view.
- **Phase 2 — Business Unit rename:** PPM `BusinessUnit→Department`, drop the dead
  duplicate, tenancy `Vertical→BusinessUnit`. (Separate PR; highest churn.)
- **Phase 3 — Access & isolation:** org-scoped context processor + providers;
  platform-vs-org superuser split; per-user business-unit scoping
  (`allowed_bus`); ≥1-admin enforcement; disable `register`; login audit.
- **Phase 4 — Onboarding & trial:** sign-in resolution (link vs new trial org);
  30-day trial gate → Billing lock; "contact your admin" banner; empty states;
  agency "Client" vs direct "Company" labels; onboarding checklist.
- **Phase 5 — Billing:** real billing (Stripe) behind the stub link. Separate.

## Open questions
1. **PPM retirement scope** — keep Projects/Strategy working (recommended:
   rename department model, retire only the *label*) or remove those features too?
2. **Belami org admin** — the `belami` user, or `sherman`?
3. **Company-admin cardinality** — one designated admin per company, or allow
   several? (Model permits several.)
4. **Org-admin transfer** — mechanism to reassign the single org admin later.
