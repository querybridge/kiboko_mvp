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

from app.forms import StrategyForm
from app.models import MonthlyGoal, DailyActual
from project.models import Project
from strategy.models import Strategy
from project.views import project_detail


def calculate_forecast(year, month, return_components=False):
    """Calculate forecast for a given month using weekday-weighted projection.

    If return_components=True, returns (base_forecast, project_uplift) tuple.
    Otherwise returns total forecast (base + project uplift).
    """
    today = date.today()
    first_of_month = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    last_of_month = date(year, month, days_in_month)

    actuals = DailyActual.objects.filter(
        date__year=year, date__month=month
    )
    actuals_total = actuals.aggregate(s=Sum('revenue'))['s'] or Decimal('0')

    # Group actuals by day-of-week and compute averages
    dow_totals = defaultdict(Decimal)
    dow_counts = defaultdict(int)
    for a in actuals:
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

    # Add approved project uplift — each project contributes its daily value
    # only for days in this month on or after its launch date
    projects = Project.objects.filter(
        approved=True,
    ).filter(
        Q(launch__isnull=True) | Q(launch__lte=last_of_month)
    )
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


def _build_chart_data(year):
    """Build MTD, QTD, and YTD chart data series for the dashboard."""
    today = date.today()
    current_month = today.month
    current_year = today.year

    # --- YTD: monthly data Jan-Dec ---
    ytd_labels = []
    ytd_budget = []
    ytd_forecast_base = []
    ytd_project_value_add = []
    ytd_actual = []

    for m in range(1, 13):
        label = date(year, m, 1).strftime('%b')
        ytd_labels.append(label)

        goal = MonthlyGoal.objects.filter(month=date(year, m, 1)).first()
        budget_val = float(goal.budget) if goal else 0
        ytd_budget.append(budget_val)

        # Check if this month has actual data (past month)
        last_day_of_month = date(year, m, calendar.monthrange(year, m)[1])
        has_actuals = last_day_of_month < today

        actual_sum = DailyActual.objects.filter(
            date__year=year, date__month=m
        ).aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if has_actuals:
            # Past month: show actual, hide forecast
            ytd_actual.append(float(actual_sum))
            ytd_forecast_base.append(0)
            ytd_project_value_add.append(0)
        else:
            # Current/future month: show forecast, hide actual (or show partial actual)
            base, proj_uplift = calculate_forecast(year, m, return_components=True)
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

        goal = MonthlyGoal.objects.filter(month=date(year, m, 1)).first()
        budget_val = float(goal.budget) if goal else 0
        qtd_budget.append(budget_val)

        # Check if this month has actual data (past month)
        last_day_of_month = date(year, m, calendar.monthrange(year, m)[1])
        has_actuals = last_day_of_month < today

        actual_sum = DailyActual.objects.filter(
            date__year=year, date__month=m
        ).aggregate(s=Sum('revenue'))['s'] or Decimal('0')

        if has_actuals:
            # Past month: show actual, hide forecast
            qtd_actual.append(float(actual_sum))
            qtd_forecast_base.append(0)
            qtd_project_value_add.append(0)
        else:
            # Current/future month: show forecast, hide actual (or show partial actual)
            base, proj_uplift = calculate_forecast(year, m, return_components=True)
            qtd_forecast_base.append(float(base))
            qtd_project_value_add.append(float(proj_uplift))
            # For current month, show actual so far; for future, null
            if m == current_month and year == current_year:
                qtd_actual.append(float(actual_sum) if float(actual_sum) > 0 else None)
            else:
                qtd_actual.append(None)

    # --- MTD: daily data for current month ---
    days_in_current_month = calendar.monthrange(year, current_month)[1]
    goal = MonthlyGoal.objects.filter(month=date(year, current_month, 1)).first()
    monthly_budget = float(goal.budget) if goal else 0
    daily_budget_rate = monthly_budget / days_in_current_month if days_in_current_month else 0

    # Gather daily actuals for the month
    daily_actuals_qs = DailyActual.objects.filter(
        date__year=year, date__month=current_month
    )
    daily_actuals_map = {a.date.day: float(a.revenue) for a in daily_actuals_qs}

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
    approved_projects = list(
        Project.objects.filter(
            approved=True,
        ).filter(
            Q(launch__isnull=True) | Q(launch__lte=last_of_current_month)
        ).values_list('value', 'launch')
    )

    def _project_uplift_for_day(d):
        """Sum daily value of all projects whose launch date is on or before d."""
        total = 0.0
        for value, launch in approved_projects:
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
        return float(Project.objects.filter(
            approved=True,
        ).filter(
            Q(launch__isnull=True) | Q(launch__lte=end_date)
        ).aggregate(s=Sum('value'))['s'] or 0)

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
        base, proj_uplift = calculate_forecast(year, m, return_components=True)
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
        base, proj_uplift = calculate_forecast(year, m, return_components=True)
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
    # Exclude archived projects from dashboard
    projects = Project.objects.filter(approved=True, archived=False).order_by('-score')
    strategy = Strategy.objects.all()
    project_count_ic = Project.objects.filter(strategy__objective="IC", approved=True, archived=False).count()
    project_value_ic = Project.objects.filter(strategy__objective="IC", approved=True, archived=False).aggregate(Sum('value'))
    project_count_ips = Project.objects.filter(strategy__objective="IPS", approved=True, archived=False).count()
    project_value_ips = Project.objects.filter(strategy__objective="IPS", approved=True, archived=False).aggregate(Sum('value'))
    project_count_ipf = Project.objects.filter(strategy__objective="IPF", approved=True, archived=False).count()
    project_value_ipf = Project.objects.filter(strategy__objective="IPF", approved=True, archived=False).aggregate(Sum('value'))
    project_count_ic_p = Project.objects.filter(strategy__objective="IC", approved=False, archived=False).count()
    project_value_ic_p = Project.objects.filter(strategy__objective="IC", approved=False, archived=False).aggregate(Sum('value'))
    project_count_ips_p = Project.objects.filter(strategy__objective="IPS", approved=False, archived=False).count()
    project_value_ips_p = Project.objects.filter(strategy__objective="IPS", approved=False, archived=False).aggregate(Sum('value'))
    project_count_ipf_p = Project.objects.filter(strategy__objective="IPF", approved=False, archived=False).count()
    project_value_ipf_p = Project.objects.filter(strategy__objective="IPF", approved=False, archived=False).aggregate(Sum('value'))

    # Build revenue chart data
    chart_data = _build_chart_data(date.today().year)

    return render(request, 'app/index2.html', {
        'projects': projects,
        'project_count_ic': project_count_ic,
        'project_value_ic': project_value_ic,
        'project_count_ips': project_count_ips,
        'project_value_ips': project_value_ips,
        'project_count_ipf': project_count_ipf,
        'project_value_ipf': project_value_ipf,
        'project_count_ic_p': project_count_ic_p,
        'project_value_ic_p': project_value_ic_p,
        'project_count_ips_p': project_count_ips_p,
        'project_value_ips_p': project_value_ips_p,
        'project_count_ipf_p': project_count_ipf_p,
        'project_value_ipf_p': project_value_ipf_p,
        'chart_data_mtd': json.dumps(chart_data['mtd']),
        'chart_data_qtd': json.dumps(chart_data['qtd']),
        'chart_data_ytd': json.dumps(chart_data['ytd']),
    })


@login_required
def adl(request):
    context = {}
    template = loader.get_template('app/adl.html')
    return HttpResponse(template.render(context, request))


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

    if request.method == 'POST':
        for m in range(1, 13):
            month_date = date(year, m, 1)
            budget_val = request.POST.get(f'budget_{m}', '0')
            try:
                budget_val = Decimal(budget_val.replace(',', ''))
            except (InvalidOperation, ValueError):
                budget_val = Decimal('0')
            MonthlyGoal.objects.update_or_create(
                month=month_date,
                defaults={'budget': budget_val}
            )
        messages.success(request, 'Budget goals saved successfully.')
        return redirect('app:edit_goals')

    # GET: build data for current year and historical years
    goals_data = []
    for m in range(1, 13):
        # Current year goal
        month_date = date(year, m, 1)
        goal, _ = MonthlyGoal.objects.get_or_create(
            month=month_date,
            defaults={'budget': 0}
        )

        # Last year data
        ly_month = date(last_year, m, 1)
        ly_goal = MonthlyGoal.objects.filter(month=ly_month).first()
        ly_budget = float(ly_goal.budget) if ly_goal else 0
        ly_actual = float(DailyActual.objects.filter(
            date__year=last_year, date__month=m
        ).aggregate(s=Sum('revenue'))['s'] or 0)
        ly_pct = ((ly_actual / ly_budget - 1) * 100) if ly_budget else 0

        # Previous year data
        py_month = date(prev_year, m, 1)
        py_goal = MonthlyGoal.objects.filter(month=py_month).first()
        py_budget = float(py_goal.budget) if py_goal else 0
        py_actual = float(DailyActual.objects.filter(
            date__year=prev_year, date__month=m
        ).aggregate(s=Sum('revenue'))['s'] or 0)
        py_pct = ((py_actual / py_budget - 1) * 100) if py_budget else 0

        goals_data.append({
            'month': m,
            'month_name': month_date.strftime('%B'),
            'budget': goal.budget,
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
    })


@login_required
def upload_actuals(request):
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
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
                defaults={'revenue': revenue_val}
            )
            count += 1

        if errors:
            messages.warning(request, f'Processed {count} rows with {len(errors)} errors: {"; ".join(errors[:5])}')
        else:
            messages.success(request, f'Successfully processed {count} rows.')
        return redirect('app:upload_actuals')

    return render(request, 'app/upload_actuals.html')
