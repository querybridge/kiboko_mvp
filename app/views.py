import calendar
import csv
import datetime as dt
import io
import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.template import loader
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponse, HttpResponseRedirect
from django.db import models
from django.db.models import Q, Sum, Count, F, Avg
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages

from django.contrib.auth.models import User

logger = logging.getLogger(__name__)
from django.http import HttpResponseForbidden

from app.forms import StrategyForm
from users.models import ROLE_CHOICES, UserProfile
from app.models import MonthlyGoal, DailyActual
from business_unit.models import Department, BusinessUnit
from business_unit.scope import scoped_vertical_id, scoped_company_id
from project.models import Action
from strategy.models import Project, Objective, Metric, KPI
from project.views import project_detail


def _scope_to(qs, vertical_id, company_id, path='vertical'):
    """Scope a queryset to a BusinessUnit, or (on the 'All' Summary roll-up) to
    the selected company so aggregates never span companies/clients. `path` is
    the FK path to the BusinessUnit (e.g. 'vertical' or 'actions__vertical')."""
    if vertical_id:
        return qs.filter(**{f'{path}_id': vertical_id})
    if company_id:
        return qs.filter(**{f'{path}__company_id': company_id})
    return qs


def _actuals_map_agg(actuals, start, end):
    """Sum a GA4 daily-actuals map {iso_date: {revenue,visits,orders}} over
    [start, end] -> {'revenue': float, 'visits': int, 'orders': int}."""
    rev = 0.0
    visits = orders = 0
    d = start
    while d <= end:
        rec = actuals.get(d.isoformat())
        if rec:
            rev += rec.get('revenue', 0) or 0
            visits += rec.get('visits', 0) or 0
            orders += rec.get('orders', 0) or 0
        d += timedelta(days=1)
    return {'revenue': rev, 'visits': int(visits), 'orders': int(orders)}


def calculate_forecast(year, month, return_components=False, vertical_id=None, actuals=None, company_id=None,
                       statuses=('WIP',)):
    """Calculate forecast for a given month using weekday-weighted projection.

    For the current month: uses actuals-to-date + day-of-week projected remainder.
    For future months with no actuals: falls back to prior-year same-month
    actuals scaled by a YoY growth factor (this year budget / last year total).

    ``statuses`` controls which projects contribute uplift. Current-period views
    use WIP only; forward-looking periods (next month/quarter/year) also pass
    'On Deck' so the pipeline's expected momentum shows up.

    If return_components=True, returns (base_forecast, project_uplift) tuple.
    Otherwise returns total forecast (base + project uplift).
    """
    today = date.today()
    first_of_month = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    last_of_month = date(year, month, days_in_month)

    # Actual daily revenue this month (through today): from GA4 when provided
    # (Standard connection), else from uploaded DailyActual rows.
    if actuals is not None:
        daily = []
        d = first_of_month
        while d <= min(last_of_month, today):
            rec = actuals.get(d.isoformat())
            daily.append((d, Decimal(str((rec or {}).get('revenue', 0) or 0))))
            d += timedelta(days=1)
    else:
        actuals_qs = _scope_to(DailyActual.objects.filter(
            date__year=year, date__month=month, date__lte=today), vertical_id, company_id)
        daily = [(a.date, a.revenue) for a in actuals_qs]

    actuals_total = sum((r for _, r in daily), Decimal('0'))

    # Group actuals by day-of-week. Use the MEDIAN (not the mean) per weekday so a
    # single seasonal spike in the days seen so far — e.g. a Labor Day or a
    # back-to-school promo landing early in the month — can't drag the projected
    # remainder up and inflate the whole-month forecast. Median needs >=3 samples
    # to shrug off one outlier; with fewer we fall back to the mean.
    dow_values = defaultdict(list)
    for d_, r in daily:
        dow_values[d_.weekday()].append(r)  # 0=Mon ... 6=Sun

    def _dow_typical(vals):
        n = len(vals)
        if n == 0:
            return Decimal('0')
        if n < 3:
            return sum(vals, Decimal('0')) / n
        s = sorted(vals)
        mid = n // 2
        return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2

    dow_avg = {dow: _dow_typical(dow_values[dow]) for dow in range(7)}

    # Count remaining days in month by day-of-week
    if last_of_month < today:
        # Past month — no remaining days
        projected_remainder = Decimal('0')
    else:
        # Start from tomorrow (or first of month if future)
        start_remaining = max(today + timedelta(days=1), first_of_month)
        remaining_dow_counts = defaultdict(int)
        d = start_remaining
        while d <= last_of_month:
            remaining_dow_counts[d.weekday()] += 1
            d += timedelta(days=1)

        projected_remainder = sum(
            dow_avg[dow] * remaining_dow_counts[dow]
            for dow in range(7)
        )

    base_forecast = actuals_total + projected_remainder

    # Fallback for future months with no actuals: use prior-year same-month
    # actuals scaled by (this year's budget / last year's actual total).
    if base_forecast == 0 and first_of_month > today:
        prior_year = year - 1
        if actuals is not None:
            py_days = calendar.monthrange(prior_year, month)[1]
            py_month_total = Decimal(str(_actuals_map_agg(
                actuals, date(prior_year, month, 1), date(prior_year, month, py_days))['revenue']))
        else:
            py_qs = _scope_to(DailyActual.objects.filter(
                date__year=prior_year, date__month=month), vertical_id, company_id)
            py_month_total = py_qs.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if py_month_total > 0:
            if actuals is not None:
                py_year_total = Decimal(str(_actuals_map_agg(
                    actuals, date(prior_year, 1, 1), date(prior_year, 12, 31))['revenue']))
            else:
                py_year_qs = _scope_to(DailyActual.objects.filter(
                    date__year=prior_year), vertical_id, company_id)
                py_year_total = py_year_qs.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

            budget_qs = _scope_to(MonthlyGoal.objects.filter(
                month__year=year), vertical_id, company_id)
            this_year_budget = budget_qs.aggregate(s=Sum('budget'))['s'] or Decimal('0')

            if py_year_total > 0 and this_year_budget > 0:
                growth_scale = this_year_budget / py_year_total
                base_forecast = py_month_total * growth_scale

    # Add active project uplift — each WIP project contributes its daily revenue
    # only for days in this month on or after its go-live (target completion).
    from strategy.models import Project
    projects = _scope_to(Project.objects.filter(
        status__in=statuses,
    ).filter(
        Q(target_completion__isnull=True) | Q(target_completion__lte=last_of_month)
    ), vertical_id, company_id)
    project_uplift = Decimal('0')
    for p in projects:
        daily_value = Decimal(str(p.value or 0)) / Decimal('365')
        if p.target_completion and p.target_completion > first_of_month:
            active_start = p.target_completion
        else:
            active_start = first_of_month
        active_days = (last_of_month - active_start).days + 1
        project_uplift += daily_value * active_days

    if return_components:
        return base_forecast, project_uplift
    return base_forecast + project_uplift


def _add_months(year, month, n):
    """Return (year, month) shifted by ``n`` months (handles year rollover)."""
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def _goal_budget_for(year, month, vertical_id, company_id):
    qs = _scope_to(MonthlyGoal.objects.filter(month=date(year, month, 1)), vertical_id, company_id)
    agg = qs.aggregate(s=Sum('budget'))['s']
    return float(agg) if agg else 0


def _month_actuals_to_date(year, month, today, vertical_id, actuals, company_id):
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    if actuals is not None:
        return float(_actuals_map_agg(
            actuals, date(year, month, 1), min(last_day, today))['revenue'])
    return float(_scope_to(DailyActual.objects.filter(
        date__year=year, date__month=month, date__lte=today), vertical_id, company_id
    ).aggregate(s=Sum('revenue'))['s'] or 0)


def _month_series(months, today, vertical_id, actuals, company_id, statuses=('WIP',)):
    """Month-granularity chart series for a list of (year, month) tuples.

    Past months render as actual bars; the current and future months render as
    stacked Trending Forecast + Project Value Add bars. The summary totals sum
    calculate_forecast across every month (past actuals + forward projection) so
    "Trending Forecast" is the full end-of-period landing spot, matching the
    existing This-Quarter / This-Year behavior."""
    cur_month, cur_year = today.month, today.year
    labels, budget, fbase, puplift, actual = [], [], [], [], []
    for (yy, mm) in months:
        labels.append(date(yy, mm, 1).strftime('%b'))
        budget.append(_goal_budget_for(yy, mm, vertical_id, company_id))
        last_day = date(yy, mm, calendar.monthrange(yy, mm)[1])
        asum = _month_actuals_to_date(yy, mm, today, vertical_id, actuals, company_id)
        if last_day < today:
            actual.append(asum)
            fbase.append(0)
            puplift.append(0)
        else:
            base, up = calculate_forecast(yy, mm, return_components=True, vertical_id=vertical_id,
                                          actuals=actuals, company_id=company_id, statuses=statuses)
            fbase.append(float(base))
            puplift.append(float(up))
            if mm == cur_month and yy == cur_year:
                actual.append(asum if asum > 0 else None)
            else:
                actual.append(None)

    actual_total = round(sum(v for v in actual if v is not None), 2)
    f_total = p_total = 0.0
    for (yy, mm) in months:
        base, up = calculate_forecast(yy, mm, return_components=True, vertical_id=vertical_id,
                                      actuals=actuals, company_id=company_id, statuses=statuses)
        f_total += float(base)
        p_total += float(up)
    budget_total = round(sum(budget), 2)
    return {
        'labels': labels, 'budget': budget, 'forecast_base': fbase,
        'project_value_add': puplift, 'actual': actual,
        'summary': {
            'actual': actual_total,
            'forecast': round(f_total, 2),
            'project_value': round(p_total, 2),
            'end_total': round(f_total + p_total, 2),
            'budget_total': budget_total,
            'delta': round(budget_total - (f_total + p_total), 2),
        },
    }


def _daily_series(year, month, today, vertical_id, actuals, company_id, statuses=('WIP',)):
    """Daily cumulative chart series for a single (future) month. No actuals
    exist yet, so every day is projected: the month's Trending Forecast spread
    evenly across days, plus the cumulative daily value of pipeline projects that
    launch on or before each day."""
    dim = calendar.monthrange(year, month)[1]
    last_of = date(year, month, dim)
    month_budget = _goal_budget_for(year, month, vertical_id, company_id)
    daily_budget_rate = month_budget / dim if dim else 0
    base, _up = calculate_forecast(year, month, return_components=True, vertical_id=vertical_id,
                                   actuals=actuals, company_id=company_id, statuses=statuses)
    base = float(base)
    daily_base_rate = base / dim if dim else 0

    from strategy.models import Project
    pqs = _scope_to(Project.objects.filter(status__in=statuses).filter(
        Q(target_completion__isnull=True) | Q(target_completion__lte=last_of)
    ), vertical_id, company_id)
    proj = list(pqs.values_list('value', 'target_completion'))

    def _uplift_day(d):
        return sum(float(v or 0) / 365.0 for v, launch in proj if (launch is None or launch <= d))

    labels, budget, fbase, puplift, actual = [], [], [], [], []
    cb = cf = cp = 0.0
    for day in range(1, dim + 1):
        d = date(year, month, day)
        labels.append(d.strftime('%b %d'))
        cb += daily_budget_rate
        cf += daily_base_rate
        cp += _uplift_day(d)
        budget.append(round(cb, 2))
        fbase.append(round(cf, 2))
        puplift.append(round(cp, 2))
        actual.append(None)

    return {
        'labels': labels, 'budget': budget, 'forecast_base': fbase,
        'project_value_add': puplift, 'actual': actual,
        'summary': {
            'actual': 0,
            'forecast': round(base, 2),
            'project_value': round(cp, 2),
            'end_total': round(base + cp, 2),
            'budget_total': round(month_budget, 2),
            'delta': round(month_budget - (base + cp), 2),
        },
    }


def _build_chart_data(year, vertical_id=None, actuals=None, company_id=None):
    """Build MTD, QTD, YTD and forward-looking (next month/quarter/year) chart
    data series for the dashboard.

    ``actuals`` (optional) is a GA4 daily-actuals map {iso_date: {revenue,...}}
    from a Standard connection; when present, actual revenue comes from GA4
    instead of uploaded DailyActual rows."""
    today = date.today()
    current_month = today.month
    current_year = today.year

    def _filter_actuals(qs):
        return _scope_to(qs, vertical_id, company_id)

    def _filter_goals(qs):
        return _scope_to(qs, vertical_id, company_id)

    def _goal_budget(year, month):
        qs = MonthlyGoal.objects.filter(month=date(year, month, 1))
        qs = _filter_goals(qs)
        agg = qs.aggregate(s=Sum('budget'))['s']
        return float(agg) if agg else 0

    # --- YTD: monthly data Jan-Dec ---
    ytd_labels = []
    ytd_budget = []
    ytd_forecast_base = []
    ytd_project_value_add = []
    ytd_actual = []

    for m in range(1, 13):
        label = date(year, m, 1).strftime('%b')
        ytd_labels.append(label)

        budget_val = _goal_budget(year, m)
        ytd_budget.append(budget_val)

        # Check if this month has actual data (past month)
        last_day_of_month = date(year, m, calendar.monthrange(year, m)[1])
        has_actuals = last_day_of_month < today

        if actuals is not None:
            actual_sum = Decimal(str(_actuals_map_agg(
                actuals, date(year, m, 1), min(last_day_of_month, today))['revenue']))
        else:
            actual_sum = _filter_actuals(DailyActual.objects.filter(
                date__year=year, date__month=m, date__lte=today
            )).aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if has_actuals:
            # Past month: show actual, hide forecast
            ytd_actual.append(float(actual_sum))
            ytd_forecast_base.append(0)
            ytd_project_value_add.append(0)
        else:
            # Current/future month: show forecast, hide actual (or show partial actual)
            base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id, actuals=actuals, company_id=company_id)
            ytd_forecast_base.append(float(base))
            ytd_project_value_add.append(float(proj_uplift))
            # For current month, show actual so far; for future, null
            if m == current_month and year == current_year:
                ytd_actual.append(float(actual_sum) if float(actual_sum) > 0 else None)
            else:
                ytd_actual.append(None)

    # --- QTD: months in current quarter ---
    quarter_start_month = ((current_month - 1) // 3) * 3 + 1
    qtd_labels = []
    qtd_budget = []
    qtd_forecast_base = []
    qtd_project_value_add = []
    qtd_actual = []

    for m in range(quarter_start_month, quarter_start_month + 3):
        if m > 12:
            break
        label = date(year, m, 1).strftime('%b')
        qtd_labels.append(label)

        budget_val = _goal_budget(year, m)
        qtd_budget.append(budget_val)

        # Check if this month has actual data (past month)
        last_day_of_month = date(year, m, calendar.monthrange(year, m)[1])
        has_actuals = last_day_of_month < today

        if actuals is not None:
            actual_sum = Decimal(str(_actuals_map_agg(
                actuals, date(year, m, 1), min(last_day_of_month, today))['revenue']))
        else:
            actual_sum = _filter_actuals(DailyActual.objects.filter(
                date__year=year, date__month=m, date__lte=today
            )).aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if has_actuals:
            # Past month: show actual, hide forecast
            qtd_actual.append(float(actual_sum))
            qtd_forecast_base.append(0)
            qtd_project_value_add.append(0)
        else:
            # Current/future month: show forecast, hide actual (or show partial actual)
            base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id, actuals=actuals, company_id=company_id)
            qtd_forecast_base.append(float(base))
            qtd_project_value_add.append(float(proj_uplift))
            # For current month, show actual so far; for future, null
            if m == current_month and year == current_year:
                qtd_actual.append(float(actual_sum) if float(actual_sum) > 0 else None)
            else:
                qtd_actual.append(None)

    # --- MTD: daily data for current month ---
    days_in_current_month = calendar.monthrange(year, current_month)[1]
    monthly_budget = _goal_budget(year, current_month)
    daily_budget_rate = monthly_budget / days_in_current_month if days_in_current_month else 0

    # Gather daily actuals for the month (only through today)
    daily_actuals_map = {}
    dow_totals = defaultdict(float)
    dow_counts = defaultdict(int)
    if actuals is not None:
        # GA4 (Standard): one record per elapsed day of the current month.
        d = date(year, current_month, 1)
        while d <= today:
            rev = float((actuals.get(d.isoformat()) or {}).get('revenue', 0) or 0)
            if rev:
                daily_actuals_map[d.day] = daily_actuals_map.get(d.day, 0) + rev
            dow_totals[d.weekday()] += rev
            dow_counts[d.weekday()] += 1
            d += timedelta(days=1)
    else:
        daily_actuals_qs = _filter_actuals(DailyActual.objects.filter(
            date__year=year, date__month=current_month, date__lte=today))
        for a in daily_actuals_qs:
            daily_actuals_map[a.date.day] = daily_actuals_map.get(a.date.day, 0) + float(a.revenue)
            dow_totals[a.date.weekday()] += float(a.revenue)
            dow_counts[a.date.weekday()] += 1

    dow_avg = {}
    for dow in range(7):
        if dow_counts[dow] > 0:
            dow_avg[dow] = dow_totals[dow] / dow_counts[dow]
        else:
            dow_avg[dow] = 0

    # Pre-compute per-project daily rates for MTD forecast
    from strategy.models import Project
    last_of_current_month = date(year, current_month, days_in_current_month)
    project_qs = _scope_to(Project.objects.filter(
        status='WIP',
    ).filter(
        Q(target_completion__isnull=True) | Q(target_completion__lte=last_of_current_month)
    ), vertical_id, company_id)
    active_projects = list(project_qs.values_list('value', 'target_completion'))

    def _project_uplift_for_day(d):
        """Sum daily value of all projects whose launch date is on or before d."""
        total = 0.0
        for value, launch in active_projects:
            if launch is None or launch <= d:
                total += float(value or 0) / 365.0
        return total

    mtd_labels = []
    mtd_budget = []
    mtd_forecast_base = []
    mtd_project_value_add = []
    mtd_actual = []

    cumulative_actual = 0
    cumulative_budget = 0
    cumulative_forecast_base = 0
    cumulative_project_uplift = 0

    for day in range(1, days_in_current_month + 1):
        d = date(year, current_month, day)
        mtd_labels.append(d.strftime('%b %d'))
        cumulative_budget += daily_budget_rate
        mtd_budget.append(round(cumulative_budget, 2))

        day_actual = daily_actuals_map.get(day, 0)
        cumulative_actual += day_actual

        # Forecast base: actual for past days, projected for future (without project uplift)
        day_project_uplift = _project_uplift_for_day(d)
        if d <= today:
            cumulative_forecast_base += day_actual
        else:
            cumulative_forecast_base += dow_avg.get(d.weekday(), 0)
        cumulative_project_uplift += day_project_uplift

        if d <= today:
            # Past/current day: show actual, hide forecast bars
            mtd_actual.append(round(cumulative_actual, 2))
            mtd_forecast_base.append(0)
            mtd_project_value_add.append(0)
        else:
            # Future day: show forecast bars, hide actual
            mtd_actual.append(None)
            mtd_forecast_base.append(round(cumulative_forecast_base, 2))
            mtd_project_value_add.append(round(cumulative_project_uplift, 2))

    # Store final cumulative values for summary (full month projection)
    mtd_forecast_base_final = round(cumulative_forecast_base, 2)
    mtd_project_uplift_final = round(cumulative_project_uplift, 2)

    # --- Summary totals for each period ---

    def _project_value_through(end_date):
        from strategy.models import Project
        qs = _scope_to(Project.objects.filter(
            status='WIP',
        ).filter(
            Q(target_completion__isnull=True) | Q(target_completion__lte=end_date)
        ), vertical_id, company_id)
        return float(qs.aggregate(s=Sum('value'))['s'] or 0)

    # MTD: use the final cumulative values (full month projection)
    mtd_actual_total = round(cumulative_actual, 2)
    mtd_forecast_base_total = mtd_forecast_base_final
    mtd_project_value_total = mtd_project_uplift_final
    mtd_budget_total = round(monthly_budget, 2)
    mtd_project_value = _project_value_through(last_of_current_month)

    # QTD: need to calculate full forecast for all months (not just display values)
    qtd_actual_total = round(sum(v for v in qtd_actual if v is not None), 2)
    qtd_forecast_base_total = 0
    qtd_project_value_total = 0
    for m in range(quarter_start_month, min(quarter_start_month + 3, 13)):
        base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id, actuals=actuals, company_id=company_id)
        qtd_forecast_base_total += float(base)
        qtd_project_value_total += float(proj_uplift)
    qtd_forecast_base_total = round(qtd_forecast_base_total, 2)
    qtd_project_value_total = round(qtd_project_value_total, 2)
    qtd_budget_total = round(sum(qtd_budget), 2)
    quarter_end_month = min(quarter_start_month + 2, 12)
    quarter_end_day = calendar.monthrange(year, quarter_end_month)[1]
    qtd_project_value = _project_value_through(date(year, quarter_end_month, quarter_end_day))

    # YTD: need to calculate full forecast for all months (not just display values)
    ytd_actual_total = round(sum(v for v in ytd_actual if v is not None), 2)
    ytd_forecast_base_total = 0
    ytd_project_value_total = 0
    for m in range(1, 13):
        base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id, actuals=actuals, company_id=company_id)
        ytd_forecast_base_total += float(base)
        ytd_project_value_total += float(proj_uplift)
    ytd_forecast_base_total = round(ytd_forecast_base_total, 2)
    ytd_project_value_total = round(ytd_project_value_total, 2)
    ytd_budget_total = round(sum(ytd_budget), 2)
    ytd_project_value = _project_value_through(date(year, 12, 31))

    # --- Forward-looking periods: what the pipeline (WIP + On Deck) is expected
    # to deliver next month / next quarter / next year. No actuals exist yet, so
    # these are pure projection — useful when the current period is already a lost
    # cause and the question is whether momentum picks up. ---
    fwd_statuses = ('WIP', 'On Deck')
    nmo_year, nmo_month = _add_months(current_year, current_month, 1)
    next_month = _daily_series(nmo_year, nmo_month, today, vertical_id, actuals, company_id, fwd_statuses)

    nq_year, nq_month = _add_months(current_year, quarter_start_month, 3)
    nq_months = [_add_months(nq_year, nq_month, i) for i in range(3)]
    next_quarter = _month_series(nq_months, today, vertical_id, actuals, company_id, fwd_statuses)

    ny_months = [(current_year + 1, m) for m in range(1, 13)]
    next_year = _month_series(ny_months, today, vertical_id, actuals, company_id, fwd_statuses)

    return {
        'nmo': next_month,
        'nq': next_quarter,
        'ny': next_year,
        'mtd': {
            'labels': mtd_labels,
            'budget': mtd_budget,
            'forecast_base': mtd_forecast_base,
            'project_value_add': mtd_project_value_add,
            'actual': mtd_actual,
            'summary': {
                'actual': mtd_actual_total,
                'forecast': mtd_forecast_base_total,
                'project_value': mtd_project_value_total,
                'end_total': mtd_forecast_base_total + mtd_project_value_total,
                'budget_total': mtd_budget_total,
                'delta': mtd_budget_total - (mtd_forecast_base_total + mtd_project_value_total),
            },
        },
        'qtd': {
            'labels': qtd_labels,
            'budget': qtd_budget,
            'forecast_base': qtd_forecast_base,
            'project_value_add': qtd_project_value_add,
            'actual': qtd_actual,
            'summary': {
                'actual': qtd_actual_total,
                'forecast': qtd_forecast_base_total,
                'project_value': qtd_project_value_total,
                'end_total': qtd_forecast_base_total + qtd_project_value_total,
                'budget_total': qtd_budget_total,
                'delta': qtd_budget_total - (qtd_forecast_base_total + qtd_project_value_total),
            },
        },
        'ytd': {
            'labels': ytd_labels,
            'budget': ytd_budget,
            'forecast_base': ytd_forecast_base,
            'project_value_add': ytd_project_value_add,
            'actual': ytd_actual,
            'summary': {
                'actual': ytd_actual_total,
                'forecast': ytd_forecast_base_total,
                'project_value': ytd_project_value_total,
                'end_total': ytd_forecast_base_total + ytd_project_value_total,
                'budget_total': ytd_budget_total,
                'delta': ytd_budget_total - (ytd_forecast_base_total + ytd_project_value_total),
            },
        },
    }


# Post-login landing keys -> the route to redirect to.
LANDER_ROUTES = {
    'pipeline': 'app:index',
    'kanban': 'project:kanban',
    'grow_sales': 'app:analytics_grow_sales',
    'storyboard': 'app:analytics_performance_story',
}


@login_required
def home(request):
    """Post-login dispatcher: send the user to their preferred (or role-default)
    landing page. LOGIN_REDIRECT_URL points here."""
    prof = getattr(request.user, 'profile', None)
    key = prof.resolved_lander_key() if prof else 'pipeline'
    try:
        return redirect(LANDER_ROUTES.get(key, 'app:index'))
    except Exception:
        return redirect('app:index')


# View All Projects Page
@login_required
def index(request):
    vertical_id = scoped_vertical_id(request)
    company_id = scoped_company_id(request)

    # Show active actions on dashboard
    projects = _scope_to(
        Action.objects.filter(status='WIP', archived=False).order_by('-normalized_score'),
        vertical_id, company_id)

    # Dynamic Objective tiles -- the pending pipeline (potential, not actual):
    # WIP projects (in flight) and On Deck projects (up next), by objective.
    # Completed/launched value is Actual revenue, so it's excluded here.
    from strategy.models import Project
    annual_rocks_data = []
    for rock in Objective.objects.filter(year=date.today().year):
        base_qs = _scope_to(Project.objects.filter(objective=rock, archived=False), vertical_id, company_id)
        count = base_qs.filter(status='WIP').count()
        value = base_qs.filter(status='WIP').aggregate(Sum('value'))
        count_p = base_qs.filter(status='On Deck').count()
        value_p = base_qs.filter(status='On Deck').aggregate(Sum('value'))
        annual_rocks_data.append({
            'rock': rock,
            'count': count,
            'value': value,
            'count_p': count_p,
            'value_p': value_p,
            'color': _objective_bar_colors(rock.name)['fill'],
            'aee_element': _AEE_ELEMENT.get(rock.aee_alignment, ''),
        })

    # Enforce display order: Shopper Volume, Close Rate, Average Order Value
    # (drive more orders first, then grow order size)
    _rock_order_keywords = ['shopper', 'close', 'order value']

    def _rock_sort_key(item):
        name = (item['rock'].name or '').lower()
        for idx, kw in enumerate(_rock_order_keywords):
            if kw in name:
                return idx
        return len(_rock_order_keywords)

    annual_rocks_data.sort(key=_rock_sort_key)

    # Actual revenue source: GA4 when the scope is a Standard connection, else
    # uploaded DailyActual rows. Fetch prior-year-start -> today so YoY deltas and
    # the forecast fallback are covered.
    from app.integrations import ga4_dashboard
    _t = date.today()
    ga4_actuals = ga4_dashboard.ga4_daily_actuals(request, date(_t.year - 1, 1, 1), _t)

    # Build revenue chart data
    chart_data = _build_chart_data(_t.year, vertical_id=vertical_id, actuals=ga4_actuals, company_id=company_id)

    # Build performance scorecard data
    performance_data = _build_performance_data(_t, vertical_id=vertical_id, actuals=ga4_actuals, company_id=company_id)

    # Build initiatives summary + a totals row for the table footer.
    initiatives = _build_initiatives_summary(vertical_id=vertical_id, company_id=company_id)
    _progs = [i['avg_progress'] for i in initiatives if i.get('avg_progress') is not None]
    initiatives_totals = {
        'actions': sum(i.get('project_count') or 0 for i in initiatives),
        'active': sum(i.get('active_count') or 0 for i in initiatives),
        'avg_progress': round(sum(_progs) / len(_progs)) if _progs else None,
        'total_value': sum(i.get('total_value') or 0 for i in initiatives),
    }

    return render(request, 'app/index2.html', {
        'annual_rocks_data': annual_rocks_data,
        'chart_data_mtd': json.dumps(chart_data['mtd']),
        'chart_data_qtd': json.dumps(chart_data['qtd']),
        'chart_data_ytd': json.dumps(chart_data['ytd']),
        'chart_data_nmo': json.dumps(chart_data['nmo']),
        'chart_data_nq': json.dumps(chart_data['nq']),
        'chart_data_ny': json.dumps(chart_data['ny']),
        'performance_data': json.dumps(performance_data),
        'initiatives': initiatives,
        'initiatives_totals': initiatives_totals,
    })


# Short AEE element name shown as the tile's second line (e.g. "Attract").
_AEE_ELEMENT = {
    'attract_traffic': 'Attract',
    'engage_customers': 'Engage',
    'expand_purchase': 'Expand',
}
# AEE pill colors -- mirror the value-pipeline palette.
_AEE_COLOR = {
    'attract_traffic': '#3FC9E0',
    'engage_customers': '#ECB752',
    'expand_purchase': '#55C892',
}


PURPOSE_COLORS = {
    'New Growth':       '#1a7a5c',  # green
    'Hold Position':    '#337ab7',  # blue
    'Defend Position':  '#f0ad4e',  # amber
    'Reverse Decay':    '#d9534f',  # red
}


PIPELINE_EXCLUDED_STATUSES = ['Launched', 'Complete']


def _build_initiatives_summary(vertical_id=None, company_id=None):
    """Annotate Projects with action rollups for the Projects summary table.
    Excludes actions in final states (Launched, Complete) since the panel
    surfaces work that will produce future value.
    """
    from django.db.models.functions import Coalesce
    from django.db.models import IntegerField

    pipeline_filter = ~Q(actions__status__in=PIPELINE_EXCLUDED_STATUSES)
    if vertical_id:
        pipeline_filter &= Q(actions__vertical_id=vertical_id)
    elif company_id:
        pipeline_filter &= Q(actions__vertical__company_id=company_id)

    # Task rollups (child Actions); the value figures use the PROJECT's own
    # revenue (the scored unit), keyed off the project's Kanban status. Scoped to
    # the selected company/business unit.
    # Executive view: only in-flight (WIP) and up-next (On Deck) projects.
    qs = _scope_to(
        Project.objects
        .select_related('objective', 'department', 'vertical')
        .annotate(
            project_count=Count('actions', distinct=True, filter=pipeline_filter),
            avg_progress=Avg('actions__progress', filter=pipeline_filter),
        )
        .filter(status__in=('WIP', 'On Deck'))
        .order_by('purpose', 'name'),
        vertical_id, company_id)

    project_qs = _scope_to(
        Action.objects.exclude(status__in=PIPELINE_EXCLUDED_STATUSES), vertical_id, company_id)
    qs = qs.prefetch_related(models.Prefetch(
        'actions', queryset=project_qs.select_related('team').order_by('launch', 'name')))

    rows = []
    for s in qs:
        # Child execution tasks (Actions) under this project -- action-level data
        # only (projects are scored, not actions).
        tasks = [{
            'id': p.id,
            'name': p.name or f'Task {p.id}',
            'team': p.team.name if p.team_id and p.team else '',
            'progress': p.progress or 0,
            'launch': p.launch.isoformat() if p.launch else '',
        } for p in s.actions.all()]

        is_wip = s.status == 'WIP'
        val = int(s.value or 0)
        aee = s.objective.aee_alignment if (s.objective_id and s.objective) else ''
        rows.append({
            'id': s.id,
            'name': s.name or f'Project {s.id}',
            'aee_element': _AEE_ELEMENT.get(aee, ''),
            'aee_color': _AEE_COLOR.get(aee, '#888'),
            'objective': s.objective.name if s.objective_id and s.objective else '',
            'score': float(s.normalized_score) if s.normalized_score is not None else 0.0,
            'scored': s.normalized_score is not None,
            'status': s.status or '',
            # Expected go-live (the project's target completion date).
            'go_live': s.target_completion.isoformat() if s.target_completion else '',
            # The BusinessUnit (GA4 property) -- matches the top-bar selector.
            'business_unit': s.vertical.name if s.vertical_id and s.vertical else '',
            'project_count': s.project_count or 0,
            # Actions currently in progress (started, not finished).
            'active_count': sum(1 for t in tasks if 0 < (t['progress'] or 0) < 100),
            'total_value': val,
            'avg_progress': int(round(s.avg_progress)) if s.avg_progress is not None else None,
            'projects': tasks,
        })
    return rows


PERFORMANCE_AOV_GOAL = 475.0           # target average order value ($)
PERFORMANCE_CLOSE_RATE_GOAL = 0.0150   # target close rate (1.5%)


def _build_performance_data(today, vertical_id=None, actuals=None, company_id=None):
    """Aggregate Sales / Visits / Close Rate / AOV per period (MTD/QTD/YTD)
    with deltas vs same period last year and vs prorated goal.

    ``actuals`` (optional) is a GA4 daily-actuals map from a Standard connection;
    when present, sales/visits/orders come from GA4 instead of DailyActual.
    """
    year = today.year
    month = today.month
    quarter_start_month = ((month - 1) // 3) * 3 + 1

    nmo_y, nmo_m = _add_months(year, month, 1)
    nmo_last = calendar.monthrange(nmo_y, nmo_m)[1]
    nq_y, nq_m = _add_months(year, quarter_start_month, 3)
    nq_end_y, nq_end_m = _add_months(nq_y, nq_m, 2)
    nq_end_last = calendar.monthrange(nq_end_y, nq_end_m)[1]

    # (start, end, is_future). Current periods run to today; forward periods span
    # the whole future window and carry no actuals yet, so their cards show the
    # target (goal) rather than actuals=0.
    periods = {
        'mtd': (date(year, month, 1), today, False),
        'qtd': (date(year, quarter_start_month, 1), today, False),
        'ytd': (date(year, 1, 1), today, False),
        'nmo': (date(nmo_y, nmo_m, 1), date(nmo_y, nmo_m, nmo_last), True),
        'nq': (date(nq_y, nq_m, 1), date(nq_end_y, nq_end_m, nq_end_last), True),
        'ny': (date(year + 1, 1, 1), date(year + 1, 12, 31), True),
    }

    def _ly_bound(d):
        try:
            return date(d.year - 1, d.month, d.day)
        except ValueError:
            # Feb 29 -> Feb 28
            return date(d.year - 1, d.month, d.day - 1)

    def _aggregate(start, end):
        if actuals is not None:
            a = _actuals_map_agg(actuals, start, end)
            revenue, visits, orders = a['revenue'], a['visits'], a['orders']
        else:
            qs = _scope_to(DailyActual.objects.filter(
                date__gte=start, date__lte=end), vertical_id, company_id)
            agg = qs.aggregate(rev=Sum('revenue'), v=Sum('visits'), o=Sum('orders'))
            revenue = float(agg['rev'] or 0)
            visits = int(agg['v'] or 0)
            orders = int(agg['o'] or 0)
        return {
            'sales': revenue,
            'visits': visits,
            'close_rate': (orders / visits) if visits else 0,
            'aov': (revenue / orders) if orders else 0,
        }

    def _sales_goal_for(start, end):
        """Sum prorated daily budget across [start, end]."""
        total = Decimal('0')
        cur = date(start.year, start.month, 1)
        while cur <= end:
            days_in_month = calendar.monthrange(cur.year, cur.month)[1]
            month_end = date(cur.year, cur.month, days_in_month)
            qs = _scope_to(MonthlyGoal.objects.filter(month=cur), vertical_id, company_id)
            month_budget = qs.aggregate(s=Sum('budget'))['s'] or Decimal('0')
            daily = month_budget / Decimal(days_in_month) if days_in_month else Decimal('0')

            slice_start = max(start, cur)
            slice_end = min(end, month_end)
            days_in_slice = (slice_end - slice_start).days + 1
            if days_in_slice > 0:
                total += daily * Decimal(days_in_slice)

            # advance to next month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return float(total)

    def _delta(actual, baseline):
        if baseline is None or baseline == 0:
            return None
        return (actual - baseline) / baseline

    result = {}
    for key, (start, end, is_future) in periods.items():
        cur = _aggregate(start, end)
        ly = _aggregate(_ly_bound(start), _ly_bound(end))

        sales_goal = _sales_goal_for(start, end)
        visits_goal = (sales_goal / PERFORMANCE_AOV_GOAL / PERFORMANCE_CLOSE_RATE_GOAL) if sales_goal else 0

        if is_future:
            # No actuals yet — show the target for the period and how it compares
            # to last year's actuals ("vs LY"). There's nothing to compare against
            # a goal (the value IS the goal), so delta_goal is n/a.
            cards = {
                'sales': {'value': sales_goal, 'unit': 'currency',
                          'delta_ly': _delta(sales_goal, ly['sales']), 'delta_goal': None},
                'visits': {'value': visits_goal, 'unit': 'integer',
                           'delta_ly': _delta(visits_goal, ly['visits']) if visits_goal else None,
                           'delta_goal': None},
                'close_rate': {'value': PERFORMANCE_CLOSE_RATE_GOAL, 'unit': 'percent',
                               'delta_ly': _delta(PERFORMANCE_CLOSE_RATE_GOAL, ly['close_rate']),
                               'delta_goal': None},
                'aov': {'value': PERFORMANCE_AOV_GOAL, 'unit': 'currency',
                        'delta_ly': _delta(PERFORMANCE_AOV_GOAL, ly['aov']), 'delta_goal': None},
            }
            result[key] = cards
            continue

        cards = {
            'sales': {
                'value': cur['sales'],
                'unit': 'currency',
                'delta_ly': _delta(cur['sales'], ly['sales']),
                'delta_goal': _delta(cur['sales'], sales_goal),
            },
            'visits': {
                'value': cur['visits'],
                'unit': 'integer',
                'delta_ly': _delta(cur['visits'], ly['visits']),
                'delta_goal': _delta(cur['visits'], visits_goal) if visits_goal else None,
            },
            'close_rate': {
                'value': cur['close_rate'],
                'unit': 'percent',
                'delta_ly': _delta(cur['close_rate'], ly['close_rate']),
                'delta_goal': _delta(cur['close_rate'], PERFORMANCE_CLOSE_RATE_GOAL),
            },
            'aov': {
                'value': cur['aov'],
                'unit': 'currency',
                'delta_ly': _delta(cur['aov'], ly['aov']),
                'delta_goal': _delta(cur['aov'], PERFORMANCE_AOV_GOAL),
            },
        }
        result[key] = cards
    return result


# Gantt bar colors keyed on the Action's Objective. Each entry provides the bar
# track color, the lighter stripe used for no-end (open-ended) bars, and the
# saturated progress-fill color.
OBJECTIVE_BAR_COLORS = {
    'aov':       {'track': '#c5f0e0', 'stripe': '#d8f3e8', 'fill': '#1a7a5c'},  # green
    'close':     {'track': '#fbe9b0', 'stripe': '#fdf3d2', 'fill': '#d4a017'},  # yellow
    'visits':    {'track': '#cfe2f3', 'stripe': '#e3eef9', 'fill': '#337ab7'},  # blue
    'default':   {'track': '#e2e2e2', 'stripe': '#efefef', 'fill': '#888888'},  # neutral
}


def _objective_bar_colors(objective_name):
    """Map an Objective name to a gantt color set (AOV=green, Close Rate=yellow,
    Shopper Volume/Visits=blue, anything else=neutral)."""
    name = (objective_name or '').lower()
    if 'order value' in name or 'aov' in name:
        return OBJECTIVE_BAR_COLORS['aov']
    if 'close' in name:
        return OBJECTIVE_BAR_COLORS['close']
    if 'shopper' in name or 'visit' in name:
        return OBJECTIVE_BAR_COLORS['visits']
    return OBJECTIVE_BAR_COLORS['default']


def _build_gantt_data(active_projects):
    """Serialize active actions + MTD/QTD/YTD period bounds for the gantt chart."""
    today = date.today()
    year = today.year
    month = today.month

    mtd_start = date(year, month, 1)
    mtd_end = date(year, month, calendar.monthrange(year, month)[1])

    quarter_start_month = ((month - 1) // 3) * 3 + 1
    quarter_end_month = min(quarter_start_month + 2, 12)
    qtd_start = date(year, quarter_start_month, 1)
    qtd_end = date(year, quarter_end_month, calendar.monthrange(year, quarter_end_month)[1])

    ytd_start = date(year, 1, 1)
    ytd_end = date(year, 12, 31)

    # Forward-looking windows: next month / next quarter / next year.
    nmo_y, nmo_m = _add_months(year, month, 1)
    nmo_start = date(nmo_y, nmo_m, 1)
    nmo_end = date(nmo_y, nmo_m, calendar.monthrange(nmo_y, nmo_m)[1])
    nq_y, nq_m = _add_months(year, quarter_start_month, 3)
    nq_end_y, nq_end_m = _add_months(nq_y, nq_m, 2)
    nq_start = date(nq_y, nq_m, 1)
    nq_end = date(nq_end_y, nq_end_m, calendar.monthrange(nq_end_y, nq_end_m)[1])
    ny_start = date(year + 1, 1, 1)
    ny_end = date(year + 1, 12, 31)

    items = []
    for p in active_projects:
        start = p.active_date or p.date_created
        # Dependency guardrail: can't start before its dependencies' end dates.
        guardrail = p.start_guardrail()
        if guardrail and (start is None or guardrail > start):
            start = guardrail
        deps = list(p.depends_on.all())
        objective_name = str(p.objective) if p.objective_id and p.objective else ''
        colors = _objective_bar_colors(objective_name)
        proj = p.project if p.project_id else None   # parent Project (scored unit)
        items.append({
            'id': p.id,
            'name': p.name or f'Action {p.id}',
            'value': float(p.value or 0),
            'progress': max(0, min(100, int(p.progress or 0))),
            'team': p.team.name if p.team_id and p.team else 'Unassigned',
            'quarterly_rock': proj.name if proj else '',
            'annual_rock': objective_name,
            # Parent project context (shown on hover of the action).
            'project_id': proj.id if proj else None,
            'project_name': proj.name if proj else '',
            'project_value': float(proj.value or 0) if proj else 0,
            'project_score': float(proj.normalized_score or 0) if proj else 0,
            'project_status': proj.status if proj else '',
            # On Deck (not yet started) — shown only in forward-looking periods so
            # the current WIP windows stay WIP-only.
            'pipeline': bool(proj and proj.status != 'WIP'),
            'depends_on': [d.name for d in deps],
            'has_deps': bool(deps),
            'objective_track': colors['track'],
            'objective_stripe': colors['stripe'],
            'objective_fill': colors['fill'],
            'start': start.isoformat() if start else None,
            'end': p.launch.isoformat() if p.launch else None,
        })

    return {
        'projects': items,
        'today': today.isoformat(),
        'periods': {
            'mtd': {'start': mtd_start.isoformat(), 'end': mtd_end.isoformat()},
            'qtd': {'start': qtd_start.isoformat(), 'end': qtd_end.isoformat()},
            'ytd': {'start': ytd_start.isoformat(), 'end': ytd_end.isoformat()},
            'nmo': {'start': nmo_start.isoformat(), 'end': nmo_end.isoformat()},
            'nq': {'start': nq_start.isoformat(), 'end': nq_end.isoformat()},
            'ny': {'start': ny_start.isoformat(), 'end': ny_end.isoformat()},
        },
    }


@login_required
def gentella_html(request):
    context = {}
    load_template = request.path.split('/')[-1]
    template = loader.get_template('app/' + load_template)
    return HttpResponse(template.render(context, request))


@login_required
def project_detail(request, project_id):
    from django.shortcuts import get_object_or_404
    project = get_object_or_404(Action, pk=project_id)
    return render(request, 'project/detail.html', {'project': project})


@login_required
def edit_goals(request):
    year = date.today().year
    last_year = year - 1
    prev_year = year - 2

    vertical_id = scoped_vertical_id(request)
    company_id = scoped_company_id(request)

    # Scope to the selected business unit, or (on the Summary roll-up) to the
    # selected company/client so goals never mix across clients.
    def _scope(qs):
        if vertical_id:
            return qs.filter(vertical_id=vertical_id)
        if company_id:
            return qs.filter(vertical__company_id=company_id)
        return qs

    _filter_goals = _scope
    _filter_actuals = _scope

    is_summary = vertical_id is None

    if request.method == 'POST' and not is_summary:
        from business_unit.access import can_manage_goals
        bu = BusinessUnit.objects.filter(pk=vertical_id).first()
        if not bu or not can_manage_goals(request.user, bu):
            return HttpResponseForbidden(
                'Only owners, executives, and business-unit leads can edit the budget.')
        for m in range(1, 13):
            month_date = date(year, m, 1)
            budget_val = request.POST.get(f'budget_{m}', '0')
            try:
                budget_val = Decimal(budget_val.replace(',', ''))
            except (InvalidOperation, ValueError):
                budget_val = Decimal('0')
            MonthlyGoal.objects.update_or_create(
                month=month_date,
                vertical_id=vertical_id,
                defaults={'budget': budget_val}
            )
        messages.success(request, 'Budget saved successfully.')
        return redirect(f'/app/goals/?vertical={vertical_id}')

    # GET: build data for current year and historical years
    goals_data = []
    for m in range(1, 13):
        # Current year goal — aggregate across verticals when Summary
        month_date = date(year, m, 1)
        goal_qs = _filter_goals(MonthlyGoal.objects.filter(month=month_date))
        budget_agg = goal_qs.aggregate(s=Sum('budget'))['s'] or Decimal('0')

        # Last year data
        ly_goal_qs = _filter_goals(MonthlyGoal.objects.filter(month=date(last_year, m, 1)))
        ly_budget = float(ly_goal_qs.aggregate(s=Sum('budget'))['s'] or 0)
        ly_actual = float(_filter_actuals(DailyActual.objects.filter(
            date__year=last_year, date__month=m
        )).aggregate(s=Sum('revenue'))['s'] or 0)
        ly_pct = ((ly_actual / ly_budget - 1) * 100) if ly_budget else 0

        # Previous year data
        py_goal_qs = _filter_goals(MonthlyGoal.objects.filter(month=date(prev_year, m, 1)))
        py_budget = float(py_goal_qs.aggregate(s=Sum('budget'))['s'] or 0)
        py_actual = float(_filter_actuals(DailyActual.objects.filter(
            date__year=prev_year, date__month=m
        )).aggregate(s=Sum('revenue'))['s'] or 0)
        py_pct = ((py_actual / py_budget - 1) * 100) if py_budget else 0

        goals_data.append({
            'month': m,
            'month_name': month_date.strftime('%B'),
            'budget': budget_agg,
            'ly_budget': ly_budget,
            'ly_actual': ly_actual,
            'ly_pct': ly_pct,
            'py_budget': py_budget,
            'py_actual': py_actual,
            'py_pct': py_pct,
        })

    # Compute totals
    total_budget = sum(float(row['budget']) for row in goals_data)
    total_ly_budget = sum(row['ly_budget'] for row in goals_data)
    total_ly_actual = sum(row['ly_actual'] for row in goals_data)
    total_ly_pct = ((total_ly_actual / total_ly_budget - 1) * 100) if total_ly_budget else 0
    total_py_budget = sum(row['py_budget'] for row in goals_data)
    total_py_actual = sum(row['py_actual'] for row in goals_data)
    total_py_pct = ((total_py_actual / total_py_budget - 1) * 100) if total_py_budget else 0

    totals = {
        'budget': total_budget,
        'ly_budget': total_ly_budget,
        'ly_actual': total_ly_actual,
        'ly_pct': total_ly_pct,
        'py_budget': total_py_budget,
        'py_actual': total_py_actual,
        'py_pct': total_py_pct,
    }

    return render(request, 'app/edit_goals.html', {
        'goals_data': goals_data,
        'totals': totals,
        'year': year,
        'last_year': last_year,
        'prev_year': prev_year,
        'is_summary': is_summary,
    })


@login_required
def objectives(request):
    """Manage annual Objectives (AEE > Objective > Project > Action). Executives
    add/edit; everyone else sees a read-only list."""
    from project.services.kanban import is_executive
    from strategy.models import Objective
    return render(request, 'app/objectives.html', {
        'title': 'Objectives',
        'objectives': Objective.objects.order_by('-year', 'name'),
        'aee_choices': _aee_choices(),
        'can_manage_objectives': is_executive(request.user),
        'year': date.today().year,
    })


@login_required
@require_POST
def add_objective(request):
    """Create an annual Objective (executives only). Every objective must align
    to an AEE element -- the Projects/Actions beneath it inherit it."""
    from project.services.kanban import is_executive
    from strategy.models import Objective
    if not is_executive(request.user):
        return HttpResponseForbidden('Only executives can add objectives.')
    name = (request.POST.get('name') or '').strip()
    aee = (request.POST.get('aee_alignment') or '').strip()
    valid_aee = {c[0] for c in _aee_choices()}
    if not name or aee not in valid_aee:
        messages.error(request, 'An objective needs a name and an AEE alignment.')
        return redirect('app:objectives')
    try:
        yr = int(request.POST.get('year') or date.today().year)
    except (TypeError, ValueError):
        yr = date.today().year
    Objective.objects.create(name=name[:150], year=yr, aee_alignment=aee,
                             description=(request.POST.get('description') or '').strip())
    messages.success(request, f'Added objective "{name}".')
    return redirect('app:objectives')


@login_required
@require_POST
def edit_objective(request, objective_id):
    """Edit an existing annual Objective (executives only) -- name, year, AEE,
    and description. AEE stays required so Projects/Actions always inherit one."""
    from project.services.kanban import is_executive
    from strategy.models import Objective
    if not is_executive(request.user):
        return HttpResponseForbidden('Only executives can edit objectives.')
    obj = get_object_or_404(Objective, pk=objective_id)
    name = (request.POST.get('name') or '').strip()
    aee = (request.POST.get('aee_alignment') or '').strip()
    if not name or aee not in {c[0] for c in _aee_choices()}:
        messages.error(request, 'An objective needs a name and an AEE alignment.')
        return redirect('app:objectives')
    try:
        obj.year = int(request.POST.get('year') or obj.year or date.today().year)
    except (TypeError, ValueError):
        pass
    obj.name = name[:150]
    obj.aee_alignment = aee
    obj.description = (request.POST.get('description') or '').strip()
    obj.save()
    messages.success(request, f'Updated objective "{obj.name}".')
    return redirect('app:objectives')


def _aee_choices():
    from project.project_field_options import AEE_ALIGNMENT_CHOICES
    return [c for c in AEE_ALIGNMENT_CHOICES if c[0]]


@login_required
def upload_actuals(request):
    verticals = BusinessUnit.objects.all()

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        vertical_id = request.POST.get('vertical', '').strip()

        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('app:upload_actuals')

        if not vertical_id:
            messages.error(request, 'Please select a Business Unit.')
            return redirect('app:upload_actuals')

        try:
            vertical_obj = BusinessUnit.objects.get(pk=int(vertical_id))
        except (BusinessUnit.DoesNotExist, ValueError):
            messages.error(request, 'Invalid vertical selected.')
            return redirect('app:upload_actuals')

        try:
            decoded = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            decoded = csv_file.read().decode('latin-1')

        reader = csv.DictReader(io.StringIO(decoded))
        count = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            date_str = row.get('Date', '').strip()
            revenue_str = row.get('Actual Revenue', '').strip()

            if not date_str or not revenue_str:
                errors.append(f'Row {i}: missing Date or Actual Revenue')
                continue

            # Flexible date parsing
            parsed_date = None
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%d/%m/%Y'):
                try:
                    parsed_date = dt.datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue

            if parsed_date is None:
                errors.append(f'Row {i}: could not parse date "{date_str}"')
                continue

            try:
                revenue_val = Decimal(revenue_str.replace(',', '').replace('$', ''))
            except (InvalidOperation, ValueError):
                errors.append(f'Row {i}: invalid revenue value "{revenue_str}"')
                continue

            DailyActual.objects.update_or_create(
                date=parsed_date,
                vertical=vertical_obj,
                defaults={'revenue': revenue_val}
            )
            count += 1

        if errors:
            messages.warning(request, f'Processed {count} rows with {len(errors)} errors: {"; ".join(errors[:5])}')
        else:
            messages.success(request, f'Successfully processed {count} rows.')
        return redirect('app:upload_actuals')

    return render(request, 'app/upload_actuals.html', {'verticals': verticals})


@login_required
def settings_company(request):
    """Manage Departments and Verticals."""
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_department':
            name = request.POST.get('dept_name', '').strip()
            owner_id = request.POST.get('dept_owner', '').strip()
            if name:
                Department.objects.create(
                    name=name,
                    owner_id=int(owner_id) if owner_id else None,
                )

        elif action == 'edit_department':
            dept_id = request.POST.get('item_id')
            dept = Department.objects.filter(pk=dept_id).first()
            if dept:
                dept.name = request.POST.get('dept_name', dept.name).strip()
                owner_id = request.POST.get('dept_owner', '').strip()
                dept.owner_id = int(owner_id) if owner_id else None
                dept.save()

        elif action == 'delete_department':
            item_id = request.POST.get('item_id')
            Department.objects.filter(pk=item_id).delete()

        elif action == 'add_vertical':
            name = request.POST.get('vert_name', '').strip()
            gm_id = request.POST.get('vert_gm', '').strip()
            if name:
                BusinessUnit.objects.create(
                    name=name,
                    general_manager_id=int(gm_id) if gm_id else None,
                )

        elif action == 'edit_vertical':
            item_id = request.POST.get('item_id')
            vert = BusinessUnit.objects.filter(pk=item_id).first()
            if vert:
                vert.name = request.POST.get('vert_name', vert.name).strip()
                gm_id = request.POST.get('vert_gm', '').strip()
                vert.general_manager_id = int(gm_id) if gm_id else None
                vert.save()

        elif action == 'delete_vertical':
            item_id = request.POST.get('item_id')
            BusinessUnit.objects.filter(pk=item_id).delete()

        return redirect('app:settings_company')

    departments = Department.objects.all()
    verticals = BusinessUnit.objects.all()
    users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    return render(request, 'app/settings_company.html', {
        'departments': departments,
        'verticals': verticals,
        'users': users,
    })


@login_required
def settings_rocks(request):
    """Manage Annual Rocks and Quarterly Rocks."""
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_annual_rock':
            name = request.POST.get('ar_name', '').strip()
            description = request.POST.get('ar_description', '').strip()
            year = request.POST.get('ar_year', '').strip()
            if name:
                Objective.objects.create(
                    name=name,
                    description=description,
                    year=int(year) if year else None,
                )

        elif action == 'edit_annual_rock':
            item_id = request.POST.get('item_id')
            rock = Objective.objects.filter(pk=item_id).first()
            if rock:
                rock.name = request.POST.get('ar_name', rock.name).strip()
                rock.description = request.POST.get('ar_description', rock.description).strip()
                year = request.POST.get('ar_year', '').strip()
                rock.year = int(year) if year else None
                rock.save()

        elif action == 'delete_annual_rock':
            item_id = request.POST.get('item_id')
            Objective.objects.filter(pk=item_id).delete()

        elif action == 'add_quarterly_rock':
            name = request.POST.get('qr_name', '').strip()
            if name:
                ar_id = request.POST.get('qr_annual_rock', '').strip()
                dept_id = request.POST.get('qr_department', '').strip()
                year = request.POST.get('qr_year', '').strip()
                quarter = request.POST.get('qr_quarter', '').strip()
                target = request.POST.get('qr_target_completion', '').strip()
                Project.objects.create(
                    name=name,
                    objective_id=int(ar_id) if ar_id else None,
                    department_id=int(dept_id) if dept_id else None,
                    year=int(year) if year else None,
                    quarter=int(quarter) if quarter else None,
                    target_completion=target if target else None,
                    why='',
                )

        elif action == 'edit_quarterly_rock':
            item_id = request.POST.get('item_id')
            rock = Project.objects.filter(pk=item_id).first()
            if rock:
                rock.name = request.POST.get('qr_name', rock.name).strip()
                ar_id = request.POST.get('qr_annual_rock', '').strip()
                rock.objective_id = int(ar_id) if ar_id else None
                dept_id = request.POST.get('qr_department', '').strip()
                rock.department_id = int(dept_id) if dept_id else None
                year = request.POST.get('qr_year', '').strip()
                rock.year = int(year) if year else None
                quarter = request.POST.get('qr_quarter', '').strip()
                rock.quarter = int(quarter) if quarter else None
                target = request.POST.get('qr_target_completion', '').strip()
                rock.target_completion = target if target else None
                rock.save()

        elif action == 'delete_quarterly_rock':
            item_id = request.POST.get('item_id')
            Project.objects.filter(pk=item_id).delete()

        return redirect('app:settings_rocks')

    annual_rocks = Objective.objects.order_by('year', 'name')
    quarterly_rocks = Project.objects.order_by('date_created')
    departments = Department.objects.all()

    return render(request, 'app/settings_rocks.html', {
        'annual_rocks': annual_rocks,
        'quarterly_rocks': quarterly_rocks,
        'departments': departments,
    })


@login_required
def settings_measurements(request):
    """Manage Metrics and KPIs."""
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_metric':
            name = request.POST.get('metric_name', '').strip()
            if name:
                Metric.objects.create(name=name, active=True)

        elif action == 'edit_metric':
            item_id = request.POST.get('item_id')
            metric = Metric.objects.filter(pk=item_id).first()
            if metric:
                metric.name = request.POST.get('metric_name', metric.name).strip()
                metric.save()

        elif action == 'delete_metric':
            item_id = request.POST.get('item_id')
            Metric.objects.filter(pk=item_id).delete()

        elif action == 'toggle_metric':
            item_id = request.POST.get('item_id')
            metric = Metric.objects.filter(pk=item_id).first()
            if metric:
                metric.active = not metric.active
                metric.save()

        elif action == 'add_kpi':
            name = request.POST.get('kpi_name', '').strip()
            if name:
                KPI.objects.create(name=name, active=True)

        elif action == 'edit_kpi':
            item_id = request.POST.get('item_id')
            kpi = KPI.objects.filter(pk=item_id).first()
            if kpi:
                kpi.name = request.POST.get('kpi_name', kpi.name).strip()
                kpi.save()

        elif action == 'delete_kpi':
            item_id = request.POST.get('item_id')
            KPI.objects.filter(pk=item_id).delete()

        elif action == 'toggle_kpi':
            item_id = request.POST.get('item_id')
            kpi = KPI.objects.filter(pk=item_id).first()
            if kpi:
                kpi.active = not kpi.active
                kpi.save()

        return redirect('app:settings_measurements')

    metrics = Metric.objects.all()
    kpis = KPI.objects.all()

    return render(request, 'app/settings_measurements.html', {
        'metrics': metrics,
        'kpis': kpis,
    })


@login_required
def help_page(request):
    return render(request, 'app/help.html')


# --- Analytics dashboards -------------------------------------------------

def _analytics_filter(request):
    """Resolve and validate the (period, comparison) filter selection, and
    return the common filter context shared by every analytics dashboard."""
    from app import analytics_data as ad

    valid_primary = dict((c, d) for c, d, _ in ad.PRIMARY_OPTIONS)

    # Period: an explicit ?period= is a fresh selection; otherwise fall back to
    # the last-used value from the session so selections persist across the
    # analytics dashboards.
    primary = request.GET.get('period') or request.session.get('analytics_period') or ad.DEFAULT_PRIMARY
    if primary not in valid_primary:
        primary = ad.DEFAULT_PRIMARY

    valid_compares = [c for c, _ in ad.COMPARE_OPTIONS.get(primary, [])]
    if 'period' in request.GET:
        # Changing the period resets the comparison (server picks a valid one).
        compare = request.GET.get('compare', '')
    else:
        compare = request.session.get('analytics_compare', '')
    if compare not in valid_compares:
        compare = ad.default_compare(primary)

    # Remember the selection for the other dashboards.
    request.session['analytics_period'] = primary
    request.session['analytics_compare'] = compare

    # Custom period: explicit start/end dates (from GET, else session).
    custom_start = request.GET.get('custom_start') or request.session.get('analytics_custom_start') or ''
    custom_end = request.GET.get('custom_end') or request.session.get('analytics_custom_end') or ''
    if primary == 'CUSTOM':
        cs, ce = _parse_iso(custom_start), _parse_iso(custom_end)
        if not (cs and ce and cs <= ce):  # default to the last 30 days
            ce = date.today() - timedelta(days=1)
            cs = ce - timedelta(days=29)
        custom_start, custom_end = cs.isoformat(), ce.isoformat()
        request.session['analytics_custom_start'] = custom_start
        request.session['analytics_custom_end'] = custom_end

    ctx = {
        'primary_options': ad.PRIMARY_OPTIONS,
        'compare_options': ad.COMPARE_OPTIONS.get(primary, []),
        'selected_primary': primary,
        'selected_compare': compare,
        'primary_label': ad.primary_label(primary),
        'compare_label': ad.compare_label(primary, compare),
        'selected_custom_start': custom_start,
        'selected_custom_end': custom_end,
    }
    from app.integrations import ga4_dashboard
    ctx['signin_prompt'] = ga4_dashboard.signin_prompt(request)
    return primary, compare, ctx


def _parse_iso(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _ga4_rows(request, primary, compare):
    """Real GA4 rows for the current scope, or None (dummy fallback)."""
    from app.integrations import ga4_dashboard
    return ga4_dashboard.ga4_rows(request, primary, compare)


@login_required
def analytics_grow_sales(request):
    from app import analytics_data as ad
    from strategy.models import Objective
    primary, compare, ctx = _analytics_filter(request)
    cards, charts = ad.build_grow_sales(primary, compare, rows=_ga4_rows(request, primary, compare))
    # Name the objective each AEE pillar drives, as a separate (contextual) field
    # so the template can style it lighter than the prominent AEE label.
    yr = date.today().year
    for card_key, aee in (('attract', 'attract_traffic'), ('engage', 'engage_customers'), ('expand', 'expand_purchase')):
        obj = (Objective.objects.filter(aee_alignment=aee, year=yr).first()
               or Objective.objects.filter(aee_alignment=aee).first())
        if obj and card_key in cards:
            cards[card_key]['objective'] = obj.name
    ctx.update({'cards': cards, 'charts_json': json.dumps(charts)})
    return render(request, 'app/analytics/grow_sales.html', ctx)


@login_required
def analytics_attract_traffic(request):
    from app import analytics_data as ad
    from app.integrations import ga4_dashboard
    primary, compare, ctx = _analytics_filter(request)
    d = ad.build_attract_traffic(
        primary, compare,
        rows=_ga4_rows(request, primary, compare),
        splits=ga4_dashboard.ga4_splits(request, primary, compare))
    ctx.update({
        'cards': d['cards'],
        'charts_json': json.dumps(d['charts']),
        'scatter_json': json.dumps(d['scatter']),
    })
    return render(request, 'app/analytics/attract_traffic.html', ctx)


@login_required
def analytics_engage_customers(request):
    from app import analytics_data as ad
    from app.integrations import ga4_dashboard
    primary, compare, ctx = _analytics_filter(request)
    d = ad.build_engage_customer(
        primary, compare,
        rows=_ga4_rows(request, primary, compare),
        eng=ga4_dashboard.ga4_engage_metrics(request, primary, compare),
        live=ga4_dashboard.is_connected(request),
        segments=ga4_dashboard.ga4_segments(request, primary, compare))
    ctx.update({
        'cards': d['cards'],
        'history': d['history'],
        'scatter': d['scatter'],
        'charts_json': json.dumps(d['charts']),
        'scatter_json': json.dumps(d['scatter']),
    })
    return render(request, 'app/analytics/engage_customers.html', ctx)


@login_required
def analytics_performance_story(request):
    from app import performance_story as ps
    from app.integrations import ga4_dashboard
    primary, compare, ctx = _analytics_filter(request)
    fundamentals = ga4_dashboard.ga4_story_fundamentals(request, primary, compare)
    ctx.update(ps.build_performance_story(primary, compare, fundamentals=fundamentals))
    return render(request, 'app/analytics/performance_story.html', ctx)


@login_required
def analytics_expand_purchases(request):
    from app import analytics_data as ad
    primary, compare, ctx = _analytics_filter(request)
    from app.integrations import ga4_dashboard
    is_premium = ga4_dashboard._premium_connection(request) is not None
    d = ad.build_expand_purchases(
        primary, compare,
        rows=_ga4_rows(request, primary, compare),
        live=ga4_dashboard.is_connected(request),
        item=ga4_dashboard.ga4_item_metrics(request, primary, compare),
        is_premium=is_premium)
    ctx.update({
        'cards': d['cards'],
        'history': d['history'],
        'scatter': d['scatter'],
        'charts_json': json.dumps(d['charts']),
        'scatter_json': json.dumps(d['scatter']),
    })
    return render(request, 'app/analytics/expand_purchases.html', ctx)


@login_required
def work_in_progress(request):
    """Work In Progress — the active-actions gantt (moved off the dashboard)."""
    vertical_id = scoped_vertical_id(request)
    company_id = scoped_company_id(request)

    # Execution tasks (Actions) of WIP projects -- the parent Project carries the
    # Kanban status now, so filter by it (not the vestigial Action.status).
    # WIP drives the current-period windows; On Deck is carried too but the
    # template only renders it in the forward-looking periods (next month/quarter/
    # year) so you can see the pipeline queued up ahead.
    projects = _scope_to(
        Action.objects.filter(project__status__in=('WIP', 'On Deck'), project__archived=False)
        .select_related('project', 'objective', 'team').prefetch_related('depends_on')
        .order_by('-project__normalized_score'),
        vertical_id, company_id)

    gantt = _build_gantt_data(projects)

    # Optional focus: highlight one action and open the smallest period that
    # contains its launch date so the user can see what's ahead of it.
    focus_id = request.GET.get('focus', '')
    try:
        focus_id = int(focus_id) if focus_id else None
    except (ValueError, TypeError):
        focus_id = None

    initial_period = 'mtd'
    if focus_id:
        focus_action = Action.objects.filter(pk=focus_id).first()
        launch = focus_action.launch.isoformat() if (focus_action and focus_action.launch) else None
        if launch:
            for key in ('mtd', 'qtd', 'ytd', 'nmo', 'nq', 'ny'):
                p = gantt['periods'][key]
                if p['start'] <= launch <= p['end']:
                    initial_period = key
                    break
            else:
                initial_period = 'ytd'
        else:
            initial_period = 'ytd'

    return render(request, 'app/work_in_progress.html', {
        'gantt_data': json.dumps(gantt),
        'focus_id': focus_id,
        'initial_period': initial_period,
    })


@login_required
def data_connection(request):
    """Settings > Data Connection. Two methods:
      * GA4 Standard  -- sign in with Google, discover + import properties.
      * GA4 Premium   -- a service account reading the GA4 -> BigQuery export."""
    import json as _json
    from django.utils.text import slugify
    from app.integrations import google_oauth, ga4_admin, bigquery as bqmod
    from business_unit import provisioning
    from business_unit.models import Company, BusinessUnit, CompanyMembership, BigQueryConnection

    identity = getattr(request.user, 'google_identity', None)
    ctx = {'title': 'Data Connection', 'has_google': identity is not None,
           'google_enabled': google_oauth.is_enabled(),
           'bigquery_available': bqmod.is_available()}

    # --- Premium: connect a Company via a BigQuery service account ------------
    if request.method == 'POST' and request.POST.get('action') == 'bigquery_connect':
        from business_unit.access import can_manage_bigquery
        if not can_manage_bigquery(request.user):
            return HttpResponseForbidden(
                'Only owners, executives, developers, and superusers can manage a BigQuery connection.')
        name = request.POST.get('company_name', '').strip()
        prop = request.POST.get('property_id', '').strip()
        try:
            sa = _json.loads(request.POST.get('service_account_json', '').strip() or '{}')
        except ValueError:
            messages.error(request, 'Service account JSON is not valid JSON.')
            return redirect('app:data_connection')
        if not (name and prop and sa):
            messages.error(request, 'Company name, GA4 property id and service account JSON are required.')
            return redirect('app:data_connection')
        ok, msg, latest = bqmod.test_connection(sa, prop)
        if not ok:
            messages.error(request, f'Connection test failed: {msg}')
            return redirect('app:data_connection')
        # Event map: standard name -> this company's actual event name (only keep
        # overrides that differ from the standard).
        event_map = {}
        for ev in BigQueryConnection.STANDARD_EVENTS:
            actual = request.POST.get(f'event__{ev}', '').strip()
            if actual and actual != ev:
                event_map[ev] = actual
        company, _ = Company.objects.get_or_create(slug=slugify(name), defaults={'name': name})
        BusinessUnit.objects.get_or_create(company=company, ga4_property_id=prop, defaults={'name': name})
        BigQueryConnection.objects.update_or_create(company=company, defaults={
            'service_account_json': sa, 'gcp_project': sa.get('project_id', ''),
            'event_map': event_map, 'data_through': latest, 'created_by': request.user})
        CompanyMembership.objects.get_or_create(company=company, user=request.user, defaults={'role': 'admin'})
        messages.success(request, f'Premium (BigQuery) connected for {name}. {msg}')
        return redirect('app:data_connection')

    # Premium companies this user already has connected.
    ctx['premium_companies'] = list(
        Company.objects.filter(bigquery__isnull=False, memberships__user=request.user).distinct()
        if not request.user.is_superuser else Company.objects.filter(bigquery__isnull=False))
    ctx['standard_events'] = BigQueryConnection.STANDARD_EVENTS
    from business_unit.access import can_manage_bigquery
    ctx['can_provision_premium'] = can_manage_bigquery(request.user)

    if not identity or not google_oauth.is_enabled():
        return render(request, 'app/data_connection.html', ctx)

    # Discover live from GA4 (on the user's behalf). Transient Google outages
    # (503/429/timeout) are already retried in the client; if they still fail we
    # show a friendly "try again" state rather than a raw error.
    from app.integrations._retry import is_transient
    try:
        creds = google_oauth.credentials_from_identity(identity)
        hierarchy = ga4_admin.discover_hierarchy(creds)
    except Exception as e:
        logger.exception('GA4 discovery failed')
        if is_transient(e):
            ctx['transient'] = True
        else:
            ctx['error'] = 'We couldn’t reach Google Analytics. Please try again.'
        return render(request, 'app/data_connection.html', ctx)

    if request.method == 'POST':
        selected = request.POST.getlist('property_ids')
        if selected:
            summary = provisioning.import_hierarchy(request.user, hierarchy, selected)
            messages.success(
                request,
                f"Imported {summary['verticals']} property(ies) and "
                f"{summary['websites']} website(s) across {summary['companies']} company(ies).")
        else:
            messages.info(request, 'No properties selected.')
        return redirect('app:data_connection')

    ctx['hierarchy'] = hierarchy
    ctx['imported_ids'] = provisioning.imported_property_ids(request.user)
    ctx['property_count'] = sum(len(a['properties']) for a in hierarchy)
    return render(request, 'app/data_connection.html', ctx)


@login_required
def settings_users(request):
    """Deprecated — user + role management is now merged into manage_users
    (Manage Users). Kept as a redirect so old links/bookmarks still resolve."""
    return redirect('app:manage_users')


def _settings_users_legacy(request):
    """Manage Users — restricted to admin and senior_leadership roles."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role not in ('admin', 'senior_leadership'):
        return HttpResponseForbidden('You do not have permission to access this page.')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_user':
            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            role = request.POST.get('role', 'staff')
            dept_id = request.POST.get('department', '').strip()
            password = request.POST.get('password', '').strip()
            if username and password:
                user = User.objects.create_user(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                )
                user.profile.role = role
                user.profile.department_id = int(dept_id) if dept_id else None
                user.profile.save()

        elif action == 'edit_user':
            user_id = request.POST.get('item_id')
            user = User.objects.filter(pk=user_id).first()
            if user:
                user.first_name = request.POST.get('first_name', user.first_name).strip()
                user.last_name = request.POST.get('last_name', user.last_name).strip()
                user.email = request.POST.get('email', user.email).strip()
                user.save()
                role = request.POST.get('role', '').strip()
                dept_id = request.POST.get('department', '').strip()
                if role:
                    user.profile.role = role
                user.profile.department_id = int(dept_id) if dept_id else None
                user.profile.save()

        elif action == 'delete_user':
            user_id = request.POST.get('item_id')
            User.objects.filter(pk=user_id).delete()

        return redirect('app:settings_users')

    all_users = User.objects.select_related('profile', 'profile__department').filter(is_active=True).order_by('username')
    departments = Department.objects.all()

    return render(request, 'app/settings_users.html', {
        'all_users': all_users,
        'role_choices': ROLE_CHOICES,
        'departments': departments,
    })


@login_required
def manage_users(request):
    """Unified user + role + company-access management.

    One screen, company-centric: adding a person to a company assigns their role
    in the same step. It creates/links their user (matched by email, so a later
    Google sign-in inherits access), sets their role, and grants a
    CompanyMembership. Company data access is by membership existence; the
    membership's admin/member level mirrors the assigned role so company admins
    can manage their own company.
    """
    from business_unit.models import Company, CompanyMembership
    from users.models import KIBOKO_ROLES

    ROLE_KEYS = dict(KIBOKO_ROLES)
    ADMIN_ROLES = ('executive', 'business_unit_leader')  # roles that administer a company

    user = request.user
    profile = getattr(user, 'profile', None)
    is_global_admin = (user.is_superuser or user.administered_orgs.exists()
                       or (profile and profile.has_role('executive')))
    if is_global_admin:
        companies = Company.objects.all().order_by('name')
    else:
        companies = Company.objects.filter(
            memberships__user=user, memberships__role='admin',
        ).distinct().order_by('name')
    if not is_global_admin and not companies.exists():
        return HttpResponseForbidden('You do not have permission to manage users.')

    def _set_roles(member, roles_list):
        """Set the user's Kiboko roles; mirror company-admin membership from them."""
        member.profile.roles = roles_list
        member.profile.save(update_fields=['roles'])
        elevated = any(r in ADMIN_ROLES for r in roles_list)
        CompanyMembership.objects.filter(user=member).update(role='admin' if elevated else 'member')

    def _is_last_admin(company, member):
        """True if `member` is the only admin of `company` (block removal/demotion)."""
        admin_ids = set(CompanyMembership.objects.filter(
            company=company, role='admin').values_list('user_id', flat=True))
        return admin_ids == {member.id}

    def _flash_starter_creds(member, company):
        """Flash the starter-login popup for a user who still has a pending starter
        password (kept from account creation) and hasn't set their own yet. Called
        after both 'add' and 'save roles' so the popup reflects the final role(s)."""
        pw = request.session.get('starter_pw_by_uid', {}).get(str(member.id))
        prof = getattr(member, 'profile', None)
        if not (pw and prof and prof.must_change_password):
            return False
        request.session['new_user_creds'] = {
            'name': member.get_full_name() or member.email or member.username,
            'username': member.username, 'password': pw,
            'roles': [ROLE_KEYS.get(r, r) for r in (prof.roles or [])],
            'company': company.name,
            'login_url': request.build_absolute_uri(reverse('users:login')),
        }
        return True

    def _gen_username(email):
        """Default login = the part before '@' in the email, made unique."""
        local = email.split('@')[0].lower()
        base = ''.join(ch for ch in local if ch.isalnum() or ch in '._-') or 'user'
        base = base[:150]
        username, i = base, 1
        while User.objects.filter(username__iexact=username).exists():
            i += 1
            username = f'{base[:150 - len(str(i))]}{i}'
        return username

    if request.method == 'POST':
        action = request.POST.get('action', '')
        company = companies.filter(pk=request.POST.get('company', '')).first()

        if action == 'add_member' and company:
            email = request.POST.get('email', '').strip()
            first = request.POST.get('first_name', '').strip()
            last = request.POST.get('last_name', '').strip()
            roles_list = [r for r in request.POST.getlist('roles') if r in ROLE_KEYS]
            if not email:
                messages.error(request, 'Enter an email or Google account.')
            elif not roles_list:
                messages.error(request, 'Select at least one role for the new user.')
            else:
                member = (User.objects.filter(email__iexact=email).first()
                          or User.objects.filter(username__iexact=email).first())
                starter_pw = None
                if member is None:
                    member = User.objects.create_user(
                        username=_gen_username(email), email=email,
                        first_name=first, last_name=last)
                    # Give a random 8-char temporary password + force a change on first
                    # login, so non-Google users can sign in. (Google users log in
                    # without a password and never see this.)
                    import secrets
                    alphabet = ''.join(c for c in
                                       'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789')  # no I l 1 O 0
                    starter_pw = ''.join(secrets.choice(alphabet) for _ in range(8))
                    member.set_password(starter_pw)
                    member.save(update_fields=['password'])
                    member.profile.must_change_password = True
                    member.profile.save(update_fields=['must_change_password'])
                    # Keep the temporary password for this session so the popup can be
                    # re-shown (with final roles) after "Save roles".
                    by_uid = request.session.get('starter_pw_by_uid', {})
                    by_uid[str(member.id)] = starter_pw
                    request.session['starter_pw_by_uid'] = by_uid
                elif first or last:
                    member.first_name = first or member.first_name
                    member.last_name = last or member.last_name
                    member.save(update_fields=['first_name', 'last_name'])
                CompanyMembership.objects.get_or_create(
                    company=company, user=member, defaults={'role': 'member'})
                _set_roles(member, roles_list)          # the roles chosen on the add row
                if starter_pw:
                    # Roles are defined at add time, so pop the credentials now — the
                    # emailed login reflects the selected role(s).
                    _flash_starter_creds(member, company)
                    messages.success(request, f'Added {email} — copy their temporary login from the popup to email.')
                else:
                    messages.success(request, f'Added {email} to {company.name} with the selected role(s).')

        elif action == 'set_roles' and company:
            member = User.objects.filter(pk=request.POST.get('user_id', '')).first()
            if member and CompanyMembership.objects.filter(company=company, user=member).exists():
                roles_list = [r for r in request.POST.getlist('roles') if r in ROLE_KEYS]
                elevated = any(r in ADMIN_ROLES for r in roles_list)
                if not roles_list:
                    messages.error(request, 'Define at least one role before saving.')
                elif not elevated and _is_last_admin(company, member):
                    messages.error(request, f'{company.name} must keep at least one admin '
                                            '(Executive or Business Unit Leader).')
                else:
                    _set_roles(member, roles_list)
                    if _flash_starter_creds(member, company):
                        messages.success(request, f'Roles saved for {member.email or member.username} — '
                                                  'copy their temporary login from the popup.')
                    else:
                        messages.success(request, f'Updated roles for {member.email or member.username}.')

        elif action == 'show_login' and company:
            # On-demand: pop the starter-login popup for a user who hasn't set their
            # own password yet. Reissues a fresh temporary password if this session no
            # longer holds it (e.g. the account was added earlier).
            member = User.objects.filter(pk=request.POST.get('user_id', '')).first()
            if member and CompanyMembership.objects.filter(company=company, user=member).exists():
                if not member.profile.must_change_password:
                    messages.info(request, f'{member.email or member.username} has already set their own password.')
                else:
                    by_uid = request.session.get('starter_pw_by_uid', {})
                    if str(member.id) not in by_uid:
                        import secrets
                        alphabet = ''.join(c for c in
                                           'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789')
                        pw = ''.join(secrets.choice(alphabet) for _ in range(8))
                        member.set_password(pw); member.save(update_fields=['password'])
                        by_uid[str(member.id)] = pw
                        request.session['starter_pw_by_uid'] = by_uid
                    _flash_starter_creds(member, company)
                    messages.success(request, 'Temporary login ready — copy it from the popup.')

        elif action == 'remove_member' and company:
            m = CompanyMembership.objects.filter(
                pk=request.POST.get('membership_id', ''), company=company).first()
            if m and m.role == 'admin' and _is_last_admin(company, m.user):
                messages.error(request, f'{company.name} must keep at least one admin.')
            elif m:
                m.delete()
                messages.success(request, 'Removed access.')

        elif action == 'set_bus' and company:
            member = User.objects.filter(pk=request.POST.get('user_id', '')).first()
            m = CompanyMembership.objects.filter(company=company, user=member).first() if member else None
            if m:
                bus = company.verticals.filter(id__in=request.POST.getlist('allowed_bus'))
                m.allowed_bus.set(bus)
                n = bus.count()
                messages.success(request, '{} can now see {} in {}.'.format(
                    member.email or member.username,
                    'all business units' if n == 0 else f'{n} business unit(s)', company.name))

        return redirect('app:manage_users')

    companies_ctx = [{
        'company': c,
        'org': c.organization,
        'noun': 'Client' if c.organization and c.organization.kind == 'agency' else 'Company',
        'business_units': list(c.verticals.all()),
        'members': (CompanyMembership.objects.filter(company=c)
                    .select_related('user', 'user__profile')
                    .prefetch_related('allowed_bus')
                    .order_by('user__email', 'user__username')),
    } for c in companies]

    return render(request, 'app/manage_users.html', {
        'companies_ctx': companies_ctx,
        'kiboko_roles': KIBOKO_ROLES,
        'new_user_creds': request.session.pop('new_user_creds', None),   # -> starter-login popup
    })


@login_required
def billing(request):
    """Billing — visible only to organization admins. Shows plan/trial status,
    the billing address, and lets the admin cancel the account (data retained 90
    days, then deleted forever). Payment collection is wired to Stripe later."""
    import datetime
    from django.utils import timezone

    if not (request.user.is_superuser or request.user.administered_orgs.exists()):
        return HttpResponseForbidden('Billing is available to organization admins only.')
    org = request.user.administered_orgs.first()

    if request.method == 'POST' and org is not None:
        action = request.POST.get('action', '')
        if action == 'save_billing_address':
            org.billing_legal_name = (request.POST.get('billing_legal_name') or '').strip()
            org.billing_email = (request.POST.get('billing_email') or '').strip()
            org.billing_address1 = (request.POST.get('billing_address1') or '').strip()
            org.billing_address2 = (request.POST.get('billing_address2') or '').strip()
            org.billing_city = (request.POST.get('billing_city') or '').strip()
            org.billing_state = (request.POST.get('billing_state') or '').strip()
            org.billing_postal = (request.POST.get('billing_postal') or '').strip()
            org.billing_country = (request.POST.get('billing_country') or '').strip()
            org.save()
            messages.success(request, 'Billing address saved.')
        elif action == 'cancel_account':
            org.plan_status = 'canceled'
            org.canceled_at = timezone.now()
            org.purge_after = datetime.date.today() + datetime.timedelta(days=org.PURGE_DAYS)
            org.save(update_fields=['plan_status', 'canceled_at', 'purge_after'])
            # No flash message here — the persistent canceled banner below already
            # states the retention window and offers Reactivate.
        elif action == 'reactivate':
            org.plan_status = 'trial' if org.trial_started else 'active'
            org.canceled_at = None
            org.purge_after = None
            org.save(update_fields=['plan_status', 'canceled_at', 'purge_after'])
            messages.success(request, 'Welcome back — your account is active again.')
        return redirect('app:billing')

    return render(request, 'app/billing.html', {'title': 'Billing', 'organization': org})


def _org_for(user):
    """The org a user administers, else the org of a real company they belong to."""
    from business_unit.access import real_companies
    org = user.administered_orgs.first()
    if org is None:
        rc = real_companies(user).first()
        org = rc.organization if rc else None
    return org


def getting_started_steps(user):
    """Shared onboarding checklist for an org's setup. Returns (org, steps) where
    each step is a dict {key, label, desc, url, done}. Used by the Getting Started
    page and the "Return to Getting Started" banner shown on each step's page."""
    from django.urls import reverse
    from business_unit.models import (Company, CompanyMembership, BigQueryConnection, BusinessUnit)
    from app.models import MonthlyGoal

    org = _org_for(user)
    if org is None:
        return None, []

    company_ids = list(org.companies.values_list('id', flat=True))
    is_agency = org.kind == 'agency'
    member_count = (CompanyMembership.objects.filter(company_id__in=company_ids)
                    .values('user').distinct().count())
    has_data = (BigQueryConnection.objects.filter(company_id__in=company_ids).exists()
                or BusinessUnit.objects.filter(company_id__in=company_ids)
                .exclude(ga4_property_id='').exists())
    details_done = any(c.details_complete() for c in Company.objects.filter(id__in=company_ids))

    first_co_label = 'Add your first client' if is_agency else 'Add your company details'
    first_co_desc = ('Add your first client’s legal name, address, and website.' if is_agency
                     else 'Add your company’s legal name, address, and website.')
    steps = [
        {'key': 'company', 'label': first_co_label, 'done': details_done,
         'url': reverse('app:company_details'), 'desc': first_co_desc},
        {'key': 'team', 'label': 'Invite your team', 'done': member_count >= 2,
         'url': reverse('app:manage_users'), 'desc': 'Add users and set each one’s role and business units.'},
        {'key': 'data', 'label': 'Connect analytics data', 'done': has_data,
         'url': reverse('app:data_connection'), 'desc': 'Connect GA4 (Standard) or a BigQuery service account (Premium).'},
        {'key': 'budget', 'label': 'Set your budget', 'done': MonthlyGoal.objects.filter(vertical__company_id__in=company_ids).exists(),
         'url': reverse('app:edit_goals'), 'desc': 'Enter monthly revenue targets per business unit.'},
    ]
    return org, steps


@login_required
def getting_started(request):
    """Onboarding checklist for an org's setup: add company details, invite the
    team, connect data, set goals. Scoped to the viewer's organization."""
    org, steps = getting_started_steps(request.user)
    if org is None:
        return render(request, 'app/getting_started.html', {'title': 'Getting Started', 'org': None, 'steps': []})
    noun = 'Client' if org.kind == 'agency' else 'Company'
    return render(request, 'app/getting_started.html', {
        'title': 'Getting Started', 'org': org, 'noun': noun, 'steps': steps,
        'done_count': sum(1 for s in steps if s['done']), 'total': len(steps)})


@login_required
def company_details(request):
    """Org-admin-scoped page to edit each company's details (legal name, address,
    website), with an option to reuse the organization's billing address."""
    from business_unit.models import Company

    org = _org_for(request.user)
    is_admin = request.user.is_superuser or (org is not None and org.org_admin_id == request.user.id)
    if org is None or not is_admin:
        return render(request, 'app/company_details.html', {
            'title': 'Company Details', 'org': org, 'forbidden': True})

    companies = list(org.companies.all().order_by('name'))
    if request.method == 'POST':
        company = next((c for c in companies if str(c.id) == request.POST.get('company', '')), None)
        if company is not None:
            company.legal_name = (request.POST.get('legal_name') or '').strip()
            company.website = (request.POST.get('website') or '').strip()
            company.same_as_billing = bool(request.POST.get('same_as_billing'))
            if company.same_as_billing:
                # Copy the org billing address so the stored company address stays in sync.
                company.address1 = org.billing_address1
                company.address2 = org.billing_address2
                company.city = org.billing_city
                company.state = org.billing_state
                company.postal = org.billing_postal
                company.country = org.billing_country
            else:
                company.address1 = (request.POST.get('address1') or '').strip()
                company.address2 = (request.POST.get('address2') or '').strip()
                company.city = (request.POST.get('city') or '').strip()
                company.state = (request.POST.get('state') or '').strip()
                company.postal = (request.POST.get('postal') or '').strip()
                company.country = (request.POST.get('country') or '').strip()
            company.save()
            messages.success(request, f'Saved details for {company.name}.')
            return redirect('app:company_details')

    noun = 'Client' if org.kind == 'agency' else 'Company'
    return render(request, 'app/company_details.html', {
        'title': 'Company Details', 'org': org, 'companies': companies, 'noun': noun,
        'has_billing': org.has_billing_address(),
        'billing_lines': org.billing_address_lines()})


# The six BVM criteria, in scoring order, carrying the given per-company weights
# plus the shared labels/hints/invert flags from project.scoring.
def _scoring_criteria(weights):
    from project.scoring import CRITERIA, CRITERIA_META, INVERTED
    rows = []
    for f in CRITERIA:
        label, hint = CRITERIA_META[f]
        rows.append({'field': f, 'label': label, 'hint': hint,
                     'weight': weights[f], 'invert': f in INVERTED})
    return rows


def _weight_companies(user):
    """Companies a user may set score weights for -- only executives and org
    admins: all for a superuser, an org admin's companies, and (for the Executive
    role) the companies they belong to."""
    from business_unit.models import Company
    if user.is_superuser:
        return Company.objects.all().order_by('name')
    ids = set()
    admin_org_ids = list(user.administered_orgs.values_list('id', flat=True))
    if admin_org_ids:
        ids |= set(Company.objects.filter(
            organization_id__in=admin_org_ids).values_list('id', flat=True))
    prof = getattr(user, 'profile', None)
    if prof and prof.has_role('executive'):
        ids |= set(user.company_memberships.values_list('company_id', flat=True))
    return Company.objects.filter(id__in=ids).order_by('name')


@login_required
def settings_score_weights(request):
    """Adjust the six BVM criteria weights per company. Executives and org admins
    only; weights are percentages and must sum to 100."""
    from project.models import ScoringWeights
    from project.scoring import CRITERIA, CRITERIA_META
    from project.services.kanban import is_executive

    if not is_executive(request.user):
        return HttpResponseForbidden('Only executives and org admins can adjust score weights.')
    companies = _weight_companies(request.user)
    if not companies.exists():
        return HttpResponseForbidden('You do not administer any companies.')

    if request.method == 'POST':
        company = companies.filter(pk=request.POST.get('company', '')).first()
        if not company:
            messages.error(request, 'Unknown company.')
            return redirect('app:settings_score_weights')
        vals = {}
        for c in CRITERIA:
            try:
                vals[c] = max(0, min(100, int(request.POST.get(c, 0))))
            except (TypeError, ValueError):
                vals[c] = 0
        if sum(vals.values()) != 100:
            messages.error(request, f'Weights must sum to 100 (they add up to {sum(vals.values())}).')
        else:
            row, _ = ScoringWeights.objects.get_or_create(company=company)
            for c in CRITERIA:
                setattr(row, c, vals[c])
            row.save()
            messages.success(request, f'Saved score weights for {company.name}.')
        return redirect('app:settings_score_weights')

    companies_ctx = []
    for company in companies:
        w = ScoringWeights.for_company(company)
        rows = [{'field': f, 'label': CRITERIA_META[f][0], 'hint': CRITERIA_META[f][1],
                 'weight': w[f]} for f in CRITERIA]
        companies_ctx.append({
            'company': company, 'rows': rows, 'total': sum(w.values()),
            'customized': ScoringWeights.objects.filter(company=company).exists(),
        })
    return render(request, 'app/settings_score_weights.html', {
        'title': 'Score Weights', 'companies_ctx': companies_ctx})


@login_required
def settings_estimator(request):
    """Per-company impact-estimator assumptions. Executives / org admins only."""
    from project.models import EstimatorSettings
    from project.services import impact
    from project.services.kanban import is_executive
    if not is_executive(request.user):
        return HttpResponseForbidden('Only executives and org admins can edit estimator settings.')
    companies = _weight_companies(request.user)
    if not companies.exists():
        return HttpResponseForbidden('You do not administer any companies.')

    if request.method == 'POST':
        company = companies.filter(pk=request.POST.get('company', '')).first()
        if not company:
            messages.error(request, 'Unknown company.')
            return redirect('app:settings_estimator')
        s, _ = EstimatorSettings.objects.get_or_create(company=company)
        try:
            s.margin_factor = max(Decimal('0.01'), min(Decimal('1'),
                                  Decimal(str(request.POST.get('margin_factor', '0.35')))))
        except (InvalidOperation, TypeError):
            pass
        try:
            s.default_ramp_days = max(1, int(request.POST.get('default_ramp_days', 30)))
        except (TypeError, ValueError):
            pass
        try:
            s.baseline_window_days = max(7, int(request.POST.get('baseline_window_days', 90)))
        except (TypeError, ValueError):
            pass
        s.save()
        impact.recompute_scores(company=company)   # margin change flows into scores
        messages.success(request, f'Saved estimator settings for {company.name}.')
        return redirect('app:settings_estimator')

    companies_ctx = [{'company': c, 's': EstimatorSettings.current(c)} for c in companies]
    return render(request, 'app/settings_estimator.html', {
        'title': 'Edit Estimator', 'companies_ctx': companies_ctx})


@login_required
def score_projects(request):
    """Anonymous, all-hands BVM scoring.

    Every pertinent user -- the members of a project's business unit plus the
    company's executives -- votes on each project. The project's score is the
    average of all votes and it only advances to Scored once everyone has voted.
    A per-project progress bar shows how many eligible voters have submitted.
    You see and edit only your own vote; individual votes are never shown.
    """
    from project.services.kanban import LANE_STATUS, PIPELINE_STATUSES
    from project.services import voting
    from project.scoring import VOTED_CRITERIA, CRITERIA_META
    from project.models import ScoringWeights, ScoreVote
    from strategy.models import Project

    if request.method == 'POST':
        pid = request.POST.get('project_id')
        proj = Project.objects.filter(id=pid, archived=False).first()
        if not proj or not voting.is_eligible(proj, request.user):
            messages.error(request, 'You are not among the voters for that project.')
            return redirect(request.get_full_path())
        values = {}
        for c in VOTED_CRITERIA:
            try:
                values[c] = int(request.POST.get(c, 0))
            except (TypeError, ValueError):
                values[c] = 0
        _, finalized = voting.record_vote(proj, request.user, values)
        if finalized:
            messages.success(request, f'All scores are in — “{proj.name or "project"}” moved to Scored.')
        else:
            prog = voting.vote_progress(proj)
            messages.success(request, f'Your score was saved ({prog["voted"]} of {prog["total"]} voted).')
        return redirect(request.get_full_path())

    vertical_id = scoped_vertical_id(request)
    company_id = scoped_company_id(request)
    qs = _scope_to(Project.objects.filter(
        archived=False, approved=True, status=LANE_STATUS['ready_to_score'],
    ).select_related('owner', 'objective', 'vertical', 'vertical__company', 'department'),
        vertical_id, company_id)

    # Only projects the current user is a voter on, ordered: not-yet-voted first,
    # then by projected value so the highest-stakes decisions surface.
    my_votes = {v.project_id: v for v in ScoreVote.objects.filter(user=request.user)}
    projects = []
    for p in qs:
        eligible = voting.eligible_scorer_ids(p)
        if request.user.id not in eligible:
            continue
        p.progress = voting.vote_progress(p, eligible=eligible)
        p.my_vote = my_votes.get(p.id)
        p.has_voted = p.my_vote is not None
        # Estimator context for voters: gross + risk-adjusted expected + realized-this-year.
        est = p._estimate()
        p.est_gross = int(round(est['gross_annual'])) if est else (p.value or 0)
        p.est_expected = int(round(est['expected_realized'])) if est else None
        p.est_realized = int(round(est['realized_annual'])) if est else None
        # Only the five voted criteria have sliders (LOE is the developer's input).
        crit = [c for c in _scoring_criteria(ScoringWeights.for_company(p._company()))
                if c['field'] in VOTED_CRITERIA]
        vote_vals = p.my_vote.as_values() if p.my_vote else {}
        p.score_rows = [dict(c, value=vote_vals.get(c['field'], 0)) for c in crit]
        projects.append(p)

    projects.sort(key=lambda p: (p.has_voted, -(p.value or 0), p.aee_alignment or 'zzz'))
    total_value = sum((p.value or 0) for p in projects)
    pending = sum(1 for p in projects if not p.has_voted)

    return render(request, 'app/score_projects.html', {
        'title': 'Score Projects',
        'projects': projects,
        'criteria_labels': [CRITERIA_META[f][0] for f in VOTED_CRITERIA],
        'total_value': total_value,
        'pending_count': pending,
    })


@login_required
def feedback(request):
    """Send user feedback to the configured address via SendGrid. If SendGrid
    isn't configured yet, the feedback is logged (not lost) and the user still
    gets a friendly confirmation."""
    if request.method != 'POST':
        return redirect('app:analytics_grow_sales')
    from app.integrations import sendgrid_mail
    back = request.POST.get('next') or 'app:analytics_grow_sales'
    msg = (request.POST.get('message') or '').strip()
    if not msg:
        messages.error(request, 'Please enter your feedback before sending.')
        return redirect(back)

    u = request.user
    who = u.get_full_name() or u.username
    cfg = sendgrid_mail.get_settings()
    to = cfg.feedback_to if cfg else 'feedback@kibokomethod.com'
    subject = f'Kiboko feedback from {who}'
    body = (f'From: {who} <{u.email}>\nUser id: {u.id}\n'
            f'Page: {request.POST.get("next") or ""}\n\n{msg}')
    ok, detail = sendgrid_mail.send(to, subject, body, reply_to=(u.email or None))
    if not ok:
        # Capture it server-side until SendGrid is live so nothing is lost.
        logging.getLogger('app.feedback').warning(
            'FEEDBACK (unsent: %s) from %s <%s>: %s', detail, u.username, u.email, msg)
    messages.success(request, 'Thanks for your feedback — the Kiboko team will see it.')
    return redirect(back)


@login_required
def insights(request):
    """Wins & Losses: metrics up/down >=10% vs the comparison period, each with
    recommended actions (admin-editable) that can be promoted to projects. Bridges
    Analytics and Project Prioritization; honors the current scope + period."""
    from app import analytics_data as ad, insights as I
    primary, compare, ctx = _analytics_filter(request)
    rows = _ga4_rows(request, primary, compare)
    metrics = ad.build_metrics(primary, compare, rows=rows)
    wins, losses = I.classify(metrics)
    ctx.update({'title': 'Insights', 'wins': wins, 'losses': losses,
                'win_threshold': int(I.WIN_THRESHOLD)})
    return render(request, 'app/insights.html', ctx)


@login_required
def insights_add_project(request):
    """Create a draft Project (the scored unit) from a recommendation, scoped to
    the current business unit and linked to the metric's objective. It enters the
    intake pipeline (Incomplete Entry, unapproved) to be approved, sized, and
    scored in Project Prioritization."""
    if request.method != 'POST':
        return redirect('app:insights')
    from datetime import date
    from django.urls import reverse
    from django.utils.html import format_html
    from app import insights as I
    from app.models import MetricRecommendation
    from strategy.models import Project, Objective
    from business_unit.models import Department
    from project.services import impact

    rec = MetricRecommendation.objects.filter(pk=request.POST.get('recommendation_id')).first()
    if not rec:
        messages.error(request, 'Recommendation not found.')
        return redirect('app:insights')

    profile = getattr(request.user, 'profile', None)
    dept = (profile.department if profile and profile.department_id else None) or Department.objects.first()
    if dept is None:
        dept, _ = Department.objects.get_or_create(name='General')

    vid = scoped_vertical_id(request)
    bu = BusinessUnit.objects.filter(pk=vid).first() if vid else None
    kw = I.objective_keyword(rec.metric)
    objective = Objective.objects.filter(name__icontains=kw).first() if kw else None
    metric_label = dict(I.METRIC_CHOICES).get(rec.metric, rec.metric)
    moving = 'improving' if rec.direction == 'win' else 'declining'

    # Don't re-add a recommendation that's already queued (same name, same company).
    name = rec.text[:75].strip()
    existing = Project.objects.filter(archived=False, name__iexact=name)
    existing = existing.filter(vertical__company=bu.company) if bu is not None else existing.filter(vertical__isnull=True)
    dup = existing.first()
    if dup is not None:
        messages.warning(request, format_html(
            '“{}” is already in <a href="{}">Project Prioritization</a> — not added again.',
            dup.name, reverse('project:approve_projects')))
        return redirect(request.POST.get('next') or 'app:insights')

    # User Story and Definition of Done are left blank — the owner writes a proper
    # story (correct format) and real acceptance criteria when completing the entry
    # (it lands in Incomplete Entries either way). The insight's context is kept as
    # a comment below.
    from project.views import _quarter_end
    p = Project(
        name=name, owner=request.user, vertical=bu, department=dept,
        objective=objective, year=date.today().year, approved=False,
        target_completion=_quarter_end(date.today()),   # default go-live: end of quarter
        why='', definition_of_done='')
    p.save()   # derive_status -> 'Incomplete Entry' (intake); approved=False
    impact.recompute_scores(company=p._company())
    # Keep the insight's context (not in the user story) as an audit comment.
    from strategy.models import ProjectComment
    ProjectComment.objects.create(
        project=p, author=request.user, approved_comment=True,
        text=f'From Insights: {metric_label} is {moving}. {rec.text}')

    messages.success(request, format_html(
        'Added to Project Prioritization: “{}” is in <a href="{}">intake</a> awaiting '
        'business-unit approval before it can be scored.',
        p.name, reverse('project:approve_projects')))
    return redirect(request.POST.get('next') or 'app:insights')
