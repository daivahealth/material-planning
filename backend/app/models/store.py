from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False, index=True)

    hospital = relationship("Hospital", back_populates="stores")
    settings = relationship("StoreSettings", back_populates="store", uselist=False)
    consumption_records = relationship("ConsumptionRecord", back_populates="store")
    closing_stocks = relationship("ClosingStock", back_populates="store")
    open_indents = relationship("OpenIndent", back_populates="store")
    indent_reports = relationship("IndentReport", back_populates="store")
    surge_records = relationship("SurgeRecord", back_populates="store")
    fsn_classifications = relationship("FSNClassification", back_populates="store")
