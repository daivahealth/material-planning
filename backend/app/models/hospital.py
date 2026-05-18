from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)

    stores = relationship("Store", back_populates="hospital", cascade="all, delete-orphan")
    settings = relationship("HospitalSettings", back_populates="hospital", uselist=False)
