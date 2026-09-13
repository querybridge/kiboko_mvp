# Server Setup & Deploy (PythonAnywhere)

Host: **PythonAnywhere**. Web user `kiboko`, project dir `/home/kiboko/kiboko_mvp`,
SQLite DB at `DATABASES['default']['NAME']` (confirm with the command below).
The site is served by the **Web tab** WSGI app at the `*.pythonanywhere.com`
domain — **never `runserver`** on the server (it binds the container's loopback
and isn't reachable).

## What git does NOT carry (set these out-of-band)
`git pull` updates code only. Two things live outside git:

1. **`gentelella/local_settings.py`** (gitignored) — secrets + env:
   ```python
   GOOGLE_OAUTH_CLIENT_ID = '...'
   GOOGLE_OAUTH_CLIENT_SECRET = '...'                 # must exactly match the client ID's secret
   GOOGLE_OAUTH_REDIRECT_URI = 'https://<domain>/auth/google/callback/'   # production https
   # GA4_USE_ROLLUP defaults True; set False to force live BigQuery reads
   ```
   The redirect URI must also be registered in the Google Cloud Console OAuth
   client (add test users if the consent screen is in Testing).

2. **`db.sqlite3`** (gitignored) — copy up with an **absolute source path** to the
   exact `NAME` path, then Reload:
   ```bash
   scp /Users/querybridge/envs/belamibvm/ecombvm/db.sqlite3 \
       kiboko@ssh.pythonanywhere.com:/home/kiboko/kiboko_mvp/db.sqlite3
   ```

## Deploy steps (on the server)
```bash
cd /home/kiboko/kiboko_mvp
git pull
python manage.py migrate
python manage.py seed_organizations            # idempotent: orgs/companies/memberships
python manage.py seed_metric_recommendations   # idempotent: Insights win/loss recommendations
python manage.py collectstatic --noinput       # if static changed
# confirm which DB Django reads:
python manage.py shell -c "from django.conf import settings as s; print(s.DATABASES['default']['NAME'])"
```
Then **Web tab → Reload**.

## Scheduled Task: daily GA4 rollup sync
Keeps the `GA4DailyRollup` cache current so Premium dashboards + the value
pipeline read cached rows instead of scanning `events_*` live. GA4's BigQuery
export lands ~a day late, so run it early (the incremental form also re-syncs the
trailing 3 days to catch late data).

**Add it on PythonAnywhere → _Tasks_ tab → _Scheduled tasks_:**

1. Find the web app's Python interpreter on the **Web tab** (the "Virtualenv"
   path), e.g. `/home/kiboko/.virtualenvs/kiboko/bin/python`.
2. Create a **daily** task, pick a UTC time (e.g. `09:00` UTC), command:
   ```bash
   cd /home/kiboko/kiboko_mvp && /home/kiboko/.virtualenvs/kiboko/bin/python manage.py sync_ga4_rollups
   ```
   (Substitute the real interpreter path from step 1.)
3. Save. Check the task's log link after the first run for the per-property
   "synced N day(s)" output.

**Notes**
- The command is **idempotent** — safe to run repeatedly.
- **New Premium company:** backfill once so its cache covers history, e.g.
  ```bash
  /home/kiboko/.virtualenvs/kiboko/bin/python manage.py sync_ga4_rollups --company <slug> --backfill
  ```
- Until a company/range is synced, reads **fall back to a live BigQuery scan**
  (correct, just costs per view) — so a missed run degrades gracefully.
- BigQuery scans cost money; the daily incremental sync keeps that to roughly one
  day's tables per property per run.
- Free PythonAnywhere accounts allow one scheduled task; paid tiers allow more.
