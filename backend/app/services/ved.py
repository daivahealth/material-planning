"""
VED classification service.
System suggestion: items whose category has is_vital=True → V,
items in categories named with 'essential' (case-insensitive) → E, else D.
Manual override takes display precedence.
"""
from sqlalchemy.orm import Session, joinedload

from app.models.classification import VEDClassification, VEDClass
from app.models.item import Item, ItemCategory


def _suggest(item: Item) -> VEDClass:
    if item.category:
        if item.category.is_vital:
            return VEDClass.V
        if "essential" in item.category.name.lower():
            return VEDClass.E
    return VEDClass.D


def compute_ved_for_all(db: Session) -> dict:
    # Eager-load categories in ONE query to avoid N+1 on item.category
    items = db.query(Item).options(joinedload(Item.category)).all()

    # ONE query: fetch all existing VED records
    existing_records = db.query(VEDClassification).all()
    existing_map: dict[int, VEDClassification] = {r.item_id: r for r in existing_records}

    new_records = []
    updated = 0
    for item in items:
        suggestion = _suggest(item)
        existing = existing_map.get(item.id)
        if existing:
            existing.system_suggestion = suggestion
        else:
            new_records.append(VEDClassification(
                item_id=item.id,
                system_suggestion=suggestion,
                manual_override=None,
            ))
        updated += 1

    if new_records:
        db.add_all(new_records)
    db.commit()
    return {"records_updated": updated}


def set_manual_override(db: Session, item_id: int, ved_class: VEDClass, reason: str) -> VEDClassification:
    existing = db.query(VEDClassification).filter(
        VEDClassification.item_id == item_id
    ).first()
    if existing:
        existing.manual_override = ved_class
        existing.override_reason = reason
    else:
        existing = VEDClassification(
            item_id=item_id,
            system_suggestion=_suggest(db.get(Item, item_id)),
            manual_override=ved_class,
            override_reason=reason,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def effective_ved(record: VEDClassification) -> VEDClass:
    """Returns the effective VED class — manual override takes precedence."""
    return record.manual_override if record.manual_override else record.system_suggestion


def set_manual_override(db: Session, item_id: int, ved_class: VEDClass, reason: str) -> VEDClassification:
    existing = db.query(VEDClassification).filter(
        VEDClassification.item_id == item_id
    ).first()
    if existing:
        existing.manual_override = ved_class
        existing.override_reason = reason
    else:
        existing = VEDClassification(
            item_id=item_id,
            system_suggestion=_suggest(db.get(Item, item_id)),
            manual_override=ved_class,
            override_reason=reason,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def effective_ved(record: VEDClassification) -> VEDClass:
    """Returns the effective VED class — manual override takes precedence."""
    return record.manual_override if record.manual_override else record.system_suggestion
