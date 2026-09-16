"""Data for the impact-estimation prototype.

Real use: a CSV of daily rows with columns
    date, users, sessions, add_to_carts, transactions, items, revenue
(export from the app's GA4DailyRollup / BigQuery). Until then, generate_sample()
produces ~2 years of realistic history with two INJECTED interventions (a lever
step-change with a ramp), so the backtest has real signal to recover.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine import levers_from_metrics, LEVER_KEYS

RAW_COLS = ['users', 'sessions', 'add_to_carts', 'transactions', 'items', 'revenue']


def generate_sample(seed=7, days=730, start=None):
    """Simulate daily lever levels (trend + weekly seasonality + noise + two
    injected interventions), then derive the raw GA4 counts from them so the
    Sales = product-of-levers identity holds exactly."""
    rng = np.random.default_rng(seed)
    start = start or (date.today() - timedelta(days=days))
    idx = [start + timedelta(days=i) for i in range(days)]
    t = np.arange(days)

    def season(amp):  # day-of-week seasonality
        return 1 + amp * np.sin(2 * np.pi * (t % 7) / 7)

    def wk(cv):  # week-level multiplier (creates realistic week-to-week variance)
        return np.repeat(rng.normal(1, cv, days // 7 + 1), 7)[:days]

    # Baseline lever paths (levels): gentle trend + week-level swings + daily noise.
    visitors = 3000 * (1 + 0.00025 * t) * season(0.18) * wk(0.14) * rng.normal(1, 0.04, days)
    vpv = 1.42 * (1 + 0.00005 * t) * wk(0.03) * rng.normal(1, 0.008, days)
    cart_creation = 0.100 * wk(0.07) * rng.normal(1, 0.02, days)
    cart_completion = 0.350 * wk(0.06) * rng.normal(1, 0.02, days)
    units_per_order = 2.05 * wk(0.04) * rng.normal(1, 0.015, days)
    avg_unit_price = 44.0 * (1 + 0.0001 * t) * wk(0.05) * rng.normal(1, 0.01, days)

    # --- Injected interventions (what a real "project" would look like) ---
    def ramp_step(series, start_day, pct, ramp):
        for i in range(days):
            k = i - start_day
            if k >= 0:
                series[i] *= 1 + pct * min(1.0, k / ramp)
        return series

    # Project A: +15% cart_creation, launched ~day 470, 30-day ramp.
    cart_creation = ramp_step(cart_creation, 470, 0.15, 30)
    # Project B: +8% avg_unit_price, launched ~day 560, 20-day ramp.
    avg_unit_price = ramp_step(avg_unit_price, 560, 0.08, 20)

    # Derive raw counts from the levers (identity holds exactly).
    users = visitors
    sessions = users * vpv
    add_to_carts = sessions * cart_creation
    transactions = add_to_carts * cart_completion
    items = transactions * units_per_order
    revenue = items * avg_unit_price

    return pd.DataFrame({
        'date': idx, 'users': users, 'sessions': sessions,
        'add_to_carts': add_to_carts, 'transactions': transactions,
        'items': items, 'revenue': revenue,
    })


def load_csv(path):
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    for c in RAW_COLS:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df.sort_values('date').reset_index(drop=True)


def window_metrics(df, start, end):
    """Sum raw counts over [start, end] -> a metrics dict for the engine."""
    m = df[(df['date'] >= start) & (df['date'] <= end)]
    return {c: float(m[c].sum()) for c in RAW_COLS}


def _levels_per_day(m, days):
    """Lever levels on a per-DAY basis so flow metrics (visitors, sales) are
    comparable across windows of different length. Ratio levers are unchanged."""
    md = {k: (v / max(1, days)) for k, v in m.items()}
    return levers_from_metrics(md)


def weekly_lever_levels(df, lever, weeks=52, ref=None):
    """The lever's per-day level in each of the trailing `weeks` 7-day buckets
    (for the plausibility distribution). Chronological order."""
    ref = ref or df['date'].max()
    out = []
    for w in range(weeks):
        end = ref - timedelta(days=7 * w)
        start = end - timedelta(days=6)
        m = window_metrics(df, start, end)
        if m['sessions'] > 0:
            out.append(_levels_per_day(m, 7)[lever])
    return list(reversed(out))


def rolling_lever_series(df, lever, window=7, days=182, ref=None):
    """Per-day lever level using a trailing `window`-day rolling aggregate, for
    the last `days` days ending at `ref`. Returns DataFrame(date, level)."""
    ref = ref or df['date'].max()
    start = ref - timedelta(days=days - 1)
    rows = []
    d = start
    while d <= ref:
        m = window_metrics(df, d - timedelta(days=window - 1), d)
        if m['sessions'] > 0:
            rows.append((d, _levels_per_day(m, window)[lever]))
        d += timedelta(days=1)
    return pd.DataFrame(rows, columns=['date', 'level'])


def baselines(df, window_days=90, ref=None):
    """Current per-day lever levels + annualized sales run-rate S0, from the
    trailing `window_days` ending at `ref` (default: last date in the data)."""
    ref = ref or df['date'].max()
    start = ref - timedelta(days=window_days - 1)
    m = window_metrics(df, start, ref)
    lv = _levels_per_day(m, window_days)
    s0_annual = lv['sales'] * 365.0            # per-day sales x 365
    return {'levels': {k: lv[k] for k in LEVER_KEYS}, 's0_annual': s0_annual,
            'window': (start, ref), 'raw': m}
