-- ============================================================================
-- Outbound / indent-generation performance indexes
--
-- WHY
--   The network-wide outbound job walks every (item, store) pair. At ~13k items
--   x ~200 stores the access pattern is store-first, but every composite index
--   on the snapshot tables led with item_id, so store-scoped reads fell back to
--   scanning every row a store had ever accumulated. The regeneration DELETE on
--   indent_reports had no index containing period_start at all and filtered it
--   in memory after reading all of a store's rows.
--
-- HOW TO RUN
--   CREATE/DROP INDEX CONCURRENTLY cannot run inside a transaction block, so do
--   NOT wrap this in BEGIN/COMMIT and do NOT run it with `psql -1`:
--
--     psql "$DATABASE_URL" -f 2026-08-outbound-performance-indexes.sql
--
--   CONCURRENTLY means no write lock is taken — the app can keep serving while
--   these build. On a large closing_stocks this can still take a long time; run
--   it in a low-traffic window and let it finish.
--
--   Re-runnable: every statement is IF NOT EXISTS / IF EXISTS. If a CONCURRENTLY
--   build is interrupted it leaves an INVALID index behind; find them with the
--   query at the bottom, drop them, and run the file again.
--
--   Fresh databases get all of this from the model definitions; this file exists
--   only to bring an already-deployed database in line.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Store-first composites for the batch indent path
-- ---------------------------------------------------------------------------

-- Serves "which items does this store track" (SELECT DISTINCT item_id ... WHERE
-- store_id = ?) and the latest-closing-stock-per-item lookup.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_closingstock_store_item_date
    ON closing_stocks (store_id, item_id, date);

-- Serves the whole-store consumption window read in one query.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_consumption_store_date_item
    ON consumption_records (store_id, date, item_id);

-- Serves the per-store open-indent snapshot lookup.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_openindent_store_item_date
    ON open_indents (store_id, item_id, as_of_date);

-- Serves the regeneration DELETE, which filters (store_id, period_start).
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_indentreport_store_period
    ON indent_reports (store_id, period_start);

-- item_store_settings has PK (item_id, store_id), so a store-only filter — how
-- the batch path loads a store's overrides — cannot use it.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_itemstoresettings_store_item
    ON item_store_settings (store_id, item_id);


-- ---------------------------------------------------------------------------
-- 2. Drop redundant indexes
--
-- Each of these is either an exact duplicate of the primary key, or the leading
-- column of a composite index that already exists (Postgres can use a composite
-- for a prefix of its columns). They can never be chosen over the composite;
-- they only add write amplification — and these tables take millions of inserts
-- a day from data mining.
--
-- Run section 1 FIRST and let it complete: the store_id drops below depend on
-- the store-first composites created above.
-- ---------------------------------------------------------------------------

-- Duplicates of the primary key index
DROP INDEX CONCURRENTLY IF EXISTS ix_closing_stocks_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_consumption_records_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_open_indents_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_indent_reports_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_surge_records_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_item_suppliers_id;

-- Prefixes of the existing item-first composites
DROP INDEX CONCURRENTLY IF EXISTS ix_closing_stocks_item_id;      -- ix_closingstock_item_store_date
DROP INDEX CONCURRENTLY IF EXISTS ix_consumption_records_item_id; -- ix_consumption_item_store_date
DROP INDEX CONCURRENTLY IF EXISTS ix_open_indents_item_id;        -- ix_openindent_item_store_date
DROP INDEX CONCURRENTLY IF EXISTS ix_surge_records_item_id;       -- ix_surgerecord_item_store

-- Prefixes of the store-first composites created in section 1
DROP INDEX CONCURRENTLY IF EXISTS ix_closing_stocks_store_id;     -- ix_closingstock_store_item_date
DROP INDEX CONCURRENTLY IF EXISTS ix_consumption_records_store_id;-- ix_consumption_store_date_item
DROP INDEX CONCURRENTLY IF EXISTS ix_open_indents_store_id;       -- ix_openindent_store_item_date
DROP INDEX CONCURRENTLY IF EXISTS ix_indent_reports_store_id;     -- ix_indentreport_store_period

-- Deliberately KEPT:
--   ix_*_date / ix_*_as_of_date  — data mining's replace_date deletes by date
--   ix_indent_reports_item_id    — nothing else leads with item_id here
--   ix_surge_records_store_id    — surge has no store-first composite


-- ---------------------------------------------------------------------------
-- 3. Refresh planner statistics
-- ---------------------------------------------------------------------------
ANALYZE closing_stocks;
ANALYZE consumption_records;
ANALYZE open_indents;
ANALYZE indent_reports;
ANALYZE item_store_settings;


-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
-- Any INVALID index left by an interrupted CONCURRENTLY build (drop and re-run):
--   SELECT i.indexrelid::regclass AS index_name
--   FROM pg_index i WHERE NOT i.indisvalid;
--
-- Confirm the new indexes are being used after a run:
--   SELECT relname, indexrelname, idx_scan
--   FROM pg_stat_user_indexes
--   WHERE indexrelname LIKE 'ix_%store%' ORDER BY idx_scan DESC;
