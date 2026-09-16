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

est_tab, back_tab, real_tab = st.tabs(
    ['🎯 Estimator (UX)', '🔬 Backtest', '📈 Realized Performance'])

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

    # --- Trend: the lever over time, actual (recent) vs historical ---
    st.markdown(f'**{E.LEVERS[lk][0]} — daily trend (7-day rolling): actual vs. historical**')
    span_days = max(120, 2 * n + 28)
    series = D.rolling_lever_series(df, lk, window=7, days=span_days, ref=rec[1])
    if len(series):
        hist_avg = D._levels_per_day(before, n)[lk]     # prior-window level = "historical"
        act_avg = D._levels_per_day(after, n)[lk]       # recent-window level = "actual"
        line = alt.Chart(series).mark_line(color='#4a1f8a').encode(
            x=alt.X('date:T', title=None),
            y=alt.Y('level:Q', title=E.LEVERS[lk][0], scale=alt.Scale(zero=False)),
            tooltip=['date:T', alt.Tooltip('level:Q', format=',.4g')])
        band_recent = alt.Chart(pd.DataFrame({'start': [rec[0]], 'end': [rec[1]]})).mark_rect(
            color='#26b99a', opacity=0.12).encode(x='start:T', x2='end:T')
        band_prior = alt.Chart(pd.DataFrame({'start': [pri[0]], 'end': [pri[1]]})).mark_rect(
            color='#888', opacity=0.10).encode(x='start:T', x2='end:T')
        rule_hist = alt.Chart(pd.DataFrame({'y': [hist_avg]})).mark_rule(
            color='#888', strokeDash=[5, 4]).encode(y='y')
        rule_act = alt.Chart(pd.DataFrame({'y': [act_avg]})).mark_rule(
            color='#26b99a', size=2).encode(y='y')
        st.altair_chart(band_prior + band_recent + line + rule_hist + rule_act,
                        use_container_width=True)
        st.caption(f'Green band/line = actual (recent {n} days, avg {act_avg:,.4g}) · '
                   f'grey band/dashed = historical (prior {n} days, avg {hist_avg:,.4g}).')
    else:
        st.caption('Not enough data for a trend on this lever.')

# ==========================================================================
# REALIZED PERFORMANCE  (in Kiboko: the completed-project detail view)
# ==========================================================================
with real_tab:
    from datetime import timedelta
    st.subheader('Realized Performance — did the project move the needle, and was it this project?')
    st.caption("In Kiboko this lives on a COMPLETED project's detail. The window "
               "runs from launch through the ramp plus a steady-state measurement "
               "(>= 7 days of post-ramp data), so we only judge once the effect is "
               "fully in and observed.")

    data_min, data_max = df['date'].min(), df['date'].max()
    c = st.columns(4)
    rp_lever = c[0].selectbox('Project lever', E.LEVER_KEYS,
                              index=E.LEVER_KEYS.index(lever),
                              format_func=lambda k: E.LEVERS[k][0], key='rp_lever2')
    default_launch = data_max - timedelta(days=int(ramp) + 45)
    rp_launch = c[1].date_input('Launch date', default_launch,
                                min_value=data_min, max_value=data_max, key='rp_launch2')
    rp_ramp = int(c[2].number_input('Ramp days', 1, 365, int(ramp), key='rp_ramp2'))
    measure_days = int(c[3].slider('Steady-state window (days, ≥7)', 7, 60, 30, key='rp_meas'))

    basis = st.radio('Compare against', ['This year — period-over-period (pre-launch)',
                                         'Year-over-year (same period last year)'], horizontal=True)
    planned_pct = (to / frm - 1) if rp_lever == lever else None

    ramp_end = rp_launch + timedelta(days=rp_ramp)
    post = (ramp_end, ramp_end + timedelta(days=measure_days - 1))
    pop = basis.startswith('This year')
    base = ((rp_launch - timedelta(days=measure_days), rp_launch - timedelta(days=1)) if pop
            else (post[0] - timedelta(days=365), post[1] - timedelta(days=365)))
    base_label = 'pre-launch (this year)' if pop else 'same period last year'

    st.caption(f'Measured window: **{post[0]} → {post[1]}** (post-ramp) vs **{base[0]} → {base[1]}** ({base_label}).')

    if post[1] > data_max:
        st.warning(f'Not enough post-launch data yet — need through {post[1]} (data ends {data_max}). '
                   'In Kiboko this tab unlocks once the window has elapsed.')
    elif base[0] < data_min:
        st.warning(f'Not enough history for the {base_label} baseline (need back to {base[0]}).')
    else:
        before = D.window_metrics(df, *base)
        after = D.window_metrics(df, *post)
        dec = E.lmdi_decompose(before, after)
        base_sales = E.levers_from_metrics(before)['sales']
        perf_pct = dec['delta'] / base_sales if base_sales else 0
        lever_contrib = dec['contrib'][rp_lever]
        share = (lever_contrib / dec['delta']) if abs(dec['delta']) > 1e-9 else 0
        base_lv = D._levels_per_day(before, measure_days)[rp_lever]
        post_lv = D._levels_per_day(after, measure_days)[rp_lever]
        actual_lever_pct = (post_lv / base_lv - 1) if base_lv else 0

        # --- Two headline questions ---
        q1, q2 = st.columns(2)
        with q1:
            st.markdown('**1) Did performance improve or decline?**')
            st.metric('Sales change (post vs baseline)', f'${dec["delta"]:,.0f}',
                      f'{perf_pct:+.1%}')
        with q2:
            st.markdown('**2) Was this project meaningful in the change?**')
            st.metric(f'{E.LEVERS[rp_lever][0]} contribution',
                      f'${lever_contrib:,.0f}', f'{share:+.0%} of the total change')

        # Verdict heuristic.
        moved = (planned_pct is None) or (actual_lever_pct > 0.3 * planned_pct) if planned_pct else actual_lever_pct > 0
        if dec['delta'] > 0 and share > 0.40 and (actual_lever_pct > 0):
            st.success(f'✅ Meaningful — {E.LEVERS[rp_lever][0]} drove {share:.0%} of a '
                       f'{perf_pct:+.1%} sales move, and the lever rose {actual_lever_pct:+.1%}.')
        elif dec['delta'] > 0 and share < 0.15:
            st.warning('⚠️ Performance improved, but NOT mainly from this project — the gain '
                       'came from other levers (see decomposition).')
        elif dec['delta'] <= 0 and actual_lever_pct > 0:
            st.info('↔️ The targeted lever moved, but performance was flat/down — its gain was '
                    'offset by other levers.')
        else:
            st.info('❔ Mixed signal — read the decomposition below.')

        st.caption(f'Reconstructed residual (should be ~$0): ${dec["residual"]:,.2f}  ·  '
                   f'{E.LEVERS[rp_lever][0]} moved {actual_lever_pct:+.1%}'
                   + (f' vs planned {planned_pct:+.1%}.' if planned_pct is not None else '.'))

        left, right = st.columns([1, 1])
        with left:
            # Estimate vs actual for the targeted lever.
            if planned_pct is not None:
                predicted = base_sales * planned_pct
                st.markdown('**Estimate vs. actual** (targeted lever, over the window)')
                ec = st.columns(2)
                ec[0].metric('Estimator predicted', f'${predicted:,.0f}')
                ec[1].metric('Actual (LMDI)', f'${lever_contrib:,.0f}',
                             f'{(lever_contrib - predicted):+,.0f}')
            contrib = pd.Series({E.LEVERS[k][0]: dec['contrib'][k] for k in E.LEVER_KEYS})
            st.bar_chart(contrib.sort_values())
        with right:
            metric_key = st.selectbox('Graph metric', ['sales', rp_lever],
                                      format_func=lambda k: 'Sales' if k == 'sales' else E.LEVERS[k][0],
                                      key='rp_metric')
            mlabel = 'Sales' if metric_key == 'sales' else E.LEVERS[metric_key][0]
            gstart = min(base[0] if pop else rp_launch - timedelta(days=max(14, measure_days)), rp_launch)
            gdays = (post[1] - gstart).days + 1
            ser = D.rolling_lever_series(df, metric_key, window=7, days=gdays, ref=post[1])
            layers = []
            layers.append(alt.Chart(ser).mark_line(color='#4a1f8a').encode(
                x=alt.X('date:T', title=None),
                y=alt.Y('level:Q', title=mlabel, scale=alt.Scale(zero=False)),
                tooltip=['date:T', alt.Tooltip('level:Q', format=',.4g')]))
            # post window shading + launch/ramp markers
            layers.append(alt.Chart(pd.DataFrame({'s': [pd.Timestamp(post[0])], 'e': [pd.Timestamp(post[1])]}))
                          .mark_rect(color='#26b99a', opacity=0.12).encode(x='s:T', x2='e:T'))
            for xd, col in [(rp_launch, '#337ab7'), (ramp_end, '#888')]:
                layers.append(alt.Chart(pd.DataFrame({'x': [pd.Timestamp(xd)]}))
                              .mark_rule(color=col, strokeDash=[4, 3]).encode(x='x:T'))
            if pop:
                base_avg = D._levels_per_day(before, measure_days)[metric_key] if metric_key != 'sales' \
                    else base_sales / measure_days
                layers.append(alt.Chart(pd.DataFrame({'y': [base_avg]}))
                              .mark_rule(color='#888', strokeDash=[5, 4]).encode(y='y'))
            else:
                ly = D.rolling_lever_series(df, metric_key, window=7, days=gdays,
                                            ref=post[1] - timedelta(days=365))
                ly['date'] = pd.to_datetime(ly['date']) + pd.Timedelta(days=365)
                layers.append(alt.Chart(ly).mark_line(color='#c0392b', strokeDash=[4, 3]).encode(
                    x='date:T', y='level:Q'))
            st.altair_chart(alt.layer(*layers), use_container_width=True)
            st.caption('Purple = this year (actual) · shaded = post-ramp window · blue/grey dashes '
                       '= launch/ramp-end · ' + ('grey dash = pre-launch avg.' if pop else 'red dash = last year.'))

