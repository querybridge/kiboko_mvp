# Spec — Project-to-Project Compounding / Synergy

Status: **proposed** (design). Implements the Charter/site headline promise of
**"compounding gains — projects that benefit each other."** Builds directly on the
impact estimator (`docs/impact_estimation_spec.md`): because **Sales is the product
of the six levers**, a *portfolio* of projects is worth more (or less) than the sum
of its parts, and Kiboko can compute that.

The point: today each project is estimated **standalone** (`value = S0 × %Δ` on one
lever) and the pipeline **sums** those values. That is wrong in two directions —
cross-lever projects **compound** (the sum undercounts), and same-lever projects
**overlap** (the sum overcounts). This spec makes the portfolio value honest and
surfaces *which projects reinforce each other* so leaders prioritize combinations,
not just individuals.

---

## 1. Why compounding exists (the identity, again)

```
Sales = Visitors × Visits/Visitor × Cart Creation × Cart Completion × Units/Order × Avg Unit Price
```

Sales is a **product**. Improving lever A by `a%` and lever B by `b%` gives:

```
(1 + a)(1 + b) = 1 + a + b + a·b
                          └── the compounding term
```

- **Different levers → multiplicative compounding.** Two projects on different
  levers deliver `a + b + a·b`. The `a·b` cross-term is the **compounding bonus** the
  naive sum (`a + b`) misses. Example: +8% visitors and +6% cart completion ⇒
  +14.5% sales, not +14%.
- **Same lever → diminishing returns / overlap.** Two projects both raising cart
  completion do **not** stack to `a + b`; they compete for the same headroom. The
  combined lift is closer to `1 − (1−a)(1−b)` on the *gap to a ceiling*, or simply
  discounted (see §3). The naive sum **overcounts**.
- The effect is **per business unit** (per `S0`). Compounding is only real for
  projects sharing the same sales base (same `vertical`).

This is not a heuristic — it falls out of the model the estimator already uses.

---

## 2. Types of synergy

| Kind | Definition | Direction | Detected |
|---|---|---|---|
| **compound** | Different levers, same BU — multiplicative uplift | + (bonus) | Auto |
| **overlap** | Same lever, same BU — diminishing returns / cannibalization | − (haircut) | Auto |
| **enables / depends_on** | Project A must ship for B's estimate to hold (e.g. a data pipeline feeding a recommendation engine) | gating | Manual link (+ auto suggest) |
| **shared_cost** | Two projects share build effort → combined effort < sum | + (cheaper) | Manual link (+ tag) |
| **timing** | Sequence matters (do A before B) | ordering | Derived from enables + go-live |

`compound` and `overlap` are computed from lever + BU automatically. `enables`,
`shared_cost`, and explicit `compound`/`overlap` overrides are **stated by a human**
(auditable, like evidence-backed targets) — the system may *suggest* them.

---

## 3. Combined portfolio value (algorithm)

Scope: the set of **planned** projects for a business unit — statuses
`Scored / Executive Approval / On Deck / WIP` (configurable; excludes intake and
terminal). Each carries a per-lever fractional change `pctᵢ = (target_to − target_from)/target_from`.

```
combined_value(projects, S0):
    by_lever = group projects by lever
    lever_factor = 1.0
    for lever, group in by_lever:
        # within a lever: diminishing returns toward the lever's own headroom.
        # simplest defensible model — multiply the *shortfalls*:
        combined_pct = 1 - Π (1 - pctᵢ)          # sub-additive; ~a+b for small a,b
        # (optional cap at a lever ceiling; optional per-project effectiveness weight)
        lever_factor *= (1 + combined_pct)
    combined_sales = S0 * lever_factor
    return combined_sales - S0                    # $ uplift of the whole portfolio
```

- **Across levers**: multiply `(1 + combined_pct)` — this is where the `a·b`
  compounding bonus appears automatically.
- **Within a lever**: `1 − Π(1 − pctᵢ)` is sub-additive, so two same-lever projects
  can't double-count the headroom.
- **Enablement gating**: a project whose `depends_on` project isn't in the planned
  set (or launches later) contributes at a reduced factor (or 0) until its enabler
  ships — its value is **conditional**.

Reported numbers:

- **Σ standalone** = `Σ project.value` (today's pipeline total).
- **Portfolio value** = `combined_value(...)`.
- **Compounding bonus** = Portfolio − Σ standalone (can be + from cross-lever, − from
  overlap). This is the headline the pipeline should show.

Attribution (so each project keeps a fair share): distribute the portfolio value by
each project's **marginal contribution** (Shapley-style or the simpler "leave-one-out"
delta), so a project's *portfolio-adjusted value* reflects the company it keeps.

---

## 4. Identifying synergy

**Automatic (no input):**
- For every pair of planned projects in the same BU:
  - different lever ⇒ **compound** (strength = `pctᵢ · pctⱼ · S0`, the $ cross-term),
  - same lever ⇒ **overlap** (strength = the headroom they share).
- Rank pairs by strength; surface the top reinforcing / conflicting pairs.

**Suggested (system proposes, human confirms):**
- Shared **team**, **objective**, or a future **component/tag** field ⇒ candidate
  `shared_cost`.
- An `enables` candidate when project A raises a lever that is B's *baseline input*
  (e.g. A raises Visitors, B improves Cart Completion on that traffic) and A's
  go-live precedes B's.

**Explicit (human):** a proposer/BU lead adds a `ProjectLink` with a note.

---

## 5. Data model

```python
class ProjectLink(models.Model):
    KIND = [('compound','Compounds with'), ('overlap','Overlaps with'),
            ('enables','Enables'), ('depends_on','Depends on'), ('shared_cost','Shares build with')]
    from_project = FK(Project, related_name='links_out')
    to_project   = FK(Project, related_name='links_in')
    kind         = CharField(choices=KIND)
    note         = CharField(max_length=300, blank=True)   # auditable justification
    created_by   = FK(User, null=True)
    auto         = BooleanField(default=False)             # system-detected vs human-stated
    class Meta: unique_together = [('from_project','to_project','kind')]
```

- `compound` / `overlap` are largely **computed on the fly** (not stored) but can be
  *overridden* by an explicit link.
- `enables`/`depends_on` are **stored** (they change the estimate) and validated:
  no cycles; a `depends_on` target should precede (go-live) the dependent.
- Extends the existing **within-project Action dependencies** up to the
  **project level** — same mental model, one tier up.

---

## 6. Effect on scoring & the pipeline

- **Portfolio-adjusted value** replaces the naive per-project value in the **Value
  Pipeline** total and the "projected value at stake." Keep the standalone value
  visible; add **Portfolio value** and **Compounding bonus**.
- **Prioritization signal** (not a hard score change first): a project gets a
  **Synergy badge** — "+$X compounding with N projects" or "overlaps with M" — shown
  on Score Projects and the Kanban card, so voters weigh portfolio fit.
- **Later**: fold a portfolio-fit term into the algorithmic score, or run a
  **budget-constrained portfolio optimizer** (§8) that maximizes combined value under
  an effort/$ budget instead of ranking projects independently.

---

## 7. UX / surfaces

1. **Pipeline Value** — a small "Portfolio" card: `Σ standalone → Portfolio value
   (▲ +$bonus compounding)`, with a tooltip explaining cross-lever vs overlap.
2. **Project detail** — a "Synergy" panel: *Compounds with / Overlaps with /
   Enables / Depends on*, each with the $ effect and a note; an "add link" control.
3. **Synergy map** (Project Review or Prioritization) — a matrix / graph of the BU's
   planned projects, green edges = reinforce, amber = overlap, arrows = enablement.
   The quick read: "these three compound; those two are redundant."
4. **Score Projects / Kanban** — the synergy badge per card.

All money in US-finance format; compound green, overlap amber (reuse the AEE/status
palette).

---

## 8. Phasing

- **Phase 1 (MVP).** Auto cross-lever compounding + same-lever overlap on the
  planned set; Portfolio card on the pipeline; per-project Synergy panel (read-only
  auto pairs). Pure math on existing data — no new required input.
- **Phase 2.** `ProjectLink` for explicit `enables`/`depends_on`/`shared_cost`
  (conditional estimates + shared-effort); the synergy map; the per-card badge.
- **Phase 3.** Portfolio optimizer: given the backlog and a budget (effort or $),
  pick the **combination** with the highest combined value (a knapsack/greedy over
  marginal contribution) — Kiboko recommends the best *set*, not just the best items.

---

## 9. Edge cases, risks, open questions

- **Same-lever model choice.** `1 − Π(1 − pct)` is the simplest defensible haircut;
  a lever **ceiling** (you can't exceed a max plausible level) is more accurate but
  needs a per-lever cap. Start simple, revisit with realized data.
- **Cross-BU.** Compounding is per `S0`; projects in different BUs don't compound.
  "All Business Units" scope must combine **per BU** then sum.
- **Double counting vs the plausibility discount.** Combined value uses each
  project's *stated* `pct`; keep the existing per-project plausibility discount so an
  implausible target can't inflate the portfolio.
- **Attribution fairness.** Marginal-contribution attribution can make a project's
  adjusted value depend on what else is planned — surface *why* (which peers) so it
  isn't a black box.
- **Only "planned" projects compound.** Decide whether `Ready to Score` counts
  (probably not until scored) and whether archived/complete projects contribute a
  *realized* compounding view (tie to Realized Performance).
- **Open:** should enablement gating zero out or just discount a dependent's value
  before its enabler ships? Recommend **discount** (partial), configurable per link.
