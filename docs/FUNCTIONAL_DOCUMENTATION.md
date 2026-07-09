# Material Planning System — Functional Documentation

> **Audience:** Business users, pharmacy/store managers, planners, and analysts who operate the system, plus stakeholders who need to understand what it does.
> **Companion document:** [`TECHNICAL_DOCUMENTATION.md`](TECHNICAL_DOCUMENTATION.md) covers architecture, APIs, algorithms, and deployment.

---

## 1. What the System Does

The Material Planning System forecasts demand and calculates replenishment quantities ("indents") for medical/pharmacy inventory across a hospital network. For every **item** at every **store**, it answers a single practical question:

> *How much should we order for the upcoming period, given past consumption, current stock, stock already on order, safety buffers, and any expected seasonal surge?*

It combines:

- **Consumption history** (how much was used, day by day)
- **Current stock** (closing stock on hand)
- **Stock in transit** (open indents already placed)
- **Configurable planning rules** (safety stock, lead time, reorder levels, minimum quantities, pack sizes)
- **Forecasting methods** (simple average, weighted-recent, or trend-based)
- **Seasonal surge adjustments** (extra demand for specific months/seasons)

…into a periodic **Indent Report** that tells staff exactly what and how much to raise — either as a **Purchase Request** or a **Stock Indent**.

The system runs calculations **on demand** (a user clicks "Generate") and **automatically on a schedule** (per store, at a configurable cadence), and can **pull source data automatically** from external hospital databases.

---

## 2. Users and Roles

The system has two roles:

| Role | Can do | Cannot do |
|------|--------|-----------|
| **Master** | Everything: manage master data, edit settings, generate/clear indents, run classifications, manage users, configure data mining, run the scheduler. | — |
| **Viewer** | Read/browse all data — dashboards, indents, settings, classifications, consumption analysis, surge records. Can change **their own** password. | Any create/update/delete action; the User Management page is hidden. |

Every user signs in with a username and password. Sessions are token-based and expire after 24 hours. Users can reset their own password at any time from the sidebar (requires the current password).

**Password policy** (enforced on every new or changed password):
- Minimum 8 characters
- At least one uppercase letter
- At least one number
- At least one special character

A default administrator (`admin`) is created automatically on first startup with the **master** role.

---

## 3. Key Concepts (Glossary)

| Term | Meaning |
|------|---------|
| **Hospital** | Top-level organizational unit. Holds network-wide default planning rules. |
| **Store** | A stocking location within a hospital (e.g., main pharmacy, ward store). Indents are generated per store. |
| **Item** | A stock-keeping product, optionally belonging to an **Item Group** and **Item Category**, with a **preferred supplier**. |
| **Supplier** | A vendor with a default lead time; items can be linked to one or more suppliers (one marked primary). |
| **Indent** | A replenishment requirement — the quantity to order for the upcoming period. |
| **Indent Report** | The saved calculation for one item at one store for one period, with the full breakdown. |
| **Lookback days** | How far back consumption history is read when forecasting. |
| **Indent duration days** | The length of the planning period the order must cover. |
| **Lead time (days)** | Procurement delay — extra days of demand to cover while an order is in transit. |
| **Safety stock (days)** | Buffer stock expressed as days of demand, held to absorb variability. |
| **Reorder level** | A stock threshold; if stock falls below it, the item is replenished up to that level. |
| **Min stock / Max stock** | Minimum order floor / maximum (reserved) values. |
| **Pack size** | Order rounding multiple (e.g., items sold in boxes of 10). |
| **Open indent** | Quantity already ordered but not yet received (stock in transit). |
| **Surge** | Extra expected demand for a specific month or season (e.g., monsoon, festive). |
| **FSN** | Fast / Slow / Non-moving classification, based on consumption velocity. |
| **VED** | Vital / Essential / Desirable classification, based on criticality. |
| **Forecast method** | The algorithm used to estimate average daily demand. |
| **Purchase Request / Stock Indent** | The request "type" a store raises; a store-level setting stamped on each report. |

---

## 4. The Planning Rules Hierarchy

Planning rules ("settings") can be defined at **six levels**, from broad to specific:

```
Item × Store   (most specific — this exact item at this exact store)
Item           (this item, everywhere)
Category       (all items in a category)
Group          (all items in a group)
Store          (all items at this store)
Hospital       (network-wide defaults — least specific)
```

When the system needs a value (say, *safety stock days*), it looks through these levels **in priority order** and uses the **first level that has a value set**. If none do, a built-in system default applies.

**Configurable order per store.** By default the order is exactly as listed above (Item × Store wins). However, each **store can define its own priority order** — for example, to make store-level rules win over item-level rules. A store can also **remove levels it doesn't want considered**, keeping only the required ones in the order it chooses; omitted levels are **not** consulted (values then fall through to the remaining levels or the system default). If a store does not define an order, the full default order is used. This lets different stores follow different resolution policies without code changes.

**Clearing a value.** Leaving a field blank (clearing it) means "inherit from the next level down." This is how you undo an override and fall back to broader rules.

Some rules are special:
- **Forecasting method** settings apply at **Store then Hospital** level.
- **FSN thresholds / periods and projection formula** are **Hospital-level only**.
- **Lead time** uses a fixed precedence: **Store → Item → Supplier** (store lead time always wins).

### Which rule lives at which level

| Rule | Hospital | Store | Item | Category | Group | Item×Store |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| Lookback days | ✓ | ✓ | ✓ | | | |
| Indent duration days | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Safety stock (days) | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Reorder level | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Min stock | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Max stock | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Lead time (days) | | ✓ | ✓ | | | | *(+ Supplier)* |
| Pack size | | | ✓ | | | |
| Forecast method | ✓ | ✓ | | | | |
| Recent weight factor / Bucket days | ✓ | ✓ | | | | |
| Trend min points | ✓ | | | | | |
| Planning enabled | ✓ | ✓ | ✓ | | | |
| Request type (PR/SI) | | ✓ | | | | |
| FSN period / thresholds / schedule | ✓ | | | | | |
| Projection formula (standard/custom) | ✓ | | | | | |

---

## 5. How an Indent Quantity Is Calculated

For each item at each store, the calculation runs in this order:

1. **Resolve settings** using the hierarchy above.
2. **Estimate average daily demand** using the store/hospital's chosen forecast method (see §6).
3. **Read current stock** (latest closing stock) and **stock in transit** (open indents).
4. **Compute the target stock level:**

   ```
   Target Stock = Avg Daily Demand × (Indent Duration + Safety Stock Days + Lead Time Days)
   ```

5. **Compute the base quantity** (standard formula):

   ```
   Base Qty = max(0, Target Stock − (Closing Stock + Open Indents))
   ```

   (A hospital may instead define a **custom formula** — see §7.)

6. **Apply the reorder-level floor:** if reorder level is set and *closing stock is below it*, ensure the item is replenished up to that level:

   ```
   if Closing Stock < Reorder Level:
       Base Qty = max(Base Qty, Reorder Level − Closing Stock)
   ```

   This makes an item eligible for ordering even when the forecast alone would have ordered nothing.

7. **Apply the minimum-stock floor:** if min stock is set, ensure stock is topped up to the minimum — ordering the shortfall against current stock (the same way the reorder floor works):

   ```
   Base Qty = max(Base Qty, Min Stock − Closing Stock)
   ```

   If current stock already meets or exceeds min stock, the shortfall is zero or negative and nothing extra is forced.

8. **Add seasonal surge** for the upcoming period's month/season (only **enabled** surge records count):

   ```
   Total Qty = Base Qty + Surge Qty
   ```

9. **Round up to the pack size** (if configured), e.g., round 47 up to 50 for a pack of 10.
10. **Stamp the request type** (Purchase Request or Stock Indent) from the store setting.
11. **Save the Indent Report** with the full breakdown (average daily, target, closing, open, safety, base, surge, total, period, formula used, request type).

The **Indent Planning** screen shows only items whose **total quantity is greater than zero** — i.e., items that actually need ordering.

---

## 6. Forecast Methods (Estimating Demand)

The system offers three ways to estimate average daily demand. The method is chosen at the store (or hospital) level.

| Method | How it works | When to use |
|--------|--------------|-------------|
| **Baseline Average** | Total consumption over the lookback window ÷ number of days. Simple and stable. | Steady, predictable demand. |
| **Weighted Rolling Average** | History is split into equal **buckets**; recent buckets are weighted more heavily (up to a configurable *recent weight factor*). | Demand that is drifting up or down and where recent behaviour matters more. |
| **Trend Adjusted** | Fits a straight-line trend (linear regression) to daily consumption and projects the next point (never below zero). | Clear upward/downward trends with enough data points. |

The **Consumption Analysis** screen lets you preview all three estimates side by side for any item + store + window, along with the daily and bucketed history — useful for choosing the right method.

---

## 7. Custom Projection Formula (Advanced)

At the hospital level, planners can switch from the **standard** formula to a **custom** formula — a math expression evaluated safely (no programming, no side effects). Available variables include: `avg_daily`, `indent_days`, `closing_stock`, `safety_pct`, `open_indent_qty`, `lead_time_days`, `safety_days`, and `target_stock`.

Example (standard equivalent):
```
avg_daily * (indent_days + safety_pct * indent_days + lead_time_days) - (closing_stock + open_indent_qty)
```

The formula is validated before it can be saved; invalid or unsafe expressions are rejected.

---

## 8. Functional Modules

### 8.1 Dashboard
Landing page with at-a-glance counts (hospitals, stores, items, indent reports), the most recent indent reports and surge records, and current scheduler job status.

### 8.2 Master Data
CRUD management of the catalog:
- **Hospitals** — name, code.
- **Stores** — name, code, parent hospital (filterable by hospital).
- **Items** — code, name, unit, group, category, preferred supplier (with search). Managed on a tabbed page together with **Item Groups** and **Item Categories**.
- **Suppliers** — name, code, default lead time; items can be linked to suppliers with a primary designation.

### 8.3 Settings
Six-tab editor (Hospital, Store, Item, Category, Group, Item × Store) reflecting the hierarchy in §4. Each tab picks the entity, shows the rules that apply at that level, and saves overrides. The Store tab additionally configures **lead time**, **request type (Purchase Request / Stock Indent)**, and the **settings priority order** — a list where levels can be reordered, **removed** (to exclude them from resolution), or added back. Blank fields inherit from lower-priority levels.

### 8.4 Data Import (CSV)
Upload spreadsheets to load operational data:
- **Consumption** (item, store, date, quantity)
- **Closing stock** (item, store, date, quantity)
- **Open indents** (item, store, as-of date, quantity)
- **Surge records** (item, store, date, extra qty, reason, season)
- **Items**, **Item Groups**, **Item Categories**

Each upload reports rows imported and any per-row errors. Consumption, closing stock, and open indents can also be cleared (optionally filtered by store/item).

### 8.5 Data Mining (Automated Source Sync)
Instead of manual CSV uploads, the system can connect directly to external hospital databases (PostgreSQL, MySQL, Oracle) and pull data on a schedule. Each configuration defines the connection, a SQL query, a column mapping, and a cron schedule. Supported data types: **consumption, closing stock, open indent, item, supplier**. Credentials are stored encrypted. Connections can be tested, run on demand, or run automatically; every run is logged with rows fetched/inserted/skipped and any error. If a scheduled run was missed while the system was offline, it catches up automatically on the next startup.

### 8.6 Indent Planning
The operational heart of the system:
- **Generate a batch** for a store (creates indents for all its stocked items), or generate a single item's indent via the API.
- **Filter** by hospital, store, item, and period.
- **Review** each indent with its full breakdown; expand a row to see codes, trigger source, request type, and hospital.
- **Add a surge** to any row (with a date picker defaulting to today).
- **Export to CSV** (includes classification and supplier context).
- **Clear** indents (all, or for a store).

### 8.7 Surge Management
A dedicated page to view all surge records (filter by item/store) and **enable or disable** each one. **Disabled surges are excluded from indent calculations.** Disabling records **who** disabled it and **when**; re-enabling clears that audit trail. Toggling a surge immediately recomputes the affected item's indent so the total updates without a manual regenerate.

### 8.8 Classification
- **FSN (Fast / Slow / Non-moving):** run per hospital; classifies each item-store by consumption velocity against configurable thresholds. Results are filterable and paginated.
- **VED (Vital / Essential / Desirable):** run across all items; suggests a criticality class from category attributes, with a manual override (and reason) per item.

### 8.9 Consumption Analysis
A diagnostic screen: for a chosen item + store + window it shows total consumption, active days, days-of-stock, days-since-last-consumption, a trend indicator, and the three forecast estimates — supporting method selection and troubleshooting.

### 8.10 Scheduler
Shows all automated jobs (per-store indent generation, per-hospital FSN, data-mining syncs) with their next run time and status. Jobs can be triggered **Run Now** individually or **Run All**. The view auto-refreshes.

### 8.11 User Management (Master only)
Create users, assign roles (master/viewer), activate/deactivate, change any user's password, and delete users. Password strength is enforced with live feedback.

---

## 9. Automation & Scheduling

The system automatically:
- **Generates indents per store** on the store's configured cadence (default every 30 days).
- **Recomputes FSN per hospital** on the hospital's FSN schedule (default every 30 days).
- **Runs data-mining syncs** on each configuration's cron schedule.
- **Catches up on missed runs** after downtime.

All schedules run in the configured local timezone (default **Asia/Kolkata**), so cron times entered in the UI are interpreted as local time.

---

## 10. Typical End-to-End Workflows

**Initial setup (Master)**
1. Create hospitals and stores.
2. Load or mine item, group, category, and supplier master data.
3. Set hospital-wide default rules under Settings; add store/item overrides as needed.
4. Load consumption, closing stock, and open indents (CSV or data mining).

**Routine planning**
1. Open **Indent Planning**, choose a store, click **Generate Batch** (or let the scheduler do it).
2. Review the resulting indents; expand rows for detail.
3. Adjust rules (Settings) or add surges where demand is expected to spike.
4. Export the CSV for procurement, raised as Purchase Requests or Stock Indents per the store's setting.

**Handling a seasonal spike**
1. On the item's row, **Add Surge** (date, extra quantity, reason, optional season).
2. The indent recomputes immediately; the surge quantity is added to the total.
3. If the spike passes or was entered in error, **disable** the surge on the Surges page — it drops out of the calculation and the change is audit-logged.

---

## 11. Notes & Current Limitations

- **Max stock** is captured in settings but is currently **reserved** (not yet used to cap orders).
- **Surge audit** records only the most recent disable action (not a full history).
- The **Indent Planning** list hides items with a total quantity of zero, so a fully-stocked item with no surge will not appear.
- Default secrets (JWT and encryption keys) ship for development and **must be overridden in production** (see the technical document).
