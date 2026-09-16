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
