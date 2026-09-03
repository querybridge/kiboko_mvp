"""
Performance Storyboard — ported from the reference kiboko app.

Recreates the funnel "story" table (ATTRACT -> INTEREST -> CONVINCE -> ENGAGE
-> INSPIRE -> ENHANCE -> EXPAND -> GROW) with three data columns:
  Current Period | % TO PRV | COMPARED TO PRV (a dynamic narrative sentence).

The COMPARED TO PRV sentence is the heart of the feature: for each metric a
qualitative phrase is chosen by a +/-2% threshold (positive / neutral /
negative) and, for dependent metrics, prefixed with a connector word
("and" / "but" / "however," ...) picked from the *previous* metric's direction —
so the column reads as a running narrative. Total Sales interpolates the actual
percent. Numbers here are illustrative dummy data driven by the shared period /
comparison-period filter.
"""
import random

from app.analytics_data import (
    _seed, PRIMARY_OPTIONS, COMPARE_OPTIONS, DEFAULT_PRIMARY,
    primary_label, compare_label, default_compare,
)

POS, NEG, NEU = 'pos', 'neg', 'neu'

# Section -> analytics group color (attract=teal, engage=gold, expand=green)
SECTION_GROUP = {
    'ATTRACT': 'attract',
    'INTEREST': 'engage',
    'CONVINCE': 'engage',
    'ENGAGE': 'engage',
    'INSPIRE': 'expand',
    'ENHANCE': 'expand',
    'EXPAND': 'expand',
    'GROW': 'grow',
}


# --- Metric definitions (order matters: the narrative chains down the list) ---
# fields: key, section, label, fmt, detail(only shown in DETAIL), bold, rev
#         (color-reversed), dep (dependency metric key), add/con connectors,
#         pos/neg/neu phrases.
def _m(key, section, label, fmt, pos, neg, neu, *, detail=False, bold=False,
       rev=False, dep=None, add='and', con='but'):
    return dict(key=key, section=section, label=label, fmt=fmt, detail=detail,
                bold=bold, rev=rev, dep=dep, add=add, con=con,
                pos=pos, neg=neg, neu=neu)


METRICS = [
    # ATTRACT
    _m('visitors', 'ATTRACT', 'Visitors', 'integer',
       'more people came to the site',
       'fewer people came to the site',
       'a similar number of people came to the site'),
    _m('new_visitor_visit', 'ATTRACT', 'New Visitor Visits', 'integer',
       'a higher portion were new',
       'a lower portion were new',
       'a similar portion were new', detail=True),
    _m('returning_visitor_visit', 'ATTRACT', 'Returning Visitor Visits', 'integer',
       'a higher portion were returning',
       'a lower portion were returning',
       'a similar portion were returning', detail=True),
    _m('visits_per_visitor', 'ATTRACT', 'Visits/Visitor', 'decimal',
       'they visited more times per person',
       'they visited fewer times per person',
       'they visited a similar number of times per person'),
    _m('visits', 'ATTRACT', 'Visits', 'integer',
       'there were more total visits to the site',
       'there were fewer total visits to the site',
       'there were similar total visits to the site', bold=True, dep='visits_per_visitor'),

    # INTEREST
    _m('bounce_rate', 'INTEREST', 'Bounce Rate', 'percentage',
       'a higher portion left immediately',
       'a lower portion left immediately',
       'a similar portion left immediately', detail=True, rev=True),
    _m('unbounced_visits', 'INTEREST', 'Unbounced Visits', 'integer',
       'there were more potentially productive visits',
       'there were fewer potentially productive visits',
       'there were a similar number of productive visits',
       detail=True, dep='bounce_rate', add='but', con='and'),
    _m('visit_duration', 'INTEREST', 'Visit Duration', 'duration',
       'visits lasted longer on average',
       'visits lasted shorter on average',
       'visits lasted a similar time on average', detail=True),
    _m('pages_per_visit', 'INTEREST', 'Pages/Visit', 'decimal',
       'viewed more pages each',
       'viewed fewer pages each',
       'viewed a similar number of pages each', detail=True, dep='visit_duration'),
    _m('category_pv_per_visit', 'INTEREST', 'Category Page Views / Visit', 'decimal',
       'category pages were viewed more often',
       'category pages were viewed less often',
       'category pages were viewed similarly often', detail=True),
    _m('pdp_per_visit', 'INTEREST', 'PDP Views / Visit', 'decimal',
       'product Detail Pages were viewed more often',
       'product Detail Pages were viewed less often',
       'product Detail Pages were viewed similar often',
       detail=True, dep='category_pv_per_visit'),
    _m('cart_to_detail', 'INTEREST', 'Carts per PDP View', 'percentage',
       'PDP views resulted in more carts each',
       'PDP views resulted in fewer carts each',
       'PDP views resulted in similar carts each', detail=True, dep='pdp_per_visit'),
    _m('cart_creation_rate', 'INTEREST', 'Cart Creation Rate', 'percentage',
       'a higher portion of all visits created carts',
       'a lower portion of all visits created carts',
       'a similar portion of all visits created carts'),
    _m('unbounced_cart_creation_rate', 'INTEREST', 'Unbounced Cart Creation Rate', 'percentage',
       'a higher portion of unbounced visits created carts',
       'a lower portion of unbounced visits created carts',
       'a similar portion of unbounced visits created carts',
       detail=True, dep='cart_creation_rate', add='likewise,', con='however,'),
    _m('carts_created', 'INTEREST', 'Carts Created', 'integer',
       'there were more total carts created',
       'there were fewer total carts created',
       'there were a similar number of carts created',
       detail=True, dep='unbounced_cart_creation_rate'),

    # CONVINCE
    _m('cart_views', 'CONVINCE', 'Cart Views', 'integer',
       'carts were viewed more times in total',
       'carts were viewed fewer times in total',
       'carts were viewed a similar number of times in total', detail=True),
    _m('checkout_views', 'CONVINCE', 'Checkout Views', 'integer',
       'checkout pages were viewed more times in total',
       'checkout pages were viewed fewer times in total',
       'checkout pages were viewed a similar number of times in total', detail=True),
    _m('billing_shipping_views', 'CONVINCE', 'Billing/Shipping Views', 'integer',
       'billing/shipping pages were viewed more times in total',
       'billing/shipping pages were viewed fewer times in total',
       'billing/Shipping pages were viewed a similar number of times in total', detail=True),
    _m('cart_completion_rate', 'CONVINCE', 'Cart Completion Rate', 'percentage',
       'a higher portion of all carts became completed orders',
       'a lower portion of all carts became completed orders',
       'a similar portion of all carts became completed orders'),
    _m('carts_completed', 'CONVINCE', 'Carts Completed', 'integer',
       'there were more total orders completed',
       'there were fewer total orders completed',
       'there were a similar number of total orders completed',
       detail=True, dep='cart_completion_rate'),

    # ENGAGE
    _m('close_rate', 'ENGAGE', 'Close Rate', 'percentage',
       'combined, a higher portion of all visits completed orders',
       'combined, a lower portion of all visits completed orders',
       'combined, a similar portion of all visits completed orders', bold=True),
    _m('unbounced_close_rate', 'ENGAGE', 'Unbounced Close Rate', 'percentage',
       'a higher portion of unbounced visits completed orders',
       'a lower portion of unbounced visits completed orders',
       'a similar portion of unbounced visits completed orders',
       detail=True, dep='close_rate', add='likewise,', con='however,'),

    # INSPIRE
    _m('cherry_pick_rate', 'INSPIRE', 'Cherry-Pick Rate', 'percentage',
       'a higher portion of orders had only 1 SKU',
       'a lower portion of orders had only 1 SKU',
       'a similar portion of orders had only 1 SKU', detail=True),
    _m('units_per_order', 'INSPIRE', 'Units per Order', 'decimal',
       'orders on average had more units each',
       'orders on average had fewer units each',
       'orders on average had a similar number of units each'),
    _m('ordered_quantity', 'INSPIRE', 'Ordered Quantity', 'integer',
       'there were more total units ordered',
       'there were fewer total units ordered',
       'there were a similar number of total units ordered',
       detail=True, dep='units_per_order', add='and', con='though'),

    # ENHANCE
    _m('avg_unit_price', 'ENHANCE', 'Avg Unit Price', 'currency',
       'units sold were on average higher priced',
       'units sold were on average lower priced',
       'units sold were on average similarly priced'),

    # EXPAND
    _m('avg_order_value', 'EXPAND', 'Avg Order Value', 'currency',
       'overall, the average value of each order was higher',
       'overall, the average value of each order was lower',
       'overall, the average value of each order was similar', bold=True),
]

# Total Sales (GROW tail) interpolates the actual percent (sign fixed to abs).
TOTAL_SALES_MSG = {
    POS: 'Total Sales increased by %0.1f%%',
    NEG: 'Total Sales decreased by %0.1f%%',
    NEU: 'Total Sales similar by %0.1f%%',
}


# --------------------------------------------------------------------------
# Dummy fundamentals + metric derivation
# --------------------------------------------------------------------------

def _fundamentals(seed):
    rnd = random.Random(seed)
    visitors = 40000 + (seed % 20000)
    sessions = visitors * (1.2 + rnd.random() * 0.4)
    engaged = sessions * (0.55 + rnd.random() * 0.20)
    total_visit_time = sessions * (120 + rnd.random() * 150)   # seconds
    page_views = sessions * (3 + rnd.random() * 4)
    category_pv = sessions * (1.4 + rnd.random() * 1.4)
    pdp_pv = sessions * (2 + rnd.random() * 2)
    add_to_cart = sessions * (0.12 + rnd.random() * 0.08)
    cart_views = add_to_cart * (1.2 + rnd.random() * 0.6)
    checkout_views = add_to_cart * (0.5 + rnd.random() * 0.3)
    billing_shipping_views = checkout_views * (0.7 + rnd.random() * 0.2)
    checkouts = add_to_cart * (0.30 + rnd.random() * 0.15)
    single_sku = checkouts * (0.25 + rnd.random() * 0.20)
    item_qty = checkouts * (1.5 + rnd.random() * 0.8)
    revenue = checkouts * (80 + rnd.random() * 50)
    new_users = visitors * (0.55 + rnd.random() * 0.20)
    return dict(visitors=visitors, new_users=new_users, sessions=sessions,
                engaged=engaged, total_visit_time=total_visit_time,
                page_views=page_views, category_pv=category_pv, pdp_pv=pdp_pv,
                add_to_cart=add_to_cart, cart_views=cart_views,
                checkout_views=checkout_views,
                billing_shipping_views=billing_shipping_views,
                checkouts=checkouts, single_sku=single_sku, item_qty=item_qty,
                revenue=revenue)


def _perturb(prim, seed, spread=0.14):
    """Prior-period fundamentals: primary jittered per-field for realistic deltas."""
    rnd = random.Random(seed)
    return {k: v * (1 + (rnd.random() * 2 - 1) * spread) for k, v in prim.items()}


def _derive(f):
    """Return {metric_key: (value, delta_basis)} from fundamentals f."""
    v, e, tt, vis, nu = f['sessions'], f['engaged'], f['total_visit_time'], f['visitors'], f['new_users']
    atc, ck, iq, rev = f['add_to_cart'], f['checkouts'], f['item_qty'], f['revenue']

    def sd(a, b):
        return a / b if b else 0

    return {
        'visitors': (vis, vis),
        'new_visitor_visit': (nu, nu),
        'returning_visitor_visit': (vis - nu, vis - nu),
        'visits_per_visitor': (sd(v, vis), sd(v, vis)),
        'visits': (v, v),
        'bounce_rate': (sd(v - e, v) * 100, e),                 # delta on engaged (proxy)
        'unbounced_visits': (e, e),
        'visit_duration': (sd(tt, v), tt),                      # delta on total time (proxy)
        'pages_per_visit': (sd(f['page_views'], v), sd(f['page_views'], v)),
        'category_pv_per_visit': (sd(f['category_pv'], v), sd(f['category_pv'], v)),
        'pdp_per_visit': (sd(f['pdp_pv'], v), sd(f['pdp_pv'], v)),
        'cart_to_detail': (sd(atc, f['pdp_pv']) * 100, sd(atc, f['pdp_pv']) * 100),
        'cart_creation_rate': (sd(atc, v) * 100, sd(atc, v) * 100),
        'unbounced_cart_creation_rate': (sd(atc, e) * 100, sd(atc, e) * 100),
        'carts_created': (atc, atc),
        'cart_views': (f['cart_views'], f['cart_views']),
        'checkout_views': (f['checkout_views'], f['checkout_views']),
        'billing_shipping_views': (f['billing_shipping_views'], f['billing_shipping_views']),
        'cart_completion_rate': (sd(ck, atc) * 100, sd(ck, atc) * 100),
        'carts_completed': (ck, ck),
        'close_rate': (sd(ck, v) * 100, sd(ck, v) * 100),
        'unbounced_close_rate': (sd(ck, e) * 100, sd(ck, e) * 100),
        'cherry_pick_rate': (sd(f['single_sku'], ck) * 100, sd(f['single_sku'], ck) * 100),
        'units_per_order': (sd(iq, ck), sd(iq, ck)),
        'ordered_quantity': (iq, iq),
        'avg_unit_price': (sd(rev, iq), sd(rev, iq)),
        'avg_order_value': (sd(rev, ck), sd(rev, ck)),
        'total_sales': (rev, rev),
    }


# --------------------------------------------------------------------------
# Formatting + message helpers
# --------------------------------------------------------------------------

def _fmt(v, kind):
    if kind == 'integer':
        return f'{round(v):,}'
    if kind == 'decimal':
        return f'{v:.2f}'
    if kind == 'percentage':
        return f'{v:.2f}%'
    if kind == 'currency':
        return f'${v:.2f}'
    if kind == 'currency0':
        return f'${round(v):,}'
    if kind == 'duration':
        s = int(round(v))
        return f'{s // 60}:{s % 60:02d}'
    return f'{v:.2f}'


def _fmt_pct(v):
    v = round(v, 1)
    if abs(v) < 0.05:
        return '0%'
    if v < 0:
        return f'({abs(v):.1f}%)'
    return f'{v:.1f}%'


def _pct_color(v, rev=False):
    good, bad = v >= 2, v <= -2
    if rev:
        good, bad = bad, good
    return 'ps-up' if good else ('ps-down' if bad else 'ps-flat')


def _pct_change(p, s):
    if (p - s) == 0:
        return 0.0
    return ((p - s) / s * 100) if s else 0.0


def _state(delta):
    if -2 <= delta <= 2:
        return NEU
    return POS if delta > 2 else NEG


def _connector(state, dep_state, add, con):
    # same direction, or either side neutral -> ADDITION; opposite -> CONTRAST
    if state == dep_state or state == NEU or dep_state == NEU:
        return add
    return con


def _capitalize(s):
    return (s[0].upper() + s[1:]) if s else s


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def build_performance_story(primary_code, compare_code):
    seed_p = _seed(primary_code, 'ps-primary')
    seed_s = _seed(primary_code, compare_code, 'ps-secondary')
    prim_f = _fundamentals(seed_p)
    sec_f = _perturb(prim_f, seed_s)

    prim = _derive(prim_f)
    sec = _derive(sec_f)

    # deltas + states for every metric (needed before message chaining)
    delta = {k: _pct_change(prim[k][1], sec[k][1]) for k in prim}
    state = {k: _state(delta[k]) for k in prim}

    # New / Returning visitor visits: state = which portion grew faster
    nd, rd = delta['new_visitor_visit'], delta['returning_visitor_visit']
    state['new_visitor_visit'] = POS if nd > rd else (NEG if nd < rd else NEU)
    state['returning_visitor_visit'] = POS if rd > nd else (NEG if rd < nd else NEU)

    # assemble rows grouped by section
    sections = []
    cur_section = None
    for meta in METRICS:
        k = meta['key']
        st = state[k]
        connector = ''
        if meta['dep']:
            connector = _connector(st, state[meta['dep']], meta['add'], meta['con'])
        phrase = meta[st]
        message = _capitalize(f'{connector} {phrase}' if connector else phrase)

        row = {
            'label': meta['label'],
            'value': _fmt(prim[k][0], meta['fmt']),
            'pct': _fmt_pct(delta[k]),
            'pct_color': _pct_color(delta[k], meta['rev']),
            'message': message,
            'detail_only': meta['detail'],
            'bold': meta['bold'],
        }
        if meta['section'] != cur_section:
            cur_section = meta['section']
            sections.append({'name': cur_section, 'group': SECTION_GROUP[cur_section], 'rows': []})
        sections[-1]['rows'].append(row)

    # GROW tail — Total Sales (interpolates the actual percent)
    ts_delta = delta['total_sales']
    ts_state = state['total_sales']
    tail = {
        'name': 'GROW',
        'group': 'grow',
        'label': 'Total Sales',
        'value': _fmt(prim['total_sales'][0], 'currency0'),
        'pct': _fmt_pct(ts_delta),
        'pct_color': _pct_color(ts_delta),
        'message': TOTAL_SALES_MSG[ts_state] % abs(ts_delta),
    }

    return {'sections': sections, 'tail': tail}
