# Deploy to PythonAnywhere

Step-by-step guide to deploy **Kiboko PPM** (`https://github.com/querybridge/kiboko_mvp`) to a PythonAnywhere account. Targets a Hacker / paid tier (custom domain optional) but works on the free tier — substitute `<username>` everywhere.

---

## 1. Create a PythonAnywhere account

1. Sign up at <https://www.pythonanywhere.com>.
2. From the dashboard, note your username — your site will live at `https://<username>.pythonanywhere.com`.

---

## 2. Clone the repo

Open a **Bash console** (Dashboard → "New console" → Bash).

```bash
cd ~
git clone https://github.com/querybridge/kiboko_mvp.git
cd kiboko_mvp
```

---

## 3. Create a virtualenv

PythonAnywhere ships several Python versions; this project targets Django 5.1 which needs Python 3.10+. Use 3.11 or 3.12.

```bash
mkvirtualenv kiboko --python=python3.11
cd ~/kiboko_mvp                    # IMPORTANT: pip needs to run from the repo root
ls requirements.txt                # sanity check — should print: requirements.txt
pip install -r requirements.txt
```

The virtualenv name `kiboko` is what we'll reference in the Web tab later.

> **Got `Could not open requirements file: requirements.txt`?**  
> You're not in the repo directory. `mkvirtualenv` activates the venv but does **not** change directories, and a new PythonAnywhere console always starts in `$HOME`. Run `cd ~/kiboko_mvp` first, then `ls requirements.txt` to confirm before pip install.
> If you ever need the absolute path, use it directly: `pip install -r ~/kiboko_mvp/requirements.txt`.

---

## 4. Environment settings (.env)

`dashboard_tmpl/settings.py` reads `DJANGO_SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS`
from a gitignored `.env` in the project root. Django refuses to start without a
secret key; `DEBUG` is off unless `.env` turns it on. Create it on the server
(the key is generated straight into the file, so it is never typed or pasted):

```bash
cd ~/kiboko_mvp
python -c "from django.core.management.utils import get_random_secret_key as g; open('.env','w').write('DJANGO_SECRET_KEY=' + g() + '\n')"
printf 'DEBUG=False\nALLOWED_HOSTS=<username>.pythonanywhere.com\n' >> .env
```

Add a custom domain to `ALLOWED_HOSTS` later as a comma-separated list. Other
server-only values (`DATABASES`, Google OAuth credentials) go in the gitignored
`dashboard_tmpl/local_settings.py`, which overrides everything in settings.py.

---

## 5. Database

The project uses SQLite by default. SQLite works fine on PythonAnywhere for low traffic.

```bash
workon kiboko                      # IMPORTANT: activate the venv (new consoles don't auto-activate)
cd ~/kiboko_mvp
which python                       # sanity check — should print /home/<username>/.virtualenvs/kiboko/bin/python
python -c "import django_tables2"  # sanity check — must print nothing (no error)
python manage.py migrate
python manage.py createsuperuser
# Optional seed data:
python manage.py seed_revenue   # 2024-2026 actuals + budgets per vertical
python manage.py seed_projects  # 6 Projects + 20 dummy Actions
```

> **Got `ModuleNotFoundError: No module named 'django_tables2'` (or any other dependency)?**  
> The console is using system Python instead of the venv. New PythonAnywhere consoles don't auto-activate — always run `workon kiboko` first. Verify with `which python` (should point inside `~/.virtualenvs/kiboko/`). If that's correct but the import still fails, re-run `pip install -r requirements.txt` from `~/kiboko_mvp` to confirm all packages installed cleanly.

> If you outgrow SQLite, PythonAnywhere offers MySQL (free) and Postgres (paid). Swap the `DATABASES` block in `local_settings.py`.

---

## 6. Collect static files

```bash
python manage.py collectstatic --noinput
```

This populates `~/kiboko_mvp/static/` (matches `STATIC_ROOT='static'` in settings.py).

---

## 7. Create the Web app

1. Dashboard → **Web** tab → **Add a new web app**.
2. Choose **Manual configuration** (not "Django" — it scaffolds a fresh project).
3. Pick the Python version that matches your virtualenv (e.g. **Python 3.11**).

You'll land on the Web app config page. Fill in:

| Field | Value |
|---|---|
| **Source code** | `/home/<username>/kiboko_mvp` |
| **Working directory** | `/home/<username>/kiboko_mvp` |
| **Virtualenv** | `/home/<username>/.virtualenvs/kiboko` |

---

## 8. Wire up the WSGI file

Click the WSGI configuration file link near the top of the Web tab (e.g. `/var/www/<username>_pythonanywhere_com_wsgi.py`). Replace its contents with:

```python
import os
import sys

path = '/home/<username>/kiboko_mvp'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'dashboard_tmpl.settings'

# Optional: load secrets from a .env-style file or set them in the Web tab "Environment variables" section.
os.environ.setdefault('DJANGO_SECRET_KEY', '<paste-your-secret-key>')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `<username>` and the secret key. Save.

> Prefer the **Environment variables** section on the Web tab for secrets — values set there are injected into the WSGI process automatically.

---

## 9. Configure static & media mappings

In the Web tab, under **Static files**:

| URL | Directory |
|---|---|
| `/static/` | `/home/<username>/kiboko_mvp/static/` |
| `/media/` | `/home/<username>/kiboko_mvp/media/` (only if you add user uploads) |

PythonAnywhere serves these directly without going through Django.

---

## 10. Reload and visit

1. Click the green **Reload** button at the top of the Web tab.
2. Browse to `https://<username>.pythonanywhere.com`.
3. Sign in with the superuser you created in step 5.

---

## 11. Smoke-check

- Dashboard renders revenue chart, Objective tiles, and active Actions.
- `/project/kanban/` loads and you can drag a card between lanes (the move calls `/project/kanban/move/`).
- Bottom-of-sidebar sun/moon toggle switches dark ↔ light theme; preference persists.
- Admin pages under `/app/company/`, `/app/rocks/`, etc. are reachable for admin / senior_leadership users.

If a request 500s, check **Web → Error log** on PythonAnywhere and **Server log** for tracebacks.

---

## 12. Updating the deployment

```bash
workon kiboko
cd ~/kiboko_mvp
git pull origin main
pip install -r requirements.txt        # only if dependencies changed
python manage.py migrate               # only if migrations changed
python manage.py collectstatic --noinput
```

Then click **Reload** on the Web tab to pick up the new code.

---

## Common gotchas

- **`DisallowedHost` 400 error**: add your domain to `ALLOWED_HOSTS` in `local_settings.py` and reload.
- **Static files 404**: make sure `collectstatic` ran and the `/static/` mapping in the Web tab points at `STATIC_ROOT`.
- **CSS still shows the old theme**: the design system stylesheet is cache-busted via `?v=N` in `app/templates/app/base_site.html`. If you've changed CSS but the version param didn't bump, update it.
- **`localStorage` theme not persisting in Safari private mode**: expected — Safari throws on `setItem`. The toggle still works for the session.
- **Free tier outbound network whitelist**: free PythonAnywhere accounts can only reach a whitelisted set of hosts. Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) is on the whitelist, but if you add other CDNs, check first.
- **Time zone**: `dashboard_tmpl/settings.py` sets `TIME_ZONE`. Adjust if reports look offset; PythonAnywhere servers are UTC.
