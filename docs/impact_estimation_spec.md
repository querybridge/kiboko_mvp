# Spec — "Kiboko Estimated Impact" & Project Score

Status: **proposed** (design). Implements the Charter/Business-Plan promise of an
**auto-derived revenue impact** and an objective **priority score** (the "Kiboko
Effect": *heaviest, fastest, most-certain, best-fit* project rises to the top).
Replaces (or augments — see §9) the current manual "analyst types the revenue"
step and the anonymous 6-criteria vote.

The point: a proposer picks **which lever** a project moves and **how far**
(From → To); Kiboko derives the **$ impact** from GA4 baselines, discounts it for
**speed** (ramp + timing), **certainty** (capability), and **strategic fit**
(distance to goal), and rolls it into a single rank-able **Score**.

---

## 1. Sales decomposition (the identity everything hangs on)

```
Sales = Visits × Close Rate × Average Order Value
```

Decomposed into the six levers (two per objective):

| Objective (AEE) | Lever key | Lever = | GA4 baseline |
|---|---|---|---|
| Attract (Visits) | `visitors` | Visitors (users) | `totalUsers` |
| Attract (Visits) | `visits_per_visitor` | Visits ÷ Visitors | `sessions / totalUsers` |
| Engage (Close Rate) | `cart_creation` | Carts ÷ Visits | `addToCarts / sessions` |
| Engage (Close Rate) | `cart_completion` | Orders ÷ Carts | `transactions / addToCarts` |
| Expand (AOV) | `units_per_order` | Units ÷ Orders | `itemsPurchased / transactions` |
| Expand (AOV) | `avg_unit_price` | Revenue ÷ Units | `purchaseRevenue / itemsPurchased` |

Because Sales is the **product** of these six factors, improving **one** lever by
`x%` (holding others constant) raises Sales by `x%`. That is the whole basis of
the estimate.

`S0` = **baseline annual sales run-rate** for the scope (business unit), from GA4
(trailing-12-month or annualized trailing-90-day; configurable).

---

## 2. Inputs (captured at ideation / intake)

Per project:

- `lever` — one of the six above (drives the objective/AEE automatically).
- `target_from` — **auto-populated** current lever level from GA4 (read-only).
- `target_to` — proposer's target level (numeric).
- `ramp_days` — days from launch to full effect.
- `launch` / `target_completion` — expected go-live date.
- `capability` — Current Capability to Complete (5-point; §5).
- `level_of_effort` — 6-point effort (developer; already in the MVP).
- `direct_expense` — one-time/period cost to run the project ($).

Company config (Setup Data):

- `margin_factor` — "direct expense revenue factor" (contribution margin, e.g.
  `0.35`), to convert revenue → contribution.
- `baseline_window` — how S0 and lever baselines are computed.

---

## 3. Gross annualized revenue impact

```
pct_delta      = (target_to - target_from) / target_from           # signed
gross_annual   = S0 × pct_delta                                    # $/yr, full-run-rate
```

Notes:
- Exact for a single multiplicative lever; first-order for combined levers (one
  lever per project keeps it exact).
- A lever that *reduces* a bad thing (e.g. bounce) is modeled as its positive
  complement (e.g. cart-creation rate) so `pct_delta` stays interpretable.

This `gross_annual` is the headline **$ Value** shown on the card (what the
project is "worth" at full run-rate) — no longer hand-typed.

---

## 4. Speed: ramp + in-year timing (the "fastest" in Kiboko Effect)

The impact isn't instant and only the part of the fiscal year after go-live
counts this year. Effectiveness on day `t` after launch (linear ramp):

```
e(t) = 0                      for t < 0            (before launch)
e(t) = min(1, t / ramp_days)  for t >= 0
```

In-year **realized fraction** = average effectiveness over the fiscal year:

```
realized_fraction = (1/DAYS_IN_YEAR) × Σ_{d = launch..Dec31} e(days_since_launch)
realized_annual   = gross_annual × realized_fraction               # $ this fiscal year
```

Two projects with identical `gross_annual` but a shorter ramp / earlier launch
yield a larger `realized_annual` — speed is rewarded automatically. (For the
forecast/value-pipeline uplift, use `realized_annual` prorated by month.)

---

## 5. Certainty: Capability to Complete (the "most-certain")

5-point scale → confidence multiplier `C`:

| Capability | `C` |
|---|---|
| Fully capable in-house | 1.00 |
| Mostly capable | 0.85 |
| Partially / stretch | 0.65 |
| Needs new capability | 0.40 |
| Not currently capable | 0.20 |

```
expected_realized = realized_annual × C
```

(This is the quantitative home for the "LLM with no LLM experts = high risk"
example — low capability discounts the expected value.)

---

## 6. Strategic fit: distance to goal (the "best-fit")

Projects that address the **objective furthest behind budget** should rise. The
analytics already compute each objective's actual-vs-goal gap. Define, for the
project's objective `O`:

```
gap_O   = max(0, (goal_pace_O - actual_pace_O) / goal_pace_O)      # 0..1, how far behind
fit     = 1 + FIT_WEIGHT × (gap_O − avg_gap_all_objectives)        # clamp to [0.5, 1.5]
```

`FIT_WEIGHT` (e.g. `1.0`) tunes how strongly strategic fit sways the ranking. An
objective that's on/ahead of pace yields `fit < 1`; the most-behind objective
gets `fit > 1`.

---

## 7. Net contribution + the Score

```
contribution_annual = gross_annual × margin_factor
net_annual          = contribution_annual − direct_expense          # $ net/yr

# Priority (the Kiboko Effect): value × speed × certainty × fit, per unit effort.
effort_factor       = LOE_COST[level_of_effort]                     # 1.0 (XS) .. ~3.0 (XL)
kiboko_raw          = (expected_realized × margin_factor − direct_expense)
                      × fit / effort_factor                          # $-denominated rank key
```

- **Backlog ranking** uses `kiboko_raw` directly (Charter: "backlog sorted by
  Score"). It is a speed-, certainty-, fit-, and effort-adjusted expected
  contribution — the literal "Kiboko Effect."
- **Display Score (0–10)** for cards/tables = min–max normalize `kiboko_raw`
  across the company's currently-scorable backlog (or a company-calibrated log
  scale so a single big project doesn't crush the rest). Ranking is invariant to
  the display transform.

`LOE_COST` (developer-set effort → cost proxy):

| Effort (t-shirt) | `LOE_COST` |
|---|---|
| XXS | 0.5 |
| XS | 0.7 |
| S | 1.0 |
| M | 1.4 |
| L | 2.0 |
| XL | 2.8 |
| XXL | 3.6 |

---

## 8. Data-model changes (project.Action → strategy.Project)

Add to `strategy.Project`:

- `lever` (CharField choices = the six keys)
- `target_from` (Decimal, cached from GA4 at ideation)
- `target_to` (Decimal)
- `ramp_days` (PositiveInteger)
- `capability` (CharField choices, 5)
- `direct_expense` (Integer $)
- computed (not stored, or cached): `gross_annual`, `realized_annual`,
  `expected_realized`, `net_annual`, `kiboko_raw`

`value` becomes the **computed** `gross_annual` (stop hand-typing it).
`normalized_score` becomes the **display Score** from `kiboko_raw`.

New service module `project/services/impact.py`:

```
baselines(business_unit, window)           -> {lever: level, "S0": annual_sales}
estimate(project, baselines, gaps, config) -> dict(gross_annual, realized_annual,
                                                    expected_realized, net_annual,
                                                    kiboko_raw)
score(kiboko_raw, backlog_raws)            -> 0..10
```

Baselines read the existing GA4 layer (`app.integrations.ga4_dashboard` /
`business_unit.rollup`); no new data source.

---

## 9. Relationship to the current 6-criteria vote (decision)

Three coherent options — pick one:

- **A. Replace.** Impact-estimation becomes *the* score (matches the Business
  Plan's "objective, scientific" claim). The vote is retired.
- **B. Overlay.** Impact-estimation produces the objective baseline score; the
  anonymous vote applies a **qualitative multiplier** (e.g. ±20%) for factors the
  math can't see (brand, strategic optionality). Keeps the HiPPO-proofing *and*
  the science.
- **C. Two lenses.** Show both an "Impact Score" (auto) and a "Team Score" (vote)
  side by side; sort by either. Most transparent, most UI.

**Recommendation: B** — it honors both signature promises (data-driven default +
idea meritocracy) and is the smallest change to the current intake flow (the
Analyst's "set revenue" step becomes "set the lever & target," the vote stays).

---

## 10. Worked example

Scope run-rate `S0 = $9,000,000/yr`. Project: improve **cart_completion** (Engage)
from `0.45 → 0.50` (`pct_delta = +11.1%`), launch Oct 1, `ramp_days = 30`,
capability = Mostly (0.85), effort = M (1.4), `margin_factor = 0.35`,
`direct_expense = $40,000`. Engage is the most-behind objective (`fit = 1.2`).

```
gross_annual      = 9,000,000 × 0.111        = $1,000,000/yr
realized_fraction ≈ (~90 days live, ~ramped) ≈ 0.20
realized_annual   = 1,000,000 × 0.20         = $200,000 (this year)
expected_realized = 200,000 × 0.85           = $170,000
net (annual)      = 1,000,000 × 0.35 − 40,000 = $310,000
kiboko_raw        = (170,000 × 0.35 − 40,000) × 1.2 / 1.4 ≈ $16,970
```

Displayed: **$ Value ≈ $1.0M/yr**, and a Score set by `kiboko_raw`'s rank in the
backlog. A faster-ramping or higher-capability variant scores higher without
touching the $ value — exactly the Kiboko Effect.

---

## 11. Open questions

- S0 window: trailing-12-month vs annualized trailing-90-day (seasonality).
- Ramp curve: linear (above) vs S-curve; make it a config enum.
- Should `fit` also nudge the **$ value**, or only the **Score**? (Spec: Score
  only, so $ stays a clean revenue figure.)
- Multi-lever projects (rare): sum first-order or force one lever per project.
- Where the vote multiplier (option B) is captured in the intake flow.
