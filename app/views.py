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
from django.db.models import Q, Sum, Count, F
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from app.forms import StrategyForm
from users.models import ROLE_CHOICES, UserProfile
from app.models import MonthlyGoal, DailyActual
from business_unit.models import BusinessUnit, Vertical
from project.models import Project
from strategy.models import Strategy, AnnualRock, Metric, KPI
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

    # Add active project uplift — each project contributes its daily value
    # only for days in this month on or after its launch date
    projects = Project.objects.filter(
        status='Active',
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
    project_qs = Project.objects.filter(
        status='Active',
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
        qs = Project.objects.filter(
            status='Active',
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

    # Show active projects on dashboard
    projects = Project.objects.filter(status='Active', archived=False).order_by('-normalized_score')
    if vertical_id:
        projects = projects.filter(vertical_id=vertical_id)

    # Dynamic Annual Rock tiles
    annual_rocks_data = []
    for rock in AnnualRock.objects.filter(year=date.today().year):
        base_qs = Project.objects.filter(annual_rock=rock, archived=False)
        if vertical_id:
            base_qs = base_qs.filter(vertical_id=vertical_id)
        count = base_qs.filter(status='Active').count()
        value = base_qs.filter(status='Active').aggregate(Sum('value'))
        count_p = base_qs.exclude(status='Active').count()
        value_p = base_qs.exclude(status='Active').aggregate(Sum('value'))
        annual_rocks_data.append({
            'rock': rock,
            'count': count,
            'value': value,
            'count_p': count_p,
            'value_p': value_p,
        })

    # Enforce display order: Shopper Volume, Average Order Value, Purchase Frequency
    _rock_order_keywords = ['shopper', 'order value', 'purchase']

    def _rock_sort_key(item):
        name = (item['rock'].name or '').lower()
        for idx, kw in enumerate(_rock_order_keywords):
            if kw in name:
                return idx
        return len(_rock_order_keywords)

    annual_rocks_data.sort(key=_rock_sort_key)

    # Build revenue chart data
    chart_data = _build_chart_data(date.today().year, vertical_id=vertical_id)

    return render(request, 'app/index2.html', {
        'projects': projects,
        'annual_rocks_data': annual_rocks_data,
        'chart_data_mtd': json.dumps(chart_data['mtd']),
        'chart_data_qtd': json.dumps(chart_data['qtd']),
        'chart_data_ytd': json.dumps(chart_data['ytd']),
    })


@login_required
def gentella_html(request):
    context = {}
    load_template = request.path.split('/')[-1]
    template = loader.get_template('app/' + load_template)
    return HttpResponse(template.render(context, request))


@login_required
def project_detail(request, project_id):
    from django.shortcuts import get_object_or_404
    project = get_object_or_404(Project, pk=project_id)
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
                AnnualRock.objects.create(
                    name=name,
                    description=description,
                    year=int(year) if year else None,
                )

        elif action == 'edit_annual_rock':
            item_id = request.POST.get('item_id')
            rock = AnnualRock.objects.filter(pk=item_id).first()
            if rock:
                rock.name = request.POST.get('ar_name', rock.name).strip()
                rock.description = request.POST.get('ar_description', rock.description).strip()
                year = request.POST.get('ar_year', '').strip()
                rock.year = int(year) if year else None
                rock.save()

        elif action == 'delete_annual_rock':
            item_id = request.POST.get('item_id')
            AnnualRock.objects.filter(pk=item_id).delete()

        elif action == 'add_quarterly_rock':
            name = request.POST.get('qr_name', '').strip()
            if name:
                ar_id = request.POST.get('qr_annual_rock', '').strip()
                dept_id = request.POST.get('qr_department', '').strip()
                year = request.POST.get('qr_year', '').strip()
                quarter = request.POST.get('qr_quarter', '').strip()
                target = request.POST.get('qr_target_completion', '').strip()
                Strategy.objects.create(
                    name=name,
                    annual_rock_id=int(ar_id) if ar_id else None,
                    department_id=int(dept_id) if dept_id else None,
                    year=int(year) if year else None,
                    quarter=int(quarter) if quarter else None,
                    target_completion=target if target else None,
                    why='',
                )

        elif action == 'edit_quarterly_rock':
            item_id = request.POST.get('item_id')
            rock = Strategy.objects.filter(pk=item_id).first()
            if rock:
                rock.name = request.POST.get('qr_name', rock.name).strip()
                ar_id = request.POST.get('qr_annual_rock', '').strip()
                rock.annual_rock_id = int(ar_id) if ar_id else None
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
            Strategy.objects.filter(pk=item_id).delete()

        return redirect('app:settings_rocks')

    annual_rocks = AnnualRock.objects.order_by('year', 'name')
    quarterly_rocks = Strategy.objects.order_by('date_created')
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
