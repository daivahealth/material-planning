# Material Planning System — Technical Documentation

> **Audience:** Developers, integrators, and operators.
> **Companion document:** [`FUNCTIONAL_DOCUMENTATION.md`](FUNCTIONAL_DOCUMENTATION.md) describes what the system does in business terms.

---

## 1. Architecture Overview

A three-tier containerized application:

```
┌────────────────────┐     HTTP/JSON      ┌────────────────────┐      SQL       ┌──────────────┐
│  Frontend (SPA)    │  ───────────────▶  │  Backend (API)     │  ───────────▶  │  PostgreSQL  │
│  React + Vite      │   Bearer JWT       │  FastAPI + uvicorn │                │   16-alpine  │
│  :5173 → host 14030│  ◀───────────────  │  :8000 → host 14020│  ◀───────────  │ :5432→14045  │
└────────────────────┘                    └─────────┬──────────┘                └──────────────┘
                                                    │
                                     ┌──────────────┼───────────────┐
                                     │ APScheduler  │  Data Mining   │
                                     │ (background) │  (ext. DBs)    │──▶ PostgreSQL / MySQL / Oracle
                                     └──────────────┴───────────────┘
```

- **Frontend** — React single-page app (Vite dev server), talks to the backend over REST with a JWT bearer token.
- **Backend** — FastAPI application exposing ~100 REST endpoints, an embedded APScheduler for periodic jobs, and a data-mining subsystem that syncs from external hospital databases.
- **Database** — PostgreSQL (primary store). External source databases can be PostgreSQL, MySQL, or Oracle.
- **Orchestration** — Docker Compose runs all three services.

---

## 2. Technology Stack

### Backend (`backend/requirements.txt`, Python 3.12)
| Library | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.111.0 | Web framework |
| uvicorn[standard] | 0.29.0 | ASGI server |
| sqlalchemy | 2.0.30 | ORM |
| alembic | 1.13.1 | (available; runtime migrations done via `start.sh`) |
| pydantic / pydantic-settings | 2.7.1 / 2.2.1 | Schemas & config |
| psycopg2-binary | 2.9.9 | PostgreSQL driver |
| pymysql / oracledb | 1.1.1 / 2.3.0 | External source DB drivers |
| apscheduler | 3.10.4 | Background scheduling |
| python-jose[cryptography] | 3.5.0 | JWT encode/decode |
| bcrypt | 4.2.1 | Password hashing (used directly) |
| cryptography | 49.0.0 | Fernet encryption for stored DB passwords |
| simpleeval | 1.0.7 | Safe custom-formula evaluation |
| python-multipart | 0.0.32 | Form/file uploads |
| kafka-python | 3.0.8 | Kafka producer for the outbound publisher |
| python-dateutil | 2.9.0 | Date parsing |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | Tests |

### Frontend (`frontend/package.json`, Node 22)
| Library | Version | Purpose |
|---------|---------|---------|
| react / react-dom | 19.2 | UI |
| vite | 8.0 | Build/dev server |
| @tanstack/react-query | 5.99 | Server state / caching |
| @tanstack/react-table | 8.21 | Tables |
| react-router-dom | 7.14 | Routing |
| axios | 1.15 | HTTP client |
| recharts | 3.8 | Charts |
| lucide-react | 1.8 | Icons |
| tailwindcss | 4.2 | Styling |
| typescript | ~6.0 | Types |

---

## 3. Repository Layout

```
material-planning/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, router registration, lifespan (scheduler)
│   │   ├── config.py          # Pydantic settings (env-driven)
│   │   ├── db.py              # Engine, SessionLocal, Base, get_db
│   │   ├── scheduler.py       # APScheduler setup + job registration
│   │   ├── models/           # SQLAlchemy ORM models (one file per domain)
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── api/              # Routers (auth, users, masters, settings, imports,
│   │   │                     #          indents, classification, scheduler, data_mining, consumption)
│   │   └── services/         # Business logic (indent, settings, fsn, ved, formula,
│   │                         #                  data_mining, auth)
│   ├── scripts/seed.py       # Sample data seeder
│   ├── tests/                # pytest suite
│   ├── requirements.txt
│   ├── Dockerfile
│   └── start.sh              # Table create + ALTER-TABLE migrations + seed + uvicorn
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Routes
│   │   ├── pages/            # One component per screen
│   │   ├── components/       # Layout, Typeahead, ToastCenter, PasswordStrength, …
│   │   ├── contexts/AuthContext.tsx
│   │   └── api/client.ts     # Axios instance + all API functions
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── docs/                     # This documentation
```

---

## 4. Data Model

PostgreSQL schema, created from SQLAlchemy models. All timestamps are timezone-aware.

### 4.1 Users & Organization
- **users** — `id, username (unique), email (unique), hashed_password, role (VARCHAR(20) — master|viewer|planner|planner_view), is_active, created_at, updated_at`.
- **hospitals** — `id, name, code (unique)`. 1:N stores; 1:1 hospital_settings.
- **stores** — `id, hospital_id (FK), name, code`. 1:N to consumption/stock/indent/surge/FSN.
- **user_hospital_access** — `id, user_id (FK, CASCADE), hospital_id (FK, CASCADE)`, unique `(user_id, hospital_id)`. A whole-hospital grant (covers all current + future stores).
- **user_store_access** — `id, user_id (FK, CASCADE), store_id (FK, CASCADE)`, unique `(user_id, store_id)`. An individual-store grant. Both tables scope **planner / planner_view** only (see §12).

### 4.2 Catalog
- **item_groups** — `id, name (unique)`.
- **item_categories** — `id, name (unique), is_vital` (drives VED).
- **items** — `id, group_id (FK, SET NULL), category_id (FK, SET NULL), preferred_supplier_id (FK, SET NULL), name, code (unique), unit`.
- **suppliers** — `id, name, code (unique), lead_time_days (default 7)`.
- **item_suppliers** — `id, item_id, supplier_id, is_primary, moq`.

### 4.3 Settings (one row per entity; nullable columns = "inherit")
- **hospital_settings** (PK `hospital_id`) — full set of defaults, all NOT NULL with defaults: `lookback_days(90), fsn_period_days(365), fsn_schedule_days(30), indent_duration_days(30), safety_stock_days(7.0), reorder_level, min_stock, max_stock, fsn_fast_threshold(1.0), fsn_slow_threshold(0.1), projection_formula(standard), projection_formula_expr, forecast_method(baseline_avg), rolling_window_days(30, legacy), rolling_recent_weight_factor(2.0), rolling_bucket_days(1), trend_min_points(7), planning_enabled(true)`.
- **store_settings** (PK `store_id`) — `indent_duration_days, lookback_days, lead_time_days, forecast_method, rolling_recent_weight_factor, rolling_bucket_days, planning_enabled, settings_priority (CSV), request_type (purchase_request|stock_indent)`.
- **item_settings** (PK `item_id`) — `indent_duration_days, pack_size, lead_time_days, safety_stock_days, reorder_level, min_stock, max_stock, lookback_days, planning_enabled`.
- **item_category_settings** (PK `category_id`) / **item_group_settings** (PK `group_id`) — `indent_duration_days, safety_stock_days, reorder_level, min_stock, max_stock`.
- **item_store_settings** (composite PK `item_id, store_id`) — `indent_duration_days, safety_stock_days, reorder_level, min_stock, max_stock`.
- **supplier_settings** (PK `supplier_id`) — `lead_time_days, moq`.

### 4.4 Operational Data
- **consumption_records** — `id, item_id, store_id, date, quantity (Numeric 20,4)`. Index `(item_id, store_id, date)`.
- **closing_stocks** — same shape; index `(item_id, store_id, date)`.
- **open_indents** — `id, item_id, store_id, as_of_date, quantity, reference`. Index `(item_id, store_id, as_of_date)`.

### 4.5 Planning & Forecasting
- **indent_reports** — `id, item_id, store_id, period_start, period_end, avg_daily_consumption, projected_need, closing_stock_qty, safety_stock_qty, base_indent_qty, surge_indent_qty, open_indent_qty, total_indent_qty, formula_used, triggered_by (TriggerType), request_type, generated_at`. Index `(store_id, item_id, generated_at)`.
- **surge_records** — `id, item_id, store_id, recorded_date, month (1-12), season (SeasonType), reason, extra_qty, enabled (default true), disabled_at, disabled_by`. Index `(item_id, store_id)`.

### 4.6 Classification
- **fsn_classifications** — `id, item_id, store_id, classification (F/S/N), avg_daily_consumption, period_days, computed_at`. Index `(item_id, store_id)`.
- **ved_classifications** — `id, item_id (unique), system_suggestion (V/E/D), manual_override, override_reason, updated_at`.

### 4.7 Data Mining
- **data_mining_configs** — `id, name, description, data_type (DataType), db_type (DbType), host, port, database_name, username, encrypted_password, query, page_size(1000), column_mapping (JSON), write_mode (skip|overwrite, default skip), enabled, schedule_cron, last_run_* summary fields, created_at, updated_at`.
- **data_mining_runs** — `id, config_id, started_at, ended_at, status (RunStatus), rows_fetched, rows_inserted, rows_skipped, error_message`. Index `(config_id, started_at)`.

### 4.8 Outbound Dispatch (see §19)
- **outbound_settings** — singleton global config: `id, enabled, db_type (DbType), host, port, database_name, username, encrypted_password, target_table, column_mapping (JSON), request_status_value(NEW), request_type_value(StockIndent), schedule_cron, kafka_brokers, kafka_topic, last_run_* fields`.
- **store_request_sequences** — composite PK `(store_id, seq_date)`, `last_seq` — per-(store, day) counter for request numbers.
- **outbound_dispatches** — `id, store_id, period_start, period_end, request_number (unique), status (DispatchStatus: pending|inserted|published|failed), rows_written, error, created_at, published_at`. Unique `(store_id, period_start)`.
- **outbox_events** — `id, request_number, topic, payload (JSON), status (OutboxStatus: unpublished|published|failed), attempts, last_error, created_at, published_at`. Index `(status, created_at)`.

### 4.8 Enums
| Enum | Values |
|------|--------|
| UserRole | master, viewer, planner, planner_view *(stored as VARCHAR, not a DB enum)* |
| FormulaType | standard, custom |
| ForecastMethod | baseline_avg, weighted_rolling, trend_adjusted |
| SeasonType | Summer, Monsoon, Winter, Festive |
| TriggerType | scheduler, manual, api |
| FSNClass | F, S, N |
| VEDClass | V, E, D |
| DataType | consumption, closing_stock, open_indent, item, supplier |
| DbType | postgresql, mysql, oracle |
| RunStatus | never, running, success, error |

**Season→month map:** Mar–May → Summer; Jun–Sep → Monsoon; Oct–Feb → Winter. (Festive is set explicitly, not auto-mapped.)

---

## 5. Settings Resolution Engine

Implemented in `app/services/settings.py` (`resolve_all` / `resolve`).

**Sources** loaded per `(item_id, store_id)`: `item_store, item, category, group, store, hospital`.

**Default priority order** (highest → lowest):
```
item_store > item > category > group > store > hospital > system DEFAULTS
```

**Per-store configurable order.** `StoreSettings.settings_priority` holds a CSV of source keys (e.g. `item,item_store,store,hospital`). At resolve time (`_parse_priority`):
1. If unset/blank (or no valid tokens) → use the full default order.
2. If set → parse tokens (validated against the six known sources), drop unknowns/duplicates, and use **exactly those levels, in that order**. Omitted levels are **not** re-appended — a store may deliberately drop levels it doesn't want consulted; values then fall through to the remaining configured levels and finally to `DEFAULTS`.

> The special-cased keys below are resolved by dedicated rules and are unaffected by dropping a level (e.g. removing `hospital` from the order does not disable FSN/projection resolution, which is always hospital-sourced).

**Resolution algorithm.** For each setting key, walk the effective order and take the first source whose column is non-null; otherwise fall back to `DEFAULTS`. Because absent columns simply read as `None`, the same generic walk resolves keys that only exist at certain levels.

**Special-cased keys (independent of the configurable order):**
- **Hospital-only:** `fsn_period_days, fsn_schedule_days, fsn_fast_threshold, fsn_slow_threshold, projection_formula, projection_formula_expr` → always from the hospital.
- **`lead_time_days`:** fixed precedence **store → item** here; the supplier fallback is applied at runtime in the indent service (see §6).
- **`planning_enabled`:** effective value is `False` if **any** of hospital/store/item disables it (logical AND).

**Clearing semantics.** Setting PUT endpoints use `model_dump(exclude_unset=True)` plus a guard that refuses to write `NULL` into NOT-NULL columns. Consequently a field explicitly sent as `null` **clears** a nullable override (falls back to lower priority), while omitted fields are left unchanged and required hospital columns are protected.

The resolved dict also returns the effective `settings_priority` (the ordered source list) for transparency, and `request_type` (store-level, default `stock_indent`).

---

## 6. Indent Calculation

Implemented in `app/services/indent.py` (`generate_indent`, `generate_batch`, `_build_indent_report`).

**Inputs** (resolved settings + data):
- `avg_daily` — from the chosen forecast method (§7)
- `closing_stock` — latest `closing_stocks` row at/for `as_of`
- `open_qty` — sum of the latest `open_indents` snapshot at/for `as_of`
- `lead_time_days` — `_get_lead_time_days(item_id, store_id)` = **store → item → supplier-settings → supplier → 0**
- `safety_stock_days`, `indent_days`, `reorder_level`, `min_stock`, `pack_size`, `request_type`

**Steps:**
1. If `planning_enabled` is false → skip (raises, caught in batch as "skipped").
2. `target_stock = avg_daily × (indent_days + safety_stock_days + lead_time_days)`
3. `safety_stock_qty = avg_daily × safety_stock_days`
4. **Base quantity:**
   - *Standard:* `base = max(0, target_stock − (closing_stock + open_qty))`
   - *Custom:* evaluate the hospital's formula expression (see §8) with `base = max(0, result)`
5. **Reorder floor:** if `reorder_level` set and `closing_stock < reorder_level`: `base = max(base, reorder_level − closing_stock)`
6. **Min-stock floor:** if `min_stock` set: `base = max(base, min_stock − closing_stock)` — orders the shortfall to reach the minimum (mirrors the reorder floor); a non-positive shortfall never lowers the calculated base.
7. **Surge:** `surge_qty = _surge_extra(...)` for the *next* period's month (`(as_of + 1 day).month`); only `enabled` surge records matching the target month **or** its season count; averaged across matching records.
8. `total = base + surge_qty`
9. **Pack rounding:** if `pack_size > 1` and `total > 0`: `total = ceil(total / pack_size) × pack_size`
10. Persist an **IndentReport** with `period_start = as_of + 1`, `period_end = as_of + indent_days`, the full breakdown, `formula_used = "{forecast_method}:{formula}"`, `triggered_by`, and `request_type`.

`generate_indent` replaces any existing report for the same item/store/period; `generate_batch` processes every item that has closing-stock at the store, replacing that store/period's reports atomically.

---

## 7. Forecast Methods

All operate on a daily consumption series over `lookback_days` ending at `as_of`.

- **baseline_avg** — `sum(consumption in window) / lookback_days`.
- **weighted_rolling** — split the series into `rolling_bucket_days`-day buckets (drop the oldest partial bucket); each bucket value = its average daily consumption; weights ramp linearly from `1.0` (oldest) to `rolling_recent_weight_factor` (newest):
  ```
  step = (recent_weight_factor − 1) / (n_buckets − 1)
  weights = [1 + step·i for i in 0..n−1]
  avg_daily = Σ(bucket_avg·weight) / Σ(weight)
  ```
  With `bucket_days = 1` this reduces to a per-day weighted average. Falls back to a plain average when there is less than one full bucket.
- **trend_adjusted** — ordinary least-squares line over the daily series; forecast the next index; clamp at ≥ 0. Requires `≥ max(2, trend_min_points)` points, else falls back to `baseline_avg`.

The **Consumption Analysis** endpoint returns all three estimates plus the daily and bucketed series for UI visualization.

---

## 8. Custom Formula Evaluator

`app/services/formula.py` uses `simpleeval.EvalWithCompoundTypes` (sandboxed; no attribute access, imports, or arbitrary calls).

**Variables:** `avg_daily, indent_days, closing_stock, safety_pct (= safety_stock_days/indent_days), open_indent_qty, lead_time_days, safety_days, target_stock`.

`validate_formula(expr)` dry-runs the expression with dummy values and requires a numeric result; it is invoked when saving hospital settings, so invalid/unsafe expressions are rejected with HTTP 422.

---

## 8.1 CSV Imports

`app/services/csv_import.py` + `app/api/imports.py`. All import endpoints are **master-only** and accept a `.csv` upload, returning `{"imported": N, "errors": [{"row": n, "message": …}]}` — rows are validated individually so one bad line never aborts the file (row numbers are 1-based including the header, so the first data row is `2`).

**Transactional / master-data imports:** consumption, closing stock, surge, open indents, items, item groups, item categories — each resolves `item_code` / `store_code` to ids and reports unknown codes per row.

**Settings uploads** (`store-settings`, `item-settings`, `item-store-settings`) share one set of semantics:

- **Upsert** — the settings row is created if absent, updated if present (`StoreSettings` / `ItemSettings` / `ItemStoreSettings`).
- **Only columns present in the CSV header** are considered; any settings field not in the header is left untouched.
- A **blank cell leaves the field unchanged** — the non-destructive default, so a partially-filled sheet cannot wipe existing configuration.
- The literal token **`NULL`** (case-insensitive) **clears** the field back to "inherit" — the explicit way to remove an override.
- Values are validated through the **same Pydantic schemas the UI uses** (`StoreSettingsCreate`, `ItemSettingsCreate`, `ItemStoreSettingsCreate`), so a CSV can never set something the Settings screen would reject. `_validate()` re-raises Pydantic's error as a terse one-line message suitable for the per-row error table.
- Type coercion is explicit per field (`int` accepts `30` and `30.0` but rejects fractions; `bool` accepts true/false/1/0/yes/no).

**`preferred-suppliers`** updates the **Item master** rather than a settings table: `item_code, supplier_code` sets `items.preferred_supplier_id`; a blank `supplier_code` leaves the item unchanged and `NULL` clears the preference.

---

## 9. Data Mining Framework

`app/services/data_mining.py` + `app/models/data_mining.py`.

- **Encryption:** source DB passwords are encrypted at rest with **Fernet** (`cryptography`), keyed by `MINING_SECRET_KEY`. Plaintext is never stored.
- **Engines:** `get_source_engine` builds a SQLAlchemy engine per `db_type` (`postgresql`/`mysql`/`oracle`) with `pool_pre_ping=True`. `test_connection` runs `SELECT 1`.
- **Pagination:** `_fetch_paginated` pages the source query (`LIMIT/OFFSET`, Oracle `ROWNUM` wrapper) when `page_size > 0`; `0` disables paging.
- **Mappers** (`column_mapping` JSON maps target field → source column):
  - `consumption` / `closing_stock`: `item_code, store_code, date, quantity` (dedup on item+store+date)
  - `open_indent`: `item_code, store_code, as_of_date, quantity`
  - `item`: `code, name` (+ optional `group_name, category_name, unit`; groups/categories auto-created)
  - `supplier`: `code, name` (+ optional `lead_time_days`)
- **Write mode** (`config.write_mode`, default `skip`): on a key that already exists —
  - `skip` — leave the existing row untouched (counts toward `rows_skipped`);
  - `overwrite` — replace it. For time-series types (`_write_timeseries_page`) this deletes existing rows for the page's keys and re-inserts (last-value-wins, within- and cross-page); for `item`/`supplier` it updates the existing record's fields in place. Both are keyed on the same natural keys used for dedup.
- **Runs:** `run_mining_config` guards against concurrent duplicates, records a `DataMiningRun`, and updates the config's last-run summary (`rows_fetched/inserted/skipped`, status, error).
- **Triggers:** manual (`POST /data-mining/configs/{id}/run`, 202 fire-and-forget background thread) or scheduled (cron via APScheduler).

---

## 10. Classification

**FSN** (`app/services/fsn.py`, `compute_fsn_for_hospital`): for each item-store, sum consumption over `fsn_period_days`, compute `avg_daily`; classify **F** if `> fsn_fast_threshold`, **N** if `< fsn_slow_threshold`, else **S**. Scheduled per hospital every `fsn_schedule_days`.

**VED** (`app/services/ved.py`): system suggestion is **V** if the item's category `is_vital`, **E** if the category name contains "essential", else **D**. A manual override (with reason) takes display precedence: `effective = manual_override or system_suggestion`. Run on demand across all items (no schedule loop).

---

## 11. Scheduler

`app/scheduler.py` — APScheduler `BackgroundScheduler` with a **SQLAlchemy job store** (jobs persist across restarts), a `ThreadPoolExecutor(max_workers=4)`, and timezone `settings.timezone` (default **Asia/Kolkata**).

| Job id | Trigger | Cadence | Action |
|--------|---------|---------|--------|
| `indent_store_{store_id}` | interval (days) | resolved `indent_duration_days` (default 30) | batch-generate indents for the store |
| `fsn_hospital_{hospital_id}` | interval (days) | `fsn_schedule_days` (default 30) | recompute FSN for the hospital |
| `datamining_{config_id}` | cron (5-field) | `schedule_cron` | run the mining config |

- **Registration:** on startup all stores/hospitals and enabled mining configs are registered; store/hospital creation and settings changes (re)schedule jobs.
- **Misfire catch-up:** on startup, if a mining config's next cron fire was due while offline (baseline = `last_run_at` or `created_at`), it is triggered once immediately, then resumes normal cadence.
- **Timezone correctness:** cron is parsed with the local tz; "run now" and next-fire computations use local time (times display and evaluate as e.g. IST, not UTC).
- **Manual control:** `GET /api/scheduler/status`, `POST /api/scheduler/run-now/{job_id}`, `POST /api/scheduler/run-all`.

---

## 12. Authentication & Authorization

`app/services/auth.py`, `app/api/auth.py`, `app/schemas/user.py`.

- **Hashing:** bcrypt used directly (`bcrypt.hashpw`/`checkpw`) — passlib intentionally avoided (incompatible with bcrypt 4.x on Python 3.12).
- **JWT:** `python-jose`, **HS256**, payload `{sub, username, role, exp}`, TTL `access_token_expire_minutes` (default 1440). Signed with `jwt_secret_key`.
- **Dependencies:** `get_current_user` (decodes token, checks active) guards most reads; `require_master` enforces `role == master`; `require_roles(*roles)` allows a named set. Most mutations are master-only, but **indent generate / generate-batch** and **purchase-request create** allow `master` + `planner`.
- **Roles:** `master` (all), `viewer` (read all screens), `planner` (Indent/PR/Consumption + generate + create PR), `planner_view` (read-only on those three). `role` is stored as **VARCHAR** so adding roles needs no DB migration.
- **Location scoping** (`app/services/access.py`): planner / planner_view users are restricted to assigned locations; master / viewer are unscoped.
  - `accessible_store_ids(db, user)` / `accessible_hospital_ids(db, user)` return `None` for unscoped roles (= "all, no filter"), else the union of *stores of granted hospitals* ∪ *individually granted stores* (an empty set for a planner with no grants → sees nothing).
  - `assert_store_access(db, user, store_id)` raises **403** for a scoped user hitting an unassigned store.
  - **Choke point:** `GET /api/masters/stores` and `/hospitals` filter to the accessible set, so the Indent / Consumption / Purchase Request dropdowns scope automatically. **Defense in depth:** the action/data endpoints enforce too — consumption analysis, PR candidates + create, indent generate (single/batch) and list all call `assert_store_access` / filter by the accessible set (hiding options in the UI is not the security boundary).
  - Grants are managed via the Users API: `UserCreate` / `UserUpdate` accept `hospital_ids` / `store_ids`; `UserOut` returns them; changing a user to a non-scoped role clears any grants.
- **Password policy** (`schemas/user.py`, applied to create/change/self-reset): ≥ 8 chars, ≥ 1 uppercase, ≥ 1 digit, ≥ 1 special character — enforced via a Pydantic validator (HTTP 422 on violation).
- **Self-service reset:** `POST /api/auth/reset-password` requires the correct current password before setting a new one.
- **Default admin:** seeded on first boot — `admin` / `Admin@123` (master). **Change in production.**

---

## 13. REST API Reference (summary)

Base: backend on host port **14020**. All routes require a bearer token except `POST /api/auth/login` and `GET /health`. Mutations require the **master** role unless noted — the exceptions are indent `generate`/`generate-batch` and purchase-request `create`, which also allow **planner**.

| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| Auth | `/api/auth` | `POST /login`, `GET /me`, `POST /reset-password` |
| Users | `/api/users` | `GET/POST /`, `PUT/DELETE /{id}`, `PUT /{id}/password` (master-only). Create/update bodies accept `hospital_ids` / `store_ids` grants; responses include them |
| Masters | `/api/masters` | `hospitals`, `stores` (`?hospital_id`), `item-groups`, `item-categories`, `items` (`?group_id,category_id,search,limit,offset`), `suppliers` (incl. `PUT /suppliers/{id}`), `item-suppliers/{item_id}` — CRUD. `GET hospitals`/`stores` are **location-scoped** for planner roles (§12) |
| Settings | `/api/settings` | `GET /resolve?item_id&store_id`; `GET/PUT` for `hospital/{id}`, `store/{id}`, `item/{id}`, `category/{id}`, `group/{id}`, `supplier/{id}`, `item-store/{item_id}/{store_id}` |
| Imports | `/api/imports` | `POST` consumption / closing-stock / surge / open-indents / items / item-groups / item-categories; **settings uploads**: `POST store-settings`, `item-settings`, `item-store-settings`, `preferred-suppliers`; `DELETE` consumption / closing-stock / open-indents (`?store_id,item_id`) |
| Indents | `/api/indents` | `POST /generate`, `POST /generate-batch`, `GET /` (`?store_id,item_id,from_date,to_date,limit`), `DELETE /clear`, `GET /export` (CSV); surges: `POST /surges`, `PATCH /surges/{id}` (enable/disable), `GET /surges`, `DELETE /surges/clear` |
| Classification | `/api/classification` | `POST /fsn/run` (`hospital_id`), `GET /fsn`; `POST /ved/run`, `GET /ved`, `PUT /ved/override` |
| Consumption | `/api/consumption` | `GET /analysis?item_id&store_id&as_of&lookback_days` (response includes `closing_stock_qty` + `closing_stock_date`) |
| Scheduler | `/api/scheduler` | `GET /status`, `POST /run-now/{job_id}`, `POST /run-all` |
| Data Mining | `/data-mining` | `GET/POST /configs`, `GET/PUT/DELETE /configs/{id}`, `POST /configs/{id}/test`, `POST /configs/{id}/run` (202), `GET /configs/{id}/runs`, `GET /status` |
| Outbound | `/api/outbound` | `GET/PUT /settings` (singleton), `POST /settings/test`, `POST /run` (dispatch now), `GET /dispatches` (`?store_id`) |
| Purchase Requests | `/api/purchase-requests` | `GET /candidates` (`?store_id&period_start&supplier_id`), `POST /` (`{store_id, period_start, item_ids}`) |

**Cross-cutting behaviors:**
- Creating a store, or changing a store's `indent_duration_days`, (re)schedules its indent job; upserting hospital settings (re)schedules FSN.
- Creating a surge, or toggling its `enabled` flag, best-effort recomputes the affected item's indent immediately.
- Toggling a surge off records `disabled_at`/`disabled_by`; toggling on clears them.

---

## 14. Frontend Architecture

- **Routing** (`App.tsx`, React Router 7): public `/login`; everything else under `ProtectedRoute` + `Layout`. Pages: Dashboard `/`, Hospitals, Stores, Items, Suppliers, Settings, Imports, IndentPlanning `/indents`, Surges, Classification, ConsumptionAnalysis, Scheduler, DataMining, Outbound `/outbound`, Users (`masterOnly`).
- **Auth** (`contexts/AuthContext.tsx`): login posts form-encoded credentials, stores `access_token` + user in `localStorage` (`medplan_token`, `medplan_user`), sets the axios `Authorization` header, exposes `isMaster` and `user.role`. A 401 clears storage and redirects to `/login`. **Both login and logout call `queryClient.clear()`** so a session switch never serves the previous user's cached data — without it, a planner logging in after a master would see the master's cached (unscoped) `['stores']` list until a reload, because `staleTime` (5 min) suppresses the refetch.
- **API client** (`api/client.ts`): axios instance; base URL = `VITE_API_BASE_URL` or inferred `{protocol}//{hostname}:14020`. Response interceptor drives success/error toasts (deduped) and the 401 redirect; 404s on settings endpoints are treated as "empty".
- **Server state:** TanStack Query (`staleTime 5m`, `gcTime 10m`, `retry 1`, no refetch-on-focus); mutations invalidate the relevant query keys.
- **RBAC:** central `utils/permissions.ts` (`canAccessRoute`, `defaultRoute`, `canGenerateIndent`, `canCreatePR`, `isManager`). `ProtectedRoute` redirects unauthenticated users, blocks `masterOnly` pages, and **redirects scoped roles** (planner / planner_view) away from screens outside their allowed set to their landing (`/indents`). The sidebar nav is filtered per role; Indent Planning hides Generate for non-planners and Clear/Add-Surge for non-masters; PR create is disabled for planner_view.
- **Shared components:** `Layout` (sidebar, theme switcher — Cyber/Ember/Swagger, change-password modal), `Typeahead`, `PasswordStrength` (+`isPasswordValid`), `ToastCenter`, `PageHeader`, `StatCard`, `TruncText`, `ProtectedRoute`.
- **Theming:** CSS custom properties (`--c-*`) with three presets persisted in `localStorage`; Tailwind utilities plus custom `cyber-*` / `btn-*` / `form-*` classes.

---

## 15. Configuration

`app/config.py` (Pydantic settings; env vars override defaults, `.env` supported):

| Setting | Env var | Default | Notes |
|---------|---------|---------|-------|
| `database_url` | `DATABASE_URL` | `postgresql://matplan:matplan@localhost:5432/matplan` | Primary DB |
| `mining_secret_key` | `MINING_SECRET_KEY` | *(dev key)* | Fernet key for source-DB password encryption |
| `jwt_secret_key` | `JWT_SECRET_KEY` | *(dev key)* | JWT signing secret |
| `jwt_algorithm` | `JWT_ALGORITHM` | `HS256` | |
| `access_token_expire_minutes` | `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token TTL (24 h) |
| `timezone` | `TIMEZONE` | `Asia/Kolkata` | App/scheduler timezone (pytz) — drives cron interpretation and the `created_at`/`published_at` the app stamps. |
| `kafka_brokers` | `KAFKA_BROKERS` | `""` | Kafka bootstrap servers for the outbound publisher (the Outbound Setting row may override). Blank → publishing is skipped; outbox rows wait. |

**Deploy-time timezone (`TZ`).** Both compose files expose a single **`TZ`** variable (default `Asia/Kolkata`) that sets the container OS clock **and** log timestamps for every service, and also feeds the backend's app-level `TIMEZONE`. Set it at deploy so container logs read on the same clock as your DB/Kafka:

```bash
TZ=Asia/Kolkata docker compose up -d          # dev
TZ=Asia/Kolkata docker compose -f docker-compose.prod.yml up -d   # prod
```

The backend images install `tzdata` so `TZ` actually resolves (slim images omit it, which silently leaves the OS clock/logs on UTC even though app timestamps via pytz are correct). A `TZ` change on the `db` service only takes effect when its container is **recreated**.

> **Production checklist:** override `JWT_SECRET_KEY` and `MINING_SECRET_KEY`, change the default admin password, and restrict CORS (currently `allow_origins=["*"]`).

---

## 16. Deployment

**`docker-compose.yml`** services:

| Service | Container | Image / build | Ports (host:container) | Notable env |
|---------|-----------|---------------|------------------------|-------------|
| db | `matplan_db` | `postgres:16-alpine` | `14045:5432` | `POSTGRES_USER/PASSWORD/DB=matplan` |
| backend | `matplan_backend` | `./backend/Dockerfile` | `14020:8000` | `DATABASE_URL`, `MINING_SECRET_KEY`, `TIMEZONE`, `TZ=Asia/Kolkata`, `RELOAD=1` |
| frontend | `matplan_frontend` | `./frontend/Dockerfile` | `14030:5173` | production build (`vite build`) served by `vite preview` |

**Run:** `docker compose up -d --build`. Backend healthy once logs show `Tables ready.` then `Scheduler started`.

**Serving under a context / base path (no proxy).** The context is **baked into the frontend bundle at image-build time** — Vite inlines the base and the API URL into the compiled assets, so these are **Docker build args**, not runtime env. Rebuild the image to change them.
- `APP_BASE` — the context/base path the app is served under (e.g. `/material-planning/`). Default `/`. Feeds Vite's `base` (`vite.config.ts` → `import.meta.env.BASE_URL`), which drives the router `basename` in `App.tsx`. It is *also* passed to the runtime so `vite preview` serves under the same base.
- `VITE_API_BASE_URL` — where the browser reaches the API (inlined at build). Blank → inferred at runtime as `http(s)://<current-host>:14020`; set explicitly for other hosts/ports. Independent of `APP_BASE`.

`docker-compose.yml` supplies both from `${APP_BASE}` / `${VITE_API_BASE_URL}`. Example — deploy under a context:
```
APP_BASE=/material-planning/ docker compose up -d --build frontend
# → app at http://<host>:14030/material-planning/  (root path 302-redirects there)
```

The backend also honors `ROOT_PATH` (default empty) so its `/docs` and OpenAPI URLs can carry a prefix if ever fronted by a proxy — not required for the direct, no-proxy context deployment above.

**Backend image:** `python:3.12-slim`, installs `requirements.txt`, launches via `start.sh`.
**Frontend image:** multi-stage `node:22-slim` — stage 1 `vite build` (bakes `APP_BASE`/`VITE_API_BASE_URL`), stage 2 serves `dist` via `vite preview`. *(No dev server / HMR — rebuild the image to pick up frontend changes.)*

**Offline / air-gapped export (`build-and-export.sh` → `docker-compose.prod.yml`).** For hosts that build elsewhere and load pre-built images, `build-and-export.sh` builds `linux/amd64` images from `backend/Dockerfile.prod` and `frontend/Dockerfile.prod` and saves them as gzipped tarballs under `docker-export/`. The **frontend prod image is nginx-based** and also honors the context base: `APP_BASE` / `VITE_API_BASE_URL` are read from the environment and passed as `--build-arg`, e.g. `APP_BASE=/material-planning/ ./build-and-export.sh`. `frontend/Dockerfile.prod` bakes them into the bundle, copies `dist` into `/usr/share/nginx/html${APP_BASE}`, and generates a base-aware nginx config (SPA fallback to `${APP_BASE}index.html`; `/` → 301 to the base when non-root; the stock nginx welcome page is removed). `docker-compose.prod.yml` runs the loaded `matplan_backend`/`matplan_frontend` images.

### Startup / migration script — `backend/start.sh`
1. **Create tables:** `Base.metadata.create_all(engine)`.
2. **Idempotent column migrations** (PostgreSQL `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — the app has no Alembic migration chain at runtime; schema evolution is handled here. Columns added include, among others:
   - `hospital_settings`: forecast_method, rolling_window_days, rolling_recent_weight_factor, trend_min_points, planning_enabled, rolling_bucket_days, safety_stock_days
   - `store_settings`: planning_enabled, safety_stock_days, forecast_method, rolling_recent_weight_factor, rolling_bucket_days, **lead_time_days, settings_priority, request_type**
   - `item_settings`: planning_enabled, indent_duration_days, pack_size, **lead_time_days**, safety_stock_days
   - `item_category_settings` / `item_group_settings`: indent_duration_days, safety_stock_days
   - `items`: preferred_supplier_id
   - `surge_records`: **enabled, disabled_at, disabled_by**
   - `indent_reports`: **request_type**
3. **Seed admin** if no users exist (`admin` / `Admin@123`, master).
4. **Seed sample data** if no hospitals exist (`python -m scripts.seed`).
5. **Launch uvicorn** (`--reload` when `RELOAD=1`).

> Because migrations are additive `ADD COLUMN IF NOT EXISTS` statements, deploying a newer build over an existing database is safe and non-destructive. Column **removals/renames** are not automated — old columns (e.g., legacy `rolling_window_days`, `safety_stock_pct`) are left in place for compatibility.

---

## 17. Testing

`backend/tests/` (pytest + pytest-asyncio) covers indent, formula, FSN, surge, import, and settings-resolution logic.

> **Known gap:** `tests/test_settings.py` still references the pre-refactor `safety_stock_pct` field and the older "forecast always from hospital" rule, so parts are stale relative to the current `safety_stock_days` model and store-level forecast/priority features. These should be updated to the current settings engine; the live behavior is validated via API-level checks in the interim.

---

## 18. Security Notes

- Default JWT and Fernet keys are development values — **must** be replaced in production.
- CORS is fully open (`allow_origins=["*"]`) — tighten for production.
- Source-DB credentials are encrypted at rest; the primary `DATABASE_URL` and secret keys are provided via environment.
- Write operations are gated behind the `master` role, except indent generation and purchase-request creation which also allow `planner`; tokens expire after 24 hours; a 401 forces re-authentication on the client.
- **Location scoping is enforced server-side** (§12): planner / planner_view users are filtered to their assigned stores on the list endpoints and get a 403 from the indent/consumption/PR endpoints for any store outside their grants. The UI dropdown filtering is convenience only — the API is the boundary.
- Passwords are bcrypt-hashed and subject to the complexity policy in §12.

---

## 19. Outbound Dispatch Pipeline (Stock Indents → external table → Kafka)

`app/services/outbound.py`, `app/api/outbound.py`, `app/models/outbound.py`, scheduler jobs in `app/scheduler.py`.

**Purpose.** On a network-wide schedule, generate indents for every store whose `request_type = stock_indent`, write the indent lines to an external "outbound" table, stamp a per-store request number, and publish that number to Kafka.

**Configuration** is a **singleton** `OutboundSetting`: target DB connection (reuses the data-mining connection/encryption — password Fernet-encrypted with `MINING_SECRET_KEY`, engine via `get_source_engine`), `target_table`, `column_mapping` (internal field → target column, identity by default), `request_status_value` (default `NEW`), `schedule_cron`, `kafka_brokers` (falls back to `KAFKA_BROKERS` env), and `kafka_topic` (default `material_planning_event`).

**Outbound row fields:** `item_code, store_code, qty, request_number, request_type, inserted_date, request_status`. `request_type` is written from the config's `request_type_value` (default `StockIndent`); `request_status` from `request_status_value` (default `NEW`); `inserted_date` is a local date+time timestamp.

**Positive quantities only.** Only lines with `qty > 0` are ever written outbound. Callers filter (`run_outbound_dispatch` keeps `total_indent_qty > 0`; the PR query filters the same way), **and** the guarantee is re-enforced where the rows are actually built — in both `dispatch_store` and `create_purchase_request` — so no zero/negative line can reach the target table by any path. `dispatch_store` logs `skipped N non-positive line(s)` when it drops any; a PR whose whole selection nets to zero raises instead of writing an empty request.

**Request number:** `SI-{STORE_CODE}-{YYYYMMDD}-{seq}` (seq zero-padded to 4). Allocated by `next_request_number` from the `store_request_sequences` counter, incremented under a `SELECT … FOR UPDATE` row lock (first-insert races absorbed via a savepoint) — resets naturally per store per day.

**Dispatch flow (`run_outbound_dispatch` → `dispatch_store`), per store:**
1. `generate_batch(store, as_of)` to (re)build the current-period indents; keep lines with `total_indent_qty > 0`.
2. Upsert `OutboundDispatch(store, period_start)`. **Idempotency:** if it already exists as `inserted`/`published`, skip; otherwise reserve a request number and **commit** the dispatch row first.
3. **External write** (`_write_to_target`): in one target-DB transaction, `DELETE … WHERE request_number = :rn` then bulk-`INSERT` the mapped rows — idempotent, so retries replace cleanly.
4. In one **app-DB transaction**: mark the dispatch `inserted`, set `rows_written`, and insert an `OutboxEvent(request_number, topic, {"requestNumber": …}, unpublished)`.

**Transactional outbox → Kafka (`publish_outbox`).** A separate interval job (`outbox_publisher`, every 60 s) selects `unpublished` events (`FOR UPDATE SKIP LOCKED`), publishes each to the topic via `kafka-python` `KafkaProducer(acks="all", retries=3)`, and on success marks the event `published` and the matching dispatch `published`. Failures increment `attempts`/`last_error`; after `MAX_PUBLISH_ATTEMPTS (10)` the event is marked `failed`. `run_outbound_dispatch` also calls `publish_outbox` once at the end for immediacy. Blank brokers → publishing is skipped and events wait.

Each successful send is logged with the broker-assigned coordinates — `published <request_number> -> <topic>[<partition>] @ offset <n>` — so a message can be traced to its exact position on the topic (`docker logs matplan_backend | grep '@ offset'`). Sends are fully synchronous: `producer.send(...).get()` blocks on the `acks="all"` ack per message, followed by `producer.flush()` and `close()`, so nothing is left buffered when the call returns. **Publishing always happens after the data is committed** — the external-table write commits in its own transaction and the app-DB commit lands before `publish_outbox` is called, so a consumer acting on the message can always read the rows. A publish failure never rolls back the request; the event simply stays queued for the next poll.

**Delivery semantics:** at-least-once. The external write and the app-DB state form a saga; because the outbox event is written in the *same* transaction that marks the dispatch `inserted`, and publishing is a separate idempotent step keyed on `request_number`, there is no dual-write loss — Kafka downtime simply delays publication. Consumers must dedupe on `requestNumber`.

**Scheduler jobs:** `outbound_dispatch` (cron from the setting, timezone-aware) and `outbox_publisher` (60 s interval). Both are (re)registered at startup (`register_outbound_jobs`); saving Outbound Settings reschedules the dispatch cron.

**API:** `GET/PUT /api/outbound/settings` (singleton; `password` is write-only and never returned — `has_password` flags whether one is stored), `POST /api/outbound/settings/test` (SELECT 1 against the target), `POST /api/outbound/run` (synchronous dispatch), `GET /api/outbound/dispatches`. All mutations are master-only.

**Frontend:** `pages/Outbound.tsx` — connection + target table + column mapping + status value + cron + Kafka topic/brokers, **Test Connection** / **Run Now** actions, and a recent-dispatches table. Master-only editing; viewers read.

**New tables** are created by `Base.metadata.create_all` at startup (no `start.sh` ALTER needed). **New config:** `KAFKA_BROKERS` env (compose default `localhost:9092`).

### 19.1 Manual Purchase Requests

`app/api/purchase_requests.py` + `create_purchase_request` in `app/services/outbound.py`. A user-driven counterpart to the automated stock-indent dispatch, writing to the **same outbound table** with `request_type = PurchaseRequest`.

- **Eligibility / candidates** — `GET /api/purchase-requests/candidates?store_id=&period_start=&supplier_id=` returns indent lines with `total_indent_qty > 0` and `pr_initiated = false`. The store must be configured `request_type = purchase_request` (else **400**); optional filters by period and preferred supplier.
- **Create** — `POST /api/purchase-requests {store_id, period_start, item_ids}` (**master or planner**): validates the store type, loads the selected eligible lines (`FOR UPDATE`), allocates a **`PR-{STORE_CODE}-{YYYYMMDD}-{seq}`** number (shared per-store/day sequencer, `PR` prefix), writes the rows to the outbound table (`request_type=PurchaseRequest`, `inserted_date`=now, `request_status` from config), sets **`pr_initiated = true`** on each line, enqueues the request number to the Kafka outbox, and best-effort publishes.
- **Idempotency** — `pr_initiated` excludes a line from future candidates; it is **preserved across indent regeneration** (`generate_batch` carries the flag forward for the same item+period) so a raised PR is never silently re-offered.
- **New column** `indent_reports.pr_initiated BOOLEAN NOT NULL DEFAULT FALSE` (migration in `start.sh`). Frontend: `pages/PurchaseRequest.tsx` (store → period → optional supplier → select items / all → Create).
