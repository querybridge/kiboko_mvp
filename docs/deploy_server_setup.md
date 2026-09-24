# Server Setup & Deploy (PythonAnywhere)

Host: **PythonAnywhere**. Web user `kiboko`, project dir `/home/kiboko/kiboko_mvp`.
Database: **MySQL** (PythonAnywhere-managed; the local dev DB is a separate MySQL).
The site is served by the **Web tab** WSGI app at the `*.pythonanywhere.com` domain
— **never `runserver`** on the server (it binds the container's loopback and isn't
reachable).

Driver: **PyMySQL** (pure-Python; registered as MySQLdb in `gentelella/__init__.py`).
`mysqlclient` is intentionally not used — it won't build on the local Mac's Python.

## What git does NOT carry (set these out-of-band)
`git pull` updates code only. Secrets + DB config live in
**`gentelella/local_settings.py`** (gitignored), which must exist on each machine:

```python
GOOGLE_OAUTH_CLIENT_ID = '...'
GOOGLE_OAUTH_CLIENT_SECRET = '...'                 # must match the client ID's secret
GOOGLE_OAUTH_REDIRECT_URI = 'https://<domain>/auth/google/callback/'   # production https

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '<user>$<dbname>',        # from the PA Databases tab, e.g. kiboko$method
        'USER': '<user>',                 # your PA username
        'PASSWORD': '<password>',         # the password you set in the Databases tab
        'HOST': '<user>.mysql.pythonanywhere-services.com',
        'PORT': '3306',
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```
The redirect URI must also be registered in the Google Cloud Console OAuth client
(add test users if the consent screen is in Testing). PA MySQL credentials live in
the gitignored `mysql_creds.md` locally — never commit them.

## First-time provisioning (fresh MySQL database)
**Order matters:** create the superuser BEFORE seeding, so seeded projects get a
real owner and `seed_tenancy_demo` grants that superuser admin access.

1. **PA → Databases tab:** create a MySQL database; note host / name / user / password.
2. Put the `DATABASES` block (above) in the server's `gentelella/local_settings.py`.
3. Install the driver + build the schema:
   ```bash
   cd /home/kiboko/kiboko_mvp && PY=/home/kiboko/.virtualenvs/kiboko/bin/python
   /home/kiboko/.virtualenvs/kiboko/bin/pip install PyMySQL
   $PY manage.py migrate --noinput
   $PY manage.py createsuperuser
   $PY manage.py seed_tenancy_demo            # companies / business units / websites + grant superuser admin
   $PY manage.py seed_plans                    # subscription plans (must precede seed_organizations)
   $PY manage.py seed_organizations           # organizations, links companies, sets internal/demo orgs to Enterprise
   $PY manage.py seed_metric_recommendations  # Insights win/loss recommendations
   $PY manage.py seed_belami_demo             # Belami demo: projects, actions, actuals (bootstraps its own BUs/depts/objectives)
   $PY manage.py collectstatic --noinput
   touch /var/www/kiboko_pythonanywhere_com_wsgi.py     # reload
   ```
4. Add real users in-app via **Manage Users** (Huey, sherman, etc.).

**Plan prices** are edited in **Django admin → Business_Unit → Plans** (price is
inline-editable). `seed_plans` is idempotent and *preserves* admin-edited prices
on re-run (pass `--reset-prices` only to force the seed defaults back). Prices are
the source of truth until Stripe is wired, at which point they're pushed to Stripe.

## Routine deploy (code + schema) — fast, no reseed
The common case. Keeps all data; the `migrate` write is brief.
```bash
cd /home/kiboko/kiboko_mvp && PY=/home/kiboko/.virtualenvs/kiboko/bin/python && \
git pull && \
$PY manage.py migrate --noinput && \
$PY manage.py collectstatic --noinput && \
touch /var/www/kiboko_pythonanywhere_com_wsgi.py && \
echo "Deployed and reloaded."
```
**Do NOT reseed on a routine deploy.** Seeds do many writes; keep them out of the
normal path (this also avoided the old SQLite "database is locked" 500s — MySQL
handles concurrent reads far better, but there's still no reason to reseed each time).

## Reseed (only when the seed logic changed)
Run these manually, ideally during low traffic. All seeds are idempotent and safe
to re-run; they touch demo data only and leave real companies untouched. The
Belami seed self-bootstraps (its BUs, departments, AEE-aligned objectives) and
backfills existing projects/actions (objective links, real-baseline s0_annual).
```bash
cd /home/kiboko/kiboko_mvp && PY=/home/kiboko/.virtualenvs/kiboko/bin/python
$PY manage.py seed_belami_demo
$PY manage.py seed_exec_approval_demo        # optional: extra Scored/Exec-Approval projects to test the greenlight queue
$PY manage.py seed_metric_recommendations   # if Insights recommendations changed
touch /var/www/kiboko_pythonanywhere_com_wsgi.py
```
If a seed errors, fix it and re-run, then reload via **Web tab → Reload**.

## Data export (Insights recommendations)
```bash
$PY manage.py export_insights               # writes insights_recommendations.xlsx
```
Download the .xlsx from the **Files tab**.

## Scheduled Task: daily GA4 rollup sync
Keeps the `GA4DailyRollup` cache current so Premium dashboards + the value pipeline
read cached rows instead of scanning `events_*` live. GA4's BigQuery export lands
~a day late, so run it early (the incremental form also re-syncs the trailing 3
days to catch late data).

**Add it on PythonAnywhere → _Tasks_ tab → _Scheduled tasks_:**

1. Find the web app's Python interpreter on the **Web tab** (the "Virtualenv"
   path), e.g. `/home/kiboko/.virtualenvs/kiboko/bin/python`.
2. Create a **daily** task at a UTC time (e.g. `09:00` UTC), command:
   ```bash
   cd /home/kiboko/kiboko_mvp && /home/kiboko/.virtualenvs/kiboko/bin/python manage.py sync_ga4_rollups
   ```
3. Save. Check the task's log link after the first run for the per-property
   "synced N day(s)" output.

**Notes**
- The command is **idempotent** — safe to run repeatedly.
- **New Premium company:** backfill once so its cache covers history:
  ```bash
  /home/kiboko/.virtualenvs/kiboko/bin/python manage.py sync_ga4_rollups --company <slug> --backfill
  ```
- Until a company/range is synced, reads **fall back to a live BigQuery scan**
  (correct, just costs per view) — a missed run degrades gracefully.
- Free PythonAnywhere accounts allow one scheduled task; paid tiers allow more.
