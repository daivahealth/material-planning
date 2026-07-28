# Security & Application Audit Scope

> **Audience:** auditors, reviewers, and the engineering team.
> **Scope:** the Hospital Material Planning application — FastAPI backend + React/Vite frontend + PostgreSQL, with a Kafka outbound pipeline and external-DB data-mining, deployed via Docker Compose.
>
> Severity legend: 🔴 high · 🟠 medium · 🟡 low. Items marked **(known)** were identified during development and are documented here so they are not missed.
> Use the checkboxes to track audit progress. This is an audit *scope*, not a certification — each box is a thing to verify, not a claim that it passes.

---

## A. Authentication & session management
- [x] 🔴 **FIXED** — the hardcoded `jwt_secret_key` default is removed. Startup now **refuses to boot** if the old shipped value is configured, and generates a random per-process key when none is set (logged CRITICAL). Supply `JWT_SECRET_KEY` per environment. **Still to do by ops:** set a stable key in prod (`openssl rand -hex 32`).
- [x] 🔴 **FIXED** — no password ships in the image: `start.sh` uses `ADMIN_INITIAL_PASSWORD` or generates a random one printed once at first boot. **Still to do by ops:** change the password on any EXISTING deployment (this only affects a fresh DB) and remove leftover test accounts (`planner1`, `pview1`).
- [ ] Token model: JWT HS256, 24h TTL, **no refresh, no server-side revocation/logout, no blocklist**. Assess whether a 24h window for a leaked token is acceptable.
- [x] **FIXED** — (a) rate-limit throttle per username/IP (429 + `Retry-After`); (b) **durable account lockout** after 5 consecutive wrong passwords (`users.locked_at`), releasable via SQL, master API, or the Users screen. **Also FIXED:** 90-day password rotation, enforced server-side. **Still to do:** password history (no-reuse), MFA.
- [ ] bcrypt hashing (direct, not passlib) — verify cost factor; confirm no plaintext/hash leakage into logs or responses.
- [ ] Self-service password reset requires current password — verify.

## B. Authorization & access scoping
- [ ] Audit **every** mutating endpoint for a role guard (`require_master` / `require_roles`); confirm none rely solely on the UI hiding the control.
- [ ] **(known)** Location scoping (`app/services/access.py`: `accessible_store_ids` / `assert_store_access`). Verify enforcement on **all** store-touching endpoints. Confirmed added to indents generate/list, consumption analysis, PR candidates/create. **Re-audit:** indents export, surges, settings-resolve, dashboard, classification — for scoped-user data leakage.
- [ ] Confirm a `planner` / `planner_view` cannot read another store's data via any list endpoint missing the scope filter.
- [ ] IDOR: object-level authorization on `/{id}` routes (users, settings, item-suppliers, hospitals, stores).
- [ ] Client-side RBAC (`utils/permissions.ts`) is UX-only — reconfirm the server is the true boundary.

## C. Secrets & configuration management
- [x] 🔴 **PARTLY FIXED** — defaults removed from `config.py`; both compose files now read secrets from the environment; `docker-compose.prod.yml` **fails fast** if `JWT_SECRET_KEY` / `MINING_SECRET_KEY` / `CORS_ALLOW_ORIGINS` are unset; `.env.example` added and `.env` stays gitignored. **Still to do by ops: rotate the exposed Fernet + JWT keys and the `matplan/matplan` DB credentials** — the old values are in git history.
- [ ] 🔴 The Fernet key (`MINING_SECRET_KEY`) decrypts **all** external-DB passwords (data-mining + outbound). Audit key storage, access, and rotation plan; leak = all source creds compromised.
- [ ] Scan repo + git history for committed secrets. Review `.env`, `commit.txt`, `compose.patch`, `docker-export/`.
- [x] 🟡 **NOT AN ISSUE** — verified with `git ls-files`: `backend/.venv/` is untracked and already covered by `.gitignore`. (Original note was wrong.) Build artifacts `docker-export/` and scratch files are now gitignored too.

## D. Injection & input validation
- [x] 🟠 **FIXED** — `_safe_identifier()` validates the target table and every mapped column against `^[A-Za-z_][A-Za-z0-9_$]{0,62}$` (optional `schema.` qualifier) before interpolation. Verified: `evt; DROP TABLE users--`, `a b`, `1abc`, `x"y` and blank are all rejected.
- [ ] 🟠 **(known)** Data-mining query builder wraps admin-provided `base_query` and interpolates `page_size`/`offset` (`data_mining.py`). Confirm pagination are ints; assess abuse of the source query (runs against external hospital DBs — enforce read-only source users).
- [ ] Query-param bounds (limits, dates); CSV import parsing (`imports`) for malformed rows and spreadsheet/formula injection on export.
- [ ] Custom projection-formula evaluator (`safe_eval`) — verify the sandbox blocks attribute access, imports, dunders, and builtins (common escape vectors).
- [ ] Pydantic v2 request-body validation coverage across all routers.

## E. Data integrity & business-logic correctness
- [ ] Indent calculation (min/reorder/surge floors, pack rounding, forecast methods) reconciled against spec; edge cases: negative stock, very large `Numeric(20,4)` values (recall the overflow fix).
- [ ] Settings resolution engine (priority order, clearing via `exclude_unset`, planning-enabled AND-logic) — verify no cross-hospital inheritance leakage.
- [x] 🟠 **FIXED** — every `Store` child relationship (settings, consumption_records, closing_stocks, open_indents, indent_reports, surge_records, fsn_classifications) and `Hospital` → stores/settings now use `cascade="all, delete-orphan"` + `passive_deletes=True`, so Postgres performs its own `ON DELETE CASCADE` instead of SQLAlchemy nulling a NOT-NULL FK.
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
- [x] 🔴 **FIXED** — origins come from `CORS_ALLOW_ORIGINS` (explicit allowlist); startup **refuses to boot** if it contains `*`. Verified: a disallowed `Origin` gets no `access-control-allow-origin` header; an allowed one is echoed back.
- [x] **PARTLY FIXED** — security headers now ship on every response, and **HSTS is emitted only when the request is HTTPS** (nginx: only in the 443 block; backend: only for an https scheme, honouring `X-Forwarded-Proto` solely when `TRUST_PROXY_HEADERS` is on). **Still outstanding (infrastructure):** actually terminating TLS — enable `nginx.ssl.conf` or terminate at the proxy/ingress.
- [x] **PARTLY FIXED** — the production backend image now runs as a non-root `appuser` (uid 10001). **Still to do:** frontend image user, DB port exposure, network segmentation/firewalling of DB & Kafka, image provenance/signing.
- [ ] Reverse-proxy/context-path (`APP_BASE`) and `ROOT_PATH` handling.

## J. Logging, monitoring & audit trail
- [x] 🔴 **IMPLEMENTED** — `audit_logs` table (actor id/username/role, action, entity, entity_id, summary, JSON before/after details, IP, timestamp) written **in the same transaction** as the audited change, with secret-bearing fields redacted. Wired into: login, failed login, self password reset, user create/update/delete (incl. role & store-grant before/after), admin password reset, purchase-request creation, indent generate-batch and clear. Read-only master API `GET /api/audit` (filter by actor/action/entity/date) — no update/delete endpoint exists. Now also covers **all settings levels** (hospital/store/item/item×store/category/group/supplier), **master-data CRUD** (hospitals, stores, items, groups, categories, suppliers, item-suppliers), **data-mining config** create/update/delete and **outbound settings + manual run** — credentials redacted via `audit.scrub()`. **Still to do:** retention/archival policy for the trail itself.
- [x] **FIXED** — those loggers were pinned to DEBUG in code; they now follow the `LOG_LEVEL` setting (default **INFO**). **Still to do:** log retention/shipping policy.
- [ ] Observability beyond `/health`: metrics, alerting, error tracking.

## K. Privacy & regulatory compliance (healthcare)
- [ ] Data classification — identify any PHI/PII (app appears inventory/consumption-oriented; confirm no patient linkage in mined data).
- [ ] Applicable regime (India → DPDP Act; any US exposure → HIPAA): access logging, retention/deletion, consent, breach process.
- [ ] Data residency for the external hospital DBs it connects to; encryption in transit & at rest.

## L. Availability, backup & DR
- [ ] DB backup/restore tested; Kafka outbox durability; RPO/RTO defined.
- [ ] Single-instance vs HA; scheduler catch-up correctness after restart; graceful shutdown.

## M. Testing & code quality
- [x] 🔴 **FIXED — suite is green (45/45 passed, was 27 failed / 18 passed).** The tests constructed `safety_stock_pct`, a column dropped from the model; they now use the real `safety_stock_days` (values chosen to match each test's documented arithmetic, e.g. `TSL=10*(30+3)`). **Gaps still remain:** no tests for auth, users, RBAC, **location scoping**, outbound/Kafka, purchase_requests, consumption — add an authorization/scoping matrix.
- [ ] CI, static analysis (bandit/semgrep), secret scanning, dependency scanning in the pipeline.

## N. Frontend security
- [ ] Token in `localStorage` (XSS-exfiltratable) — assess vs. httpOnly cookie.
- [x] **CSP + headers FIXED** for the nginx production image (`default-src 'self'`, `script-src 'self'`, `frame-ancestors 'none'`, nosniff, Referrer-Policy, Permissions-Policy). **Still to do:** audit XSS sinks (`dangerouslySetInnerHTML`, untrusted rendering); note the dev `vite preview` image does not send these headers.
- [ ] npm dependency audit; sourcemaps/secrets not shipped in the bundle.

## O. Dependency & supply chain
- [ ] Audit `backend/requirements.txt` and `frontend/package.json` for known CVEs (Dependabot has been in use — confirm zero open alerts).
- [ ] Pin/verify versions; review the `kafka-python` / `bcrypt` / `python-jose` chain.

---

## Highest-priority remediation (before / around the audit)
1. 🔴 Rotate & externalize secrets (JWT, Fernet, DB creds); change the default admin.
   → **Code done** (defaults removed, env-driven, prod fails fast, `.env.example`).
   **Ops still must rotate the exposed keys and DB credentials** — old values are in git history.
2. 🔴 Enforce TLS everywhere; fix the CORS `*` + credentials combination.
   → **CORS fixed** (explicit allowlist, boot refused on `*`). **TLS is still outstanding** — it is
   infrastructure, not code: terminate HTTPS at the proxy/ingress, or enable `frontend/nginx.ssl.conf`.
3. 🔴 Add an application **audit trail** (who-did-what).
   → **Implemented** for auth + user/role/grant + PR + indent actions; extend to settings,
   master data, data-mining and outbound config next.
4. 🟠 Location-scoping review; dynamic-SQL identifiers; delete-cascade 500; PR-publish atomicity.
   → **SQL identifiers validated** and **delete-cascade fixed**. **Still open:** the full
   scoping sweep (exports, surges, dashboard, classification) and PR-publish atomicity.

### Implementation status snapshot
| Area | State |
|------|-------|
| Secrets externalized, prod fail-fast, `.env.example` | ✅ code done — ops must rotate |
| Default admin password no longer shipped | ✅ (fresh DB only) |
| CORS allowlist + boot guard | ✅ |
| Audit trail (table, service, API) | ✅ extended — auth, users/roles/grants, **all settings levels**, **master data CRUD**, **data-mining configs**, **outbound config + manual run**, PR creation, indent generate/clear |
| Log levels no longer pinned to DEBUG | ✅ |
| Dynamic-SQL identifier validation | ✅ |
| Store/Hospital delete cascade | ✅ |
| Non-root production backend container | ✅ |
| TLS, backups/DR, network segmentation | ⛔ infrastructure — not addressable in code |
| Rate limiting / account lockout | ✅ login throttle + lockout + admin unlock |
| Password rotation (90 days) | ✅ enforced server-side + forced UI change |
| Token revocation, MFA, password history | ⛔ not started |
| Test suite | ✅ green 45/45 — authz/scoping test matrix still ⛔ |

## Related documents
- `docs/TECHNICAL_DOCUMENTATION.md` — architecture, data model, auth (§12), config (§15), deployment (§16), outbound pipeline (§19).
- `docs/FUNCTIONAL_DOCUMENTATION.md` — roles & location scoping (§2), modules (§8).
