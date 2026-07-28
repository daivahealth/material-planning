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
    # All child rows have ON DELETE CASCADE at the DB level. passive_deletes
    # lets Postgres do the cascade instead of SQLAlchemy trying to NULL the
    # (NOT NULL) store_id first — which otherwise fails with a
    # NotNullViolation when deleting a store/hospital that has any child rows.
    settings = relationship("StoreSettings", back_populates="store", uselist=False,
                            cascade="all, delete-orphan", passive_deletes=True)
    consumption_records = relationship("ConsumptionRecord", back_populates="store",
                                       cascade="all, delete-orphan", passive_deletes=True)
    closing_stocks = relationship("ClosingStock", back_populates="store",
                                  cascade="all, delete-orphan", passive_deletes=True)
    open_indents = relationship("OpenIndent", back_populates="store",
                                cascade="all, delete-orphan", passive_deletes=True)
    indent_reports = relationship("IndentReport", back_populates="store",
                                  cascade="all, delete-orphan", passive_deletes=True)
    surge_records = relationship("SurgeRecord", back_populates="store",
                                 cascade="all, delete-orphan", passive_deletes=True)
    fsn_classifications = relationship("FSNClassification", back_populates="store",
                                       cascade="all, delete-orphan", passive_deletes=True)
