# Pre-Launch Feature & Readiness Checklist

Everything that should be built/addressed before going live. Priority tags:
- **[MUST]** — blocks a safe public launch.
- **[REC]** — my recommendation: strongly advised, not strictly blocking.
- **[POST]** — fine to ship after launch.

> Legend note: **[REC]** items are recommendations, called out as such per request.

---

## 1. Security & data protection
- **[MUST] Encrypt secrets at rest.** `BigQueryConnection.service_account_json` and
  `GoogleIdentity.refresh_token` are stored **plaintext** (scaffolding — see the
  model docstrings). A service-account key grants BigQuery access to a client's
  data; a refresh token impersonates a user's GA4. Encrypt with
  `django-cryptography`/Fernet (key in env) before any real client data lands.
- **[MUST] Rotate `SECRET_KEY` and move it out of code.** It's hardcoded in
  `gentelella/settings.py` and committed to git → effectively compromised.
  Generate a new one, load from env/`local_settings.py`, never commit it.
- **[MUST] Production settings hardening.** `DEBUG=True`, `ALLOWED_HOSTS=['*']`
  today. For prod (via server `local_settings.py`): `DEBUG=False`,
  `ALLOWED_HOSTS=['<domain>']`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_SSL_REDIRECT`, HSTS, `CSRF_TRUSTED_ORIGINS`.
- **[MUST] Google OAuth consent screen verification.** The app requests the
  **sensitive** scope `analytics.readonly`. In "Testing" mode only added test
  users can sign in and refresh tokens expire weekly. Publishing to production
  requires Google's OAuth verification (privacy policy, domain, scope
  justification) — start early; it can take days/weeks.
- **[MUST] Rotate any shared/dev passwords** (e.g. the demo master login) and
  remove dev-only access paths before launch.
- **[REC] Cross-org isolation audit.** We enforce org boundaries in code; do a
  focused review/test pass that a member of Org A can never reach Org B's data
  (URLs, API params, admin).

## 2. Payments & billing  *(you flagged Stripe)*
- **[MUST] Stripe integration.** Wire the blank Billing page: plans (Standard vs
  Premium + setup fee), checkout, webhooks, subscription status on `Organization`.
- **[MUST] Trial gating (deferred with Stripe).** 30-day trial clock + "lock all
  but Billing" at expiry, and trial-Organization creation on first Google sign-in
  (both were deferred pending Stripe — see `onboarding_workflow_plan.md` Phase 5).
- **[REC] Transactional email (SendGrid).** Invites, trial-ending notices, receipts,
  password reset. The invite-only model adds users by email but sends nothing today.

## 3. Infrastructure & operations  *(you flagged MySQL)*
- **[MUST] Move SQLite → MySQL** on PythonAnywhere (concurrency, durability).
  Migrate data; point `DATABASES` via `local_settings.py`.
- **[MUST] Database backups.** Automated, especially post-MySQL.
- **[MUST] Schedule the GA4 rollup sync.** Add the daily Scheduled Task
  (`sync_ga4_rollups`) per `docs/deploy_server_setup.md` — without it Premium
  reads fall back to costly live BigQuery scans.
- **[REC] Static files for prod** (collectstatic + WhiteNoise/served correctly).
- **[REC] Error monitoring & logging** (Sentry or similar) + custom 404/500 pages.
- **[REC] BigQuery cost guardrails** — monitoring/alerts; consider a per-query
  byte cap; the rollup keeps steady-state cost low but backfills scan a lot.

## 4. Provisioning & onboarding
- **[REC] Auto-backfill on Premium provisioning.** When a company is connected,
  kick off `sync_ga4_rollups --company <slug> --backfill` (with a sane cap) so its
  dashboards are cached immediately instead of scanning live. Deferred to control
  cost; currently run manually.
- **[REC] First-class "Add Company / Add Client" step.** Company creation is still
  bundled into Data Connection; the onboarding flows call for a named
  create-company step separate from connecting data (esp. agency "Add Client").
- **[REC] Org-admin transfer.** The single org admin can't be reassigned via the
  UI — needed when the admin changes. (Open item from the onboarding design.)
- **[REC] Standard connection resilience.** Graceful handling + re-auth prompt when
  a user's Google token is revoked/expired; clear messaging on GA4 API rate limits.

## 5. Features to complete
- **[MUST?] Project scoring — NEEDS CLARIFICATION.** Infrastructure exists (6
  criteria on `Action`, `weighted_score` → `normalized_score`, `approvals.html`,
  plus a separate `score` app). Flagged as "missing" — confirm the exact gap
  (scoring entry UI? the two implementations `project/scoring.py` vs the `score`
  app? not reachable/linked? criteria weights?) and finish/consolidate it.
- **[REC] Automated test suite.** No tests today (stub `tests.py` only). Add
  coverage for access/isolation, billing/trial gating, scoring, and the GA4/rollup
  data paths before launch.

## 6. Post-launch / later
- **[POST] Adobe Analytics** connection (Premium-only; needs a developer account).
  Go-to-market is GA4 Standard + Premium first.
- **[POST]** Port remaining Premium detail metrics to the rollup if any live-only
  paths remain; advanced reporting/exports.

---

## Recommended launch sequence
1. **Security must-haves** (encryption, SECRET_KEY, prod settings, OAuth
   verification) — start OAuth verification first (longest lead time).
2. **MySQL + backups.**
3. **Stripe + trial gating + SendGrid invites.**
4. **Provisioning auto-backfill + scheduled sync + Create-Company step.**
5. **Project scoring completion** (pending clarification) + **test suite**.
6. Launch. Adobe + advanced features post-launch.
