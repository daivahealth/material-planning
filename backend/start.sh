#!/bin/sh
set -e

echo "==> Creating database tables..."
python3 -c "
from app.db import engine
from app.db import Base
from sqlalchemy import text
import app.models  # registers all models
Base.metadata.create_all(bind=engine)

# Lightweight compatibility patch for existing Postgres databases when new
# HospitalSettings columns are introduced without alembic migrations.
with engine.begin() as conn:
  if engine.dialect.name == 'postgresql':
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS forecast_method VARCHAR(50) DEFAULT 'baseline_avg' NOT NULL\"))
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS rolling_window_days INTEGER DEFAULT 30 NOT NULL\"))
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS rolling_recent_weight_factor DOUBLE PRECISION DEFAULT 2.0 NOT NULL\"))
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS trend_min_points INTEGER DEFAULT 7 NOT NULL\"))
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS planning_enabled BOOLEAN DEFAULT TRUE NOT NULL\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS planning_enabled BOOLEAN\"))
    conn.execute(text(\"ALTER TABLE item_settings ADD COLUMN IF NOT EXISTS planning_enabled BOOLEAN\"))
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS rolling_bucket_days INTEGER DEFAULT 1 NOT NULL\"))
    conn.execute(text(\"ALTER TABLE item_settings ADD COLUMN IF NOT EXISTS indent_duration_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE item_settings ADD COLUMN IF NOT EXISTS pack_size INTEGER\"))
    conn.execute(text(\"ALTER TABLE item_category_settings ADD COLUMN IF NOT EXISTS indent_duration_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE item_group_settings ADD COLUMN IF NOT EXISTS indent_duration_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE items ADD COLUMN IF NOT EXISTS preferred_supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL\"))
    # Settings refactor: safety_stock_days (days) replaces safety_stock_pct (percentage)
    conn.execute(text(\"ALTER TABLE hospital_settings ADD COLUMN IF NOT EXISTS safety_stock_days FLOAT NOT NULL DEFAULT 7.0\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS safety_stock_days FLOAT\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS forecast_method VARCHAR(50)\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS rolling_recent_weight_factor FLOAT\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS rolling_bucket_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE item_settings ADD COLUMN IF NOT EXISTS safety_stock_days FLOAT\"))
    conn.execute(text(\"ALTER TABLE item_settings ADD COLUMN IF NOT EXISTS lead_time_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE item_category_settings ADD COLUMN IF NOT EXISTS safety_stock_days FLOAT\"))
    conn.execute(text(\"ALTER TABLE item_group_settings ADD COLUMN IF NOT EXISTS safety_stock_days FLOAT\"))
    # Surge records can be disabled so they are excluded from indent calculation
    conn.execute(text(\"ALTER TABLE surge_records ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE\"))
    conn.execute(text(\"ALTER TABLE surge_records ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ\"))
    conn.execute(text(\"ALTER TABLE surge_records ADD COLUMN IF NOT EXISTS disabled_by VARCHAR(150)\"))
    # Store-level: lead time, configurable settings priority order, PR/indent mode
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS lead_time_days INTEGER\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS settings_priority VARCHAR(200)\"))
    conn.execute(text(\"ALTER TABLE store_settings ADD COLUMN IF NOT EXISTS request_type VARCHAR(30)\"))
    conn.execute(text(\"ALTER TABLE indent_reports ADD COLUMN IF NOT EXISTS request_type VARCHAR(30)\"))
    # Data mining: skip (default) vs overwrite existing records
    conn.execute(text(\"ALTER TABLE data_mining_configs ADD COLUMN IF NOT EXISTS write_mode VARCHAR(20) NOT NULL DEFAULT 'skip'\"))
    # Widen indent_reports numeric columns 12,4 -> 20,4 to hold large source values
    _prec = conn.execute(text(\"SELECT numeric_precision FROM information_schema.columns WHERE table_name='indent_reports' AND column_name='closing_stock_qty'\")).scalar()
    if _prec is not None and int(_prec) < 20:
        for _c in ['avg_daily_consumption','projected_need','closing_stock_qty','safety_stock_qty','base_indent_qty','surge_indent_qty','open_indent_qty','total_indent_qty']:
            conn.execute(text('ALTER TABLE indent_reports ALTER COLUMN ' + _c + ' TYPE NUMERIC(20,4)'))
    # Drop the dead legacy safety_stock_pct column (replaced by safety_stock_days).
    # Its NOT NULL on hospital_settings broke inserts of new hospitals' settings.
    for _t in ['hospital_settings','store_settings','item_settings','item_category_settings','item_group_settings']:
        conn.execute(text('ALTER TABLE ' + _t + ' DROP COLUMN IF EXISTS safety_stock_pct'))
    # Outbound: value written to the target request_type column
    conn.execute(text(\"ALTER TABLE outbound_settings ADD COLUMN IF NOT EXISTS request_type_value VARCHAR(50) NOT NULL DEFAULT 'StockIndent'\"))
    # Purchase-request initiated flag on indent lines
    conn.execute(text(\"ALTER TABLE indent_reports ADD COLUMN IF NOT EXISTS pr_initiated BOOLEAN NOT NULL DEFAULT FALSE\"))
    # users.role: native enum -> varchar so new roles need no type migration
    _role_type = conn.execute(text(\"SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='role'\")).scalar()
    if _role_type is not None and _role_type != 'character varying':
        conn.execute(text('ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(20) USING role::text'))
print('Tables ready.')
"

echo "==> Seeding default admin user if no users exist..."
python3 -c "
from app.db import SessionLocal
from app.models.user import User, UserRole
from app.services.auth import hash_password
db = SessionLocal()
try:
    if db.query(User).count() == 0:
        admin = User(
            username='admin',
            email='admin@medplan.local',
            hashed_password=hash_password('Admin@123'),
            role=UserRole.master.value,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print('Default admin user created  (username=admin  password=Admin@123)')
    else:
        print('Users already exist — skipping default admin creation.')
finally:
    db.close()
"

echo "==> Checking if seed data is needed..."
python3 -c "
from app.db import SessionLocal
from app.models.hospital import Hospital
db = SessionLocal()
count = db.query(Hospital).count()
db.close()
import sys
sys.exit(0 if count == 0 else 1)
" && {
  echo "==> Seeding sample data..."
  python3 -m scripts.seed
  echo "==> Seed complete."
} || echo "==> Data already present, skipping seed."

echo "==> Starting uvicorn..."
if [ "${RELOAD:-0}" = "1" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
