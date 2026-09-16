# Impact Estimation — standalone prototype

A minimal, **standalone** prototype of Kiboko's impact-estimation engine, for two
purposes:

1. **Backtest the model** against real history — does "improve a lever x% → sales
   x%" hold, and which levers actually drove past sales changes?
2. **Feel the UX** of proposing a project by lever + target and seeing the
   estimated impact + priority score update live.

It has **zero coupling to the Django app** (own deps, own runner). The math lives
in `engine.py` as pure functions so, once validated here, it ports straight into
`project/services/impact.py`. Design basis: `docs/impact_estimation_spec.md`.

## Run

```bash
cd prototypes/impact_estimation
python3 -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt
streamlit run app.py
```

Opens in the browser with **sample history** by default. Two tabs:

- **Estimator (UX)** — pick a lever, a target %, launch/ramp, capability, effort;
  see gross vs. realized-this-year vs. expected vs. net, a 0–10 priority score,
  and the cumulative-impact curve. Drop capability or lengthen the ramp: the $
  value holds but the score falls (the "Kiboko Effect").
  - **Plausibility (accountability):** the target is scored against the lever's
    own last-12-months distribution — a **blue→red heat gauge** + a histogram
    with current/target markers, a z-score, and "reached N of 52 weeks." A wild
    claim (e.g. a target only hit once, 3σ out) lights up red, nudging the user
    to back down — or to knowingly own a bold call. Optionally **risk-adjusts**
    the expected impact by a plausibility factor `P` (so over-estimators can't
    quietly inflate numbers; they either temper the target or go on record).
- **Backtest** — LMDI decomposition splits an actual sales change (recent N days
  vs. the prior N) into **exact per-lever dollar drivers** (contributions sum to
  the change). Plus an "estimator vs. actual" confounding check for any lever,
  and a **trend chart** of that lever's 7-day-rolling level over time with the
  actual (recent) window vs. its historical average highlighted.
- **Realized Performance** — the post-mortem for a *completed* project (in Kiboko
  this lives on the completed-project detail view). Measures the window from
  **launch → ramp + a steady-state period (≥7 days)** and answers two questions:
  **"did performance improve or decline?"** (sales change vs baseline) and
  **"was this project meaningful in the change?"** (the targeted lever's LMDI
  share of the change + estimate-vs-actual). Toggle the baseline between **this
  year period-over-period** (pre-launch) and **year-over-year**; the historical-
  vs-actual chart marks launch/ramp-end and shades the measured window. Shows the
  reconstructed residual (~$0) so you can trust the attribution.

## Data

Sample data is generated with two **injected interventions** (a +15% cart-creation
project and a +8% avg-unit-price project) so the backtest has real signal to
recover. To backtest **your** data, upload a CSV with daily rows:

```
date,users,sessions,add_to_carts,transactions,items,revenue
2025-01-01,3012,4270,431,151,309,13820.55
...
```

Where the six levers derive as:

| Lever | = |
|---|---|
| Visitors | users |
| Visits per Visitor | sessions / users |
| Cart Creation Rate | add_to_carts / sessions |
| Cart Completion Rate | transactions / add_to_carts |
| Units per Order | items / transactions |
| Avg Unit Price | revenue / items |

(Sales = the product of all six = revenue.)

### Exporting real data from the app

The app already stores these fundamentals per business unit in
`GA4DailyRollup` (and the GA4/BigQuery layer). A small `dumpdata`/management
command can emit the CSV above for a chosen business unit + date range — that's
the intended bridge from prototype backtesting to production.

## Files

- `engine.py` — pure engine: lever derivation, LMDI decomposition (backtest),
  `estimate()` (forward impact + score). Portable into the Django app.
- `data.py` — sample generator, CSV loader, baseline/window helpers.
- `app.py` — Streamlit UI (Estimator + Backtest tabs).

## What this validates before we build it into Kiboko

- Whether the multiplicative model explains real sales moves (residual ≈ $0).
- How much **confounding** there is (do other levers move when one is targeted?),
  which calibrates how much to trust a single-lever estimate.
- The **UX**: is "lever + target → impact + score" intuitive for proposers, and
  do the speed/certainty discounts feel right?
