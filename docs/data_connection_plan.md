# Data Connection — Design Plan (GA4)

Status: **In build (Increment 1 done)** · Scope: connect real GA4 data into Kiboko
Analytics, Storyboard, and the Project Pipeline Value. Author: Sherman.

## v1 — locked decisions (speed to market)

We ship the **GA4 Data API** tier first (BigQuery/Premium tier deferred).

- **Auth:** *Google-required login.* App login becomes "Sign in with Google";
  a Django superuser fallback stays for break-glass. Existing users get linked to a
  Google email.
- **Data access:** *Per-user, access-gated live.* GA4 is read with the signed-in
  user's Google token, so a user only sees Properties/Websites their own Google
  account can access. **Kiboko must surface, to the admin, the exact GA4 access a
  user needs.**
- **Provisioning:** *Auto-discover* via the GA4 Admin API (Accounts → Properties →
  Data Streams); the user picks which to bring into Kiboko.
- **Selectors:** *Rollups included.* Top bar has cascading **Company → Property →
  Website** with "All Properties" (company roll-up) and "All Websites" (property
  roll-up).

### Tenancy mapping (GA4-native) — Vertical **is** the property
`Property` and `Vertical` are **unified**: the existing `Vertical` model gained a
`company` FK + GA4 fields and now *is* the GA4 property. One selector drives both
the GA4 scope and the existing PPM vertical filtering.

| Kiboko | = GA4 | Example |
|---|---|---|
| **Company** (Account) | customer / GA4 account grouping | Belami, VW Group |
| **Vertical** (Business Unit) | GA4 **property** | Lighting, Heating / Lamborghini, Audi |
| **Website** | GA4 **data stream** | lighting.com, ca.lighting.com |

**Roll-ups sum the underlying streams:** "All Websites" = sum of a Vertical's data
streams; "All Verticals" (Summary) = company-wide total. The goal is total business
performance across multiple websites.

### Build increments
1. **Tenancy + top-bar selectors — DONE (this repo).** `Company/Property/Website/
   CompanyMembership/GoogleIdentity` models + migration; cascading selectors with
   roll-ups + session persistence + cascade reset (`app/context_processors.tenancy_selector`,
   `top_navigation.html`); `seed_tenancy_demo` command. Verified via test client +
   screenshot.
2. **Sign in with Google** — replace app login (superuser fallback), store the
   user's Google identity + refresh token (encrypted). *Needs OAuth client creds.*
3. **GA4 Admin auto-discovery** — list the user's Accounts/Properties/Streams and
   create Company/Property/Website; note required access to the admin.
4. **GA4 Data API live fetch** — per-user, access-gated, wired into
   `analytics_data.build_metrics` for the selected Website / roll-up, with dummy
   fallback.

### Dependency to activate increments 2–4
A Google Cloud **OAuth client (id + secret)** with the consent screen configured,
the **Analytics Data API + Admin API enabled**, authorized redirect URI for the
Kiboko domain, and a **test GA4 property** the tester's Google account can access.
Google login is gated behind these creds so the current login keeps working until
they're provided.

---


This plan is grounded in a review of the original Kiboko implementation at
`/Users/querybridge/envs/kiboko_itg` (the `kiboko_api_app` / `kiboko_jobs_app`
backend) and the current repo's data layer (`app/analytics_data.py`,
`app/models.py`, `business_unit/models.py`).

---

## 1. Goal

Replace the deterministic **dummy** data behind the analytics dashboards with real
GA4 data, delivered through **two selectable connection types sold as pricing tiers**:

| Tier | Connection type | Pitch | Cost / setup |
|---|---|---|---|
| **Standard** | **GA4 Data API** | Fast to set up, good-enough accuracy | Lower cost tier |
| **Premium** | **GA4 → BigQuery export** (identical to the original Kiboko build) | "More accurate" — unsampled, event-level | Higher cost + setup fees (GA4→BigQuery link, GCP billing) |

Both connection types **normalize into the same canonical daily store**, so the
dashboards are provider-agnostic and a customer can be upgraded from Standard →
Premium without any dashboard changes (just a re-sync/backfill).

Adobe Analytics is **out of scope for this iteration** but the connector interface
below is deliberately provider-neutral so Adobe (or Shopify, etc.) can be added
later without touching the store or the dashboards.

---

## 2. What the original Kiboko does (reference)

The original is a **GA4 → BigQuery** pipeline, per Organization:

- **`BigQueryConfiguration`** (OneToOne per org): `property_id` (→ dataset
  `analytics_<property_id>`), three page-path fields (`cart_page_path`,
  `checkout_page_path`, `billing_shipping_page_path`), service-account fields, and
  an **encrypted** `json_key` (GCP service-account JSON, JSON-schema validated,
  encrypted with `django-cryptography`).
- **`BigQueryDailyData`** (per org, per day): the aggregated store the dashboards
  read. A wide denormalized row — every metric (`total_revenue, sessions,
  checkouts, total_users, new_users, add_to_cart, item_purchase_quantity,
  engaged_visits, …`) stored as a total **and** split by **device**
  (desktop/mobile/tablet/others) and **channel**
  (direct/organic/paid/referral/social/others).
- **BigQuery SQL** against GA4 raw event tables (`events_YYYYMMDD`): sessions =
  distinct `user_pseudo_id + ga_session_id`; revenue from `purchase` events; new
  users from `first_visit`; carts from `add_to_cart`; a large channel-grouping
  `CASE` that replicates GA4's default channel grouping.
- **Jobs (Celery)**: initial backfill on connect, a chunked/gap-aware **daily**
  aggregator, a gap-filler; plus connection-failure alert emails and a
  "please configure GA" reminder email.
- **Config API**: create/retrieve config (admin/owner only); saving kicks off the
  initial import.

**Key reuse signal:** the current repo's `analytics_data.build_metrics` already uses
the original's field names (`totalRevenue, sessions, checkouts, totalUsers,
itemPurchaseQuantity`, device/channel splits). The dashboards were modeled on this
store, so wiring them to real data is mostly swapping the dummy generator for reads
of the store, and the Premium (BigQuery) SQL is largely portable as-is.

---

## 3. Tenancy: Account → Segment (Vertical) → Connection

The current repo is flat: `Vertical(name, general_manager)` and
`BusinessUnit(name, owner)` with no parent. We introduce an **Account** as the top
tenant and hang the reporting segments off it.

### Concepts
- **Account** — the customer. One paying entity. (e.g. **Belami**, **VW**.)
- **Vertical** — a **reporting segment = one domain / one GA4 property**. This is the
  unit a data connection attaches to and the key the daily store is bucketed by.
  (e.g. Belami → *Lighting*, *Heating*; VW → *Lamborghini*, *Audi*.)
- **BusinessUnit / Department** — the **internal ownership axis** for actions
  (who owns the work). Orthogonal to data; unchanged by this plan except for an
  optional `account` scope.

> Naming note: the customer-facing sub-brands in the examples (Lighting/Heating,
> Lamborghini/Audi) map to **Verticals** because each is its own domain + GA4
> property + data feed. If a customer prefers the label "Business Unit," we can
> alias it in the UI, but the **data-bearing unit is the Vertical**.

### Shape
```
Account: Belami
 ├─ Vertical "Lighting"  (lighting.example.com,  GA4 property 111111)  ─ DataConnection (Premium / BigQuery)
 └─ Vertical "Heating"   (heating.example.com,   GA4 property 222222)  ─ DataConnection (Standard / Data API)

Account: VW
 ├─ Vertical "Lamborghini" (GA4 property 333333) ─ DataConnection (Standard / Data API)
 └─ Vertical "Audi"        (GA4 property 444444) ─ DataConnection (Premium / BigQuery)
```

- One **Account** → many **Verticals**; each Vertical → **one active DataConnection**
  (of either tier) → its own GA4 property/domain.
- Tiers can be **mixed within an account** (Belami: Lighting on Premium, Heating on
  Standard).
- **Roll-ups**: an account-level view aggregates the daily store across its verticals;
  a vertical-level view reads that vertical only. (The dashboards already accept a
  `vertical` filter — see `_get_vertical_id` — so account/vertical scoping slots in.)
- **Users ↔ Account**: add account membership so a logged-in user only sees their
  account's verticals + connections. The app can ship with a single default Account
  and generalize to many later.

### Model changes
- **`Account`** (new): `name`, `slug`, optional `plan/tier`, `created`.
- **`Vertical`**: add `account` (FK), `domain` (URL), `timezone`, `currency`.
- **`BusinessUnit`**: add optional `account` (FK) for scoping.
- **`DailyActual` / new store**: already keyed by `vertical` → inherits account via the
  vertical.

---

## 4. Data model (new)

### `DataConnection` — one active connection per Vertical
| field | notes |
|---|---|
| `vertical` | FK — the domain/GA4 property this feeds (account derived from it) |
| `provider` | `ga4_data_api` \| `ga4_bigquery` (extensible: `adobe`, …) |
| `tier` | `standard` \| `premium` (derived from provider, stored for billing/reporting) |
| `enabled`, `status` | `never_synced` \| `connected` \| `error` |
| `config` (JSON) | `property_id`, `cart_page_path`, `checkout_page_path`, `billing_shipping_page_path`, `timezone` — **used by both tiers** |
| `credentials` (encrypted) | Data API: OAuth refresh token **or** service-account w/ Analytics scope · BigQuery: GCP service-account `json_key` (JSON-schema validated) |
| `field_mapping` (JSON) | reserved for provider quirks / non-GA providers |
| `last_synced_at`, `last_sync_log` | status + row counts + errors from the last run |
| `created_by`, `created_date` | audit |

Encryption via **`django-cryptography`** (same as the original). Secrets are never
rendered back to the page (show "•••• saved").

### `AnalyticsDailyData` — canonical store the dashboards read
- Port of the original `BigQueryDailyData`, keyed on **`(vertical, date)`**,
  **provider-neutral**.
- Totals **and** device/channel splits for each fundamental
  (`total_revenue, sessions, checkouts, total_users, new_users, add_to_cart,
  item_purchase_quantity, engaged_visits`, plus funnel views: cart/checkout/
  billing views derived from the configured page paths).
- Unique on `(vertical, date)` → **idempotent upserts** so re-syncs and gap-fills are
  safe. `source`/`provider` column records which tier produced the row (for
  reconciliation on tier changes).
- `DailyActual` (existing, used by the Project Pipeline Value) becomes a thin
  rollup/compat view of this store.

---

## 5. The two GA4 connectors

Common interface (`connectors/base.py`):
```
test_connection() -> ok/error         # live credential + access check
fetch(date_range) -> [normalized daily rows]   # → AnalyticsDailyData upsert
```

### 5a. Standard — GA4 Data API (`connectors/ga4_data_api.py`)
- **Auth**: OAuth2 (web flow, store refresh token) or a service account granted GA
  read access. Scope: `analytics.readonly`.
- **Pull**: `runReport` per day with metrics + dimensions; page-path filters use the
  same configured `cart/checkout/billing` paths (via `pagePath` + `screenPageViews`).
- **Lib**: `google-analytics-data`.
- **Trade-offs (the "less accurate" tier)**: subject to **sampling**, cardinality
  limits, and quota; some raw-event metrics are **approximated** (see parity table).
- **Setup**: minimal — grant the property read access; no GCP billing.

### 5b. Premium — GA4 → BigQuery (`connectors/ga4_bigquery.py`)
- **Auth**: GCP **service-account JSON** (`json_key`), BigQuery read on dataset
  `analytics_<property_id>`.
- **Pull**: port the original's SQL (`bigquery_metrics_handler`) + channel-grouping
  `CASE` almost verbatim; union daily `events_YYYYMMDD` tables; chunked + gap-aware.
- **Lib**: `google-cloud-bigquery`, `pandas`.
- **Trade-offs (the "more accurate" tier)**: unsampled, event-level, exact funnel via
  page paths — but requires **GA4→BigQuery export enabled**, a **GCP project with
  billing**, and **setup fees**.

### Metric parity (why Premium is sold as "more accurate")
| Metric | Data API (Standard) | BigQuery (Premium) |
|---|---|---|
| sessions / users / revenue / orders / units | ✅ (may be sampled on large ranges) | ✅ unsampled |
| new vs returning | ✅ | ✅ |
| device / channel splits | ✅ (GA4 default channel group) | ✅ (custom `CASE`, matches original) |
| cart / checkout / billing funnel views | ⚠️ approximate (pagePath page-views) | ✅ exact (event-level) |
| high-cardinality (product category changeplots) | ⚠️ cardinality-limited | ✅ full |

Both write the **same schema**; the dashboards can't tell which tier produced a row.

---

## 6. Sync / scheduling (no Celery here)

The current app runs on PythonAnywhere without Celery, so replace the original's
Celery beat with:
- A management command `sync_analytics --connection <id> [--initial | --gap | --daily]`
  replicating the original's **initial backfill**, **daily incremental**, and
  **gap-fill** logic (chunked, idempotent upserts).
- A **PythonAnywhere Scheduled Task** running the daily variant across enabled
  connections.
- On tier change (Standard→Premium), run `--initial` to re-backfill from the new
  source and supersede prior rows (via the `source` column).
- Failures write to `last_sync_log` and (optionally) email an admin, mirroring the
  original's alerts.

**Backfill depth:** default **13 months** so YoY comparison periods resolve.

---

## 7. Wiring the dashboards

- Add a data-provider path in `analytics_data.build_metrics` that reads
  `AnalyticsDailyData` for the selected **primary + comparison periods** (and the
  active account/vertical filter) and computes the exact same derived series and
  deltas it does today. **Output shape is unchanged**, so the templates and Chart.js
  need no edits.
- **Fallback to the dummy generator** when a vertical has no data (keeps demos/sales
  environments working). Controlled by a flag.
- Account-level views aggregate across the account's verticals; vertical-level views
  read a single vertical.

---

## 8. Data Connection page (replaces the "coming soon" stub)

- **Scope by account**: list the account's verticals, each with its connection status
  badge (Connected / Error / Never synced), tier, and last-sync time + row count.
- **Add / Edit wizard** (per vertical):
  1. Pick the vertical (domain / GA4 property).
  2. Choose connection type — **Standard (Data API)** or **Premium (BigQuery)** — with
     the cost/accuracy note shown inline.
  3. Enter credentials (OAuth connect **or** paste service-account JSON).
  4. Enter `property_id` + the three page paths.
  5. **Test Connection** (live check) → **Save** → kick off initial backfill.
- **Per-connection actions**: Sync now, Backfill (date range), Upgrade tier,
  Disable/Delete, view last sync log.
- **Role-gated** to admin / senior_leadership. Encrypted creds, never rendered back.

---

## 9. Dependencies to add
- `google-analytics-data` (Standard / Data API)
- `google-cloud-bigquery`, `pandas` (Premium / BigQuery — as in the original)
- `django-cryptography` (+ `cryptography`) for encrypted credential fields
- Encryption key + any OAuth client secrets in gitignored `gentelella/local_settings.py`

---

## 10. Phased roadmap (each phase independently shippable)

- **Phase 0 — Store + read path.** Add `Account`, `AnalyticsDailyData`; extend
  `Vertical` (account, domain). Point `analytics_data` at the store with dummy
  fallback. *Dashboards become data-driven before any external call.*
- **Phase 1 — Connections + UI.** `DataConnection` model + Data Connection page
  (CRUD, encrypted creds, Test Connection). Wire account/vertical scoping.
- **Phase 2 — Standard (GA4 Data API).** Connector + initial/daily/gap sync command +
  scheduled task. First real, low-setup dashboard.
- **Phase 3 — Premium (GA4 → BigQuery).** Port the original's SQL connector into the
  same store; add tier upgrade/backfill.
- **Phase 4 — Full splits + funnel metrics** (device/channel + page-path funnel views)
  to fully replace the detail dashboards' dummy data.
- **Phase 5 — Roll-ups & ops.** Account roll-up views, reconciliation on tier change,
  sync-health alerts, multi-account user membership.

**Recommended first slice:** Phase 0 → 1 → 2 (Standard), since the Data API has the
lowest setup friction; then Phase 3 reuses the original's proven SQL for Premium.

---

## 11. Open decisions
1. **Data API auth**: OAuth web flow (per-customer consent, refresh token) vs a
   service account added to each property? (OAuth is friendlier for self-serve.)
2. **One connection per vertical**, or allow a vertical to run **both tiers** in
   parallel (e.g. validate Premium against Standard)? Default: one active per vertical.
3. **Account ↔ user membership** model now, or ship single-account first and
   generalize? (Model supports many; UI can start with one.)
4. **BusinessUnit vs Vertical** for the customer's sub-brands — confirm sub-brands map
   to Verticals (data) and Departments stay the ownership axis.
5. **Backfill depth** beyond 13 months? Any per-tier caps (Data API sampling on long
   ranges)?
6. **Currency/timezone** per vertical — needed for correct daily bucketing and money
   formatting across an account's domains.
