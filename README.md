# Kiboko PPM

Project Portfolio Management tool. Helps teams propose, score, prioritize, and track e-commerce execution Actions against revenue goals across multiple business verticals.

## Overview

Kiboko PPM connects execution work to revenue outcomes. The planning hierarchy cascades from annual strategy down to day-to-day execution:

```
Objective (annual, measured by a KPI)
  └─ Project (quarterly, measured by a Metric)
       └─ Action (execution, measured by a Measure)
```

Actions flow through a structured lifecycle (proposal, scoring, approval, execution, launch) while the dashboard visualizes how active work contributes to monthly, quarterly, and annual revenue forecasts. A global vertical filter (Lighting, Patio, Bailey Street Home) lets users drill into any business unit.

## Action Lifecycle

A **Action** is the granular unit of execution work (formerly called a "Project"). Actions roll up to Projects, which roll up to Objectives.

```
New Action --> Score (Value + LOE) --> Approve --> Assign --> Active --> Complete --> Launched (Archived)
```

1. **Propose** -- Any authenticated user submits a Action linked to a Project, Department, Vertical, and Objective.
2. **Score** -- Senior Leadership / Admin estimate the Action's dollar Value and six weighted criteria (Customer Value, Business Value, Cost Savings, Operational Cost, Business Risk, Level of Effort). The system computes a normalized 0-10 score.
3. **Approve** -- Scored Actions appear in the Approvals queue. Approving moves a Action to Pending Assignment.
4. **Execute** -- Managers assign owners and move Actions to Active. Progress is tracked as a percentage.
5. **Launch** -- Completed Actions are marked Launched and automatically archived.

## Roles & Permissions

### Admin
Full access to everything.

- **Dashboard** -- View revenue chart (MTD/QTD/YTD), Objective tiles, and WIP table. Filter by vertical.
- **Actions** -- Create Projects and Actions. Estimate Value and LOE. Approve Actions. Edit all Action fields including Value on the manager edit form.
- **Revenue** -- Edit budget goals per vertical. Upload daily actuals via CSV.
- **Settings** -- Manage Departments, Verticals, Objectives, Projects, Metrics, KPIs, and Users.

### Senior Leadership
Same access as Admin except cannot manage Users directly (restricted to Admin role only for user creation/deletion).

- **Dashboard** -- Full dashboard access with vertical filter.
- **Actions** -- Create Projects and Actions. Estimate Value and LOE. Approve Actions.
- **Revenue** -- Edit budget goals. Upload actuals.
- **Settings** -- Manage Company, Objectives/Projects, and Measurements settings.

### Supervisor
Department-level oversight.

- **Dashboard** -- View dashboard filtered by vertical.
- **Actions** -- Create Actions. Estimate LOE for Actions in their department. Approve Actions in their department.
- **Revenue** -- View budget goals. Upload actuals.

### General Manager
Vertical-level management.

- **Dashboard** -- View dashboard filtered by vertical.
- **Actions** -- Create Actions. View all Actions.
- **Revenue** -- Edit budget goals per vertical. Upload daily actuals via CSV.

### Staff
Base-level access.

- **Dashboard** -- View dashboard.
- **Actions** -- Create Actions. Edit own Actions. View all Actions and archive.

## Key Features

### Vertical Filter
A global dropdown in the top navigation filters the entire application by business vertical (Lighting, Patio, Bailey Street Home). "Summary" shows aggregated data across all verticals. The filter applies to:
- Dashboard revenue chart and summary stats
- Objective tiles
- WIP Action table
- All Action list views (active, pending, value, LOE, approvals, archive)
- Budget goals (read-only in Summary, editable per vertical)

### Revenue Forecasting
The revenue chart shows Budget, Actual, Forecast, and Action Value Add for MTD, QTD, and YTD periods. Forecasting uses:
- Weekday-weighted projection of current month actuals
- Prior-year same-month actuals scaled by YoY budget growth for future months
- Active Action uplift based on each Action's annualized value and launch date

### Scoring System
Actions are scored on six weighted criteria (0-10 each):
| Criteria | Weight |
|---|---|
| Business Value | 40% |
| Customer Value | 25% |
| Cost Savings | 10% |
| Operational Cost | 10% |
| Level of Effort | 10% |
| Business Risk | 5% |

The weighted average produces a normalized score (0-10) used for stack-ranking Actions.

### Kanban Board
A drag-and-drop Kanban view (`/project/kanban/`) groups active Actions into lanes (Blocked, Incomplete Entry, Ready to Score, Scored, On Deck, Active). KPI summary tiles show aggregate impact totals (Visits, Close Rate, AOV, Sales) per lane, and a vertical filter narrows the board to a single business unit.

### Theming
Dark and light themes ship out of the box, anchored on a monochrome purple palette (`#5C3C9F`). A toggle at the bottom of the left panel switches modes; the preference persists in `localStorage` and is applied before first paint to avoid a flash.

### Help Page
An in-app Help page is available at the bottom of the left sidebar. It covers:
- **Platform Overview** -- What Kiboko PPM does and the four main areas (Dashboard, Actions, Revenue, Admin).
- **Initial Setup** -- Step-by-step guide for configuring departments, verticals, Objectives/Projects, measurements, users, and budget goals.
- **Add a Action** -- How to submit a Action, score it, get it approved, and track it on the dashboard.
- **Update Actuals** -- How to prepare a CSV, upload daily revenue, and verify the data on the dashboard.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_revenue      # Revenue actuals (2024-2026) and budgets by vertical
python manage.py seed_projects     # 6 Projects + 20 dummy Actions
python manage.py runserver
```

## Tech Stack

- **Backend** -- Django 5.1, SQLite
- **Frontend** -- Bootstrap 3 (Gentelella admin theme), Chart.js 2.9, jQuery, DataTables
- **Auth** -- Django auth with role-based UserProfile (Admin, Senior Leadership, Supervisor, General Manager, Staff)
