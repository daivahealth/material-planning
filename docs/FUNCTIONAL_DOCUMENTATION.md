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

The system has four roles:

| Role | Can do | Cannot do |
|------|--------|-----------|
| **Master** | Everything: manage master data, edit settings, generate/clear indents, run classifications, manage users, configure data mining, run the scheduler. | — |
| **Viewer** | Read/browse **all** screens — dashboards, indents, settings, classifications, consumption, surges, etc. Can change **their own** password. | Any create/update/delete action; the User Management page is hidden. |
| **Planner** | Access **only** the Indent Planning, Purchase Requisition, and Consumption screens. Can **generate indent batches** and **create purchase requisitions**. | Every other screen (masters, settings, imports, data mining, outbound, users…) is hidden/denied; cannot clear indents or add surges. |
| **Planner View** | Read-only on those same three screens (Indent Planning, Purchase Requisition, Consumption). | Cannot generate indents or create purchase requisitions; all other screens hidden/denied. |

Planner and Planner View are **scoped** roles — they see only their three screens and land on Indent Planning after login. Viewer, by contrast, can read every screen.

**Location scoping (Planner / Planner View only).** Each planner user is assigned a set of **hospitals and/or stores** (configured on the User Management page). On the Indent Planning, Consumption, and Purchase Request screens they then see **only their assigned stores** — a granted hospital covers all of its stores (including any added later), and individual stores can be granted for finer control. A planner requesting a store outside their assignment is refused. **A planner with no assignment sees no stores** until an administrator maps them (the secure default). **Master and Viewer are never scoped** — they see all hospitals and stores.

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
| **Pack size** | Order rounding multiple (e.g., items sold in boxes of 10). Settable per **item**, or per **item × store** to override it for one store. |
| **Open indent** | Quantity already ordered but not yet received (stock in transit). |
| **Surge** | Extra expected demand for a specific month or season (e.g., monsoon, festive). |
| **FSN** | Fast / Slow / Non-moving classification, based on consumption velocity. |
| **VED** | Vital / Essential / Desirable classification, based on criticality. |
| **Forecast method** | The algorithm used to estimate average daily demand. |
| **Purchase Request / Stock Indent** | The request "type" a store raises; a store-level setting stamped on each report. |
| **Outbound table** | An external database table the system writes stock-indent lines into (configured on the Outbound Settings page). |
| **Request number** | A unique per-store, per-day identifier (`SI-{STORE_CODE}-{YYYYMMDD}-{seq}`) stamped on outbound rows and published to Kafka. |
| **Kafka topic** | The message stream to which each generated request number is published for downstream systems. |

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
   These are combined into the **inventory position** (on hand + on order), which is what the reorder-level and minimum-stock rules compare against — so quantities already ordered are never ordered again.

   > **Open indents are read strictly as on the reference date.** Only rows dated exactly that date count (several lines on the same date are added together). An item that does not appear in that day's open-indent data is treated as having **nothing on order** — the figure is never carried forward from an earlier date. This is deliberate: once an indent is received the item stops being reported, and carrying the last-seen quantity forward would keep suppressing orders for it indefinitely.
   >
   > **Operational consequence:** the open-indent data for a date must be loaded *before* indents are generated for it. If generation runs first, every item looks as though nothing is on order and quantities will be over-stated. Sequence the mining schedule ahead of the indent/outbound schedule.
4. **Compute the target stock level:**

   ```
   Target Stock = Avg Daily Demand × (Indent Duration + Safety Stock Days + Lead Time Days)
   ```

5. **Compute the base quantity** (standard formula):

   ```
   Base Qty = max(0, Target Stock − (Closing Stock + Open Indents))
   ```

   (A hospital may instead define a **custom formula** — see §7.)

6. **Apply the reorder-level floor:** if reorder level is set and the *inventory position is below it*, ensure the item is replenished up to that level:

   ```
   Inventory Position = Closing Stock + Open Indents      (on hand + already on order)

   if Inventory Position < Reorder Level:
       Base Qty = max(Base Qty, Reorder Level − Inventory Position)
   ```

   This makes an item eligible for ordering even when the forecast alone would have ordered nothing. Both floors work off the **inventory position**, not bare closing stock, so quantities already on order are never ordered a second time while they are in transit.

7. **Apply the minimum-stock floor:** if min stock is set, ensure the position is topped up to the minimum — ordering the shortfall (the same way the reorder floor works):

   ```
   Base Qty = max(Base Qty, Min Stock − Inventory Position)
   ```

   If current stock **plus quantities already on order** already meets or exceeds min stock, the shortfall is zero or negative and nothing extra is forced.

8. **Add seasonal surge** for the upcoming period's month/season (only **enabled** surge records count):

   ```
   Total Qty = Base Qty + Surge Qty
   ```

9. **Apply the minimum order quantity** (if configured at Item × Store) — only when something is actually being ordered:

   ```
   if Total Qty > 0:
       Total Qty = max(Total Qty, Min Order Qty)
   ```

10. **Round up to the pack size** (if configured), e.g., round 47 up to 50 for a pack of 10.
11. **Stamp the request type** (Purchase Request or Stock Indent) from the store setting.
12. **Save the Indent Report** with the full breakdown (average daily, target, closing, open, safety, base, surge, total, period, formula used, request type).

The **Indent Planning** screen shows only items whose **total quantity is greater than zero** — i.e., items that actually need ordering.

---

### Minimum Order Quantity
Some items can only be ordered in a minimum lot. Set a **Min Order Qty** on the **Item × Store** settings tab and, whenever that item is actually being ordered for that store, the quantity is raised to at least that minimum.

- It is a **floor, not a cap** — a larger calculated quantity is never reduced.
- It applies to the final quantity (calculated need plus any surge), and pack-size rounding is applied after it.
- **If nothing is needed, nothing is ordered.** A zero requirement is not raised to the minimum, so items that are well stocked are never ordered just because a minimum exists.
- It flows through to Purchase Requests automatically, since a PR uses the generated indent quantity.

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

### 8.0 Environment Ribbon
Non-production instances can display a coloured diagonal **ribbon in the top-left corner of every page** (e.g. `UAT`), so it is obvious at a glance which environment you are looking at.

- It appears **only when configured at deployment time**; production sets nothing and shows no ribbon.
- The label and colour are chosen per environment when the application image is built.
- It is purely visual — it never covers a control or blocks a click.

### 8.1 Dashboard
Landing page with at-a-glance counts (hospitals, stores, items, indent reports), the most recent indent reports and surge records, and current scheduler job status.

### 8.2 Master Data
CRUD management of the catalog:
- **Hospitals** — name, code.
- **Stores** — name, code, parent hospital. Filter by hospital and/or a name/code search box.
- **Items** — code, name, unit, group, category, preferred supplier (with search). Managed on a tabbed page together with **Item Groups** and **Item Categories**.
- **Suppliers** — name, code, default lead time. Filter by name/code search; each supplier is **editable** (including its lead time). Items can be linked to suppliers with a primary designation.

### 8.3 Settings
Six-tab editor (Hospital, Store, Item, Category, Group, Item × Store) reflecting the hierarchy in §4. Each tab picks the entity, shows the rules that apply at that level, and saves overrides. The Store tab additionally configures **lead time**, **request type (Purchase Request / Stock Indent)**, the **indent scheduler** (Inherit / Enabled / Disabled — see §8.9a), and the **settings priority order** — a list where levels can be reordered, **removed** (to exclude them from resolution), or added back. The Hospital tab carries the network-wide **Indent Scheduler Enabled** default, and the Item × Store tab adds **Min Order Qty** and **Pack Size** (see §5). Blank fields inherit from lower-priority levels.

### 8.4 Data Import (CSV)
Upload spreadsheets to load operational data:
- **Consumption** (item, store, date, quantity)
- **Closing stock** (item, store, date, quantity)
- **Open indents** (item, store, as-of date, quantity)
- **Surge records** (item, store, date, extra qty, reason, season)
- **Items**, **Item Groups**, **Item Categories**
- **Item Master — Preferred Supplier** (item_code, supplier_code)
- **Settings uploads** — bulk-configure the planning hierarchy:
  - **Store settings** (store_code + indent duration, lookback, lead time, forecast method, rolling factors, planning enabled, settings priority, request type)
  - **Item settings** (item_code + indent duration, pack size, lead time, safety stock days, reorder level, min/max stock, lookback, planning enabled)
  - **Item × Store settings** (item_code + store_code + indent duration, safety stock days, reorder level, min/max stock, min order qty, pack size)

  Settings uploads **update existing rows and create missing ones**. Only the columns present in the file are touched; a **blank cell leaves that value unchanged**, and the literal **NULL** clears it back to inherit. Values are validated exactly as on the Settings screen, so an upload can never set something the UI would reject.

Each upload reports rows imported and any per-row errors. Consumption, closing stock, and open indents can also be cleared (optionally filtered by store/item).

### 8.5 Data Mining (Automated Source Sync)
Instead of manual CSV uploads, the system can connect directly to external hospital databases (PostgreSQL, MySQL, Oracle) and pull data on a schedule. Each configuration defines the connection, a SQL query, a column mapping, and a cron schedule. Supported data types: **consumption, closing stock, open indent, item, supplier**. Credentials are stored encrypted. Each job also has an **existing-records mode**:
- **Skip** (default) — leave records that already exist untouched.
- **Overwrite** — replace the rows the feed sends with the newly mined values.
- **Replace by date** — treat the feed as a full snapshot of the day: **all existing data for that date is deleted first** (every store, every item), then the mined rows are inserted. Use this for **closing stock** and **open indents**, where an item the source has stopped reporting would otherwise keep a stale value forever. Only the dates the feed carries are affected — data for other dates is never touched. The delete runs once at the start of the job and is recorded in the run log. Connections can be tested, run on demand, or run automatically; every run is logged with rows fetched/inserted/skipped and any error. If a scheduled run was missed while the system was offline, it catches up automatically on the next startup.

### 8.6 Indent Planning
The operational heart of the system:
- **Generate a batch** for a store (creates indents for all its stocked items), or generate a single item's indent via the API.
- **Filter** by hospital, store, item, and period.
- **Review** each indent with its full breakdown; expand a row to see codes, trigger source, request type, and hospital.
- **Add a surge** to any row (with a date picker defaulting to today).
- **Export to CSV** — the full breakdown per line: average daily consumption, projected need, **closing stock, open indent quantity**, safety stock, base/surge/total quantities, plus FSN & VED classification and supplier context.
- **Clear** indents (all, or for a store).

### 8.7 Surge Management
A dedicated page to view all surge records (filter by item/store) and **enable or disable** each one. **Disabled surges are excluded from indent calculations.** Disabling records **who** disabled it and **when**; re-enabling clears that audit trail. Toggling a surge immediately recomputes the affected item's indent so the total updates without a manual regenerate.

### 8.8 Classification
- **FSN (Fast / Slow / Non-moving):** run per hospital; classifies each item-store by consumption velocity against configurable thresholds. Results are filterable and paginated.
- **VED (Vital / Essential / Desirable):** run across all items; suggests a criticality class from category attributes, with a manual override (and reason) per item.

### 8.9 Consumption Analysis
A diagnostic screen: for a chosen item + store + window it shows total consumption, active days, days-of-stock, days-since-last-consumption, the **latest closing stock** and the **open indent quantity** (each with the date it was recorded), a trend indicator, and the three forecast estimates — supporting method selection and troubleshooting.

The open indent figure is the quantity already ordered but not yet received. It is read the same way the calculation reads it — **strictly the "as of" date you selected**, never a total across historical imports and never carried forward from an earlier date — so what you see here is exactly what the indent calculation subtracts. A blank date with a zero quantity means the item was not in that day's open-indent data at all.

### 8.9a Indent Scheduler Toggle
The automatic **per-store indent job** is **off by default**. When the Outbound pipeline is configured it already generates each store's indents, so leaving the per-store job on would create the same indents twice.

- Enable it per **store** (Settings → Store → *Indent Scheduler*: Inherit / Enabled / Disabled) or set the default for a whole hospital (Settings → Hospital → *Indent Scheduler Enabled*).
- A store's own choice always beats the hospital default; "Inherit" follows the hospital.
- Turning it on or off takes effect immediately — the scheduled job is created or removed on save, with no restart.
- Jobs for deleted stores are cleaned up automatically.

**Upgrading:** since the default is off, existing per-store indent jobs stop after the upgrade. Re-enable them for the stores that still need them.

### 8.10 Scheduler
Shows all automated jobs (per-store indent generation, per-hospital FSN, data-mining syncs) with their next run time and status. Jobs can be triggered **Run Now** individually or **Run All**. The view auto-refreshes.

### 8.11 User Management (Master only)
Create users, assign roles (**Master / Viewer / Planner / Planner View**), activate/deactivate, change any user's password, and delete users. Password strength is enforced with live feedback.

For **Planner / Planner View** users, the create/edit dialog also shows a **Store access** editor for assigning the hospitals and stores that user may work with (see *Location scoping* in §2). Stores are grouped under collapsible hospital sections with a search box, so it stays usable across many hospitals and hundreds of stores; ticking a hospital grants all of its stores (now and future). The editor is hidden for Master/Viewer, whose access is unrestricted.

### 8.11a Audit Trail (Master only)
A read-only record of **who changed what, and when**. Opens on the **latest 50 records**, newest first, and shows for each entry the time, the user (with role), the action, the affected record, a plain-English summary, and the originating IP address.

- Rows with recorded field changes expand to a **Field / From / To** table, so you can see exactly what a value was changed from and to (e.g. a store's lead time, or a user's assigned stores).
- Filter by **actor, action, entity, and date range**, and switch the page size (50 / 100 / 250 / 1000).
- Actions are colour-coded — deletions red, creations green, failed logins orange.
- Covers sign-ins (including **failed** attempts), password changes, user/role/store-access changes, all settings levels, master-data changes, data-mining and outbound configuration, purchase requests, and indent generation/clearing. Passwords and connection secrets are never stored in the trail.
- The trail is **append-only** — there is no way to edit or delete entries from the application.

### 8.11b Network Access (IP Restriction) — Master only
Restricts which network addresses may use the system.

- Configure a list of allowed **IP addresses or ranges** (e.g. `10.1.2.3`, or `10.1.0.0/16` for a whole hospital LAN), each with a description and an on/off switch.
- **While the list is empty the restriction is off and every address is allowed.** Adding the first enabled entry turns it on: only listed addresses can reach the system, and everyone else is refused.
- Changes take effect **immediately** — no restart needed.
- To prevent accidents, a change that would block **your own** address is rejected with a warning unless you explicitly confirm it.
- Every addition, change and removal is recorded in the Audit Trail.

### 8.11c Account Lockout
After **5 consecutive wrong passwords** an account is locked and cannot sign in — even with the correct password — until an administrator releases it. The count resets on any successful sign-in, and a lock never expires on its own.

- A locked user is told the account is locked and to contact an administrator (not merely to "try again later").
- The **User Management** screen shows a red **Locked** badge and an unlock button for affected accounts.
- Locks, failed attempts and releases all appear in the Audit Trail.
- If every administrator is locked out, a database administrator can release an account directly (see the Technical Documentation).

### 8.11d Password Rotation (90 days)
Passwords must be changed every **90 days**.

- From 7 days before expiry a banner warns the user, with a link to change it early.
- Once expired, the user can still sign in but is shown a **change-password dialog that cannot be dismissed**, and every other screen stays unavailable until a new password is set. This is enforced by the server, not just the screen.
- Setting a new password immediately restores access and starts a fresh 90-day period.
- Creating a user or having an administrator reset a password also starts a fresh period.
- On upgrade, everyone's clock starts from the upgrade date — no one is expired retroactively.

### 8.12 Outbound Dispatch (Stock Indents → external system + Kafka)
Automates handoff of generated indents to a downstream system. On a **single network-wide schedule**, the pipeline:

1. Generates indents for every store whose **request type is Stock Indent**.
2. For each such store, allocates a **request number** — `SI-{STORE_CODE}-{YYYYMMDD}-{seq}` (the sequence resets per store per day).
3. **Writes the indent lines to an external "outbound" table** (item code, store code, quantity, request number, request type, inserted date, request status), all tagged with that store's request number. **Only items with a quantity greater than zero are sent** — zero-quantity lines are never dispatched, and a store with nothing to order raises no request at all.
4. After the rows are written **and committed**, **publishes the request number to a Kafka topic** as `{"requestNumber": "..."}` — so a downstream consumer that reacts to the message can always read the rows.

The **Outbound Settings** page (master-only) configures it all: the external database connection (with a Test Connection button), the target table and its column mapping, the value written to `request_status` (default `NEW`), the dispatch schedule (cron), and the Kafka topic. A **Run Now** button dispatches immediately, and a **Recent Dispatches** table shows each store's request number, row count, and publish status.

**Reliability:** the pipeline is **idempotent** — re-running the same day/period reuses the same request number and replaces (never duplicates) the outbound rows. Kafka delivery is **at-least-once** via a durable outbox: if Kafka is temporarily unreachable, the rows are still written and the request numbers publish automatically once the broker is back (downstream consumers should treat a request number as unique).

### 8.13 Create Purchase Request
A user-driven counterpart to the automated stock-indent dispatch, for stores configured as **Purchase Request**. On the **Create Purchase Request** page (available to **Master** and **Planner**; **Planner View** can view but not create) the user:

1. Selects a **store** (must have request type **Purchase Request** in Store settings — otherwise the page shows a validation message and won't load).
2. Selects the **period** for which indents were generated; matching lines load.
3. Optionally filters by **preferred supplier** and/or an **item** code/name search.
4. Ticks specific items (or **select all**) and clicks **Create Purchase Request**.

Each candidate line shows the calculation behind the quantity, so the request can be sanity-checked without switching to Indent Planning: **Avg Daily** (forecast demand per day), **Closing Stk** (stock on hand), **Open Indent** (already on order), **Base Qty** (before surge, minimum order quantity and pack rounding) and the final **Qty**.

**Generate Batch** (Master and Planner) regenerates the store's indent lines from the current data without leaving the page — useful when the candidate list is empty or stale because indents have not yet been generated for the period. It reruns the same calculation as the Indent Planning screen and reloads the candidates; lines already flagged PR-initiated are preserved.

It runs for the **store selected in the Store dropdown and all of that store's items** — the Period, Supplier and Item filters only narrow what is displayed, not what is generated, and the reference date is today. It stays **disabled until a store configured for Purchase Request is selected and confirmed**, so it cannot be used on a Stock Indent store from this screen (use Indent Planning for those); it is also disabled while the store's lines are still loading.

The selected lines are written to the **same outbound table** with request type **PurchaseRequest** (request number prefixed `PR-`), the request number is published to Kafka, and each line is flagged **PR-initiated** so it drops off the list and can't be requested again. Only lines with a positive quantity that haven't already been PR'd appear as candidates. The PR-initiated flag survives indent regeneration, so a raised request is never re-offered.

---

## 9. Automation & Scheduling

The system automatically:
- **Generates indents per store** on the store's configured cadence (default every 30 days).
- **Recomputes FSN per hospital** on the hospital's FSN schedule (default every 30 days).
- **Runs data-mining syncs** on each configuration's cron schedule.
- **Dispatches stock-indent stores** (outbound table + Kafka) on the network-wide outbound schedule.
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
