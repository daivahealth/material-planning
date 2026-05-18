from sqlalchemy import Column, Integer, Date, Numeric, String, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship
import enum
from app.db import Base


class SeasonType(str, enum.Enum):
    Summer = "Summer"
    Monsoon = "Monsoon"
    Winter = "Winter"
    Festive = "Festive"


SEASON_MAP = {
    3: SeasonType.Summer, 4: SeasonType.Summer, 5: SeasonType.Summer,
    6: SeasonType.Monsoon, 7: SeasonType.Monsoon, 8: SeasonType.Monsoon, 9: SeasonType.Monsoon,
    10: SeasonType.Winter, 11: SeasonType.Winter, 12: SeasonType.Winter,
    1: SeasonType.Winter, 2: SeasonType.Winter,
}


def get_season(month: int) -> SeasonType:
    return SEASON_MAP.get(month, SeasonType.Summer)


class SurgeRecord(Base):
    __tablename__ = "surge_records"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_date = Column(Date, nullable=False)
    month = Column(Integer, nullable=False)            # 1-12
    season = Column(Enum(SeasonType), nullable=False)
    reason = Column(String(500), nullable=False)
    extra_qty = Column(Numeric(12, 4), nullable=False)

    item = relationship("Item", back_populates="surge_records")
    store = relationship("Store", back_populates="surge_records")


Index("ix_surgerecord_item_store", SurgeRecord.item_id, SurgeRecord.store_id)
