from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProductBase(BaseModel):
    ExternalSku: Optional[str] = None
    ProductId: Optional[int] = None
    ProductName: str
    Retailer: Optional[str] = None
    Price: float
    OriginalPrice: Optional[float] = None
    Url: str
    StockStatus: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    pass

class ProductOut(ProductBase):
    Id: int
    CreatedAt: datetime
    UpdatedAt: datetime

    class Config:
        from_attributes = True   # Enable ORM mode for SQLAlchemy
