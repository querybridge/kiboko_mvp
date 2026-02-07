"""
Seed DailyActual and MonthlyGoal with realistic retail revenue data.

Coverage:
  - DailyActual: 2024-01-01 → 2026-03-13
  - MonthlyGoal (budget): 2026 only, totalling $130 M

Assumptions – retail e-commerce seasonality:
  Monthly weight index (% of annual revenue):
    Jan  6.5   Feb  5.5   Mar  6.5   Apr  7.0
    May  7.5   Jun  7.5   Jul  7.0   Aug  7.5
    Sep  8.0   Oct  8.5   Nov 12.0   Dec 16.5
  Within each month, day-of-week multipliers:
    Mon 0.90  Tue 0.95  Wed 1.00  Thu 1.00  Fri 1.10  Sat 1.05  Sun 1.00
  Special-day uplifts (applied on top):
    Black Friday week (Mon-Sun of BF week): 2.0×-3.5× (BF itself 3.5×)
    Cyber Monday: 3.2×
    Dec 15-23 (pre-Christmas rush): 1.6×
    Valentine's week (Feb 7-14): 1.3×
    Mother's Day week: 1.25×
    Prime Day window (Jul 15-16): 1.5×
    Labor Day weekend (Sat-Mon): 1.2×
    Presidents' Day weekend: 1.15×
    Memorial Day weekend: 1.2×
    Back-to-school (Aug 1-15): 1.15×

Annual totals used:
    2024: $115 M
    2025: $122 M
    2026: $130 M  (also the budget target)
"""
import random
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from app.models import DailyActual, MonthlyGoal
from business_unit.models import Vertical


# ---------- constants ----------

ANNUAL_TOTALS = {
    2024: 115_000_000,
    2025: 122_000_000,
    2026: 130_000_000,
}

MONTHLY_WEIGHT = {
    1: 6.5,  2: 5.5,  3: 6.5,   4: 7.0,
    5: 7.5,  6: 7.5,  7: 7.0,   8: 7.5,
    9: 8.0, 10: 8.5, 11: 12.0, 12: 16.5,
}
_mw_sum = sum(MONTHLY_WEIGHT.values())
MONTHLY_PCT = {m: w / _mw_sum for m, w in MONTHLY_WEIGHT.items()}

DOW_MULT = {
    0: 0.90,  # Mon
    1: 0.95,  # Tue
    2: 1.00,  # Wed
    3: 1.00,  # Thu
    4: 1.10,  # Fri
    5: 1.05,  # Sat
    6: 1.00,  # Sun
}


def _thanksgiving(year):
    """4th Thursday of November."""
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(weeks=3)


def _mothers_day(year):
    """2nd Sunday of May."""
    may1 = date(year, 5, 1)
    first_sun = may1 + timedelta(days=(6 - may1.weekday()) % 7)
    return first_sun + timedelta(weeks=1)


def _memorial_day(year):
    """Last Monday of May."""
    may31 = date(year, 5, 31)
    offset = (may31.weekday() - 0) % 7  # days back to Monday
    return may31 - timedelta(days=offset)


def _labor_day(year):
    """First Monday of September."""
    sep1 = date(year, 9, 1)
    offset = (0 - sep1.weekday()) % 7
    return sep1 + timedelta(days=offset)


def _presidents_day(year):
    """3rd Monday of February."""
    feb1 = date(year, 2, 1)
    first_mon = feb1 + timedelta(days=(0 - feb1.weekday()) % 7)
    return first_mon + timedelta(weeks=2)


def _special_day_mult(d):
    """Return an extra multiplier for holiday / promo days."""
    year = d.year

    # Black Friday week
    bf = _thanksgiving(year) + timedelta(days=1)  # Friday
    bf_week_start = bf - timedelta(days=4)  # Monday
    bf_week_end = bf + timedelta(days=2)    # Sunday
    if bf_week_start <= d <= bf_week_end:
        if d == bf:
            return 3.5
        if d == bf + timedelta(days=2):  # Cyber Monday is actually the Monday after
            pass  # handled below
        if d == bf - timedelta(days=1):  # Thanksgiving day — lower
            return 1.3
        return 2.0

    # Cyber Monday (Monday after Thanksgiving)
    cm = _thanksgiving(year) + timedelta(days=4)
    if d == cm:
        return 3.2

    # Pre-Christmas rush Dec 15-23
    if d.month == 12 and 15 <= d.day <= 23:
        return 1.6

    # Christmas Eve / Day — dip
    if d.month == 12 and d.day in (24, 25):
        return 0.5

    # Valentine's week Feb 7-14
    if d.month == 2 and 7 <= d.day <= 14:
        return 1.3

    # Mother's Day week
    md = _mothers_day(year)
    if md - timedelta(days=6) <= d <= md:
        return 1.25

    # Prime Day window Jul 15-16
    if d.month == 7 and d.day in (15, 16):
        return 1.5

    # Labor Day weekend (Sat-Mon)
    ld = _labor_day(year)
    if ld - timedelta(days=2) <= d <= ld:
        return 1.2

    # Presidents' Day weekend (Sat-Mon)
    pd = _presidents_day(year)
    if pd - timedelta(days=2) <= d <= pd:
        return 1.15

    # Memorial Day weekend (Sat-Mon)
    memd = _memorial_day(year)
    if memd - timedelta(days=2) <= d <= memd:
        return 1.2

    # Back-to-school Aug 1-15
    if d.month == 8 and 1 <= d.day <= 15:
        return 1.15

    # New Year's Day — slight dip
    if d.month == 1 and d.day == 1:
        return 0.7

    return 1.0


def _generate_daily(year, end_date, annual_total):
    """Return dict {date: revenue} for one year up to end_date."""
    first = date(year, 1, 1)
    last = min(date(year, 12, 31), end_date)
    year_end = date(year, 12, 31)

    # 1. Compute raw weights for the FULL year (so partial years prorate correctly)
    full_year_weight = 0.0
    d = first
    while d <= year_end:
        m_pct = MONTHLY_PCT[d.month]
        dow_m = DOW_MULT[d.weekday()]
        special = _special_day_mult(d)
        full_year_weight += m_pct * dow_m * special
        d += timedelta(days=1)

    # 2. Compute weights only for the days we need to output
    raw = {}
    d = first
    while d <= last:
        m_pct = MONTHLY_PCT[d.month]
        dow_m = DOW_MULT[d.weekday()]
        special = _special_day_mult(d)
        raw[d] = m_pct * dow_m * special
        d += timedelta(days=1)

    # 3. Scale to annual total using full-year denominator, add noise
    rng = random.Random(year * 1000 + 7)
    daily = {}
    for d, w in raw.items():
        base = annual_total * (w / full_year_weight)
        noise = rng.gauss(1.0, 0.04)  # +/- ~4 % daily noise
        daily[d] = max(0, round(base * noise, 2))

    return daily


VERTICAL_SPLITS = {
    'Lighting': Decimal('0.45'),
    'Patio': Decimal('0.35'),
    'Bailey Street Home': Decimal('0.20'),
}


class Command(BaseCommand):
    help = 'Seed DailyActual (2024-2026-03-13) and MonthlyGoal budget (2026, $250M), split by vertical.'

    def handle(self, *args, **options):
        # Ensure verticals exist
        verticals = {}
        for name in VERTICAL_SPLITS:
            vert, _ = Vertical.objects.get_or_create(name=name)
            verticals[name] = vert

        end_2026 = date(2026, 3, 13)

        # ---- Daily actuals ----
        total_rows = 0
        for year, annual in ANNUAL_TOTALS.items():
            end = end_2026 if year == 2026 else date(year, 12, 31)
            daily = _generate_daily(year, end, annual)
            objs = []
            for d, rev in daily.items():
                for vert_name, pct in VERTICAL_SPLITS.items():
                    vert_rev = Decimal(str(rev)) * pct
                    objs.append(DailyActual(
                        date=d,
                        vertical=verticals[vert_name],
                        revenue=vert_rev.quantize(Decimal('0.01')),
                    ))
            # Bulk upsert: delete existing range then bulk create
            DailyActual.objects.filter(date__gte=date(year, 1, 1), date__lte=end).delete()
            DailyActual.objects.bulk_create(objs)
            total_rows += len(objs)
            self.stdout.write(f'  {year}: {len(objs)} daily rows ({len(objs) // 3} days x 3 verticals)')

        self.stdout.write(self.style.SUCCESS(f'Created {total_rows} DailyActual rows.'))

        # ---- 2026 Monthly budget ($250M with seasonal shape) ----
        budget_total = 250_000_000
        MonthlyGoal.objects.filter(month__year=2026).delete()
        for m in range(1, 13):
            month_budget = round(budget_total * MONTHLY_PCT[m], 2)
            for vert_name, pct in VERTICAL_SPLITS.items():
                vert_budget = Decimal(str(month_budget)) * pct
                MonthlyGoal.objects.create(
                    month=date(2026, m, 1),
                    vertical=verticals[vert_name],
                    budget=vert_budget.quantize(Decimal('0.01')),
                )
            self.stdout.write(f'  2026-{m:02d} budget: ${month_budget:,.2f} (split across 3 verticals)')

        self.stdout.write(self.style.SUCCESS('Created 2026 monthly budget goals ($250M total, split by vertical).'))
