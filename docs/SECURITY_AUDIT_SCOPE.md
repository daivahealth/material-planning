# Security & Application Audit Scope

> **Audience:** auditors, reviewers, and the engineering team.
> **Scope:** the Hospital Material Planning application — FastAPI backend + React/Vite frontend + PostgreSQL, with a Kafka outbound pipeline and external-DB data-mining, deployed via Docker Compose.
>
> Severity legend: 🔴 high · 🟠 medium · 🟡 low. Items marked **(known)** were identified during development and are documented here so they are not missed.
> Use the checkboxes to track audit progress. This is an audit *scope*, not a certification — each box is a thing to verify, not a claim that it passes.

---

## A. Authentication & session management
- [ ] 🔴 **(known)** `jwt_secret_key` has a hardcoded default in `backend/app/config.py`. Confirm it is overridden in every environment; if the dev default ever shipped, all tokens are forgeable. Rotate.
- [ ] 🔴 **(known)** Default admin `admin` / `Admin@123` seeded by `backend/start.sh`. Verify changed/disabled in prod. Check for leftover test accounts (`planner1`, `pview1`).
- [ ] Token model: JWT HS256, 24h TTL, **no refresh, no server-side revocation/logout, no blocklist**. Assess whether a 24h window for a leaked token is acceptable.
- [ ] Password policy (≥8, upper, digit, special) present, but: no account lockout, no brute-force throttling, no password history/expiry. Assess.
- [ ] bcrypt hashing (direct, not passlib) — verify cost factor; confirm no plaintext/hash leakage into logs or responses.
- [ ] Self-service password reset requires current password — verify.

## B. Authorization & access scoping
- [ ] Audit **every** mutating endpoint for a role guard (`require_master` / `require_roles`); confirm none rely solely on the UI hiding the control.
- [ ] **(known)** Location scoping (`app/services/access.py`: `accessible_store_ids` / `assert_store_access`). Verify enforcement on **all** store-touching endpoints. Confirmed added to indents generate/list, consumption analysis, PR candidates/create. **Re-audit:** indents export, surges, settings-resolve, dashboard, classification — for scoped-user data leakage.
- [ ] Confirm a `planner` / `planner_view` cannot read another store's data via any list endpoint missing the scope filter.
- [ ] IDOR: object-level authorization on `/{id}` routes (users, settings, item-suppliers, hospitals, stores).
- [ ] Client-side RBAC (`utils/permissions.ts`) is UX-only — reconfirm the server is the true boundary.

## C. Secrets & configuration management
- [ ] 🔴 **(known)** Hardcoded secrets: `mining_secret_key` and `jwt_secret_key` defaults in `config.py`; `MINING_SECRET_KEY` literal in **both** `docker-compose.yml` and `docker-compose.prod.yml`; DB creds `matplan/matplan`. Move to a secrets manager / `.env` excluded from VCS; **rotate the exposed Fernet + JWT keys**.
- [ ] 🔴 The Fernet key (`MINING_SECRET_KEY`) decrypts **all** external-DB passwords (data-mining + outbound). Audit key storage, access, and rotation plan; leak = all source creds compromised.
- [ ] Scan repo + git history for committed secrets. Review `.env`, `commit.txt`, `compose.patch`, `docker-export/`.
- [ ] 🟡 `backend/.venv/` appears committed — should be gitignored.

## D. Injection & input validation
- [ ] 🟠 **(known)** Dynamic SQL via f-strings: `outbound._write_to_target` interpolates `target_table` and mapped column names into `INSERT`/`DELETE` (from admin-set `OutboundSetting`) — stored-injection surface into the external DB. Validate identifiers against an allowlist/regex.
- [ ] 🟠 **(known)** Data-mining query builder wraps admin-provided `base_query` and interpolates `page_size`/`offset` (`data_mining.py`). Confirm pagination are ints; assess abuse of the source query (runs against external hospital DBs — enforce read-only source users).
- [ ] Query-param bounds (limits, dates); CSV import parsing (`imports`) for malformed rows and spreadsheet/formula injection on export.
- [ ] Custom projection-formula evaluator (`safe_eval`) — verify the sandbox blocks attribute access, imports, dunders, and builtins (common escape vectors).
- [ ] Pydantic v2 request-body validation coverage across all routers.

## E. Data integrity & business-logic correctness
- [ ] Indent calculation (min/reorder/surge floors, pack rounding, forecast methods) reconciled against spec; edge cases: negative stock, very large `Numeric(20,4)` values (recall the overflow fix).
- [ ] Settings resolution engine (priority order, clearing via `exclude_unset`, planning-enabled AND-logic) — verify no cross-hospital inheritance leakage.
- [ ] 🟠 **(known)** Referential-integrity cascade: hospital/store delete → `FSNClassification` NOT-NULL FK causes a 500 (ORM nullifies instead of deferring to the DB `ON DELETE CASCADE`). Audit **all** `Store`/`Hospital` child relationships (consumption_records, closing_stocks, open_indents, indent_reports, surge_records, fsn_classifications) for the same mismatch. (Tracked as a separate task.)
- [ ] Concurrency: request-number sequencer locking, dispatch idempotency on `(store, period)`.

## F. Outbound / Kafka reliability
- [ ] 🟠 **(known)** Non-atomic PR publish: `create_purchase_request` commits the external-table write before the app-DB outbox commit. A failure between them leaves target rows with no outbox event and `pr_initiated` unset. Recommend the reserve-record-before-write pattern used by `dispatch_store`.
- [ ] 🟠 At-least-once → duplicates: a fresh idempotent producer per publish means idempotence does **not** dedupe across poller runs; a timed-out-but-delivered send re-sends next cycle. Confirm the downstream consumer is idempotent on `requestNumber`.
- [ ] Broker connectivity: `172.19.0.0/16` Docker default subnet overlapping the LAN Kafka (`172.19.1.x`). Audit network topology / address pools; queued outbox during an outage is by design — confirm monitoring/alerting exists.
- [ ] Outbox growth & retention; `MAX_PUBLISH_ATTEMPTS` dead-lettering; visibility of the `broker_unavailable` path (currently does not increment `attempts`, hiding outages).
- [ ] Timezone/log alignment across container ↔ DB ↔ Kafka (deploy-time `TZ` now configurable — verify prod sets it).

## G. External integrations (data mining)
- [ ] Encrypted source credentials, `connect_timeout`, startup orphaned-run reset — verify.
- [ ] Least-privilege, **read-only** source DB users; TLS to source DBs.
- [ ] `skip` vs `overwrite` write-mode correctness; scheduler misfire/catch-up; job isolation.

## H. Database & migrations
- [ ] 🟠 **(known)** No Alembic — schema evolves via `start.sh` `ADD COLUMN IF NOT EXISTS` + `create_all`. Audit for drift and non-reversibility; **removals/renames are not automated** (legacy dead columns persist, e.g. `rolling_window_days`, `safety_stock_pct`). Assess prod migration safety.
- [ ] Backups + tested restore, PITR, encryption at rest, `sslmode` on the app↔DB connection.
- [ ] Static DB credentials — rotation plan.

## I. Infrastructure, deployment & network
- [ ] 🔴 **(known)** CORS `allow_origins=["*"]` **with** `allow_credentials=True` (`main.py`) — invalid/insecure combination. Restrict to known origins.
- [ ] 🔴 **TLS:** HTTPS is only the optional, disabled `frontend/nginx.ssl.conf`; the default (vite-preview and root nginx) serve **plain HTTP** — tokens/credentials in the clear. Mandate TLS in prod.
- [ ] Containers run as **root** (no `USER` in Dockerfiles); dev bind-mounts source; DB port 14045 is published. Review network segmentation, firewalling of DB/Kafka, and image provenance/signing.
- [ ] Reverse-proxy/context-path (`APP_BASE`) and `ROOT_PATH` handling.

## J. Logging, monitoring & audit trail
- [ ] 🔴 **(known)** **No application audit trail.** Only `surge.disabled_by/disabled_at` and `indent.triggered_by` capture an actor. There is **no who-did-what record** for: user create/update/delete & role/grant changes, settings changes, master-data CRUD, PR creation, indent generation/clear, data-mining config changes, outbound config changes. For a hospital system this is typically mandatory — recommend an immutable audit-log table (actor, action, entity, before/after, timestamp, IP).
- [ ] DEBUG logging enabled for `data_mining` and `indent` — audit for PII/credential leakage; set prod log levels and retention.
- [ ] Observability beyond `/health`: metrics, alerting, error tracking.

## K. Privacy & regulatory compliance (healthcare)
- [ ] Data classification — identify any PHI/PII (app appears inventory/consumption-oriented; confirm no patient linkage in mined data).
- [ ] Applicable regime (India → DPDP Act; any US exposure → HIPAA): access logging, retention/deletion, consent, breach process.
- [ ] Data residency for the external hospital DBs it connects to; encryption in transit & at rest.

## L. Availability, backup & DR
- [ ] DB backup/restore tested; Kafka outbox durability; RPO/RTO defined.
- [ ] Single-instance vs HA; scheduler catch-up correctness after restart; graceful shutdown.

## M. Testing & code quality
- [ ] Existing tests: indent, formula, fsn, surge, import, settings. **Gaps:** no tests for auth, users, RBAC, **location scoping**, outbound/Kafka, purchase_requests, consumption. Add an authorization/scoping test matrix.
- [ ] CI, static analysis (bandit/semgrep), secret scanning, dependency scanning in the pipeline.

## N. Frontend security
- [ ] Token in `localStorage` (XSS-exfiltratable) — assess vs. httpOnly cookie.
- [ ] XSS sinks (`dangerouslySetInnerHTML`, untrusted rendering); CSP headers.
- [ ] npm dependency audit; sourcemaps/secrets not shipped in the bundle.

## O. Dependency & supply chain
- [ ] Audit `backend/requirements.txt` and `frontend/package.json` for known CVEs (Dependabot has been in use — confirm zero open alerts).
- [ ] Pin/verify versions; review the `kafka-python` / `bcrypt` / `python-jose` chain.

---

## Highest-priority remediation (before / around the audit)
1. 🔴 Rotate & externalize secrets (JWT, Fernet, DB creds); change the default admin.
2. 🔴 Enforce TLS everywhere; fix the CORS `*` + credentials combination.
3. 🔴 Add an application **audit trail** (who-did-what) — likely a hard requirement for a hospital system.
4. 🟠 Complete the location-scoping enforcement review; validate dynamic-SQL identifiers; fix the delete-cascade 500 and the PR-publish atomicity.

## Related documents
- `docs/TECHNICAL_DOCUMENTATION.md` — architecture, data model, auth (§12), config (§15), deployment (§16), outbound pipeline (§19).
- `docs/FUNCTIONAL_DOCUMENTATION.md` — roles & location scoping (§2), modules (§8).
