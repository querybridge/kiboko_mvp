import calendar
import csv
import datetime as dt
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.template import loader
from django.http import HttpResponse, HttpResponseRedirect
from django.db import models
from django.db.models import Q, Sum, Count, F, Avg
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from app.forms import StrategyForm
from users.models import ROLE_CHOICES, UserProfile
from app.models import MonthlyGoal, DailyActual
from business_unit.models import BusinessUnit, Vertical
from project.models import Action
from strategy.models import Project, Objective, Metric, KPI
from project.views import project_detail


def calculate_forecast(year, month, return_components=False, vertical_id=None):
    """Calculate forecast for a given month using weekday-weighted projection.

    For the current month: uses actuals-to-date + day-of-week projected remainder.
    For future months with no actuals: falls back to prior-year same-month
    actuals scaled by a YoY growth factor (this year budget / last year total).

    If return_components=True, returns (base_forecast, project_uplift) tuple.
    Otherwise returns total forecast (base + project uplift).
    """
    today = date.today()
    first_of_month = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    last_of_month = date(year, month, days_in_month)

    actuals_qs = DailyActual.objects.filter(
        date__year=year, date__month=month, date__lte=today
    )
    if vertical_id:
        actuals_qs = actuals_qs.filter(vertical_id=vertical_id)
    actuals_total = actuals_qs.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

    # Group actuals by day-of-week and compute averages
    dow_totals = defaultdict(Decimal)
    dow_counts = defaultdict(int)
    for a in actuals_qs:
        dow = a.date.weekday()  # 0=Mon ... 6=Sun
        dow_totals[dow] += a.revenue
        dow_counts[dow] += 1

    dow_avg = {}
    for dow in range(7):
        if dow_counts[dow] > 0:
            dow_avg[dow] = dow_totals[dow] / dow_counts[dow]
        else:
            dow_avg[dow] = Decimal('0')

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
        py_qs = DailyActual.objects.filter(date__year=prior_year, date__month=month)
        if vertical_id:
            py_qs = py_qs.filter(vertical_id=vertical_id)
        py_month_total = py_qs.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if py_month_total > 0:
            py_year_qs = DailyActual.objects.filter(date__year=prior_year)
            if vertical_id:
                py_year_qs = py_year_qs.filter(vertical_id=vertical_id)
            py_year_total = py_year_qs.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

            budget_qs = MonthlyGoal.objects.filter(month__year=year)
            if vertical_id:
                budget_qs = budget_qs.filter(vertical_id=vertical_id)
            this_year_budget = budget_qs.aggregate(s=Sum('budget'))['s'] or Decimal('0')

            if py_year_total > 0 and this_year_budget > 0:
                growth_scale = this_year_budget / py_year_total
                base_forecast = py_month_total * growth_scale

    # Add active action uplift — each action contributes its daily value
    # only for days in this month on or after its launch date
    projects = Action.objects.filter(
        status='WIP',
    ).filter(
        Q(launch__isnull=True) | Q(launch__lte=last_of_month)
    )
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)
    project_uplift = Decimal('0')
    for p in projects:
        daily_value = Decimal(str(p.value or 0)) / Decimal('365')
        if p.launch and p.launch > first_of_month:
            active_start = p.launch
        else:
            active_start = first_of_month
        active_days = (last_of_month - active_start).days + 1
        project_uplift += daily_value * active_days

    if return_components:
        return base_forecast, project_uplift
    return base_forecast + project_uplift


def _build_chart_data(year, vertical_id=None):
    """Build MTD, QTD, and YTD chart data series for the dashboard."""
    today = date.today()
    current_month = today.month
    current_year = today.year

    def _filter_actuals(qs):
        if vertical_id:
            return qs.filter(vertical_id=vertical_id)
        return qs

    def _filter_goals(qs):
        if vertical_id:
            return qs.filter(vertical_id=vertical_id)
        return qs

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
            base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id)
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
            base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id)
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
    daily_actuals_qs = _filter_actuals(DailyActual.objects.filter(
        date__year=year, date__month=current_month, date__lte=today
    ))
    daily_actuals_map = {}
    for a in daily_actuals_qs:
        daily_actuals_map[a.date.day] = daily_actuals_map.get(a.date.day, 0) + float(a.revenue)

    # Weekday averages for projection
    dow_totals = defaultdict(float)
    dow_counts = defaultdict(int)
    for a in daily_actuals_qs:
        dow = a.date.weekday()
        dow_totals[dow] += float(a.revenue)
        dow_counts[dow] += 1

    dow_avg = {}
    for dow in range(7):
        if dow_counts[dow] > 0:
            dow_avg[dow] = dow_totals[dow] / dow_counts[dow]
        else:
            dow_avg[dow] = 0

    # Pre-compute per-project daily rates for MTD forecast
    last_of_current_month = date(year, current_month, days_in_current_month)
    project_qs = Action.objects.filter(
        status='WIP',
    ).filter(
        Q(launch__isnull=True) | Q(launch__lte=last_of_current_month)
    )
    if vertical_id:
        project_qs = project_qs.filter(vertical_id=vertical_id)
    active_projects = list(project_qs.values_list('value', 'launch'))

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
        qs = Action.objects.filter(
            status='WIP',
        ).filter(
            Q(launch__isnull=True) | Q(launch__lte=end_date)
        )
        if vertical_id:
            qs = qs.filter(vertical_id=vertical_id)
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
        base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id)
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
        base, proj_uplift = calculate_forecast(year, m, return_components=True, vertical_id=vertical_id)
        ytd_forecast_base_total += float(base)
        ytd_project_value_total += float(proj_uplift)
    ytd_forecast_base_total = round(ytd_forecast_base_total, 2)
    ytd_project_value_total = round(ytd_project_value_total, 2)
    ytd_budget_total = round(sum(ytd_budget), 2)
    ytd_project_value = _project_value_through(date(year, 12, 31))

    return {
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


# View All Projects Page
@login_required
def index(request):
    vertical_id = request.GET.get('vertical', '')
    try:
        vertical_id = int(vertical_id) if vertical_id else None
    except (ValueError, TypeError):
        vertical_id = None

    # Show active actions on dashboard
    projects = Action.objects.filter(status='WIP', archived=False).order_by('-normalized_score')
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)

    # Dynamic Objective tiles
    annual_rocks_data = []
    for rock in Objective.objects.filter(year=date.today().year):
        base_qs = Action.objects.filter(objective=rock, archived=False)
        if vertical_id:
            base_qs = base_qs.filter(vertical_id=vertical_id)
        count = base_qs.filter(status='WIP').count()
        value = base_qs.filter(status='WIP').aggregate(Sum('value'))
        count_p = base_qs.exclude(status='WIP').count()
        value_p = base_qs.exclude(status='WIP').aggregate(Sum('value'))
        annual_rocks_data.append({
            'rock': rock,
            'count': count,
            'value': value,
            'count_p': count_p,
            'value_p': value_p,
            'color': _objective_bar_colors(rock.name)['fill'],
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

    # Build revenue chart data
    chart_data = _build_chart_data(date.today().year, vertical_id=vertical_id)

    # Build performance scorecard data
    performance_data = _build_performance_data(date.today(), vertical_id=vertical_id)

    # Build initiatives summary
    initiatives = _build_initiatives_summary(vertical_id=vertical_id)

    return render(request, 'app/index2.html', {
        'annual_rocks_data': annual_rocks_data,
        'chart_data_mtd': json.dumps(chart_data['mtd']),
        'chart_data_qtd': json.dumps(chart_data['qtd']),
        'chart_data_ytd': json.dumps(chart_data['ytd']),
        'performance_data': json.dumps(performance_data),
        'initiatives': initiatives,
    })


PURPOSE_COLORS = {
    'New Growth':       '#1a7a5c',  # green
    'Hold Position':    '#337ab7',  # blue
    'Defend Position':  '#f0ad4e',  # amber
    'Reverse Decay':    '#d9534f',  # red
}


PIPELINE_EXCLUDED_STATUSES = ['Launched', 'Complete']


def _build_initiatives_summary(vertical_id=None):
    """Annotate Projects with action rollups for the Projects summary table.
    Excludes actions in final states (Launched, Complete) since the panel
    surfaces work that will produce future value.
    """
    from django.db.models.functions import Coalesce
    from django.db.models import IntegerField

    pipeline_filter = ~Q(actions__status__in=PIPELINE_EXCLUDED_STATUSES)
    if vertical_id:
        pipeline_filter &= Q(actions__vertical_id=vertical_id)

    qs = (
        Project.objects
        .select_related('objective', 'department')
        .annotate(
            project_count=Count('actions', distinct=True, filter=pipeline_filter),
            active_count=Count(
                'actions', distinct=True,
                filter=pipeline_filter & Q(actions__status='WIP'),
            ),
            active_value=Coalesce(
                Sum('actions__value', filter=pipeline_filter & Q(actions__status='WIP')),
                0, output_field=IntegerField(),
            ),
            inactive_value=Coalesce(
                Sum('actions__value', filter=pipeline_filter & ~Q(actions__status='WIP')),
                0, output_field=IntegerField(),
            ),
            avg_progress=Avg('actions__progress', filter=pipeline_filter),
        )
        .order_by('purpose', 'name')
    )

    project_qs = Action.objects.exclude(status__in=PIPELINE_EXCLUDED_STATUSES)
    if vertical_id:
        project_qs = project_qs.filter(vertical_id=vertical_id)
    qs = qs.prefetch_related(models.Prefetch('actions', queryset=project_qs.order_by('-normalized_score')))

    rows = []
    for s in qs:
        if (s.project_count or 0) == 0:
            continue

        projects = [{
            'id': p.id,
            'name': p.name or f'Action {p.id}',
            'score': float(p.normalized_score) if p.normalized_score is not None else 0.0,
            'progress': p.progress or 0,
            'value': int(p.value or 0),
            'launch': p.launch.isoformat() if p.launch else '',
            'status': p.status or '',
        } for p in s.actions.all()]

        rows.append({
            'id': s.id,
            'name': s.name or f'Project {s.id}',
            'purpose': s.purpose or '',
            'purpose_color': PURPOSE_COLORS.get(s.purpose, '#888'),
            'objective': s.objective.name if s.objective_id and s.objective else '',
            'level': s.level or '',
            'business_unit': s.department.name if s.department_id and s.department else '',
            'project_count': s.project_count or 0,
            'active_count': s.active_count or 0,
            'active_value': int(s.active_value or 0),
            'inactive_value': int(s.inactive_value or 0),
            'avg_progress': int(round(s.avg_progress)) if s.avg_progress is not None else None,
            'projects': projects,
        })
    return rows


PERFORMANCE_AOV_GOAL = 475.0           # target average order value ($)
PERFORMANCE_CLOSE_RATE_GOAL = 0.0150   # target close rate (1.5%)


def _build_performance_data(today, vertical_id=None):
    """Aggregate Sales / Visits / Close Rate / AOV per period (MTD/QTD/YTD)
    with deltas vs same period last year and vs prorated goal.
    """
    year = today.year
    month = today.month
    quarter_start_month = ((month - 1) // 3) * 3 + 1

    periods = {
        'mtd': (date(year, month, 1), today),
        'qtd': (date(year, quarter_start_month, 1), today),
        'ytd': (date(year, 1, 1), today),
    }

    def _ly_bound(d):
        try:
            return date(d.year - 1, d.month, d.day)
        except ValueError:
            # Feb 29 -> Feb 28
            return date(d.year - 1, d.month, d.day - 1)

    def _aggregate(start, end):
        qs = DailyActual.objects.filter(date__gte=start, date__lte=end)
        if vertical_id:
            qs = qs.filter(vertical_id=vertical_id)
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
            qs = MonthlyGoal.objects.filter(month=cur)
            if vertical_id:
                qs = qs.filter(vertical_id=vertical_id)
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
    for key, (start, end) in periods.items():
        cur = _aggregate(start, end)
        ly = _aggregate(_ly_bound(start), _ly_bound(end))

        sales_goal = _sales_goal_for(start, end)
        visits_goal = (sales_goal / PERFORMANCE_AOV_GOAL / PERFORMANCE_CLOSE_RATE_GOAL) if sales_goal else 0

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

    items = []
    for p in active_projects:
        start = p.active_date or p.date_created
        objective_name = str(p.objective) if p.objective_id and p.objective else ''
        colors = _objective_bar_colors(objective_name)
        items.append({
            'id': p.id,
            'name': p.name or f'Action {p.id}',
            'value': float(p.value or 0),
            'progress': max(0, min(100, int(p.progress or 0))),
            'team': p.team.name if p.team_id and p.team else 'Unassigned',
            'quarterly_rock': p.project.name if p.project_id and p.project else '',
            'annual_rock': objective_name,
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

    vertical_id = request.GET.get('vertical', '')
    try:
        vertical_id = int(vertical_id) if vertical_id else None
    except (ValueError, TypeError):
        vertical_id = None

    def _filter_goals(qs):
        if vertical_id:
            return qs.filter(vertical_id=vertical_id)
        return qs

    def _filter_actuals(qs):
        if vertical_id:
            return qs.filter(vertical_id=vertical_id)
        return qs

    is_summary = vertical_id is None

    if request.method == 'POST' and not is_summary:
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
        messages.success(request, 'Budget goals saved successfully.')
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
def upload_actuals(request):
    verticals = Vertical.objects.all()

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        vertical_id = request.POST.get('vertical', '').strip()

        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('app:upload_actuals')

        if not vertical_id:
            messages.error(request, 'Please select a Vertical.')
            return redirect('app:upload_actuals')

        try:
            vertical_obj = Vertical.objects.get(pk=int(vertical_id))
        except (Vertical.DoesNotExist, ValueError):
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
                BusinessUnit.objects.create(
                    name=name,
                    owner_id=int(owner_id) if owner_id else None,
                )

        elif action == 'edit_department':
            dept_id = request.POST.get('item_id')
            dept = BusinessUnit.objects.filter(pk=dept_id).first()
            if dept:
                dept.name = request.POST.get('dept_name', dept.name).strip()
                owner_id = request.POST.get('dept_owner', '').strip()
                dept.owner_id = int(owner_id) if owner_id else None
                dept.save()

        elif action == 'delete_department':
            item_id = request.POST.get('item_id')
            BusinessUnit.objects.filter(pk=item_id).delete()

        elif action == 'add_vertical':
            name = request.POST.get('vert_name', '').strip()
            gm_id = request.POST.get('vert_gm', '').strip()
            if name:
                Vertical.objects.create(
                    name=name,
                    general_manager_id=int(gm_id) if gm_id else None,
                )

        elif action == 'edit_vertical':
            item_id = request.POST.get('item_id')
            vert = Vertical.objects.filter(pk=item_id).first()
            if vert:
                vert.name = request.POST.get('vert_name', vert.name).strip()
                gm_id = request.POST.get('vert_gm', '').strip()
                vert.general_manager_id = int(gm_id) if gm_id else None
                vert.save()

        elif action == 'delete_vertical':
            item_id = request.POST.get('item_id')
            Vertical.objects.filter(pk=item_id).delete()

        return redirect('app:settings_company')

    departments = BusinessUnit.objects.all()
    verticals = Vertical.objects.all()
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
    departments = BusinessUnit.objects.all()

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

    primary = request.GET.get('period', ad.DEFAULT_PRIMARY)
    if primary not in dict((c, d) for c, d, _ in ad.PRIMARY_OPTIONS):
        primary = ad.DEFAULT_PRIMARY
    valid_compares = [c for c, _ in ad.COMPARE_OPTIONS.get(primary, [])]
    compare = request.GET.get('compare', '')
    if compare not in valid_compares:
        compare = ad.default_compare(primary)

    ctx = {
        'primary_options': ad.PRIMARY_OPTIONS,
        'compare_options': ad.COMPARE_OPTIONS.get(primary, []),
        'selected_primary': primary,
        'selected_compare': compare,
        'primary_label': ad.primary_label(primary),
        'compare_label': ad.compare_label(primary, compare),
    }
    return primary, compare, ctx


@login_required
def analytics_grow_sales(request):
    from app import analytics_data as ad
    primary, compare, ctx = _analytics_filter(request)
    cards, charts = ad.build_grow_sales(primary, compare)
    ctx.update({'cards': cards, 'charts_json': json.dumps(charts)})
    return render(request, 'app/analytics/grow_sales.html', ctx)


@login_required
def analytics_attract_traffic(request):
    from app import analytics_data as ad
    primary, compare, ctx = _analytics_filter(request)
    d = ad.build_attract_traffic(primary, compare)
    ctx.update({
        'cards': d['cards'],
        'charts_json': json.dumps(d['charts']),
        'scatter_json': json.dumps(d['scatter']),
    })
    return render(request, 'app/analytics/attract_traffic.html', ctx)


@login_required
def analytics_engage_customers(request):
    from app import analytics_data as ad
    primary, compare, ctx = _analytics_filter(request)
    d = ad.build_engage_customer(primary, compare)
    ctx.update({
        'cards': d['cards'],
        'history': d['history'],
        'scatter': d['scatter'],
        'charts_json': json.dumps(d['charts']),
        'scatter_json': json.dumps(d['scatter']),
    })
    return render(request, 'app/analytics/engage_customers.html', ctx)


@login_required
def analytics_expand_purchases(request):
    from app import analytics_data as ad
    primary, compare, ctx = _analytics_filter(request)
    d = ad.build_expand_purchases(primary, compare)
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
    vertical_id = request.GET.get('vertical', '')
    try:
        vertical_id = int(vertical_id) if vertical_id else None
    except (ValueError, TypeError):
        vertical_id = None

    projects = Action.objects.filter(status='WIP', archived=False).order_by('-normalized_score')
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)

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
            for key in ('mtd', 'qtd', 'ytd'):
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
    """Settings > Data Connection (placeholder; content defined later)."""
    return render(request, 'app/data_connection.html')


@login_required
def settings_users(request):
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
    departments = BusinessUnit.objects.all()

    return render(request, 'app/settings_users.html', {
        'all_users': all_users,
        'role_choices': ROLE_CHOICES,
        'departments': departments,
    })
