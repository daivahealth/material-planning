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
            role=UserRole.master,
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
