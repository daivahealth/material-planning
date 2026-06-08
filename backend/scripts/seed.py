"""
Seed script — inserts realistic data for 2 hospitals, 4 stores, 30 items, 90 days consumption.
Run: cd backend && python -m scripts.seed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date, timedelta
from decimal import Decimal
import random

from app.db import SessionLocal, engine
from app.db import Base
import app.models  # noqa

Base.metadata.create_all(bind=engine)

db = SessionLocal()
random.seed(42)

# ---- Hospitals ----
from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import ItemGroup, ItemCategory, Item, Supplier, ItemSupplier
from app.models.settings import HospitalSettings, StoreSettings, ItemSettings
from app.models.classification import VEDClassification

hospitals = [
    Hospital(name="City General Hospital", code="CGH"),
    Hospital(name="Rural Health Centre", code="RHC"),
]
db.add_all(hospitals)
db.flush()

# ---- Stores ----
stores = [
    Store(hospital_id=hospitals[0].id, name="Main Pharmacy", code="CGH-PH"),
    Store(hospital_id=hospitals[0].id, name="OT Stores", code="CGH-OT"),
    Store(hospital_id=hospitals[1].id, name="General Stores", code="RHC-GS"),
    Store(hospital_id=hospitals[1].id, name="Emergency Stores", code="RHC-EM"),
]
db.add_all(stores)
db.flush()

# ---- Hospital Settings ----
db.add(HospitalSettings(
    hospital_id=hospitals[0].id,
    lookback_days=90, fsn_period_days=365, fsn_schedule_days=30,
    indent_duration_days=30, safety_stock_pct=0.10,
    fsn_fast_threshold=2.0, fsn_slow_threshold=0.2,
    projection_formula="standard",
    forecast_method="baseline_avg",
    rolling_recent_weight_factor=2.0, trend_min_points=7,
    planning_enabled=True,
))
db.add(HospitalSettings(
    hospital_id=hospitals[1].id,
    lookback_days=60, fsn_period_days=180, fsn_schedule_days=30,
    indent_duration_days=15, safety_stock_pct=0.15,
    fsn_fast_threshold=1.5, fsn_slow_threshold=0.1,
    projection_formula="standard",
    forecast_method="baseline_avg",
    rolling_recent_weight_factor=2.0, trend_min_points=7,
    planning_enabled=True,
))
db.flush()

# ---- Store Settings (RHC-EM overrides indent duration) ----
db.add(StoreSettings(store_id=stores[3].id, indent_duration_days=7))
db.flush()

# ---- Item Groups (independent) ----
groups = [
    ItemGroup(name="Pharmaceuticals"),
    ItemGroup(name="Surgical Supplies"),
    ItemGroup(name="Diagnostics"),
    ItemGroup(name="General Consumables"),
]
db.add_all(groups)
db.flush()

# ---- Item Categories (independent) ----
categories = [
    ItemCategory(name="Antibiotics", is_vital=True),
    ItemCategory(name="Analgesics", is_vital=False),
    ItemCategory(name="IV Fluids", is_vital=True),
    ItemCategory(name="Surgical Gloves", is_vital=False),
    ItemCategory(name="Syringes", is_vital=False),
    ItemCategory(name="Reagents", is_vital=False),
]
db.add_all(categories)
db.flush()

# ---- Suppliers ----
suppliers = [
    Supplier(name="MediCorp Pvt Ltd", code="MED-01", lead_time_days=5),
    Supplier(name="PharmaDist Ltd", code="PH-02", lead_time_days=7),
    Supplier(name="SurgiSupply Inc", code="SS-03", lead_time_days=3),
]
db.add_all(suppliers)
db.flush()

# ---- Items (30 items, each linked to a group AND a category) ----
item_defs = [
    ("Amoxicillin 500mg", "AMX-500", "Strips", groups[0], categories[0]),
    ("Ciprofloxacin 250mg", "CIP-250", "Tabs", groups[0], categories[0]),
    ("Metronidazole 400mg", "MET-400", "Tabs", groups[0], categories[0]),
    ("Paracetamol 500mg", "PAR-500", "Tabs", groups[0], categories[1]),
    ("Ibuprofen 400mg", "IBU-400", "Tabs", groups[0], categories[1]),
    ("Diclofenac 50mg", "DIC-050", "Tabs", groups[0], categories[1]),
    ("Normal Saline 500ml", "NS-500", "Bottles", groups[1], categories[2]),
    ("Ringer Lactate 500ml", "RL-500", "Bottles", groups[1], categories[2]),
    ("Dextrose 5% 500ml", "D5-500", "Bottles", groups[1], categories[2]),
    ("Sterile Gloves S", "GLV-S", "Pairs", groups[1], categories[3]),
    ("Sterile Gloves M", "GLV-M", "Pairs", groups[1], categories[3]),
    ("Sterile Gloves L", "GLV-L", "Pairs", groups[1], categories[3]),
    ("Syringe 2ml", "SYR-2", "Nos", groups[1], categories[4]),
    ("Syringe 5ml", "SYR-5", "Nos", groups[1], categories[4]),
    ("Syringe 10ml", "SYR-10", "Nos", groups[1], categories[4]),
    ("Syringe 20ml", "SYR-20", "Nos", groups[1], categories[4]),
    ("Blood Glucose Strips", "BGS-01", "Strips", groups[2], categories[5]),
    ("Urine Strips", "URI-01", "Strips", groups[2], categories[5]),
    ("Malaria RDT Kit", "MAL-RDT", "Kits", groups[2], categories[5]),
    ("Bandage 4inch", "BND-4", "Rolls", groups[3], categories[3]),
    ("Bandage 6inch", "BND-6", "Rolls", groups[3], categories[3]),
    ("Cotton 500g", "CTN-500", "Packs", groups[3], categories[3]),
    ("Micropore Tape", "MPT-01", "Rolls", groups[3], categories[3]),
    ("Spirit 500ml", "SPR-500", "Bottles", groups[3], categories[3]),
    ("Betadine 100ml", "BET-100", "Bottles", groups[3], categories[3]),
    ("IV Cannula 20G", "IVC-20", "Nos", groups[1], categories[4]),
    ("IV Cannula 22G", "IVC-22", "Nos", groups[1], categories[4]),
    ("Omeprazole 20mg", "OME-20", "Caps", groups[0], categories[1]),
    ("Metformin 500mg", "MET-500", "Tabs", groups[0], categories[1]),
    ("Amlodipine 5mg", "AML-5", "Tabs", groups[0], categories[1]),
]

items = []
for name, code, unit, grp, cat in item_defs:
    i = Item(name=name, code=code, unit=unit, group_id=grp.id, category_id=cat.id)
    db.add(i)
    items.append(i)
db.flush()

# ---- Item-Supplier Links ----
for item in items[:15]:
    db.add(ItemSupplier(item_id=item.id, supplier_id=suppliers[0].id, is_primary=True))
for item in items[15:22]:
    db.add(ItemSupplier(item_id=item.id, supplier_id=suppliers[1].id, is_primary=True))
for item in items[22:]:
    db.add(ItemSupplier(item_id=item.id, supplier_id=suppliers[2].id, is_primary=True))
db.flush()

# ---- Item-level override for one item ----
db.add(ItemSettings(item_id=items[0].id, safety_stock_pct=0.20, reorder_level=100))
db.flush()

# ---- Consumption records — 90 days ending today ----
from app.models.consumption import ConsumptionRecord, ClosingStock

today = date(2026, 4, 22)
consumption_rows = []
closing_rows = []

# Define base daily consumption per item (realistic varied rates)
base_consumption = {
    items[0].id: 15, items[1].id: 12, items[2].id: 10,
    items[3].id: 50, items[4].id: 35, items[5].id: 20,
    items[6].id: 8,  items[7].id: 6,  items[8].id: 5,
    items[9].id: 25, items[10].id: 30, items[11].id: 20,
    items[12].id: 60, items[13].id: 45, items[14].id: 30, items[15].id: 15,
    items[16].id: 5, items[17].id: 4, items[18].id: 2,
    items[19].id: 10, items[20].id: 8, items[21].id: 12, items[22].id: 5,
    items[23].id: 3, items[24].id: 4,
    items[25].id: 20, items[26].id: 18,
    items[27].id: 8, items[28].id: 22, items[29].id: 10,
}

for store in stores:
    for item in items:
        base = base_consumption.get(item.id, 5)
        for d in range(90):
            rec_date = today - timedelta(days=90 - d)
            # Add some noise; some items have zero consumption on some days
            qty = max(0, base + random.randint(-int(base * 0.3), int(base * 0.3)))
            if random.random() < 0.05:  # 5% chance of zero day
                qty = 0
            consumption_rows.append(ConsumptionRecord(
                item_id=item.id,
                store_id=store.id,
                date=rec_date,
                quantity=Decimal(str(qty)),
            ))
        # Closing stock for most recent date
        closing_rows.append(ClosingStock(
            item_id=item.id,
            store_id=store.id,
            date=today,
            quantity=Decimal(str(base * random.randint(5, 20))),
        ))

db.add_all(consumption_rows)
db.add_all(closing_rows)
db.flush()

# ---- Surge records ----
from app.models.surge import SurgeRecord, SeasonType

surges = [
    SurgeRecord(item_id=items[3].id, store_id=stores[0].id, recorded_date=date(2026, 1, 15),
                month=1, season=SeasonType.Winter, reason="Winter flu season spike", extra_qty=Decimal("200")),
    SurgeRecord(item_id=items[6].id, store_id=stores[0].id, recorded_date=date(2026, 7, 10),
                month=7, season=SeasonType.Monsoon, reason="Monsoon cholera prevention", extra_qty=Decimal("50")),
    SurgeRecord(item_id=items[12].id, store_id=stores[1].id, recorded_date=date(2026, 4, 5),
                month=4, season=SeasonType.Summer, reason="Increased OT procedures", extra_qty=Decimal("300")),
]
db.add_all(surges)
db.commit()

print(f"Seeded: {len(hospitals)} hospitals, {len(stores)} stores, {len(items)} items, "
      f"{len(consumption_rows)} consumption records, {len(closing_rows)} closing stock records, "
      f"{len(surges)} surge records")
