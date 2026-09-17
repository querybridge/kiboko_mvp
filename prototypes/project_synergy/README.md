# Project Synergy Prototype

Standalone Streamlit prototype for **project-to-project compounding / synergy**
(phases 1–3 of `docs/project_synergy_spec.md`). No Django — pure math on a sample
Lighting backlog.

## Why
Sales is the **product** of six levers, so a *set* of projects is worth more or
less than the sum of the individual impact estimates:
- different levers → **compounding** (multiplicative bonus),
- same lever → **overlap** (diminishing returns),
- enables/depends → a dependent is **gated** until its enabler ships.

## Run
```bash
cd prototypes/project_synergy
pip install -r requirements.txt
streamlit run app.py
```

## Tabs
1. **Portfolio & Compounding** — committed set (On Deck + WIP) value vs. the naive
   sum, the compounding bonus, per-lever combination, per-project marginal
   contribution (portfolio fit), and the strongest reinforcing / overlapping pairs.
2. **Links & Synergy Map** — dependency gating and a graph of what reinforces what.
3. **Portfolio Optimizer** — best *combination* under an effort budget vs. ranking
   projects individually.

The base project score (vote + standalone estimate) is unchanged — this is a
**portfolio layer** over the committed set, per the scoring discussion.
