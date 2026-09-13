"""Populate GA4DailyRollup from each Premium company's GA4 -> BigQuery export, so
dashboards + the value pipeline read cached daily rows instead of scanning
events_* live. Idempotent (update_or_create per company/property/day).

Usage:
  python manage.py sync_ga4_rollups                     # incremental (all Premium cos)
  python manage.py sync_ga4_rollups --backfill          # ~400-day one-time backfill
  python manage.py sync_ga4_rollups --company autocado --since 2025-08-10 --until 2025-08-16
"""
import datetime

from django.core.management.base import BaseCommand
from django.db.models import Max

from business_unit.models import BigQueryConnection, BusinessUnit, GA4DailyRollup
from app.integrations import bigquery as bqmod

FUND_KEYS = GA4DailyRollup.FUND_KEYS


def _parse(s):
    return datetime.date.fromisoformat(s) if s else None


class Command(BaseCommand):
    help = 'Sync GA4 daily rollups for Premium companies from BigQuery.'

    def add_arguments(self, parser):
        parser.add_argument('--company', help='Limit to one company slug.')
        parser.add_argument('--backfill', action='store_true',
                            help='Backfill ~--backfill-days back from the latest export day.')
        parser.add_argument('--backfill-days', type=int, default=400)
        parser.add_argument('--trailing-days', type=int, default=3,
                            help='On incremental runs, also re-sync the last N days (late data).')
        parser.add_argument('--since', help='YYYY-MM-DD override start.')
        parser.add_argument('--until', help='YYYY-MM-DD override end.')

    def handle(self, *args, **o):
        conns = BigQueryConnection.objects.exclude(service_account_json={})
        if o['company']:
            conns = conns.filter(company__slug=o['company'])
        if not conns:
            self.stdout.write('No Premium companies to sync.')
            return

        since, until = _parse(o['since']), _parse(o['until'])
        for bq in conns:
            company = bq.company
            events = bq.event_map
            try:
                client = bqmod.connect(bq.service_account_json)
            except Exception as e:
                self.stderr.write(f'{company}: connect failed ({type(e).__name__}: {e})')
                continue
            pids = list(BusinessUnit.objects.filter(company=company)
                        .exclude(ga4_property_id='').values_list('ga4_property_id', flat=True))
            for pid in pids:
                ds = bqmod.dataset_for(pid)
                if not ds:
                    continue
                try:
                    latest = bqmod.latest_daily_date(client, ds)
                except Exception as e:
                    self.stderr.write(f'  {pid}: latest-date failed ({type(e).__name__}: {e})')
                    continue
                if latest is None:
                    self.stdout.write(f'  {pid}: no export tables, skipped')
                    continue

                start, end = self._window(company, pid, latest, since, until, o)
                if start is None or start > end:
                    self.stdout.write(f'  {pid}: up to date (through {latest})')
                    continue

                n = self._sync_range(client, ds, events, company, pid, start, end)
                self.stdout.write(self.style.SUCCESS(
                    f'  {pid}: synced {n} day(s) {start}..{end}'))
            if bq.data_through != latest:
                bq.data_through = latest
                bq.save(update_fields=['data_through'])
        self.stdout.write(self.style.SUCCESS('sync_ga4_rollups complete.'))

    def _window(self, company, pid, latest, since, until, o):
        if since or until:
            return (since or latest - datetime.timedelta(days=o['backfill_days']),
                    until or latest)
        if o['backfill']:
            return latest - datetime.timedelta(days=o['backfill_days']), latest
        last = GA4DailyRollup.objects.filter(company=company, property_id=pid).aggregate(
            m=Max('date'))['m']
        if last is None:  # first run -> backfill
            return latest - datetime.timedelta(days=o['backfill_days']), latest
        return last - datetime.timedelta(days=o['trailing_days'] - 1), latest

    def _sync_range(self, client, ds, events, company, pid, start, end):
        fund = bqmod.fetch_daily_fundamentals(client, ds, start, end, events)
        tot = bqmod.fetch_daily_totals(client, ds, start, end, events)
        dev = bqmod.fetch_split_daily(client, ds, start, end, 'device', events)
        chan = bqmod.fetch_split_daily(client, ds, start, end, 'channel', events)
        oi = bqmod.fetch_daily_order_item(client, ds, start, end, events)
        cat = bqmod.fetch_daily_category(client, ds, start, end, events)

        days = set(fund) | set(tot) | set(dev) | set(chan) | set(oi) | set(cat)
        for day in days:
            d = datetime.date(int(day[:4]), int(day[4:6]), int(day[6:8]))
            f = fund.get(day, {})
            o = oi.get(day, {})
            GA4DailyRollup.objects.update_or_create(
                company=company, property_id=pid, date=d,
                defaults={
                    **{k: float(f.get(k, 0) or 0) for k in FUND_KEYS},
                    'totals': tot.get(day, {}),
                    'device': dev.get(day, {}),
                    'channel': chan.get(day, {}),
                    'categories': cat.get(day, {}),
                    'item_orders': o.get('orders', 0.0),
                    'unique_skus_weighted': o.get('unique_skus_per_order', 0.0) * o.get('orders', 0.0),
                    'single_sku_orders': o.get('single_sku_orders', 0.0),
                })
        return len(days)
