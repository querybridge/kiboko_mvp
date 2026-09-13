"""Read the GA4DailyRollup cache in the same per-day, merged-across-properties
shapes the live BigQuery fetch functions emit, so Premium providers can swap the
source transparently. Gated by settings.GA4_USE_ROLLUP + a coverage check that
guarantees the requested range sits inside synced data (so a missing day is a
genuine zero, never an un-synced gap)."""
from django.conf import settings
from django.db.models import Min, Max

from business_unit.models import GA4DailyRollup

_FUND = GA4DailyRollup.FUND_KEYS


def _key(d):
    return d.strftime('%Y%m%d')


def covers(company, property_ids, start, end):
    """True if the cache brackets [start, end] for EVERY property (safe to read)."""
    if not getattr(settings, 'GA4_USE_ROLLUP', True) or not property_ids:
        return False
    for pid in property_ids:
        agg = GA4DailyRollup.objects.filter(company=company, property_id=pid).aggregate(
            lo=Min('date'), hi=Max('date'))
        if agg['lo'] is None or agg['lo'] > start or agg['hi'] < end:
            return False
    return True


def _rows(company, property_ids, start, end):
    return GA4DailyRollup.objects.filter(
        company=company, property_id__in=property_ids, date__gte=start, date__lte=end)


def fundamentals(company, property_ids, start, end):
    out = {}
    for r in _rows(company, property_ids, start, end):
        acc = out.setdefault(_key(r.date), {k: 0.0 for k in _FUND})
        for k in _FUND:
            acc[k] += getattr(r, k)
    return out


def totals(company, property_ids, start, end):
    out = {}
    for r in _rows(company, property_ids, start, end):
        acc = out.setdefault(_key(r.date), {})
        for k, v in (r.totals or {}).items():
            acc[k] = acc.get(k, 0.0) + float(v or 0)
    return out


def split_daily(company, property_ids, start, end, split):
    out = {}
    for r in _rows(company, property_ids, start, end):
        bmap = (r.device if split == 'device' else r.channel) or {}
        day = out.setdefault(_key(r.date), {})
        for bucket, rec in bmap.items():
            acc = day.setdefault(bucket, {k: 0.0 for k in _FUND})
            for k in _FUND:
                acc[k] += float(rec.get(k, 0) or 0)
    return out


def order_item(company, property_ids, start, end):
    out = {}
    for r in _rows(company, property_ids, start, end):
        day = out.setdefault(_key(r.date), {'orders': 0.0, '_w': 0.0, 'single_sku_orders': 0.0})
        day['orders'] += r.item_orders
        day['_w'] += r.unique_skus_weighted
        day['single_sku_orders'] += r.single_sku_orders
    for v in out.values():
        v['unique_skus_per_order'] = (v['_w'] / v['orders']) if v['orders'] else 0.0
        del v['_w']
    return out


def category(company, property_ids, start, end):
    out = {}
    for r in _rows(company, property_ids, start, end):
        day = out.setdefault(_key(r.date), {})
        for cat, rec in (r.categories or {}).items():
            acc = day.setdefault(cat, {'orders': 0.0, 'units': 0.0, 'sales': 0.0})
            for k in ('orders', 'units', 'sales'):
                acc[k] += float(rec.get(k, 0) or 0)
    return out
