# Belami PPM

Project Portfolio Management tool for Belami. Helps teams propose, score, prioritize, and track e-commerce projects against revenue goals across multiple business verticals.

## Overview

Belami PPM connects project work to revenue outcomes. Projects flow through a structured lifecycle (proposal, scoring, approval, execution, launch) while the dashboard visualizes how active projects contribute to monthly, quarterly, and annual revenue forecasts. A global vertical filter (Lighting, Patio, Bailey Street Home) lets users drill into any business unit.

## Project Lifecycle

```
New Project --> Score (Value + LOE) --> Approve --> Assign --> Active --> Complete --> Launched (Archived)
```

1. **Propose** -- Any authenticated user submits a project linked to a Quarterly Rock, Department, Vertical, and Annual Rock.
2. **Score** -- Senior Leadership / Admin estimate the project's dollar Value and six weighted criteria (Customer Value, Business Value, Cost Savings, Operational Cost, Business Risk, Level of Effort). The system computes a normalized 0-10 score.
3. **Approve** -- Scored projects appear in the Approvals queue. Approving moves a project to Pending Assignment.
4. **Execute** -- Managers assign owners and move projects to Active. Progress is tracked as a percentage.
5. **Launch** -- Completed projects are marked Launched and automatically archived.

## Roles & Permissions

### Admin
Full access to everything.

- **Dashboard** -- View revenue chart (MTD/QTD/YTD), Annual Rock tiles, and WIP table. Filter by vertical.
- **Projects** -- Create Quarterly Rocks and Projects. Estimate Value and LOE. Approve projects. Edit all project fields including Value on the manager edit form.
- **Revenue** -- Edit budget goals per vertical. Upload daily actuals via CSV.
- **Settings** -- Manage Departments, Verticals, Annual Rocks, Quarterly Rocks, Metrics, KPIs, and Users.

### Senior Leadership
Same access as Admin except cannot manage Users directly (restricted to Admin role only for user creation/deletion).

- **Dashboard** -- Full dashboard access with vertical filter.
- **Projects** -- Create Quarterly Rocks and Projects. Estimate Value and LOE. Approve projects.
- **Revenue** -- Edit budget goals. Upload actuals.
- **Settings** -- Manage Company, Rocks, and Measurements settings.

### Supervisor
Department-level oversight.

- **Dashboard** -- View dashboard filtered by vertical.
- **Projects** -- Create Projects. Estimate LOE for projects in their department. Approve projects in their department.
- **Revenue** -- View budget goals. Upload actuals.

### General Manager
Vertical-level management.

- **Dashboard** -- View dashboard filtered by vertical.
- **Projects** -- Create Projects. View all projects.
- **Revenue** -- Edit budget goals per vertical. Upload daily actuals via CSV.

### Staff
Base-level access.

- **Dashboard** -- View dashboard.
- **Projects** -- Create Projects. Edit own projects. View all projects and archive.

## Key Features

### Vertical Filter
A global dropdown in the top navigation filters the entire application by business vertical (Lighting, Patio, Bailey Street Home). "Summary" shows aggregated data across all verticals. The filter applies to:
- Dashboard revenue chart and summary stats
- Annual Rock tiles
- WIP project table
- All project list views (active, pending, value, LOE, approvals, archive)
- Budget goals (read-only in Summary, editable per vertical)

### Revenue Forecasting
The revenue chart shows Budget, Actual, Forecast, and Project Value Add for MTD, QTD, and YTD periods. Forecasting uses:
- Weekday-weighted projection of current month actuals
- Prior-year same-month actuals scaled by YoY budget growth for future months
- Active project uplift based on each project's annualized value and launch date

### Scoring System
Projects are scored on six weighted criteria (0-10 each):
| Criteria | Weight |
|---|---|
| Business Value | 40% |
| Customer Value | 25% |
| Cost Savings | 10% |
| Operational Cost | 10% |
| Level of Effort | 10% |
| Business Risk | 5% |

The weighted average produces a normalized score (0-10) used for stack-ranking projects.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_revenue      # Revenue actuals (2024-2026) and budgets by vertical
python manage.py seed_projects     # 6 Quarterly Rocks + 20 dummy projects
python manage.py runserver
```

## Tech Stack

- **Backend** -- Django 5.1, SQLite
- **Frontend** -- Bootstrap 3 (Gentelella admin theme), Chart.js 2.9, jQuery, DataTables
- **Auth** -- Django auth with role-based UserProfile (Admin, Senior Leadership, Supervisor, General Manager, Staff)
