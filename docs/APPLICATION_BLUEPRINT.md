# Application Development Blueprint

*A stage-by-stage template derived from building the Material Planning system
(FastAPI + React + PostgreSQL + Kafka, deployed as Docker images across UAT and
production).*

---

## How to use this document

This is not a generic "how to build software" guide. Every rule, checklist item
and anti-pattern below is traceable to a specific decision, bug, or outage-class
problem encountered while building **this** application. That is what makes it
reusable: the shape of the stages generalises, and the failures repeat.

Three ways to use it:

1. **Starting a new application** — walk Part I in order. Each stage has *Decide
   before you build*, *Deliverables*, and *Exit criteria*. Do not leave a stage
   until its exit criteria hold; most of the expensive rework in this project
   came from stages declared "done" while an exit criterion was still open.
2. **Auditing an application in flight** — jump to Part III and run the
   checklists. They are written to be answerable yes/no.
3. **Debugging a class of problem** — Part IV is a catalogue of real defects,
   each with the symptom, the root cause, and the generalised rule.

**A note on sequencing.** The stages are ordered by *dependency*, not by
calendar. Stages 7–11 (integration, scheduling, security, observability,
performance) are not a "phase two" — they are threads that start early and run
continuously. Treating them as a later phase is the single most common way a
project accumulates the debt catalogued in Part IV.

---

# Part I — The Stages

---

## Stage 0 — Frame the problem

**Goal:** know what you are building, for whom, and what "correct" means, before
any schema exists.

### Decide before you build

| Question | Why it matters later |
|---|---|
| What is the **unit of work** the domain revolves around? | It becomes your primary aggregate, your batch boundary, and your idempotency key. Here it was *(item, store, period)*. |
| What is the **scale** in each dimension? | 13,000 items × 200 stores = 2.6M combinations. That number should have been on a whiteboard on day one; it determines whether per-row processing is viable at all. |
| Who are the **actors** and what may each do? | Roles designed late get bolted on as `if user.is_admin` scattered through handlers. |
| What is the **system of record** for each entity? | Determines which data you own, which you mirror, and which you must never write. |
| What must be **auditable**? | Retrofitting an audit trail means touching every mutating path. |
| What are the **environments** and how do they differ? | Drives config strategy (Stage 12) more than anything else. |

### The scale question, concretely

Write down the cardinality of every entity and every important join *before*
designing the calculation. Then multiply.

```
items                 13,000
stores                   200
item × store       2,600,000     ← the real working set
× queries per unit        15
= round trips     39,000,000     ← per run
```

If a number like that appears, the architecture must be *set-based* from the
start. Retrofitting it later is possible (this project did it — Stage 11) but
costs a full rewrite of the core path plus a parity test suite to prove nothing
changed.

### Deliverables
- One-page domain glossary (every term used in code and UI means one thing)
- Cardinality table with the multiplied working-set size
- Role × capability matrix
- Environment list with what differs between them

### Exit criteria
- [ ] You can state the unit of work in one sentence
- [ ] The largest working-set number is written down and someone has said out loud whether per-row processing is acceptable at that size
- [ ] Every role's capabilities are enumerated, not implied

---

## Stage 1 — Domain and data model

**Goal:** a schema that reflects the domain and the *access patterns*, not just
the entities.

### Design rules that paid off

**Model the hierarchy explicitly if the domain has one.** This application
resolves every setting through a six-level hierarchy:

```
item×store  >  item  >  category  >  group  >  store  >  hospital  >  system default
```

One table per level, all columns nullable, `NULL` meaning "inherit". A single
resolver walks the levels. This is enormously better than denormalising defaults
into the leaf rows, because changing a hospital-wide default takes effect
immediately everywhere it was not overridden.

**Make the resolution order data, not code.** A per-store `settings_priority`
column ("item_store,item,store,hospital") lets a store *drop* levels it does not
want. The resolver parses it; unknown tokens are dropped; blank means the system
default order.

**Separate "the value" from "who may set it".** Some settings only exist at one
level (`min_order_qty` at item×store; FSN thresholds at hospital only). Encode
that as a set of keys, not as a comment.

### Index design is part of the data model, not a later optimisation

Indexes must be designed from the **access patterns**, and access patterns
usually split into more than one shape. In this application:

| Reader | Filter shape | Index needed |
|---|---|---|
| Consumption analysis, single-pair calc | `item_id = ? AND store_id = ? AND date BETWEEN` | `(item_id, store_id, date)` |
| Batch indent generation | `store_id = ? AND date BETWEEN` | `(store_id, date, item_id)` |
| Mining `replace_date` delete | `date = ?` | `(date)` |

**A composite index serves only a *prefix* of its columns.** An
`(item_id, store_id, date)` index cannot help a `store_id`-only filter. This one
fact caused the batch path to read every row a store had ever accumulated. Both
directions are needed when both readers exist.

**Delete redundant indexes deliberately.** Auto-generated single-column indexes
(`index=True` on a primary key, or on a column that already leads a composite)
can never be chosen and cost write amplification on every insert. On tables
taking millions of rows a day this is pure loss. Fourteen such indexes were
removed from this schema.

**Decide retention at schema time.** Snapshot tables (daily closing stock, daily
consumption) and regenerated tables (indent reports) grow without bound unless
someone decides otherwise. Every retained period makes every scan larger. If
retention is "we'll decide later", write it in the ticket queue on day one —
"later" arrives as an incident.

### Deliverables
- ERD with cardinalities
- Per-table index list, each index annotated with *which query it serves*
- Retention policy per table (including "unbounded, accepted, because…")

### Exit criteria
- [ ] Every index maps to a named query; every hot query maps to an index
- [ ] No index is a prefix of another index on the same table
- [ ] Every table that grows monotonically has a written retention decision

---

## Stage 2 — Core domain logic

**Goal:** the calculation/business rules, expressed so they can be tested,
reused, and optimised without being rewritten.

### The single most valuable structural rule

> **Separate *gathering inputs* from *computing the answer*.**

Write the computation as **pure functions that take already-resolved values**.
Then write thin adapters that fetch those values. This one decision:

- makes the logic testable without a database,
- lets you add a batched/bulk path later **without duplicating the formula**,
- makes a formula change impossible to apply to one path and not the other.

This project learned it the hard way. The original calculation interleaved
queries and arithmetic:

```python
def build_report(db, item_id, store_id, as_of):
    s = resolve_all(db, item_id, store_id)        # 8 queries
    avg = avg_daily(db, item_id, store_id, ...)   # 1 query
    closing = latest_closing_stock(db, ...)       # 1 query
    ...                                           # 15 queries total, per pair
    return IndentReport(...)                      # arithmetic buried at the end
```

At 2.6M pairs that is 39M round trips. The fix was to extract the arithmetic
into `_assemble_report(...)` plus pure helpers, then add a second adapter that
loads a whole store's inputs at once:

```python
# Pure core — no DB, shared by both paths
def _assemble_report(*, item_id, store_id, s, avg_daily, closing_stock,
                     open_qty, lead_time_days, surge_qty) -> Report: ...

# Adapter A: one pair, fetches its own inputs      (~15 queries)
# Adapter B: one store, bulk-loads every input     (~13-19 queries, flat)
```

Result: **13–19 queries per store regardless of item count** (verified: a
1-item store costs 17, a 2,454-item store costs 19).

### Prove equivalence, do not assert it

When you add a second path, the risk is silent divergence. Mitigate with a
**parity test**: seed a fixture that exercises every branch, run both paths, and
assert field-for-field equality.

The fixture must be deliberately awkward. This project's covers: all three
forecast methods, mixed per-item lookback windows, both replenishment floors,
minimum order quantity, pack-size rounding, averaged *and* disabled surge
records, multi-row snapshots, items with no consumption, items with no stock,
and a disabled-planning item that both paths must refuse.

Parity was verified over 4,299 real pairs with **0 mismatches** before the new
path was trusted.

### Preserve quirks deliberately

Two behaviours in this calculation look like bugs:

- the baseline-average window is one day wider than the dense-series window;
- duplicate same-day rows are *summed* for one statistic and *last-wins* for another.

They were **preserved**, with comments explaining why, because a performance
change must not silently alter output. Fix quirks in a separate, announced
change where the diff in results is the point.

### Deliverables
- Pure calculation module with no persistence imports
- Adapters per access pattern
- Parity test if more than one adapter exists
- A written note for each preserved quirk

### Exit criteria
- [ ] The formula appears exactly once in the codebase
- [ ] Core logic tests run without a database
- [ ] Every adapter produces identical output, proven by test

---

## Stage 3 — Persistence, migrations, and session semantics

**Goal:** predictable data access; schema changes that deploy safely.

### Migration strategy

This project uses an idempotent startup script of `ALTER TABLE … ADD COLUMN IF
NOT EXISTS` statements rather than a migration framework. That is a legitimate
choice for a single-deployment application, with conditions:

- every statement must be **idempotent and re-runnable**;
- backfills must be safe on an existing dataset (adding
  `password_changed_at`, the script backfills to `NOW()` so an upgrade does not
  instantly expire every account and lock the admins out);
- **destructive or long-locking DDL must not run at startup.**

That last point matters. `CREATE INDEX` on a large table takes an
`ACCESS EXCLUSIVE` lock — running it at container start means the application is
down for the duration. Index creation for this project ships as a **separate SQL
script using `CREATE INDEX CONCURRENTLY`**, applied deliberately in a low-traffic
window, while the model definitions cover fresh databases. Never surprise a
production database at boot.

### ORM session semantics deserve an explicit decision

Two defaults quietly cost this application millions of queries:

**1. `expire_on_commit=True` (the default).** Every commit expires all loaded
instances; touching an attribute afterwards re-SELECTs the row. The batch path
commits thousands of reports and the caller then reads their quantities:

```
expire_on_commit=True    314 reports →  314 queries on the post-commit read
expire_on_commit=False   314 reports →    0 queries
```

At production scale that was ~2.6M extra queries per run, invisible in the code.

**2. Negative lookups are never cached.** An identity-map `get()` that returns
`None` re-queries every single time. In a hierarchy where most levels are unset,
that is most of your lookups.

**Rule:** configure the session explicitly, document why, and **make the test
fixture mirror it**. This project's tests originally used a default session, so
they did not exercise real semantics — a bug that only surfaced when a change
depended on them.

### Long-running jobs need session hygiene

A job iterating 200 stores × 13,000 rows will accumulate millions of ORM
instances in the identity map, and every flush walks it. Expunge what you no
longer need — but only if the session does not expire on commit, or the detached
instances become unusable:

```python
if not db.expire_on_commit:
    for r in reports:
        db.expunge(r)
```

### Connection pool

The default pool (5 + 10 overflow) assumes short request-scoped work. A
scheduled job holding one connection for its entire run leaves the API
contending for the rest. Size the pool for *concurrent workloads*, and expose it
as configuration.

### Deliverables
- Migration script (idempotent) + separate script for long-locking DDL
- Documented session configuration
- Pool sizing as config, not a constant

### Exit criteria
- [ ] Migrations re-run cleanly against an already-migrated database
- [ ] No DDL that takes a long exclusive lock runs automatically at startup
- [ ] Test fixtures use the same session settings as production
- [ ] Backfills are safe on existing rows

---

## Stage 4 — API layer and authorization

**Goal:** a consistent surface with authorization that cannot be forgotten.

### Authorization as composable dependencies

Express permissions as reusable dependencies, not inline checks:

```python
require_master               # role gate
require_roles("planner", "planner_view")
assert_store_access(db, user, store_id)   # data-scope gate
```

**Two distinct concerns, both required:**

1. **Role gates** — *may this kind of user call this endpoint?*
2. **Data-scope gates** — *may this specific user see this specific row?*

Role gates alone are the classic hole: a `planner` who is allowed to call
`/indents` can still read another hospital's data unless the query is scoped.
This application maps users to hospitals *and* stores (a hybrid grant: a
hospital grant implies all its stores; store grants add individual ones), with a
convention that returning `None` from `accessible_store_ids()` means *unscoped*
— distinct from returning `[]`, which means *no access at all*. Conflating those
two is a silent privilege escalation or a silent lockout.

### Design the grant UI for the real cardinality

An admin screen that renders 200 checkboxes is unusable, and one that renders
10,000 is a browser hang. The grant model and its UI must be designed against
the Stage 0 cardinality table, not against the demo dataset.

### Error responses

- Return a **stable error shape** with an `error_id` that also appears in the
  server log; users can quote the id, and internals stay server-side.
- Distinguish status codes that mean different things to the caller. This
  application returns **423 Locked** for a locked account and **429** for rate
  limiting; originally a locked account got 429, which sent users down the
  "wait and retry" path for a condition that waiting would never fix.

### Deliverables
- Dependency-based auth gates, applied at router level where possible
- Data-scoping helper used by every endpoint that reads scoped data
- Documented error envelope

### Exit criteria
- [ ] No endpoint reads scoped data without a data-scope gate
- [ ] `None` vs `[]` semantics for "unscoped" vs "nothing" are documented and tested
- [ ] Every 4xx the client must handle differently has a distinct status code

---

## Stage 5 — Frontend

**Goal:** a UI that survives being deployed somewhere other than `localhost:3000`.

### Build-time versus run-time configuration

This is the highest-leverage frontend decision, and the most commonly botched.

A bundler bakes `import.meta.env.*` / `process.env.*` into the compiled output.
That means **any value baked at build time requires a different image per
environment**. In this project:

| Layer | Config style | Images needed |
|---|---|---|
| Backend | pure run-time env vars | **one** image for all environments |
| Frontend | build-time baked (`APP_BASE`, API URL, env ribbon) | **one per environment** |

Consequences to plan for:
- you cannot promote a UAT frontend image to production by retagging;
- a "change the API URL" request is a rebuild, not a restart;
- if you want a single image, you need run-time config (a `config.json` fetched
  at startup, or server-injected `<script>` values) — decide **before** you have
  a release pipeline.

### Context-path (sub-path) deployment

Serving from `/myapp/` instead of `/` breaks things in ways that only appear in
production. Two real defects from this build:

**Router basename vs. hard redirects.** The router was configured with
`basename={import.meta.env.BASE_URL}`, so in-app navigation was correct. But the
401 interceptor did:

```js
window.location.href = '/login'      // bypasses basename entirely
```

An expired session under `APP_BASE=/mtp/` therefore landed on `host/login` —
outside the served context — showing the web server's default page instead of
the login screen. **Rule: every `window.location` assignment must be prefixed
with the base path; the router only handles in-app navigation.**

**Static server configuration must be base-aware.** The SPA fallback, the root
redirect, and the asset paths all change with the base. Generate the server
config from the same variable that built the bundle, rather than maintaining two
files that must agree.

### Cache headers are part of the deployment, not a detail

A static server that sends **no `Cache-Control`** lets browsers cache
heuristically off `Last-Modified`. A cached `index.html` names the *previous*
build's hashed asset files, so a redeployed image appears not to take effect —
intermittently, and "fixed" by a hard refresh, which makes it look like a
phantom.

```
index.html + SPA fallback   →  Cache-Control: no-store, must-revalidate
/assets/* (content-hashed)  →  Cache-Control: public, max-age=31536000, immutable
```

**Nginx-specific trap:** `add_header` is *not additive*. Declaring one inside a
`location` block discards the entire inherited set. Adding `Cache-Control`
naively silently drops your CSP and every other security header. Put the shared
headers in an include file and re-include it in every location that sets its own.

### Client-side state on identity change

Any client-side cache keyed by "the current user's data" must be cleared on
login **and** logout. This application uses TanStack Query; without
`queryClient.clear()` on both transitions, a scope-limited user saw the previous
user's unscoped data until a manual page reload.

### Deliverables
- Documented list of build-time vs run-time config values
- Base-path handling verified for: deep-link reload, expired-session redirect, bare root
- Cache-header policy
- Cache-clearing on identity change

### Exit criteria
- [ ] The app works when served from a sub-path, including reload on a deep route
- [ ] No `window.location` assignment omits the base path
- [ ] `index.html` is non-cacheable and hashed assets are immutable
- [ ] Security headers survive in every location block

---

## Stage 6 — External integration

**Goal:** exchange data with systems you do not control, without losing or
duplicating it.

### Ingest: make the write mode explicit

When importing snapshots from an external system, "insert the rows" is
under-specified. This application ended up needing three distinct modes:

| Mode | Behaviour | Use when |
|---|---|---|
| `skip` | ignore rows that already exist | append-only history |
| `overwrite` | update existing rows in place | corrections to known keys |
| `replace_date` | **delete the whole date, then insert** | the feed is the authoritative daily snapshot |

`replace_date` has a subtlety worth generalising: with **paged** processing, a
naive "delete then insert" deletes rows the *same run* just inserted on an
earlier page. The delete must fire **once per run**, guarded by the page offset:

```python
if page_num == 0:                     # fire the wipe on the first page only
    for on_date in to_purge:
        db.query(model).filter(date_col == on_date).delete(...)
```

Its blast radius must also be stated plainly: clearing the whole date means a
feed covering only *some* stores will remove the others' data for that date.
Correct when the feed is the whole-network snapshot; wrong if you run two
configs for the same date.

### Egress: transactional outbox

Writing to an external database *and* publishing to a message broker *and*
updating your own state is a distributed-write problem. The pattern that worked:

```
1. Reserve an idempotency key (request number) and COMMIT it first
2. Write to the external target — idempotent: DELETE by key, then INSERT
3. In ONE local transaction: mark dispatched + insert the outbox event
4. A separate poller publishes outbox events and marks them published
```

Properties this buys:
- **At-least-once** delivery with no dual-write inconsistency
- Broker downtime delays publication; it never loses or rolls back the business record
- Retries are safe because step 2 is keyed and idempotent
- Consumers must dedupe on the key — say so in the integration contract

**Publish only after the data is committed.** A consumer that reacts to the
message must be able to read the rows. Publishing inside the transaction that
writes them is a race you will lose intermittently.

### Integration hygiene that caught real bugs

- **Log broker coordinates on success** — `published KEY -> topic[partition] @ offset N`. Without it, "did it send?" is unanswerable.
- **Name things once.** A producer using `material_planning_event` and a consumer using `material-planning-event` looks identical at a glance and fails silently. Put topic names in shared config, never in two string literals.
- **Validate admin-supplied identifiers.** Target table and column names cannot be bound parameters, so they get interpolated into SQL — that is a stored-injection vector. Validate against a strict identifier pattern before interpolating.
- **Filter at the choke point.** "Only positive quantities go outbound" is enforced where rows are *built*, not only where they are selected, so no future caller can bypass it.

### Exit criteria
- [ ] Every external write is idempotent under retry
- [ ] Publication happens after commit
- [ ] Names shared with another system exist in exactly one place
- [ ] Interpolated SQL identifiers are validated

---

## Stage 7 — Scheduling and background work

**Goal:** jobs that run when intended, survive restarts, and can be reasoned about.

### Persistent job stores need lifecycle management

Using a database-backed scheduler store means jobs **outlive the process** —
including jobs for entities that no longer exist. This application accumulated
**104 orphaned per-store jobs** for deleted stores, firing indefinitely.

Rules:
- prune orphaned jobs at startup, making current configuration authoritative;
- unschedule explicitly when the owning entity is deleted;
- make "should this job exist?" a derived property of configuration, not an
  action someone remembered to take.

### Default scheduled work to *off*

A per-store job that defaults to on will, at 200 stores, create 200 jobs nobody
asked for — and if another subsystem already does the same work (here, the
outbound pipeline generates indents itself), they duplicate. Default off; make
enabling explicit and configurable at the level that owns the decision.

### Timezone: two separate knobs

Container OS time (log timestamps) and application time (cron interpretation,
stored timestamps) are different things, and slim base images often lack
`tzdata`, so setting `TZ` silently does nothing. Symptom: container logs show
UTC while the database and downstream systems show local time — the same
instant, presented two ways, which burns hours in incident review.

Provide **one deploy-time variable** that sets both, and install `tzdata`.

### Exit criteria
- [ ] Orphaned jobs are pruned at startup
- [ ] Deleting an entity unschedules its jobs
- [ ] Scheduled work defaults to off
- [ ] One timezone knob drives OS and app; `tzdata` is installed

---

## Stage 8 — Security hardening

**Goal:** defensible by default; failures are loud, not silent.

Run this as a **scoped audit** producing a written document, then implement
against it. This project produced `SECURITY_AUDIT_SCOPE.md` first and worked
through it, which kept the work bounded and reviewable.

### Secrets: no shipped defaults

- **Refuse to boot** on a known-shipped secret. A default JWT key in a public
  repo means every token is forgeable.
- A **blank** secret should generate a random one *and log loudly* — safe by
  default, but sessions die on restart and replicas reject each other, so it is
  visibly not a production configuration.
- **Reject `*` for CORS** when credentials are enabled.
- Assume anything ever committed is compromised. Rotation is the remedy;
  deleting the file is not.

### Layered access control

| Layer | Mechanism | Failure mode it addresses |
|---|---|---|
| Network | IP allowlist (DB-configured, memory-cached, empty = allow all) | unauthorised origin |
| Session | JWT with expiry | stolen/stale token |
| Credential | bcrypt, rotation window, lockout on consecutive failures | password attack |
| Rate | per-username and per-IP sliding window | brute force |
| Role | role gates | wrong kind of user |
| Data | scope gates | right kind of user, wrong rows |

### Two real bugs worth internalising

**Cached-policy poisoning.** The IP allowlist is cached in memory for speed. A
guard reloaded that shared cache *inside an uncommitted transaction*, so a rule
that was subsequently rejected started being enforced globally. **Rule: never
populate a shared cache from uncommitted state.** Provide a separate
cache-bypassing read for validation paths.

**Interacting lockouts.** Account lockout (per user, released in the DB) and
throttling (per IP) were both counting the same failures. An administrator who
unlocked an account in the database found the user still blocked, by a different
mechanism with a different message. **Rule: when two protections can trigger on
the same event, define precedence explicitly, make each independently
releasable, and return distinct, accurate status codes.**

### Response headers, conditionally

Send HSTS **only over HTTPS** — browsers ignore it on plain HTTP, and it can
wrongly pin an http-only deployment. Generate the header set per scheme rather
than sending one list everywhere.

### Exit criteria
- [ ] Boot fails on a known-compromised secret
- [ ] Every protection is independently releasable by an operator
- [ ] No shared cache is populated from uncommitted state
- [ ] HSTS is TLS-only; CSP present; `*` CORS rejected

---

## Stage 9 — Observability and audit

**Goal:** answer "what happened, to what, by whom, when" without a debugger.

### Audit trail

Decide **what** is auditable from the domain, not from the code. This
application's scope: authentication events, user/role/grant changes, settings
changes, master-data changes, imports, outbound dispatch and PR creation,
security-configuration changes. Each record: actor, action, entity type, entity
id, timestamp, source IP, outcome.

Give it a **UI with a sensible default** (latest 50) — an audit trail only
reachable by SQL will not be used, and therefore will not be maintained.

### Logging discipline at scale

A log line that is reasonable per request is catastrophic per row. A single
`log.info` inside the per-item calculation becomes **2.6M lines per run** — real
I/O, and contention if logs share a disk with the database.

**Rule:** log level should scale with the *unit*, not the *event*. Per-run and
per-store at INFO; per-item at DEBUG.

### Error identity

A global exception handler that assigns an `error_id`, logs the detail
server-side, and returns only the id gives users something to quote without
leaking connection strings, SQL, or host names into a browser.

### Exit criteria
- [ ] Every mutating path writes an audit record
- [ ] Audit is viewable in the UI
- [ ] No log statement fires per row at INFO
- [ ] Errors return an id, not internals

---

## Stage 10 — Testing

**Goal:** tests that would have caught the bugs you actually shipped.

### Layers

| Layer | Scope | Speed |
|---|---|---|
| Pure logic | calculation cores, no DB | milliseconds |
| Service | against a real schema (in-memory or containerised) | seconds |
| Parity | two implementations must agree | seconds |
| Contract | API shape, status codes, auth gates | seconds |
| Smoke | the built artifact, running | minutes |

### Prove your tests can fail

A regression test that passes against the *old* code proves nothing. When fixing
the replenishment-floor bug, the fix was validated by **temporarily reverting
the logic** and confirming the four new tests failed, then restoring it and
confirming they passed. Do this once per genuinely important test.

### Fixtures must mirror production semantics

Test session configuration must match the application's. A fixture using
framework defaults where production overrides them means the tests are
exercising a system you do not deploy.

### Test the artifact, not the source

The most embarrassing bug class in this project: **a fix was made in the source,
the tests passed, and the deployed behaviour was unchanged — because the image
had not been rebuilt.** For anything baked at build time (frontend bundles,
compiled config), verification must inspect the *built output*:

```bash
# not "is the source right?" but "is the shipped bundle right?"
curl -s "$HOST/assets/index-<hash>.js" | grep -o 'expected-token'
```

### Exit criteria
- [ ] Core logic tests need no database
- [ ] Each important regression test has been observed failing against the old code
- [ ] Fixtures mirror production session/config semantics
- [ ] Build-time-baked behaviour is verified against the built artifact

---

## Stage 11 — Performance

**Goal:** find the real cost, fix the structure, prove the change.

### Method: measure, do not reason

Reasoning about performance from source produces plausible wrong answers. The
sequence that worked here:

**1. Instrument and count.** A query-counting hook is worth more than any amount
of reading:

```python
@event.listens_for(engine, "before_cursor_execute")
def _count(conn, cursor, statement, params, context, executemany):
    counts[table_of(statement)] += 1
```

Output: **15 queries per unit of work**, attributed by table — which immediately
showed that three of them re-fetched the *same store row* for every item.

**2. Multiply by the Stage 0 cardinality.** 15 × 2.6M = 39M round trips.

**3. Read the actual plans.** `EXPLAIN (ANALYZE, BUFFERS)` showed a delete
reading every period and discarding non-matches in memory
(`Rows Removed by Filter: 2502`) — invisible from the code, obvious from the plan.

**4. Fix the structure, then the details.** Batching removed ~99.99% of the
queries; indexes and pool sizing were secondary.

**5. Re-measure and quote real numbers.**

```
before:  15 queries/item   ·  4,299 items → 64,485+ queries, ~20 s
after:   13-19 queries/store (flat) ·  4,299 items → 59 queries, 0.45 s
```

**6. Report honestly.** One measurement in this exercise (210 queries/item from
a harness) could not be attributed and was therefore **not** quoted; the
reproducible 15/item figure was. A number you cannot explain is not evidence.

### The recurring performance anti-patterns

| Pattern | Symptom | Fix |
|---|---|---|
| N+1 per unit of work | high load, no slow query | batch-load per parent |
| ORM expiry on commit | queries after a write, from reading your own objects | `expire_on_commit=False` |
| Uncached negative lookups | repeated identical queries returning nothing | preload the whole small table |
| Wrong index column order | full scans on a filtered query | index per access pattern |
| Redundant indexes | slow writes | drop prefixes and PK duplicates |
| Missing column in index | `Rows Removed by Filter` in the plan | add the filtered column |
| Unbounded growth | everything degrades over months | retention policy |
| Per-row logging | I/O contention | level scales with unit |

### Exit criteria
- [ ] Query counts measured, not estimated
- [ ] Hot query plans read and understood
- [ ] Improvement quoted with before/after numbers from the same harness
- [ ] Behaviour proven unchanged (parity tests)

---

## Stage 12 — Packaging and deployment

**Goal:** reproducible artifacts; environments that differ only where intended.

### Determine images from config style

From Stage 5: run-time-configured services need **one** image; build-time-baked
services need **one per environment**. State this explicitly in the build script
so nobody tries to promote by retagging.

### Environment isolation on a shared host

Running UAT and production side by side requires every collision point to be
parameterised:

```
project name  ·  container names  ·  ports  ·  volumes  ·  image tags
```

Compose project prefixing handles volumes and container names; ports and tags
must be explicit. One `.env` per environment, one compose file.

### Make the environment visible in the UI

An environment ribbon, enabled only by a deploy-time variable (blank in
production), prevents "I was testing in the wrong system". Two implementation
notes that cost time here:

- `??` (nullish coalescing) does **not** fall back on an empty string, and an
  unset build arg is `""`, not `undefined` — use `||` for build-arg defaults;
- do not weaken it with opacity; the point is that it cannot be missed.

### Deliverables
- Build script parameterised by environment, emitting tagged, exported images
- One compose file, one `.env` per environment
- Documented rollout: load images → apply pending DDL → recreate containers
- `.env.example` per environment, tracked; real `.env` never tracked

### Exit criteria
- [ ] Two environments run on one host without collision
- [ ] Rebuild from a clean checkout produces an equivalent image
- [ ] Deployment does not run long-locking DDL implicitly
- [ ] The running environment is identifiable from the UI

---

# Part II — Cross-cutting playbooks

## Configuration taxonomy

Classify **every** setting into exactly one of these, and record it:

| Class | Changed by | Takes effect | Example |
|---|---|---|---|
| Build-time baked | rebuild | new image | frontend base path, API URL, ribbon |
| Deploy-time env | restart | container restart | DB URL, secrets, timezone, pool size |
| Runtime DB config | admin in the UI | immediately | IP allowlist, outbound target, schedules |
| Domain settings | planner in the UI | next calculation | lookback days, safety stock, pack size |

Misclassification is expensive in one direction specifically: putting something
in the build-time class that operations needs to change means a rebuild for a
config tweak.

## Idempotency patterns used

| Operation | Key | Mechanism |
|---|---|---|
| Report regeneration | (store, period, item set) | delete-then-insert in one transaction |
| Snapshot ingest | (date) | `replace_date`, delete fired once per run |
| External write | request number | delete-by-key then insert |
| Message publish | request number | outbox + consumer-side dedupe |
| Sequence allocation | (store, day) | `SELECT … FOR UPDATE` + savepoint for first-insert race |

## Failure-handling posture

Decide per operation, and write it down:

- **Fail fast** — compromised secret, invalid config at boot.
- **Fail soft, retry** — broker unavailable (leave queued; do not count as a message failure — a down broker is not a bad message).
- **Fail soft, skip** — one item's calculation raises; log and continue, count skipped.
- **Fail loud, halt** — external write failed; mark the dispatch failed with the error, do not publish.

---

# Part III — Reusable checklists

## Before writing code
- [ ] Domain glossary written
- [ ] Cardinality table with the multiplied working set
- [ ] Role × capability matrix
- [ ] Config taxonomy started
- [ ] Environments enumerated with their differences

## Before merging a feature
- [ ] Data-scope gate on every scoped read
- [ ] Audit record on every mutation
- [ ] No per-row logging at INFO
- [ ] Indexes exist for the new access pattern
- [ ] Tests exist and have been seen failing against the old code
- [ ] Documentation updated in the same change

## Before deploying
- [ ] Migrations re-run cleanly against a migrated database
- [ ] Long-locking DDL applied separately and deliberately
- [ ] Images rebuilt for anything baked at build time
- [ ] Verified against the **built artifact**, not the source
- [ ] Sub-path routing checked: deep reload, expired session, bare root
- [ ] Cache headers correct
- [ ] Environment ribbon shows the right environment

## Performance investigation
- [ ] Query count measured with a hook, attributed by table
- [ ] Multiplied by real production cardinality
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` read for each hot query
- [ ] Structure fixed before micro-optimisation
- [ ] Re-measured on the same harness
- [ ] Output proven unchanged
- [ ] Only explainable numbers quoted

## Security review
- [ ] No shipped secret can boot the app
- [ ] CORS explicit, `*` rejected
- [ ] HSTS only on HTTPS; CSP present
- [ ] Interpolated SQL identifiers validated
- [ ] Every lockout independently releasable
- [ ] No shared cache populated from uncommitted state
- [ ] Distinct status codes for distinct conditions

---

# Part IV — Anti-pattern catalogue

Each entry: **symptom → root cause → generalised rule.**

| # | Symptom | Root cause | Rule |
|---|---|---|---|
| 1 | Sustained high DB load, no slow query in logs | N+1: 15 queries × 2.6M units = 39M round trips | Batch by parent entity; separate gathering from computing |
| 2 | Queries fire *after* a write, reading your own objects | ORM expires instances on commit | Configure session expiry explicitly; mirror it in fixtures |
| 3 | Repeated identical queries returning nothing | Negative lookups are never cached | Preload small lookup tables wholesale |
| 4 | Query reads a whole partition to return a few rows | Composite index leads with the wrong column | One index per access pattern; a composite serves only a prefix |
| 5 | `Rows Removed by Filter` in the plan | Filtered column absent from any index | Add it |
| 6 | Writes slow on a high-insert table | Redundant indexes (PK duplicates, prefixes) | Audit and drop |
| 7 | Everything degrades over months | No retention policy | Decide retention at schema time |
| 8 | Redeploy appears to have no effect | Static server sends no `Cache-Control`; browser reuses stale `index.html` | `no-store` for HTML, `immutable` for hashed assets |
| 9 | Adding a cache header silently dropped CSP | Nginx `add_header` replaces the inherited set | Shared headers in an include, re-included per location |
| 10 | Expired session lands on the web server's default page | `window.location` bypasses the router basename | Prefix every hard redirect with the base path |
| 11 | Deep-link reload 404s under a sub-path | SPA fallback not base-aware | Generate server config from the same variable as the build |
| 12 | Fix works locally, not in the deployed app | Build-time-baked value; image not rebuilt | Verify the built artifact |
| 13 | User sees the previous user's data until reload | Client cache not cleared on identity change | Clear on login **and** logout |
| 14 | Message never arrives, no error anywhere | Topic name spelled two ways in two places | Shared names live in one place |
| 15 | Consumer reads and finds nothing | Published before the transaction committed | Publish after commit |
| 16 | Paged snapshot import loses rows | Delete re-fired on later pages of the same run | Guard bulk deletes on the page offset; once per run |
| 17 | A rejected config rule started being enforced | Shared cache reloaded inside an uncommitted transaction | Never populate a shared cache from uncommitted state |
| 18 | DB-level account unlock did not work | A second protection (IP throttle) still blocking | Define precedence; make each independently releasable |
| 19 | Users told to "wait and retry" a permanent lock | Locked account returned 429 instead of 423 | Distinct status codes for distinct conditions |
| 20 | Jobs firing for deleted entities | Persistent job store outlives entities | Prune at startup; unschedule on delete |
| 21 | Duplicate work from two subsystems | Per-entity jobs default to on | Default scheduled work off |
| 22 | Logs and database disagree about time | Container `TZ` unset or `tzdata` missing | One timezone knob for OS and app; install `tzdata` |
| 23 | Upgrade locks every user out | Backfill expired all passwords at once | Backfill to `NOW()`, not to the epoch |
| 24 | Startup hangs / app down after deploy | Long-locking DDL ran automatically | Long DDL is a separate, deliberate step |
| 25 | Env ribbon invisible | `??` does not fall back on `""`; unset build arg is `""` | Use `\|\|` for build-arg defaults |
| 26 | UI unusable at real scale | Grant UI designed against demo data | Design UI against the cardinality table |
| 27 | Migration breaks with a syntax error | Unescaped quotes inside a shell-embedded script | Keep migration SQL out of nested shell quoting, or escape and test |

---

## Closing note

The stages generalise. The specific numbers do not — **yours will differ, and
you must measure them rather than inherit them from this document.** The single
most transferable habit in the whole blueprint is the one in Stage 11: instrument
first, multiply by real cardinality, read the plan, fix the structure, re-measure,
and quote only what you can explain.
