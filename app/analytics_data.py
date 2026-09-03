"""
Dummy analytics data + metric calculations for the Analytics dashboards.

The numbers here are illustrative (deterministically generated from the selected
period so switching the filter changes the charts) — they are NOT real. The point
is to show how every card/chart in the ported dashboards looks and behaves.

Metric model (all derived from a handful of daily fundamentals so the on-card
equations tie out exactly):

    visits  -> visitors (visits / visits-per-visitor)
            -> carts   (visits * cart-creation-rate)
            -> orders  (carts  * cart-completion-rate)      => close rate = orders/visits
            -> units   (orders * units-per-order)
            -> sales   (orders * avg-order-value)           => avg unit price = sales/units

Everything a card needs (close rate, AOV, $/visit, etc.) is a ratio of these
totals, so `visits x closeRate x AOV = sales` and friends hold to the penny.
"""
import datetime
import random
import zlib


def _seed(*parts):
    """Deterministic (restart-stable) seed from the given parts."""
    return zlib.crc32('|'.join(str(p) for p in parts).encode()) & 0xFFFFFFFF

# ---------------------------------------------------------------------------
# Period filter options (ported from the reference AnalyticsDateFilter)
# ---------------------------------------------------------------------------

# code -> (display label, number of days in the period)
PRIMARY_OPTIONS = [
    ('THISWEEKSUN', 'This week starting Sunday WTD', 7),
    ('THISWEEKMON', 'This week starting Monday WTD', 7),
    ('LASTWEEKSUN', 'Last week starting Sunday', 7),
    ('LASTWEEKMON', 'Last week starting Monday', 7),
    ('THISMONTH', 'This Month MTD', 30),
    ('LASTMONTH', 'Last Month', 30),
    ('THISQT', 'This Quarter QTD', 90),
    ('ROLLQTR', 'Rolling Quarter (13 weeks)', 91),
    ('ROLLYEAR', 'Rolling 12 Months', 365),
    ('CUSTOM', 'Custom', 30),
]

# primary code -> list of (comparison code, display label)
COMPARE_OPTIONS = {
    'THISWEEKSUN': [('LASTWEEKSUN', 'Last week WTD'), ('SAMEWEEKLYSUN', 'Same week prior year')],
    'THISWEEKMON': [('LASTWEEKMON', 'Last week WTD'), ('SAMEWEEKLYMON', 'Same week prior year')],
    'LASTWEEKSUN': [('LSAMEWEEKLYSUN', 'Same week prior year'), ('2WEEKSAGOSUN', '2 Weeks ago')],
    'LASTWEEKMON': [('LSAMEWEEKLYMON', 'Same week prior year'), ('2WEEKSAGOMON', '2 Weeks ago')],
    'THISMONTH': [('LSTMONTH', 'Last Month'), ('SAMEMONLY', 'Same Month prior year')],
    'LASTMONTH': [('2MONTHSAGO', '2 Months ago'), ('LSAMEMONLY', 'Same Month prior year')],
    'THISQT': [('LASTQTR', 'Last Quarter'), ('SAMEQTRLY', 'Same quarter prior year')],
    'ROLLQTR': [('PRIOR13', 'Prior 13 weeks'), ('13WEEKSLY', 'Same 13 weeks prior year')],
    'ROLLYEAR': [('PRIOR12', 'Prior 12 months'), ('SAME12ML2YEAR', 'Same 12 months 2 years ago')],
    'CUSTOM': [('CUSTOM', 'Comparison Period')],
}

DEFAULT_PRIMARY = 'THISMONTH'

# Cap chart points so long periods (quarter / year) stay readable.
MAX_POINTS = 30

# Grow Sales cards drill down to their group's detail dashboard.
GROUP_LINKS = {
    'attract': '/app/analytics/attract-traffic/',
    'engage': '/app/analytics/engage-customers/',
    'expand': '/app/analytics/expand-purchases/',
}


def primary_label(code):
    for c, label, _ in PRIMARY_OPTIONS:
        if c == code:
            return label
    return code


def compare_label(primary_code, compare_code):
    for c, label in COMPARE_OPTIONS.get(primary_code, []):
        if c == compare_code:
            return label
    opts = COMPARE_OPTIONS.get(primary_code)
    return opts[0][1] if opts else 'Prior Period'


def default_compare(primary_code):
    opts = COMPARE_OPTIONS.get(primary_code)
    return opts[0][0] if opts else ''


# ---------------------------------------------------------------------------
# Formatting helpers (mirror the reference formatValue: $, %, K/M abbreviation)
# ---------------------------------------------------------------------------

def _abbrev(num):
    """Return (display, full) where display abbreviates >=1K to K / >=1M to M."""
    full = f"{num:,.0f}" if abs(num) >= 100 else f"{num:,.2f}"
    a = abs(num)
    if a >= 1_000_000:
        return f"{num / 1_000_000:.2f}M", full
    if a >= 1_000:
        return f"{num / 1_000:.1f}K", full
    return full, full


def fmt(num, kind):
    """Format a number as the reference would; returns (display, full_number)."""
    num = float(num or 0)
    if kind == 'currency':
        disp, full = _abbrev(num)
        return f"${disp}", f"${full}"
    if kind == 'percentage':
        return f"{num:.2f}%", f"{num:.2f}%"
    if kind == 'integer':
        disp, full = _abbrev(round(num))
        return disp, full
    if kind == 'normal':
        return f"{num:.2f}", f"{num:.2f}"
    if kind == 'time':                      # seconds -> M:SS
        total = int(round(num))
        disp = f"{total // 60}:{total % 60:02d}"
        return disp, disp
    return f"{num:.2f}", f"{num:.2f}"


def _jseries(mean, n, seed, spread=0.15):
    """A short daily series jittered around `mean` (for synthetic sparklines)."""
    rnd = random.Random(seed)
    return [round(mean * (1 - spread + 2 * spread * rnd.random()), 4) for _ in range(n)]


def fmt_delta(pct):
    """Signed 2-decimal percent string, e.g. +12.34% / -3.10%."""
    pct = float(pct or 0)
    return f"{'+' if pct >= 0 else ''}{pct:.2f}%"


# ---------------------------------------------------------------------------
# Dummy data generation
# ---------------------------------------------------------------------------

def _params(seed):
    """Behavioural ratios + scale for a scenario, from a deterministic seed."""
    rnd = random.Random(seed)
    return {
        'base_visits': 1400 + (seed % 900),        # scenario-dependent scale
        'vpv': 1.25 + rnd.random() * 0.25,          # visits per visitor
        'cart_rate': 0.16 + rnd.random() * 0.06,    # carts / visits
        'completion': 0.30 + rnd.random() * 0.12,   # orders / carts
        'upo': 1.6 + rnd.random() * 0.6,            # units / order
        'aov': 80 + rnd.random() * 40,              # avg order value ($)
        'trend': 0.30,
    }


def _perturb(params, seed, spread=0.10):
    """Return a copy of `params` nudged by up to +/-`spread` (deterministic).

    Used to build the comparison period from the primary's ratios so the two
    periods stay comparable and deltas land in a realistic band.
    """
    rnd = random.Random(seed)

    def jig(v):
        return v * (1 + (rnd.random() * 2 - 1) * spread)

    return {
        'base_visits': jig(params['base_visits']),
        'vpv': jig(params['vpv']),
        'cart_rate': jig(params['cart_rate']),
        'completion': jig(params['completion']),
        'upo': jig(params['upo']),
        'aov': jig(params['aov']),
        'trend': 0.18,
    }


def _daily_series(seed, n, params):
    """Generate `n` daily fundamentals dicts from `params` + a noise seed."""
    rnd = random.Random(seed)
    base_visits = params['base_visits']
    vpv, cart_rate = params['vpv'], params['cart_rate']
    completion, upo, aov = params['completion'], params['upo'], params['aov']
    trend = params['trend']

    rows = []
    for i in range(n):
        seasonal = 1 + trend * (i / max(n - 1, 1))
        noise = 0.82 + rnd.random() * 0.36
        visits = base_visits * seasonal * noise
        visitors = visits / vpv
        carts = visits * cart_rate
        orders = carts * completion
        units = orders * upo
        sales = orders * aov
        rows.append({
            'visits': visits,
            'visitors': visitors,
            'carts': carts,
            'orders': orders,
            'units': units,
            'sales': sales,
        })
    return rows


def _aggregate(rows):
    """Sum daily fundamentals and derive all aggregate metrics."""
    s = {k: sum(r[k] for r in rows) for k in ('visits', 'visitors', 'carts', 'orders', 'units', 'sales')}
    visits, visitors, carts, orders, units, sales = (
        s['visits'], s['visitors'], s['carts'], s['orders'], s['units'], s['sales'])

    def safe(a, b):
        return a / b if b else 0

    new_users = visitors * 0.62
    return {
        'visits': visits,
        'visitors': visitors,
        'carts': carts,
        'orders': orders,
        'units': units,
        'sales': sales,
        'new_users': new_users,
        'returning_users': visitors - new_users,
        'aov': safe(sales, orders),
        'close_rate': safe(orders, visits) * 100,
        'visit_per_visitor': safe(visits, visitors),
        'units_per_order': safe(units, orders),
        'cart_creation_pct': safe(carts, visits) * 100,
        'cart_completion': safe(orders, carts) * 100,
        'avg_unit_price': safe(sales, units),
        'expand_visit': safe(sales, visits),   # $/visit
    }


def _pct_change(primary, secondary):
    return ((primary - secondary) / secondary * 100) if secondary else 0


def build_metrics(primary_code, compare_code):
    """Return everything needed to render the Grow Sales dashboard for a
    given (primary period, comparison period) selection."""
    days = next((d for c, _, d in PRIMARY_OPTIONS if c == primary_code), 30)
    n = min(days, MAX_POINTS)

    seed_p = _seed(primary_code, 'primary')
    seed_s = _seed(primary_code, compare_code, 'secondary')

    params_p = _params(seed_p)
    params_s = _perturb(params_p, seed_s, spread=0.10)
    rows_p = _daily_series(seed_p, n, params_p)
    rows_s = _daily_series(seed_s, n, params_s)

    agg_p = _aggregate(rows_p)
    agg_s = _aggregate(rows_s)

    # x-axis labels (MM-DD), ending yesterday
    today = datetime.date.today()
    start = today - datetime.timedelta(days=n)
    labels = [(start + datetime.timedelta(days=i + 1)).strftime('%m-%d') for i in range(n)]

    # per-day chart series (derived ratios per point)
    def series(rows, fn):
        return [round(fn(r), 4) for r in rows]

    def s_ratio(r, a, b):
        return (r[a] / r[b]) if r[b] else 0

    daily = {
        'totalRevenue': series(rows_p, lambda r: r['sales']),
        'sessions': series(rows_p, lambda r: r['visits']),
        'checkouts': series(rows_p, lambda r: r['orders']),
        'totalUsers': series(rows_p, lambda r: r['visitors']),
        'itemPurchaseQuantity': series(rows_p, lambda r: r['units']),
        'expandAvgOrderValue': series(rows_p, lambda r: s_ratio(r, 'sales', 'orders')),
        'engageExpandVisitValue': series(rows_p, lambda r: s_ratio(r, 'sales', 'visits')),
        'engageCartCreationValue': series(rows_p, lambda r: s_ratio(r, 'carts', 'visits') * 100),
        'visitPerVisitorValue': series(rows_p, lambda r: s_ratio(r, 'visits', 'visitors')),
        'cartCompletionValue': series(rows_p, lambda r: s_ratio(r, 'orders', 'carts') * 100),
        'expandAvgUnitPrice': series(rows_p, lambda r: s_ratio(r, 'sales', 'units')),
        'engageCloseRate': series(rows_p, lambda r: s_ratio(r, 'orders', 'visits') * 100),
        'expandUnitsPerOrderValue': series(rows_p, lambda r: s_ratio(r, 'units', 'orders')),
    }
    daily_secondary = {
        'totalRevenue': series(rows_s, lambda r: r['sales']),
        'checkouts': series(rows_s, lambda r: r['orders']),
        'engageExpandVisitValue': series(rows_s, lambda r: s_ratio(r, 'sales', 'visits')),
    }

    # percentage deltas primary vs secondary
    pct = {
        'total_sales': _pct_change(agg_p['sales'], agg_s['sales']),
        'total_visits': _pct_change(agg_p['visits'], agg_s['visits']),
        'aov': _pct_change(agg_p['aov'], agg_s['aov']),
        'total_visitor': _pct_change(agg_p['visitors'], agg_s['visitors']),
        'attract_engage_order': _pct_change(agg_p['orders'], agg_s['orders']),
        'engage_expand_visit': _pct_change(agg_p['expand_visit'], agg_s['expand_visit']),
        'close_rate': _pct_change(agg_p['close_rate'], agg_s['close_rate']),
        'cart_creation': _pct_change(agg_p['cart_creation_pct'], agg_s['cart_creation_pct']),
        'visit_per_visitor': _pct_change(agg_p['visit_per_visitor'], agg_s['visit_per_visitor']),
        'units_per_order': _pct_change(agg_p['units_per_order'], agg_s['units_per_order']),
        'cart_completion': _pct_change(agg_p['cart_completion'], agg_s['cart_completion']),
        'avg_unit_price': _pct_change(agg_p['avg_unit_price'], agg_s['avg_unit_price']),
    }

    return {
        'labels': labels,
        'daily': daily,
        'daily_secondary': daily_secondary,
        'primary': agg_p,
        'secondary': agg_s,
        'pct': pct,
    }


# ---------------------------------------------------------------------------
# Card assembly for the Grow Sales dashboard
# ---------------------------------------------------------------------------

def build_grow_sales(primary_code, compare_code):
    """Return (cards, charts) for the Grow Sales dashboard.

    `cards` is a dict keyed by card id (each a fully-formatted card for the
    template partial); `charts` is a JSON-serializable dict keyed by the same
    ids carrying the Chart.js series/labels.
    """
    m = build_metrics(primary_code, compare_code)
    p = m['primary']
    pct = m['pct']
    clabel = compare_label(primary_code, compare_code)
    labels = m['labels']

    def E(value, kind, unit):
        return {'value': fmt(value, kind)[0], 'unit': unit}

    def kpi(value, kind):
        disp, full = fmt(value, kind)
        return disp, (full if full != disp else '')

    cards = {}
    charts = {}

    def card(cid, group, title, header, *, kpi_kind=None, kpi_val=None,
             delta_key=None, equation=None, result=None, bottom=None,
             series_key=None, two_sets=False, fmt_kind='integer',
             secondary_key=None, chart_height=90):
        disp, tip = ('', '')
        if kpi_kind is not None:
            disp, tip = kpi(kpi_val, kpi_kind)
        delta = pct.get(delta_key) if delta_key else None
        cards[cid] = {
            'id': cid, 'group': group, 'title': title, 'header': header,
            'kpi': disp, 'kpi_tooltip': tip,
            'delta': delta,
            'delta_str': fmt_delta(delta) if delta is not None else '',
            'delta_to': clabel,
            'equation': equation or [],
            'equation_result': result,
            'bottom_text': bottom,
            'chart_height': chart_height,
        }
        chart = {
            'labels': labels,
            's1': m['daily'][series_key],
            'format': fmt_kind,
            'two_sets': two_sets,
            'group': group,
            'main_label': primary_label(primary_code),
            'compare_label': clabel,
        }
        if secondary_key:
            chart['s2'] = m['daily_secondary'][secondary_key]
        charts[cid] = chart

    # 1. GROW / SALES  (hero, full width, 2-series)
    card('grow_sales', 'grow', 'GROW', 'SALES',
         kpi_kind='currency', kpi_val=p['sales'], delta_key='total_sales',
         equation=[E(p['visits'], 'integer', 'Visits  ×'),
                   E(p['close_rate'], 'percentage', 'Close Rate  ×'),
                   E(p['aov'], 'currency', 'Avg. Order Value  =')],
         result=E(p['sales'], 'currency', 'Sales'),
         series_key='totalRevenue', secondary_key='totalRevenue',
         two_sets=True, fmt_kind='currency', chart_height=150)

    # 2-4. ATTRACT / ENGAGE / EXPAND  (KPI + sparkline)
    card('attract', 'attract', 'ATTRACT', 'VISITS',
         kpi_kind='integer', kpi_val=p['visits'], delta_key='total_visits',
         series_key='sessions', fmt_kind='integer')
    card('engage', 'engage', 'ENGAGE', 'CLOSE RATE',
         kpi_kind='percentage', kpi_val=p['close_rate'], delta_key='close_rate',
         series_key='engageCloseRate', fmt_kind='percentage')
    card('expand', 'expand', 'EXPAND', 'AVG ORDER VALUE',
         kpi_kind='currency', kpi_val=p['aov'], delta_key='aov',
         series_key='expandAvgOrderValue', fmt_kind='currency')

    # 5-7. VISITORS / CART CREATION / UNITS PER ORDER  (KPI + equation)
    card('attract_visitors', 'attract', '', 'VISITORS',
         kpi_kind='integer', kpi_val=p['visitors'], delta_key='total_visitor',
         equation=[E(p['new_users'], 'integer', 'New  +'),
                   E(p['returning_users'], 'integer', 'Returning')],
         series_key='totalUsers', fmt_kind='integer')
    card('engage_cart_creation', 'engage', '', 'CART CREATION',
         kpi_kind='percentage', kpi_val=p['cart_creation_pct'], delta_key='cart_creation',
         equation=[E(p['carts'], 'integer', 'Carts  /'),
                   E(p['visits'], 'integer', 'Visits')],
         series_key='engageCartCreationValue', fmt_kind='percentage')
    card('expand_units_per_order', 'expand', '', 'UNITS PER ORDER',
         kpi_kind='normal', kpi_val=p['units_per_order'], delta_key='units_per_order',
         equation=[E(p['units'], 'integer', 'Units  /'),
                   E(p['orders'], 'integer', 'Orders')],
         series_key='expandUnitsPerOrderValue', fmt_kind='normal')

    # 8-10. VISITS PER VISITOR / CART COMPLETION / AVG UNIT PRICE  (KPI + eq + sentence)
    card('attract_visits', 'attract', '', 'VISITS PER VISITOR',
         kpi_kind='normal', kpi_val=p['visit_per_visitor'], delta_key='visit_per_visitor',
         equation=[E(p['visits'], 'integer', 'Visits  /'),
                   E(p['visitors'], 'integer', 'Visitors')],
         bottom=(f"{fmt(p['visitors'], 'integer')[0]} visitors came to the site. "
                 f"On average, they had {fmt(p['visit_per_visitor'], 'normal')[0]} visits each, "
                 f"yielding {fmt(p['visits'], 'integer')[0]} total Visits."),
         series_key='visitPerVisitorValue', fmt_kind='normal')
    card('engage_cart_completion', 'engage', '', 'CART COMPLETION',
         kpi_kind='percentage', kpi_val=p['cart_completion'], delta_key='cart_completion',
         equation=[E(p['orders'], 'integer', 'Orders  /'),
                   E(p['carts'], 'integer', 'Carts')],
         bottom=(f"{fmt(p['cart_creation_pct'], 'percentage')[0]} of all visits created a cart. "
                 f"Of those carts, {fmt(p['cart_completion'], 'percentage')[0]} completed purchase, "
                 f"yielding a {fmt(p['close_rate'], 'percentage')[0]} Close Rate."),
         series_key='cartCompletionValue', fmt_kind='percentage')
    card('expand_avg_unit_price', 'expand', '', 'AVG UNIT PRICE',
         kpi_kind='currency', kpi_val=p['avg_unit_price'], delta_key='avg_unit_price',
         equation=[E(p['sales'], 'currency', 'Sales  /'),
                   E(p['units'], 'integer', 'Units')],
         bottom=(f"The average order had {fmt(p['units_per_order'], 'normal')[0]} units at "
                 f"{fmt(p['avg_unit_price'], 'currency')[0]} each, yielding a "
                 f"{fmt(p['aov'], 'currency')[0]} Avg. Order Value."),
         series_key='expandAvgUnitPrice', fmt_kind='currency')

    # 11. ATTRACT & ENGAGE / ORDERS  (wide, 2-series) — gold/yellow theme
    card('attract_engage', 'engage', 'ATTRACT & ENGAGE', 'ORDERS',
         kpi_kind='integer', kpi_val=p['orders'], delta_key='attract_engage_order',
         equation=[E(p['visits'], 'integer', 'Visits  ×'),
                   E(p['close_rate'], 'percentage', 'Close Rate  =')],
         result=E(p['orders'], 'integer', 'Orders'),
         series_key='checkouts', secondary_key='checkouts',
         two_sets=True, fmt_kind='integer', chart_height=130)

    # 12. EXPAND / AVG ORDER VALUE  (equation result, delta on right)
    card('expand_two', 'expand', 'EXPAND', 'AVG ORDER VALUE',
         delta_key='aov',
         equation=[E(p['sales'], 'currency', 'Sales  /'),
                   E(p['orders'], 'integer', 'Orders  =')],
         result=E(p['aov'], 'currency', 'AOV'),
         series_key='expandAvgOrderValue', fmt_kind='currency', chart_height=130)

    # 13. ATTRACT TRAFFIC / VISITS  (equation result, delta on right)
    card('attract_traffic', 'attract', 'ATTRACT TRAFFIC', 'VISITS',
         delta_key='total_visits',
         equation=[E(p['visitors'], 'integer', 'Visitors  ×'),
                   E(p['visit_per_visitor'], 'normal', 'Visits each  =')],
         result=E(p['visits'], 'integer', 'Visits'),
         series_key='sessions', fmt_kind='integer', chart_height=130)

    # 14. ENGAGE & EXPAND / $/VISIT  (wide, 2-series) — green theme
    card('engage_expand', 'expand', 'ENGAGE & EXPAND', '$/VISIT',
         kpi_kind='currency', kpi_val=p['expand_visit'], delta_key='engage_expand_visit',
         equation=[E(p['close_rate'], 'percentage', 'Close Rate  ×'),
                   E(p['aov'], 'currency', 'AOV  =')],
         result=E(p['expand_visit'], 'currency', 'per Visit'),
         series_key='engageExpandVisitValue', secondary_key='engageExpandVisitValue',
         two_sets=True, fmt_kind='currency', chart_height=130)

    # Link each card to its group's detail dashboard (right-chevron + click).
    for c in cards.values():
        c['link'] = GROUP_LINKS.get(c['group'], '')

    # Period winner / loser highlight (recreates the reference get6ChartPercentages):
    # among the six granular "detail" cards, pulse the biggest gainer green and
    # the biggest decliner red — only when the move is actually positive/negative.
    detail_ids = ['attract_visitors', 'engage_cart_creation', 'expand_units_per_order',
                  'attract_visits', 'engage_cart_completion', 'expand_avg_unit_price']
    detail = [(cid, cards[cid]['delta']) for cid in detail_ids
              if cards[cid].get('delta') is not None]
    if detail:
        win_id, win_val = max(detail, key=lambda kv: kv[1])
        lose_id, lose_val = min(detail, key=lambda kv: kv[1])
        if win_val > 0:
            cards[win_id]['highlight'] = 'win'
        if lose_val < 0 and lose_id != win_id:
            cards[lose_id]['highlight'] = 'loss'

    return cards, charts


# ---------------------------------------------------------------------------
# Generic deck builder (used by Attract / Engage / Expand dashboards)
# ---------------------------------------------------------------------------

class Deck:
    """Accumulates cards / charts / history cards / scatter widgets for a
    dashboard, with the shared date labels + comparison label baked in."""

    def __init__(self, labels, main_label, compare_lbl):
        self.labels = labels
        self.main_label = main_label
        self.compare_lbl = compare_lbl
        self.cards = {}
        self.charts = {}
        self.history = {}
        self.scatter = {}

    def eq(self, value, kind, unit):
        return {'value': fmt(value, kind)[0], 'unit': unit}

    def card(self, cid, group, title, header, *, kpi_val=None, kpi_kind=None,
             delta=None, equation=None, result=None, bottom=None,
             s1=None, s2=None, two_sets=False, fmt_kind='integer', chart_height=90):
        disp, tip = ('', '')
        if kpi_kind is not None:
            disp, tip = fmt(kpi_val, kpi_kind)
            if tip == disp:
                tip = ''
        self.cards[cid] = {
            'id': cid, 'group': group, 'title': title, 'header': header,
            'kpi': disp, 'kpi_tooltip': tip,
            'delta': delta,
            'delta_str': fmt_delta(delta) if delta is not None else '',
            'delta_to': self.compare_lbl,
            'equation': equation or [],
            'equation_result': result,
            'bottom_text': bottom,
            'chart_height': chart_height,
        }
        self.charts[cid] = {
            'labels': self.labels, 's1': s1, 'format': fmt_kind,
            'two_sets': two_sets, 'group': group,
            'main_label': self.main_label, 'compare_label': self.compare_lbl,
        }
        if s2 is not None:
            self.charts[cid]['s2'] = s2

    def history_card(self, cid, group, title, kpi_val, kpi_kind, delta, weeks,
                     reversed_color=False, equation=None):
        """weeks = list of (label, formatted_value) trailing readouts."""
        disp = fmt(kpi_val, kpi_kind)[0]
        good = (delta is not None) and ((delta < 0) if reversed_color else (delta >= 0))
        self.history[cid] = {
            'id': cid, 'group': group, 'title': title, 'kpi': disp,
            'delta': delta, 'delta_str': fmt_delta(delta) if delta is not None else '',
            'delta_to': self.compare_lbl, 'delta_good': good,
            'weeks': weeks, 'equation': equation or [],
        }

    def scatter_widget(self, wid, group, title, charts):
        self.scatter[wid] = {'id': wid, 'group': group, 'title': title, 'charts': charts}


def _linfit(pts):
    """Least-squares line through [(x,y)]; returns endpoints spanning the x range."""
    n = len(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
    b = my - slope * mx
    x1, x2 = min(xs), max(xs)
    pad = (x2 - x1) * 0.08 or 1
    x1 -= pad
    x2 += pad
    return {'x1': round(x1, 2), 'y1': round(slope * x1 + b, 2),
            'x2': round(x2, 2), 'y2': round(slope * x2 + b, 2)}


def _scatter_chart(seed, heading, x_label, y_label, names, lever_kind):
    """Build one scatter chart: a point per name (YoY deltas) + a trend line."""
    rnd = random.Random(seed)
    points = []
    raw = []
    for name in names:
        x = round(rnd.uniform(-18, 32), 2)          # YoY % change, x metric
        y = round(rnd.uniform(-18, 32), 2)          # YoY % change, y metric
        if lever_kind == 'currency':
            primary = rnd.uniform(60, 260)
        elif lever_kind == 'normal':
            primary = rnd.uniform(1.1, 3.2)
        else:
            primary = rnd.uniform(1.5, 12.0)        # percentage
        change = round(rnd.uniform(-15, 20), 2)
        secondary = primary / (1 + change / 100.0)
        raw.append((x, y))
        points.append({
            'label': name, 'x': x, 'y': y,
            'primary': fmt(primary, lever_kind)[0],
            'secondary': fmt(secondary, lever_kind)[0],
            'change': change,
        })
    return {
        'heading': f'Change in {heading}',
        'x_label': x_label, 'y_label': y_label,
        'points': points, 'trend': _linfit(raw),
    }


def _split_series(daily, share, seed):
    """Scale a daily series by `share` with a little per-day noise."""
    rnd = random.Random(seed)
    return [round(v * share * (0.9 + rnd.random() * 0.2), 2) for v in daily]


def build_attract_traffic(primary_code, compare_code):
    """Attract Traffic dashboard — all area/line charts (visits, visitors,
    device & channel splits)."""
    m = build_metrics(primary_code, compare_code)
    p, pct = m['primary'], m['pct']
    d = Deck(m['labels'], primary_label(primary_code), compare_label(primary_code, compare_code))
    E = d.eq

    new_pct = p['new_users'] / p['visitors'] * 100 if p['visitors'] else 0
    ret_pct = p['returning_users'] / p['visitors'] * 100 if p['visitors'] else 0
    new_daily = [round(v * 0.62, 2) for v in m['daily']['totalUsers']]
    ret_daily = [round(v * 0.38, 2) for v in m['daily']['totalUsers']]

    # ATTRACT / Visits  (comparison)
    d.card('attract_visits', 'attract', 'ATTRACT', 'VISITS',
           kpi_val=p['visits'], kpi_kind='integer', delta=pct['total_visits'],
           equation=[E(p['visitors'], 'integer', 'Visitors  ×'),
                     E(p['visit_per_visitor'], 'normal', 'Visits each  =')],
           result=E(p['visits'], 'integer', 'Visits'),
           s1=m['daily']['sessions'],
           s2=_split_series(m['daily']['sessions'], 0.92, _seed(compare_code, 'v')),
           two_sets=True, fmt_kind='integer', chart_height=150)

    # INVITE / RETURNING / ENCOURAGE
    d.card('invite', 'attract', 'INVITE', 'NEW VISITORS',
           kpi_val=p['new_users'], kpi_kind='integer', delta=pct['total_visitor'] + 1.2,
           equation=[E(new_pct, 'percentage', 'of Visitors')],
           s1=new_daily, fmt_kind='integer')
    d.card('returning', 'attract', '', 'RETURNING VISITORS',
           kpi_val=p['returning_users'], kpi_kind='integer', delta=pct['total_visitor'] - 0.8,
           equation=[E(ret_pct, 'percentage', 'of Visitors')],
           s1=ret_daily, fmt_kind='integer')
    d.card('encourage', 'attract', 'ENCOURAGE', 'VISITS PER VISITOR',
           kpi_val=p['visit_per_visitor'], kpi_kind='normal', delta=pct['visit_per_visitor'],
           equation=[E(p['visits'], 'integer', 'Visits  /'),
                     E(p['visitors'], 'integer', 'Visitors')],
           s1=m['daily']['visitPerVisitorValue'], fmt_kind='normal')

    # VISITORS  (comparison)
    d.card('visitors', 'attract', '', 'VISITORS',
           kpi_val=p['visitors'], kpi_kind='integer', delta=pct['total_visitor'],
           equation=[E(p['new_users'], 'integer', 'New Visitors  +'),
                     E(p['returning_users'], 'integer', 'Returning Visitors  =')],
           result=E(p['visitors'], 'integer', 'Visitors'),
           s1=m['daily']['totalUsers'],
           s2=_split_series(m['daily']['totalUsers'], 0.9, _seed(compare_code, 'vis')),
           two_sets=True, fmt_kind='integer', chart_height=150)

    # Device + channel splits
    sessions = m['daily']['sessions']
    devices = [('dev_desktop', 'DESKTOP', 0.55), ('dev_mobile', 'MOBILE', 0.34),
               ('dev_tablet', 'TABLET', 0.08), ('dev_other', 'OTHER', 0.03)]
    channels = [('ch_direct', 'DIRECT', 0.24), ('ch_organic', 'ORGANIC SEARCH', 0.30),
                ('ch_paid', 'PAID SEARCH', 0.16), ('ch_social', 'SOCIAL', 0.12),
                ('ch_referral', 'REFERRAL', 0.10), ('ch_other', 'OTHER', 0.08)]
    for cid, header, share in devices + channels:
        rnd = random.Random(_seed(primary_code, compare_code, cid))
        total = p['visits'] * share
        delta = round(rnd.uniform(-12, 15), 2)
        d.card(cid, 'attract', '', header,
               kpi_val=total, kpi_kind='integer', delta=delta,
               equation=[E(share * 100, 'percentage', 'of Visits')],
               s1=_split_series(sessions, share, _seed(cid, 's')), fmt_kind='integer')

    return {'cards': d.cards, 'charts': d.charts, 'history': d.history, 'scatter': d.scatter}


def _weeks(base, kind, seed):
    """Three trailing 'Last N wks' readouts near `base`."""
    rnd = random.Random(seed)
    return [(f'Last {w} wks', fmt(base * (0.9 + rnd.random() * 0.2), kind)[0])
            for w in (4, 8, 13)]


def _dummy_delta(seed, lo=-12, hi=15):
    return round(random.Random(seed).uniform(lo, hi), 2)


def build_engage_customer(primary_code, compare_code):
    """Engage Customer dashboard — area charts + KPI/history cards + two
    device/channel close-rate changeplots (scatter)."""
    m = build_metrics(primary_code, compare_code)
    p, pct = m['primary'], m['pct']
    n = len(m['labels'])
    d = Deck(m['labels'], primary_label(primary_code), compare_label(primary_code, compare_code))
    E = d.eq

    def sd(key):  # deterministic seed for this dashboard
        return _seed(primary_code, compare_code, 'eng', key)

    # derived dummy aggregates
    pdp_views = p['visits'] * 2.6
    cart_to_detail = p['carts'] / pdp_views * 100 if pdp_views else 0
    buy_to_detail = p['orders'] / pdp_views * 100 if pdp_views else 0
    returning_pct = p['returning_users'] / p['visitors'] * 100 if p['visitors'] else 0
    cart_views = p['orders'] * 1.8
    checkout_views = p['orders'] * 1.3
    billing_views = p['orders'] * 1.1

    # synthetic daily comparison series
    def s2(series, seed):
        rnd = random.Random(seed)
        return [round(v * (0.86 + rnd.random() * 0.2), 4) for v in series]

    s_close = m['daily']['engageCloseRate']
    s_creation = m['daily']['engageCartCreationValue']
    s_completion = m['daily']['cartCompletionValue']
    s_ctd = _jseries(cart_to_detail, n, sd('ctd'))
    s_ret = _jseries(returning_pct, n, sd('ret'))
    s_btd = _jseries(buy_to_detail, n, sd('btd'))
    s_cartv = _jseries(cart_views / n, n, sd('cv'))
    s_checkv = _jseries(checkout_views / n, n, sd('chk'))

    # SECTION 1 -----------------------------------------------------------
    d.card('engage_close_rate', 'engage', 'ENGAGE', 'CLOSE RATE',
           kpi_val=p['close_rate'], kpi_kind='percentage', delta=pct['close_rate'],
           equation=[E(p['cart_creation_pct'], 'percentage', 'Cart Creation  ×'),
                     E(p['cart_completion'], 'percentage', 'Cart Completion  =')],
           result=E(p['close_rate'], 'percentage', 'Close Rate'),
           s1=s_close, s2=s2(s_close, sd('close2')),
           two_sets=True, fmt_kind='percentage', chart_height=150)
    d.card('interest', 'engage', 'INTEREST', 'CART CREATION',
           kpi_val=p['cart_creation_pct'], kpi_kind='percentage', delta=pct['cart_creation'],
           equation=[E(p['carts'], 'integer', 'carts  /'), E(p['visits'], 'integer', 'Visits')],
           s1=s_creation, fmt_kind='percentage')
    d.card('convince', 'engage', 'CONVINCE', 'CART COMPLETION',
           kpi_val=p['cart_completion'], kpi_kind='percentage', delta=pct['cart_completion'],
           equation=[E(p['orders'], 'integer', 'orders  /'), E(p['carts'], 'integer', 'carts')],
           s1=s_completion, fmt_kind='percentage')

    # SECTION 2 -----------------------------------------------------------
    d.card('interest_big', 'engage', 'INTEREST', 'CART CREATION',
           kpi_val=p['cart_creation_pct'], kpi_kind='percentage', delta=pct['cart_creation'],
           equation=[E(p['carts'], 'integer', 'Carts  /'), E(p['visits'], 'integer', 'Visits  =')],
           result=E(p['cart_creation_pct'], 'percentage', 'Cart Creation Rate'),
           s1=s_creation, s2=s2(s_creation, sd('cre2')),
           two_sets=True, fmt_kind='percentage', chart_height=150)

    history = [
        ('bounce_rate', 'BOUNCE RATE', 38.0, 'percentage', True),
        ('visit_duration', 'VISIT DURATION', 204, 'time', False),
        ('shopper_activity', 'SHOPPER ACTIVITY', 46.0, 'percentage', False),
        ('pages_per_visit', 'PAGES PER VISIT', 5.4, 'normal', False),
        ('cat_pdp_per_visit', 'CATEGORY PAGE VIEWS PER VISIT', 3.1, 'normal', False),
        ('pdp_per_visit', 'PDP VIEWS PER VISIT', 4.2, 'normal', False),
    ]
    for cid, title, base, kind, rev in history:
        d.history_card(cid, 'engage', title, base, kind, _dummy_delta(sd(cid)),
                       _weeks(base, kind, sd(cid + 'w')), reversed_color=rev)

    d.card('carts_per_pdp', 'engage', '', 'CARTS PER PDP VIEW',
           kpi_val=cart_to_detail, kpi_kind='percentage', delta=_dummy_delta(sd('ctdd')),
           equation=[E(p['carts'], 'integer', 'Carts  /'),
                     E(pdp_views, 'integer', 'PDP Views  =')],
           result=E(cart_to_detail, 'percentage', 'Carts per PDP View'),
           s1=s_ctd, s2=s2(s_ctd, sd('ctd2')), two_sets=True, fmt_kind='percentage', chart_height=130)

    # SECTION 3 -----------------------------------------------------------
    d.card('convince_big', 'engage', 'CONVINCE', 'CART COMPLETION',
           kpi_val=p['cart_completion'], kpi_kind='percentage', delta=pct['cart_completion'],
           equation=[E(p['orders'], 'integer', 'Orders  /'), E(p['carts'], 'integer', 'Carts  =')],
           result=E(p['cart_completion'], 'percentage', 'Cart Completion Rate'),
           s1=s_completion, s2=s2(s_completion, sd('com2')),
           two_sets=True, fmt_kind='percentage', chart_height=150)
    d.card('cart_views', 'engage', '', 'CART VIEWS',
           kpi_val=cart_views, kpi_kind='integer', delta=_dummy_delta(sd('cvd')),
           s1=s_cartv, fmt_kind='integer')
    d.card('checkout_views', 'engage', '', 'CHECKOUT VIEWS',
           kpi_val=checkout_views, kpi_kind='integer', delta=_dummy_delta(sd('chkd')),
           s1=s_checkv, fmt_kind='integer')
    d.card('billing_shipping_views', 'engage', '', 'BILLING/SHIPPING VIEWS',
           kpi_val=billing_views, kpi_kind='integer', delta=_dummy_delta(sd('bsd')),
           s1=s2(s_checkv, sd('bs2')), fmt_kind='integer')

    # SECTION 4 -----------------------------------------------------------
    ret_cr = 7.2
    new_cr = 4.1
    d.card('pct_returning', 'engage', 'ENGAGE', '% RETURNING VISITORS',
           kpi_val=returning_pct, kpi_kind='percentage', delta=_dummy_delta(sd('retd')),
           equation=[E(p['returning_users'], 'integer', 'Returning Visitors  /'),
                     E(p['visitors'], 'integer', 'Visitors  =')],
           result=E(returning_pct, 'percentage', 'Returning Visitors'),
           bottom=(f"Returning Visitor Close Rate: {fmt(ret_cr, 'percentage')[0]}  |  "
                   f"New Visitor Close Rate: {fmt(new_cr, 'percentage')[0]}"),
           s1=s_ret, s2=s2(s_ret, sd('ret2')), two_sets=True, fmt_kind='percentage', chart_height=150)
    d.card('orders_per_pdp', 'engage', '', 'ORDERS PER PDP VIEW',
           kpi_val=buy_to_detail, kpi_kind='percentage', delta=_dummy_delta(sd('btdd')),
           equation=[E(p['orders'], 'integer', 'Orders  /'),
                     E(pdp_views, 'integer', 'PDP Views  =')],
           result=E(buy_to_detail, 'percentage', 'Orders per PDP View'),
           s1=s_btd, s2=s2(s_btd, sd('btd2')), two_sets=True, fmt_kind='percentage', chart_height=130)

    # SECTION 5 — changeplots --------------------------------------------
    devices = ['Desktop', 'Mobile', 'Tablet', 'Other']
    channels = ['Direct', 'Organic Search', 'Paid Search', 'Social', 'Referral', 'Other']
    for wid, title, names in (
        ('device_changeplot', 'Device Close Rate Changeplot', devices),
        ('channel_changeplot', 'Channel Close Rate Changeplot', channels),
    ):
        charts = [
            _scatter_chart(sd(wid + '1'), 'Cart Creation Rate', 'Visits', 'Carts', names, 'percentage'),
            _scatter_chart(sd(wid + '2'), 'Cart Completion Rate', 'Carts', 'Orders', names, 'percentage'),
            _scatter_chart(sd(wid + '3'), 'Close Rate', 'Visits', 'Orders', names, 'percentage'),
        ]
        d.scatter_widget(wid, 'engage', title, charts)

    return {'cards': d.cards, 'charts': d.charts, 'history': d.history, 'scatter': d.scatter}


def build_expand_purchases(primary_code, compare_code):
    """Expand Purchases dashboard — area charts + KPI/history cards + a product
    category AOV changeplot (scatter)."""
    m = build_metrics(primary_code, compare_code)
    p, pct = m['primary'], m['pct']
    d = Deck(m['labels'], primary_label(primary_code), compare_label(primary_code, compare_code))
    E = d.eq

    def sd(key):
        return _seed(primary_code, compare_code, 'exp', key)

    def s2(series, seed):
        rnd = random.Random(seed)
        return [round(v * (0.86 + rnd.random() * 0.2), 4) for v in series]

    unique_skus = 2.3
    cherry_pick = 28.0
    single_sku_orders = p['orders'] * cherry_pick / 100.0

    s_aov = m['daily']['expandAvgOrderValue']
    s_upo = m['daily']['expandUnitsPerOrderValue']
    s_aup = m['daily']['expandAvgUnitPrice']
    s_units = m['daily']['itemPurchaseQuantity']

    # SECTION 1 -----------------------------------------------------------
    d.card('expand_aov', 'expand', 'EXPAND', 'AVERAGE ORDER VALUE',
           kpi_val=p['aov'], kpi_kind='currency', delta=pct['aov'],
           equation=[E(p['sales'], 'currency', 'Sales  /'), E(p['orders'], 'integer', 'Orders  =')],
           result=E(p['aov'], 'currency', 'AOV'),
           s1=s_aov, s2=s2(s_aov, sd('aov2')), two_sets=True, fmt_kind='currency', chart_height=150)
    d.card('inspire', 'expand', 'INSPIRE', 'UNITS PER ORDER',
           kpi_val=p['units_per_order'], kpi_kind='normal', delta=pct['units_per_order'],
           equation=[E(p['units'], 'integer', 'units  /'), E(p['orders'], 'integer', 'orders')],
           s1=s_upo, fmt_kind='normal')
    d.card('enhance', 'expand', 'ENHANCE', 'AVERAGE UNIT PRICE',
           kpi_val=p['avg_unit_price'], kpi_kind='currency', delta=pct['avg_unit_price'],
           equation=[E(p['sales'], 'currency', 'Sales  /'), E(p['units'], 'integer', 'units')],
           s1=s_aup, fmt_kind='currency')

    # SECTION 2 -----------------------------------------------------------
    d.card('inspire_big', 'expand', 'INSPIRE', 'UNITS PER ORDER',
           kpi_val=p['units_per_order'], kpi_kind='normal', delta=pct['units_per_order'],
           equation=[E(p['units'], 'integer', 'Units  /'), E(p['orders'], 'integer', 'Orders  =')],
           result=E(p['units_per_order'], 'normal', 'Units per Order'),
           s1=s_upo, s2=s2(s_upo, sd('upo2')), two_sets=True, fmt_kind='normal', chart_height=150)
    d.card('total_units', 'expand', '', 'TOTAL UNITS ORDERED (QUANTITY)',
           kpi_val=p['units'], kpi_kind='integer', delta=_dummy_delta(sd('tud')),
           equation=[E(p['orders'], 'integer', 'Orders  ×'),
                     E(p['units_per_order'], 'normal', 'Units per Order  =')],
           result=E(p['units'], 'integer', 'Units Ordered'),
           s1=s_units, s2=s2(s_units, sd('units2')), two_sets=True, fmt_kind='normal', chart_height=150)
    d.history_card('unique_skus', 'expand', 'UNIQUE SKUS PER ORDER', unique_skus, 'normal',
                   _dummy_delta(sd('usk')), _weeks(unique_skus, 'normal', sd('uskw')))
    d.history_card('cherry_pick', 'expand', 'CHERRY PICK RATE', cherry_pick, 'percentage',
                   _dummy_delta(sd('chp')), _weeks(cherry_pick, 'percentage', sd('chpw')),
                   reversed_color=True,
                   equation=[E(single_sku_orders, 'integer', 'single-SKU orders  /'),
                             E(p['orders'], 'integer', 'orders')])

    # SECTION 3 -----------------------------------------------------------
    d.card('enhance_big', 'expand', 'ENHANCE', 'AVERAGE UNIT PRICE',
           kpi_val=p['avg_unit_price'], kpi_kind='currency', delta=pct['avg_unit_price'],
           equation=[E(p['sales'], 'currency', 'Sales  /'), E(p['units'], 'integer', 'Units  =')],
           result=E(p['avg_unit_price'], 'currency', 'Avg Unit Price'),
           s1=s_aup, s2=s2(s_aup, sd('aup2')), two_sets=True, fmt_kind='currency', chart_height=150)

    # SECTION 4 — product category changeplot ----------------------------
    cats = ['Mattresses', 'Bedding', 'Furniture', 'Pillows', 'Frames', 'Accessories']
    charts = [
        _scatter_chart(sd('cat1'), 'Units per Order', 'Orders', 'Units', cats, 'normal'),
        _scatter_chart(sd('cat2'), 'Avg Unit Price', 'Units', 'Sales', cats, 'currency'),
        _scatter_chart(sd('cat3'), 'AOV', 'Orders', 'Sales', cats, 'currency'),
    ]
    d.scatter_widget('category_changeplot', 'expand', 'Product Category AOV Changeplot', charts)

    return {'cards': d.cards, 'charts': d.charts, 'history': d.history, 'scatter': d.scatter}
