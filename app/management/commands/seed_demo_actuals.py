"""
Idempotently fill DailyActual gaps with realistic demo data.

By default, seeds every day from the day AFTER the latest existing actual through
today (per vertical). Pass --start / --end to override the range, --force to
overwrite existing rows, or --year to reseed an entire year.

Revenue is derived from MonthlyGoal at ~97% achievement with day-of-week
weighting and ±8% noise. visits and orders are derived from year-specific
AOV/close-rate profiles so YoY uplift looks realistic.
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from app.models import DailyActual, MonthlyGoal
from business_unit.models import Vertical


DOW_MULT = {0: 1.05, 1: 1.10, 2: 1.10, 3: 1.05, 4: 0.95, 5: 0.85, 6: 0.90}
ACHIEVEMENT = Decimal('0.97')

# Per-year AOV / close-rate profiles for visits + orders backfill
YEAR_PROFILES = {
    2024: {'aov_mean': 440, 'aov_jitter': 35, 'close_rate_mean': 0.0140, 'close_rate_jitter': 0.0025},
    2025: {'aov_mean': 460, 'aov_jitter': 35, 'close_rate_mean': 0.0148, 'close_rate_jitter': 0.0025},
    2026: {'aov_mean': 478, 'aov_jitter': 35, 'close_rate_mean': 0.0156, 'close_rate_jitter': 0.0025},
}
DEFAULT_PROFILE = {'aov_mean': 470, 'aov_jitter': 35, 'close_rate_mean': 0.0150, 'close_rate_jitter': 0.0025}


def _parse_date(s):
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise CommandError(f'Invalid date "{s}" — use YYYY-MM-DD.') from e


def _derive_visits_orders(rng, revenue, year):
    profile = YEAR_PROFILES.get(year, DEFAULT_PROFILE)
    aov = max(50.0, rng.gauss(profile['aov_mean'], profile['aov_jitter']))
    close_rate = max(0.002, rng.gauss(profile['close_rate_mean'], profile['close_rate_jitter']))
    rev = float(revenue or 0)
    orders = max(0, int(round(rev / aov))) if rev > 0 else 0
    visits = max(orders, int(round(orders / close_rate))) if orders > 0 else 0
    return visits, orders


class Command(BaseCommand):
    help = (
        'Seed DailyActual revenue/visits/orders to fill the gap from the latest '
        'existing actual through today. Idempotent unless --force is set.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--start', help='Start date YYYY-MM-DD (default: day after latest actual per vertical)')
        parser.add_argument('--end', help='End date YYYY-MM-DD (default: today)')
        parser.add_argument('--year', type=int, help='Shorthand to seed an entire year (overrides --start/--end)')
        parser.add_argument('--force', action='store_true', help='Overwrite existing rows in range')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility (default: 42)')

    def handle(self, *args, **options):
        verticals = list(Vertical.objects.all())
        if not verticals:
            raise CommandError('No verticals found. Run seed_revenue first.')

        rng = random.Random(options['seed'])

        if options['year']:
            year = options['year']
            start_override = date(year, 1, 1)
            end_override = date(year, 12, 31)
        else:
            start_override = _parse_date(options['start']) if options['start'] else None
            end_override = _parse_date(options['end']) if options['end'] else date.today()

        force = options['force']
        total_created = total_updated = total_skipped = 0

        for vertical in verticals:
            if start_override is None:
                latest = DailyActual.objects.filter(vertical=vertical).aggregate(m=Max('date'))['m']
                start = latest + timedelta(days=1) if latest else date(date.today().year, 1, 1)
            else:
                start = start_override
            end = end_override

            if start > end:
                self.stdout.write(f'  {vertical.name}: already current (latest >= {end}); skipping')
                continue

            # Cache monthly budgets by month for this vertical
            budgets = {}
            for g in MonthlyGoal.objects.filter(vertical=vertical, month__gte=date(start.year, 1, 1), month__lte=date(end.year, 12, 31)):
                budgets[(g.month.year, g.month.month)] = Decimal(g.budget)

            created = updated = skipped = 0
            d = start
            while d <= end:
                budget = budgets.get((d.year, d.month), Decimal('0'))
                if budget <= 0:
                    d += timedelta(days=1)
                    continue

                days_in_month = calendar.monthrange(d.year, d.month)[1]
                weights = [DOW_MULT[date(d.year, d.month, i).weekday()] for i in range(1, days_in_month + 1)]
                avg_w = sum(weights) / len(weights)
                base = budget * ACHIEVEMENT / Decimal(days_in_month)
                dow_adj = Decimal(str(DOW_MULT[d.weekday()] / avg_w))
                noise = Decimal(str(rng.uniform(0.92, 1.08)))
                revenue = (base * dow_adj * noise).quantize(Decimal('0.01'))
                visits, orders = _derive_visits_orders(rng, revenue, d.year)

                existing = DailyActual.objects.filter(date=d, vertical=vertical).first()
                if existing and not force:
                    # Backfill visits/orders if missing, leave revenue
                    if (existing.visits or 0) == 0 and (existing.orders or 0) == 0:
                        existing.visits = visits
                        existing.orders = orders
                        existing.save(update_fields=['visits', 'orders'])
                        updated += 1
                    else:
                        skipped += 1
                else:
                    DailyActual.objects.update_or_create(
                        date=d, vertical=vertical,
                        defaults={'revenue': revenue, 'visits': visits, 'orders': orders},
                    )
                    if existing:
                        updated += 1
                    else:
                        created += 1

                d += timedelta(days=1)

            self.stdout.write(
                f'  {vertical.name}: {created} created, {updated} updated, {skipped} unchanged '
                f'({start} → {end})'
            )
            total_created += created
            total_updated += updated
            total_skipped += skipped

        self.stdout.write(self.style.SUCCESS(
            f'Done. {total_created} created, {total_updated} updated, {total_skipped} unchanged.'
        ))
