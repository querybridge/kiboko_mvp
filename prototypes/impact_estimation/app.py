"""Impact-estimation prototype (Streamlit).

Two goals:
  * Estimator tab  -- feel the UX of proposing a project by lever + target.
  * Backtest tab   -- validate the model against real history (LMDI decomposition
                      of actual sales changes into per-lever dollar drivers).

Run:  cd prototypes/impact_estimation && streamlit run app.py
Data: sample by default; upload a CSV (date + 6 GA4 metrics) for a real backtest.
"""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import data as D
import engine as E

st.set_page_config(page_title='Kiboko Impact Estimation', layout='wide')
st.title('Kiboko — Impact Estimation Prototype')

# --------------------------------------------------------------------------
# Data + shared config (sidebar)
# --------------------------------------------------------------------------
st.sidebar.header('Data')
src = st.sidebar.radio('Source', ['Sample history', 'Upload CSV'])
if src == 'Upload CSV':
    up = st.sidebar.file_uploader('CSV: date,users,sessions,add_to_carts,transactions,items,revenue', type='csv')
    df = D.load_csv(up) if up else D.generate_sample()
    if not up:
        st.sidebar.info('No file yet — showing sample history.')
else:
    df = D.generate_sample()

st.sidebar.caption(f'{len(df)} days: {df["date"].min()} → {df["date"].max()}')
st.sidebar.header('Assumptions')
window_days = st.sidebar.slider('Baseline window (days)', 30, 365, 90, 15)
margin = st.sidebar.slider('Contribution margin (direct-expense revenue factor)', 0.05, 0.9, 0.35, 0.05)

base = D.baselines(df, window_days)
st.sidebar.metric('Baseline annual sales (S0)', f'${base["s0_annual"]:,.0f}')

est_tab, back_tab = st.tabs(['🎯 Estimator (UX)', '🔬 Backtest'])

# ==========================================================================
# ESTIMATOR
# ==========================================================================
with est_tab:
    st.subheader('Propose a project by the lever it moves')
    c1, c2, c3 = st.columns([1.3, 1, 1])

    with c1:
        lever = st.selectbox('Lever', E.LEVER_KEYS,
                             format_func=lambda k: f'{E.LEVERS[k][0]}  ·  {E.LEVERS[k][1]}')
        frm = base['levels'][lever]
        st.caption(f'Current level (auto from GA4): **{frm:,.4g}**')
        pct = st.slider('Target improvement', -20, 50, 10, 1, format='%d%%') / 100.0
        to = frm * (1 + pct)
        st.caption(f'Target: **{to:,.4g}**  ({pct:+.0%})')

    with c2:
        launch = st.date_input('Launch (go-live)', date.today() + timedelta(days=14))
        ramp = st.number_input('Ramp to full effect (days)', 1, 365, 30)
        direct_expense = st.number_input('Direct expense ($)', 0, 5_000_000, 40_000, 5_000)

    with c3:
        capability = st.selectbox('Capability to complete', list(E.CAPABILITY),
                                  index=1, format_func=lambda k: E.CAPABILITY[k][0])
        effort = st.selectbox('Level of effort', list(E.LOE_COST), index=2)

    # --- Plausibility: how does the target level compare to the last 12 months? ---
    levels = D.weekly_lever_levels(df, lever, weeks=52)
    pl = E.plausibility(to, levels)
    st.markdown('---')
    st.markdown('**Plausibility of the target** — accountability check vs. recent history')
    P = 1.0
    if pl.get('ok'):
        pc1, pc2 = st.columns([1, 1])
        with pc1:
            pos = pl['position'] * 100
            st.markdown(f'''
              <div style="margin:2px 0 3px;font-weight:700;color:{pl['color']};">{pl['band']} · {pl['z']:+.1f}σ</div>
              <div style="position:relative;height:20px;border-radius:10px;
                   background:linear-gradient(90deg,#2b83ba 0%, #7fbf7b 28%, #fdae61 62%, #d7191c 100%);">
                <div style="position:absolute;left:{pos:.1f}%;top:-5px;width:0;height:0;
                     border-left:6px solid transparent;border-right:6px solid transparent;
                     border-top:9px solid #111;transform:translateX(-6px);"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:11px;color:#888;margin-top:3px;">
                <span>Plausible</span><span>Implausible</span></div>
            ''', unsafe_allow_html=True)
            st.caption(f"Target **{to:,.4g}** was reached **{pl['reached']} of the last {pl['n']} weeks** "
                       f"({pl['z']:+.1f}σ vs. a {pl['mean']:,.4g} mean). "
                       f"12-mo range {pl['hist_min']:,.4g}–{pl['hist_max']:,.4g}.")
            if pl['z'] > 3:
                st.warning("Beyond nearly all recent experience — back it down, or own the bold call.")
            elif pl['z'] > 2:
                st.info("Aggressive — rarely achieved. Make sure the project justifies it.")
        with pc2:
            dfl = pd.DataFrame({'level': levels})
            hist = alt.Chart(dfl).mark_bar(opacity=0.55, color='#8899aa').encode(
                alt.X('level:Q', bin=alt.Bin(maxbins=28), title=f'{E.LEVERS[lever][0]} — weekly, 12 mo'),
                alt.Y('count()', title='weeks'))
            r_from = alt.Chart(pd.DataFrame({'x': [frm]})).mark_rule(color='#2b83ba', size=2).encode(x='x')
            r_to = alt.Chart(pd.DataFrame({'x': [to]})).mark_rule(color=pl['color'], size=3).encode(x='x')
            st.altair_chart(hist + r_from + r_to, use_container_width=True)
            st.caption('Blue rule = current level · colored rule = target')
        risk_adj = st.checkbox('Risk-adjust impact by plausibility (×P)', value=(pl['z'] > 2),
                               help=f'Multiply expected impact by P={pl["factor"]:.2f}. Uncheck to own the full claim.')
        P = pl['factor'] if risk_adj else 1.0
    else:
        st.caption('Not enough history to assess plausibility.')

    e = E.estimate(lever, frm, to, base['s0_annual'], launch=launch, ramp_days=ramp,
                   capability=capability, effort=effort, direct_expense=direct_expense,
                   margin_factor=margin, plausibility=P)

    # 0-10 score relative to an illustrative backlog (each lever, +10%, same terms).
    backlog = [E.estimate(k, base['levels'][k], base['levels'][k] * 1.10, base['s0_annual'],
                          launch=launch, ramp_days=ramp, capability=capability,
                          effort=effort, direct_expense=direct_expense,
                          margin_factor=margin).kiboko_raw for k in E.LEVER_KEYS]
    score10 = E.display_score(e.kiboko_raw, backlog + [e.kiboko_raw])

    st.markdown('---')
    m = st.columns(5)
    m[0].metric('Gross impact / yr', f'${e.gross_annual:,.0f}', help='S0 × %Δ lever, full run-rate')
    m[1].metric('Realized this year', f'${e.realized_annual:,.0f}', help=f'× {e.realized_fraction:.0%} after ramp + timing')
    m[2].metric('Expected (risk-adj.)' if P < 1 else 'Expected (× capability)',
                f'${e.expected_realized:,.0f}',
                help=f'realized × capability × plausibility (P={P:.2f})')
    m[3].metric('Net contribution / yr', f'${e.net_annual:,.0f}', help='gross × margin − direct expense')
    m[4].metric('Priority score (0–10)', f'{score10}', help=f'Kiboko raw: {e.kiboko_raw:,.0f}')

    # Cumulative realized impact through year-end.
    ye = date(launch.year, 12, 31)
    days = [launch + timedelta(days=i) for i in range((ye - launch).days + 1)]
    daily = e.gross_annual / E.DAYS_IN_YEAR
    cum, running = [], 0.0
    for d in days:
        eff = min(1.0, max(0, (d - launch).days) / max(1, ramp))
        running += daily * eff
        cum.append(running)
    st.markdown('**Cumulative realized impact through year-end**')
    st.line_chart(pd.DataFrame({'cumulative $': cum}, index=pd.to_datetime(days)))

    st.caption('The score rewards the "Kiboko Effect": heaviest impact, fastest '
               '(shorter ramp / earlier launch), most certain (capability), least '
               'effort. Try dropping capability or lengthening the ramp — the $ '
               'value holds but the score falls.')

# ==========================================================================
# BACKTEST
# ==========================================================================
with back_tab:
    st.subheader('Validate the model on history (LMDI decomposition)')
    st.caption('Because Sales = the product of the six levers, any actual sales '
               'change splits EXACTLY into per-lever dollar drivers. This is the '
               'backtest: does the data behave the way the estimator assumes?')

    lo, hi = df['date'].min(), df['date'].max()
    n = st.slider('Compare last N days vs the prior N days', 14, 180, 90, 7)
    ref = st.date_input('Recent period ends', hi, min_value=lo, max_value=hi)
    rec = (ref - timedelta(days=n - 1), ref)
    pri = (rec[0] - timedelta(days=n), rec[0] - timedelta(days=1))

    before = D.window_metrics(df, *pri)
    after = D.window_metrics(df, *rec)
    dec = E.lmdi_decompose(before, after)

    a, b = st.columns([1, 1])
    with a:
        st.metric('Actual sales change', f'${dec["delta"]:,.0f}',
                  help=f'Recent {rec[0]}–{rec[1]} vs prior {pri[0]}–{pri[1]}')
        st.caption(f'Reconstruction residual (should be ~$0): ${dec["residual"]:,.2f}')
        contrib = pd.Series({E.LEVERS[k][0]: v for k, v in dec['contrib'].items()})
        st.bar_chart(contrib.sort_values())
    with b:
        tbl = pd.DataFrame({
            'Lever': [E.LEVERS[k][0] for k in E.LEVER_KEYS],
            'Objective': [E.LEVERS[k][1] for k in E.LEVER_KEYS],
            '$ contribution': [dec['contrib'][k] for k in E.LEVER_KEYS],
            '% of change': [(dec['contrib'][k] / dec['delta'] * 100) if dec['delta'] else 0
                            for k in E.LEVER_KEYS],
        }).sort_values('$ contribution', key=abs, ascending=False)
        st.dataframe(tbl.style.format({'$ contribution': '${:,.0f}', '% of change': '{:.1f}%'}),
                     use_container_width=True, hide_index=True)

    st.markdown('---')
    st.markdown('**Estimator vs. actual — confounding check**')
    st.caption('For a chosen lever, the estimator predicts "improve it x% → sales '
               'x%, holding others constant." Compare that to what the lever '
               'actually contributed (LMDI). A gap = other levers moved too.')
    lk = st.selectbox('Lever to check', E.LEVER_KEYS,
                      format_func=lambda k: E.LEVERS[k][0], key='bt_lever')
    lb = E.levers_from_metrics(before)
    lt = E.levers_from_metrics(after)
    pred = lb['sales'] * (lt[lk] / lb[lk] - 1)   # estimator: holding others constant
    actual = dec['contrib'][lk]                  # LMDI-attributed actual
    cc = st.columns(3)
    cc[0].metric('Estimator predicts', f'${pred:,.0f}')
    cc[1].metric('Actual (LMDI)', f'${actual:,.0f}')
    err = (pred - actual)
    cc[2].metric('Difference', f'${err:,.0f}',
                 help='Driven by concurrent movement in other levers + nonlinearity.')
