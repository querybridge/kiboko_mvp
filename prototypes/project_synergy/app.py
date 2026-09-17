"""Project Synergy prototype (Streamlit) — phases 1-3 of docs/project_synergy_spec.md.

  Phase 1 — Portfolio & Compounding: the committed set (On Deck + WIP) is worth
            more/less than the sum of standalone estimates. Show the bonus + pairs.
  Phase 2 — Links & Synergy Map: dependency gating + a graph of what reinforces what.
  Phase 3 — Optimizer: pick the best COMBINATION under a budget, vs ranking items.

Run:  cd prototypes/project_synergy && streamlit run app.py
"""
import pandas as pd
import streamlit as st

import engine as E
from data import PROJECTS, S0_ANNUAL

st.set_page_config(page_title='Kiboko — Project Synergy', layout='wide')
st.title('Kiboko — Project Compounding & Synergy')
st.caption('Sales is the PRODUCT of six levers, so a set of projects is worth more '
           '(cross-lever compounding) or less (same-lever overlap) than the sum of parts.')

AEE_COLOR = {'Attract': '#3FC9E0', 'Engage': '#ECB752', 'Expand': '#55C892'}


def usd(v):
    v = round(v)
    return f'(${abs(v):,})' if v < 0 else f'${v:,}'


# --------------------------------------------------------------------------
# Shared controls: S0 + which projects are in the committed set (On Deck + WIP)
# --------------------------------------------------------------------------
st.sidebar.header('Business unit')
s0 = st.sidebar.number_input('Annual sales baseline (S0)', 1_000_000, 100_000_000, S0_ANNUAL, 500_000)
st.sidebar.caption('Compounding is per business unit — it only applies to projects sharing this S0.')

st.sidebar.header('Committed set (On Deck + WIP)')
st.sidebar.caption('The base project score (vote + standalone estimate) is unchanged. '
                   'Compounding is a PORTFOLIO layer over what you actually commit to.')
names = [p['name'] for p in PROJECTS]
committed = st.sidebar.multiselect('Projects on the board', names, default=names)
# optional live tweak of each lift
with st.sidebar.expander('Tweak lifts (%)'):
    lifts = {}
    for p in PROJECTS:
        lifts[p['name']] = st.slider(p['name'], 0, 30, int(round(p['pct'] * 100)), 1,
                                     key='lift_' + p['name']) / 100.0

projects = [dict(p, pct=lifts[p['name']]) for p in PROJECTS]           # apply tweaks
planned = [p for p in projects if p['name'] in committed]
committed_names = set(committed)

tab1, tab2, tab3 = st.tabs(['① Portfolio & Compounding', '② Links & Synergy Map', '③ Portfolio Optimizer'])

# ==========================================================================
# PHASE 1 — Portfolio value + compounding bonus + per-project marginal fit
# ==========================================================================
with tab1:
    if not planned:
        st.info('Select at least one project in the sidebar.')
    else:
        ss = E.standalone_sum(planned, s0)
        pv = E.combined_uplift(planned, s0, committed_names)
        bonus = pv - ss
        c = st.columns(3)
        c[0].metric('Σ standalone (today’s pipeline)', usd(ss))
        c[1].metric('Portfolio value (compounded)', usd(pv), delta=usd(bonus))
        c[2].metric('Compounding bonus', usd(bonus),
                    help='Positive = net cross-lever compounding; negative = net same-lever overlap.')
        if bonus >= 0:
            st.success(f'These projects **reinforce** each other — the set is worth {usd(bonus)} MORE '
                       f'than the sum of the individual estimates.')
        else:
            st.warning(f'These projects **overlap** — the set is worth {usd(-bonus)} LESS than the sum. '
                       f'Some of them chase the same win.')

        st.markdown('**Per-lever combination** (why the number differs from the sum)')
        by_lever = {}
        for p in E._effective_pcts(planned, committed_names):
            by_lever.setdefault(p[0], []).append(p[1])
        rows = []
        for lever, pcts in by_lever.items():
            combined = 1 - E._prod(1 - x for x in pcts)
            rows.append({'Lever': E.LEVERS[lever][0], 'Pillar': E.LEVERS[lever][1],
                         '# projects': len(pcts), 'Sum of lifts': f'{sum(pcts)*100:.1f}%',
                         'Combined lift': f'{combined*100:.1f}%'})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown('**Per-project: standalone value vs. marginal contribution** '
                    '(what it adds *given the others* — the portfolio-fit number)')
        marg = E.marginal_contributions(planned, s0)
        dfp = pd.DataFrame([{'Project': p['name'],
                             'Lever': E.LEVERS[p['lever']][0],
                             'Standalone': round(E.standalone_value(p, s0)),
                             'Marginal (in set)': round(marg[p['name']])} for p in planned])
        st.bar_chart(dfp.set_index('Project')[['Standalone', 'Marginal (in set)']])
        st.dataframe(dfp.style.format({'Standalone': '${:,}', 'Marginal (in set)': '${:,}'}),
                     use_container_width=True, hide_index=True)

        st.markdown('**Strongest reinforcing & overlapping pairs**')
        pairs = E.pair_synergies(planned, s0)
        comp = [p for p in pairs if p['kind'] == 'compound'][::-1][:6]
        over = [p for p in pairs if p['kind'] == 'overlap'][:6]
        cc = st.columns(2)
        cc[0].caption('Compound (do together) 🟢')
        cc[0].dataframe(pd.DataFrame([{'Pair': f"{p['a']} + {p['b']}", 'Bonus': usd(p['value'])} for p in comp]),
                        use_container_width=True, hide_index=True)
        cc[1].caption('Overlap (redundant) 🟡')
        cc[1].dataframe(pd.DataFrame([{'Pair': f"{p['a']} + {p['b']}", 'Loss': usd(p['value'])} for p in over])
                        if over else pd.DataFrame([{'Pair': '—', 'Loss': '—'}]),
                        use_container_width=True, hide_index=True)

# ==========================================================================
# PHASE 2 — dependency gating + synergy map
# ==========================================================================
with tab2:
    st.markdown('**Enablement / dependency** — a dependent project’s value is gated until '
                f'its enabler is committed (contributes ×{E.GATE_WHEN_ENABLER_ABSENT:.2f} before then).')
    deps = [p for p in planned if p.get('depends_on')]
    if deps:
        rows = []
        for p in deps:
            enabler_in = p['depends_on'] in committed_names
            full = E.standalone_value(p, s0)
            eff = full * (1 if enabler_in else E.GATE_WHEN_ENABLER_ABSENT)
            rows.append({'Project': p['name'], 'Depends on': p['depends_on'],
                         'Enabler committed?': '✅' if enabler_in else '❌ not yet',
                         'Full value': usd(full), 'Effective now': usd(eff)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption('No dependency links among the committed projects.')

    st.markdown('**Synergy map** — 🟢 compound · 🟡 overlap · ➜ enables')
    if planned:
        dot = ['digraph G { rankdir=LR; bgcolor="transparent"; node [style=filled, fontcolor="#0B0616", '
               'fontname="Helvetica", shape=box, penwidth=0];']
        for p in planned:
            dot.append(f'"{p["name"]}" [fillcolor="{AEE_COLOR[E.LEVERS[p["lever"]][1]]}"];')
        pairs = E.pair_synergies(planned, s0)
        strong = [p for p in pairs if p['kind'] == 'compound'][::-1][:6]   # top compound edges
        for p in strong:
            dot.append(f'"{p["a"]}" -> "{p["b"]}" [dir=none, color="#55C892", penwidth=2];')
        for p in [p for p in pairs if p['kind'] == 'overlap']:
            dot.append(f'"{p["a"]}" -> "{p["b"]}" [dir=none, color="#ECB752", style=dashed];')
        for p in deps:
            if p['depends_on'] in committed_names:
                dot.append(f'"{p["depends_on"]}" -> "{p["name"]}" [color="#9B7FE0", penwidth=2];')
        dot.append('}')
        st.graphviz_chart('\n'.join(dot), use_container_width=True)
        st.caption('Green links = projects that multiply each other (different levers). '
                   'Amber = same lever, redundant. Purple arrow = must ship first.')

# ==========================================================================
# PHASE 3 — pick the best COMBINATION under a budget
# ==========================================================================
with tab3:
    st.markdown('Given an effort budget, pick the **set** with the highest combined value — '
                'not just the highest-scoring individual projects.')
    total_effort = sum(E.effort(p) for p in projects)
    budget = st.slider('Effort budget (t-shirt points)', 1.0, round(total_effort, 1),
                       round(total_effort * 0.5, 1), 0.5)

    base_sel, base_val = E.top_by_score(projects, s0, budget)
    opt_sel, opt_val = E.best_portfolio(projects, s0, budget)
    c = st.columns(2)
    c[0].metric('Rank projects individually (top by value)', usd(base_val),
                help='Take the highest standalone-value projects until the budget is spent.')
    c[1].metric('Optimizer — best combination', usd(opt_val), delta=usd(opt_val - base_val))
    if opt_val > base_val:
        st.success(f'The optimizer’s set is worth {usd(opt_val - base_val)} MORE for the same budget — '
                   f'by favouring projects that compound across levers.')

    cc = st.columns(2)
    cc[0].caption('Individually-ranked pick')
    cc[0].dataframe(pd.DataFrame([{'Project': p['name'], 'Lever': E.LEVERS[p['lever']][1],
                                   'Effort': p['effort']} for p in base_sel]),
                    use_container_width=True, hide_index=True)
    cc[1].caption('Optimizer pick')
    cc[1].dataframe(pd.DataFrame([{'Project': p['name'], 'Lever': E.LEVERS[p['lever']][1],
                                   'Effort': p['effort']} for p in opt_sel]),
                    use_container_width=True, hide_index=True)
    st.caption(f'Spent {sum(E.effort(p) for p in opt_sel):.1f} / {budget:.1f} effort points on the optimizer set.')
