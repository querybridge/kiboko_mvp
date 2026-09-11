# Daily-Rollup Cache — Plan

Status: **designed, not yet built** (parked to work through new-account creation
& company onboarding first). Revisit this doc when ready to implement.

## Objective
Stop Premium (GA4 → BigQuery) dashboards from scanning raw `events_*` on every
page load. A once-a-day job pre-aggregates each Premium company's numbers into a
local table; dashboards read that table (free, fast). Mirrors what Kiboko ITG did
(`aggregate_bigquery_daily_data` → `BigQueryDailyData`).

## Cost problem this solves
Each Premium page currently fires ~6 live BigQuery scans (fundamentals + period
totals + device split + channel split + item-level + category), each scanning the
whole period's daily tables. Cost scales with **page views × period length**.
After this change: **one incremental scan per property per day**; page views cost
nothing.

## Locked decisions
- **Backfill window:** ~400 days per company on first load (covers year-over-year
  comparisons). One-time, bounded.
- **Pre-sync behavior:** if a company has **no** cached rows yet, do a single live
  BigQuery fetch and log it (dashboard works immediately; auto-stops once the
  backfill runs). Gated by a `GA4_USE_ROLLUP` setting (default on).
- **Scheduler:** daily PythonAnywhere Scheduled Task **plus** a backfill kicked
  off when a Premium company is provisioned in Data Connection.

## Design

### 1. New model — `GA4DailyRollup`
One row per **(company, property_id, date)** so company / all-verticals rollups
are sums, and a single-vertical scope filters to its property.

- `company` (FK, CASCADE), `property_id` (str, indexed), `date` (indexed);
  `unique_together(company, property_id, date)`
- **Scalar columns:** 7 fundamentals (visits, visitors, new_visitors, carts,
  orders, units, sales); ~10 engage/story totals (sessions, totalUsers, newUsers,
  engagedSessions, userEngagementDuration, screenPageViews, addToCarts,
  ecommercePurchases, itemsPurchased, purchaseRevenue); 5 funnel counts
  (view_item, view_item_list, view_cart, begin_checkout, add_shipping_info);
  item-level (order_count, unique_skus_weighted, single_sku_orders)
- **JSON columns:** `device` = `{bucket: {funds}}`, `channel` = `{bucket: {funds}}`,
  `categories` = `{cat: {orders, units, sales}}`

Metrics are stored **already event-map-resolved**, so reads don't need the map
(re-sync if a connection's `event_map` changes).

### 2. Per-day BigQuery fetch variants (`app/integrations/bigquery.py`)
`fetch_daily_fundamentals` and `fetch_split_daily` are already per-day. Add per-day
versions of the three period/aggregate queries (same SQL + `event_date` in
SELECT/GROUP BY): `fetch_daily_totals`, `fetch_daily_order_item`,
`fetch_daily_category`.

### 3. Sync command — `manage.py sync_ga4_rollups`
For each Premium company, for each property:
- **Incremental:** from `(last stored date + 1)` through `latest_daily_date`,
  **plus re-sync the trailing ~3 days** to catch late-landing data.
- **Backfill:** `--backfill` → ~400 days back (one-time).
- Idempotent `update_or_create` per (company, property_id, date); update
  `data_through` / `last_tested_at`.
- Flags: `--company <slug>`, `--since` / `--until` for targeted re-syncs.

### 4. Rewire Premium providers (`app/integrations/ga4_dashboard.py`)
Swap the live-BigQuery branches to read from `GA4DailyRollup`: `_bq_rows`,
`_bq_splits`, `_bq_engage_metrics`, `_bq_story_fundamentals`, `_bq_segments`,
`ga4_item_metrics` → query rollup rows for the scoped properties over
`[start, end]`, sum across properties per day, then feed the **exact same**
downstream helpers (`_bucketize`, `_split_metrics`, `_engage_compute`,
`_story_fundamentals`, `_real_scatter_chart`). Shapes unchanged → dashboards
render identically.
- **Fallback:** if a company has zero rollup rows, one live fetch + log (until the
  first sync). Controlled by `GA4_USE_ROLLUP` (default on).

### 5. Provisioning hook
When a Premium company is connected in Data Connection, kick off its backfill so
it's queryable from cache immediately instead of hitting live per view.

### 6. Scheduling (PythonAnywhere)
Daily Scheduled Task: `python manage.py sync_ga4_rollups` (early morning; GA4
export lands ~day+1). Document in `docs/deploy_server_setup.md`.

## Validation
- Backfill Autocado; assert rollup reproduces known live numbers
  (Aug 2025 = 5,888 visits / 57 orders / $15,540; device/channel/funnel/categories
  match).
- Diff each provider's rollup output vs its live output for a fixed period — must
  be identical.
- Confirm incremental re-sync is idempotent and cheap.

## Files touched
- `business_unit/models.py` (+migration) — `GA4DailyRollup`
- `app/integrations/bigquery.py` — 3 per-day fetch fns
- `app/integrations/ga4_dashboard.py` — read-from-rollup + live fallback
- `app/management/commands/sync_ga4_rollups.py` (new)
- `app/views.py` — provision hook
- `docs/deploy_server_setup.md` — scheduled-task setup

## Notes / dependencies
- Depends on the current live BigQuery layer already validated on Autocado.
- Premium pages hit live BigQuery on the server until this lands — keep the
  "go light on Autocado browsing" caution in the interim.
