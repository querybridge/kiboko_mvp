# Kiboko MVP — Gap Analysis vs. Core Promises

Assessment of whether the MVP meets the feature/functional promises made in:

- **Site** — https://kibokomethod.com/features-benefits/
- **Charter** — `Kiboko Charter.docx` (screen-by-screen spec)
- **Business Plan** — `Business Plan v4 (1).pdf`

Prepared 2026-09-16. Kiboko has evolved (terminology has drifted — e.g. the MVP's
hierarchy is **AEE › Objective › Project › Action**, vs. the Charter's
**Objective › Strategy/Initiative › Tactic/Project**); this focuses on the
*functional* promises, not naming.

---

## Verdict

The MVP **delivers the core experiential loop** — the "heads-up display vs.
rearview mirror," anti-HiPPO objective scoring, Attract/Engage/Expand analytics,
and budget beat/miss forecasting are real and working. It is credibly "the
Kiboko Method" for a **design-partner / private beta today**.

The gaps are concentrated in **(a) the proprietary scoring / impact-estimation
math, (b) the structured strategic-ideation screens, and (c) commercial plumbing
(billing, self-serve signup).** Nothing in the core loop is missing, but a few
*signature algorithmic claims* are implemented differently than the documents
describe.

---

## What's MET ✅

| Promise (source) | In the MVP |
|---|---|
| Idea meritocracy / score ideas from everyone, not the loudest voice; **anti-HiPPO** (all three) | Anonymous all-hands voting; per-company weights; score = the average |
| Attract / Engage / Expand analytics; 3 objectives → 6 levers; decompose sales | Grow Sales + Attract/Engage/Expand dashboards |
| Performance Story (auto narrative), scorecards, trend graphs, date+comparison selector | Performance Storyboard, scorecards (vs-LY & vs-Budget), period/compare selector |
| "Analytics Centrifuge" mix-impact decomposition (device/channel, product category) | Changeplot / segment decomposition on Engage & Expand |
| Home: actual vs budget vs run-rate vs run-rate+project-impact graph + **beat/miss** table | Value Pipeline revenue chart (Budget/Actual/Forecast/Project Value) + Delta-to-Budget (red parens on a miss) |
| Active/inactive project counts + expected revenue by Objective | Objective tiles (WIP / On Deck counts + potential revenue) |
| Initiatives table (Purpose/Objective/revenue/BU/counts); Gantt of active projects | Projects Summary + WIP Gantt |
| Kanban PPO with statuses; backlog sorted by score | Kanban (intake → score → exec approval → on deck → WIP) |
| GA4 via BigQuery + minimal config (monthly budgets + cart path) | GA4 Standard + Premium/BigQuery, event mapping, monthly budgets |
| Roles/permissions; per-role "what's in it for me" | Multi-role model (Exec/BUL/BU User/Analyst/Developer), enforced |

---

## Gaps 🚩

### Material (touch a signature claim)

1. **Scoring / impact-estimation algorithm differs from the documents.**
   The Charter & Business Plan describe scoring driven by **Revenue Impact ($),
   Direct Expense, Ramp Time, Level of Effort, Capability to Complete**, plus an
   **auto-derived "Kiboko estimated impact"** (the "Kiboko Effect": size × speed
   × certainty of impact, factoring viability / product lifecycle / distance to
   goals). The Business Plan states these "proprietary algorithms … are complete
   and tested."
   The MVP scores via a **6-criteria weighted vote** and an **analyst manually
   types the revenue** — there is **no auto-estimate of impact from a lever +
   target**.
   → **Decision needed:** is the voting model the intended evolution, or must the
   auto-impact-estimation math ship? *This is the single biggest conceptual gap.*
   See `docs/impact_estimation_spec.md` for a concrete algorithm.

2. **Strategic ideation layer (the IDEATE step) is thin.**
   The Charter's *Create Initiative / Recommend Project* screens (Purpose →
   Objective auto-derive; **Lever, Target From→To→By, Ramp Time, Intent,
   Justification**; **auto-generated Strategy/Tactic summaries**) aren't in the
   MVP. Today: Objectives + Projects + "add from Insights," but not the
   structured lever-target ideation with generated narratives.

3. **"Compounding gains — projects that benefit each other."**
   A headline differentiator on the site and Charter. The MVP has **action-level
   dependencies within a project** (new) but **no project-to-project synergy /
   compounding** identification.

4. **Billing / Payment / self-serve signup.**
   Placeholder only (Stripe not integrated) → cannot onboard or charge the public.

### Minor / polish

5. **Blocker auto-escalation with opportunity-cost context** — MVP has a Blocked
   lane + comments, but no *automatic* escalation surfacing the opportunity cost.
6. **Inbox / alerts** (pending action items) screen — not present.
7. **Microsoft sign-in** — Charter says Google *or* Microsoft; only Google wired.
8. **Cadence details** — Charter wants **WTD** scorecards and a **13-week** Gantt;
   the MVP uses **MTD/QTD/YTD** windows.
9. Small screen items: user "initials color"; FAQ (Help exists instead).

### Infra / pre-launch (tracked separately)

- MySQL migration; encrypt stored secrets (service-account JSON, refresh tokens,
  SendGrid key) before production; rotate the committed SECRET_KEY; OAuth consent
  verification. (See `docs/pre_launch_checklist.md`.)

---

## Recommended sequence before public / self-serve launch

1. **Resolve the scoring/impact-estimation question** — align the math to the
   promise (implement the Kiboko estimated impact) or consciously re-position the
   voting model. (Spec provided.)
2. **Billing + signup** (Stripe, trial gate).
3. **Ideation depth** (lever/target Recommend-Project flow + auto-narratives) and
   the **project-synergy / compounding** claim.
4. Minor items (blocker escalation, inbox, Microsoft SSO) as fast-follows.

---

# Re-assessment — 2026-09-17

Same three promise sources. Updated to reflect what has shipped since 2026-09-16
(the impact estimator, plausibility accountability, evidence-backed targets,
blended scoring, DailyActual data tier) and the **scaled-down Insights**.

## Updated verdict

The v1 report called the **auto impact-estimation math** the "single biggest
conceptual gap." **That gap is now closed.** The Kiboko Effect estimator is built
end-to-end and wired into scoring, so the MVP now delivers its *signature
algorithmic claim*, not just the experiential loop. Remaining gaps are narrower:
**project-to-project compounding, commercial plumbing (billing/signup), the
post-launch Realized-Performance accountability loop, and auto-generated strategy
narratives.** Insights is intentionally a **rules-based Wins/Losses recommender**,
not AI ideation.

## Newly MET since v1 ✅

| Promise (source) | Now in the MVP |
|---|---|
| **Auto-derived "Kiboko estimated impact"** — size × speed × certainty × effort (was **Gap 1**, "must-ship") | Add Project **Impact Estimator**: pick the **lever**, **Target From → To**, sales baseline (auto from GA4/BigQuery/actuals or manual), **ramp time**, **direct expense**; a developer sets **effort (t-shirt XXS–XXL)** + **Capability to Complete**. Produces **Gross / Realized-this-year / Expected (risk-adjusted) / Net** and a 0–10 algorithmic priority relative to the backlog. |
| **Score = the estimate, not a typed number** | Final score = **average of the anonymous vote (5 BVM criteria) and the algorithmic 0–10**, shown as **one number** so a HiPPO can't argue the vote up to rescue a vanity project. Revenue is **auto-estimated**, not analyst-typed (the Analyst stage was removed). |
| **Plausibility / accountability gauge** (the Figma heat gradient — hold over-estimators accountable) | Live **plausibility gauge**: the target is scored against the lever's own weekly history (from the **current level**, in units of weekly volatility); an over-aggressive target **auto-discounts** the algorithmic score. Greys out until enough history exists. |
| **Justification / intent for a target** | **Evidence-backed target**: anchor plausibility to an evidenced prior level (e.g. restoring a rate lost to a regression) with a required, **audited** note shown to voters — so a genuine recovery isn't unfairly discounted. |
| **Lever/Target ideation fields** (Charter *Recommend Project*) — partial of **Gap 2** | Intake now captures **Lever, Target From→To, Ramp, baseline, go-live**, with the **lever scoped to the objective's AEE element** (AEE › Objective › Project enforced). |
| GA4 via BigQuery **and** a graceful demo path | Data tiers now resolve **BigQuery (Premium) → GA4 (Standard) → DailyActual (seeded/uploaded) → dummy**, so a no-GA4 account shows **real seasonal performance** (retail-calendar actuals: Labor Day / Black Friday spikes) on the dashboards + estimator instead of generic sample data. |

## Insights — scaled down (accurate current scope)

Insights is a **"Wins & Losses" bridge**: metrics that moved ≥ 10% vs the
comparison period, each with **admin-curated recommendations** (`MetricRecommendation`,
~4 per metric × direction, editable in admin — *not* generated). **"Add project"**
seeds an intake **draft** (name + objective from the metric; user story / DoD left
blank; go-live defaults to quarter-end) that lands in **Incomplete Entries** until
the estimator is completed. It is a curated analytics→prioritization handoff, **not**
the auto-generating strategic-ideation engine the Charter's ideation screens imply.

## Remaining gaps 🚩

### Material
1. **Project-to-project compounding / synergy** — still open. Action-level
   dependencies exist within a project, but the headline "projects that benefit
   each other" claim has no cross-project synergy detection. *(Unchanged from v1.)*
2. **Realized Performance loop (post-launch accountability)** — the estimator's
   back half. Prototyped (LMDI decomposition: did the lever actually move, and was
   it this project?) but **not yet on the completed-project detail view**. Without
   it, over-estimation is checked *before* launch (plausibility) but not *after*.
3. **Billing / self-serve signup** — still a placeholder; no Stripe / trial gate.
   *(Unchanged from v1.)*
4. **Auto-generated Strategy/Tactic narratives** — the Charter's generated
   summaries aren't produced; the user writes the user story / DoD (guided by
   format hints). Insights recommendations are curated, not generated.

### Minor / polish (unchanged from v1)
Blocker auto-escalation with opportunity cost · inbox/alerts screen · Microsoft
SSO · WTD scorecards + 13-week Gantt (MVP uses MTD/QTD/YTD) · user initials color.

### Infra / pre-launch (tracked in `pre_launch_checklist.md`)
MySQL migration · encrypt stored secrets (service-account JSON, refresh tokens,
SendGrid key) · rotate committed SECRET_KEY · OAuth consent verification. On
PythonAnywhere, live GA4/BigQuery need paid outbound; the DailyActual tier covers
demos without it.

## Recommended sequence (updated)

1. **Realized Performance tab** on completed projects — closes the accountability
   loop the estimator opened (highest-leverage next build).
2. **Billing + self-serve signup** (Stripe, trial gate) — the gate to public launch.
3. **Project synergy / compounding** — the last unbuilt signature differentiator.
4. Fast-follows: blocker escalation, inbox, Microsoft SSO, WTD/13-week cadence;
   then the pre-launch infra hardening.
