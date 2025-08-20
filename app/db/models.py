from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey, func, Text, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Product(Base):
    __tablename__ = "Product"

    # Id = Column(Integer, primary_key=True, autoincrement=True)
    # Sku = Column(String(100), nullable=True)     # SKU ngoài web crawl
    # ProductId = Column(Integer, nullable=True)           # Map tới Product trong nopCommerce
    # ProductName = Column(String(500), nullable=False)
    # Retailer = Column(String(200), nullable=True)
    # Price = Column(Numeric(18, 2), nullable=False)
    # OriginalPrice = Column(Numeric(18, 2), nullable=True)
    # Url = Column(Text, nullable=False)
    # StockStatus = Column(String(100), nullable=True)
    # CreatedAt = Column(DateTime, server_default=func.now())
    # UpdatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now())

    Id = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String(400), nullable=False)
    Sku = Column(String(400), nullable=True)
    Price = Column(Numeric(18, 4), nullable=False, default=0)
    OldPrice = Column(Numeric(18, 4), nullable=False, default=0)
    Published = Column(Boolean, nullable=False, default=True)
    Deleted = Column(Boolean, nullable=False, default=False)
    CreatedOnUtc = Column(DateTime, server_default=func.now())
    UpdatedOnUtc = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Product(Id={self.Id}, Name='{self.ProductName}', Price={self.Price})>"


