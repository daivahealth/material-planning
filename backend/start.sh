#!/bin/sh
set -e

echo "==> Creating database tables..."
python3 -c "
from app.db import engine
from app.db import Base
import app.models  # registers all models
Base.metadata.create_all(bind=engine)
print('Tables ready.')
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
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
