from pydantic import BaseModel
from typing import Optional


class HospitalBase(BaseModel):
    name: str
    code: str


class HospitalCreate(HospitalBase):
    pass


class HospitalUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class HospitalOut(HospitalBase):
    id: int

    model_config = {"from_attributes": True}


# ---- Store ----
class StoreBase(BaseModel):
    hospital_id: int
    name: str
    code: str


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class StoreOut(StoreBase):
    id: int

    model_config = {"from_attributes": True}


# ---- ItemGroup ----
class ItemGroupBase(BaseModel):
    name: str


class ItemGroupCreate(ItemGroupBase):
    pass


class ItemGroupOut(ItemGroupBase):
    id: int

    model_config = {"from_attributes": True}


# ---- ItemCategory ----
class ItemCategoryBase(BaseModel):
    name: str
    is_vital: bool = False


class ItemCategoryCreate(ItemCategoryBase):
    pass


class ItemCategoryUpdate(BaseModel):
    name: Optional[str] = None
    is_vital: Optional[bool] = None


class ItemCategoryOut(ItemCategoryBase):
    id: int

    model_config = {"from_attributes": True}


# ---- Supplier ----
class SupplierBase(BaseModel):
    name: str
    code: str
    lead_time_days: int = 7


class SupplierCreate(SupplierBase):
    pass


class SupplierOut(SupplierBase):
    id: int

    model_config = {"from_attributes": True}


# ---- Item ----
class ItemBase(BaseModel):
    name: str
    code: str
    unit: str = "Nos"
    group_id: Optional[int] = None
    category_id: Optional[int] = None
    preferred_supplier_id: Optional[int] = None


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    unit: Optional[str] = None
    group_id: Optional[int] = None
    category_id: Optional[int] = None
    preferred_supplier_id: Optional[int] = None


class ItemOut(ItemBase):
    id: int

    model_config = {"from_attributes": True}


# ---- ItemSupplier ----
class ItemSupplierCreate(BaseModel):
    item_id: int
    supplier_id: int
    is_primary: bool = False
    moq: Optional[float] = None


class ItemSupplierOut(ItemSupplierCreate):
    id: int

    model_config = {"from_attributes": True}
