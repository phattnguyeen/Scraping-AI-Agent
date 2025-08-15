from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List

class Products(BaseModel):
    product_id: str = Field(..., description="Unique identifier for the product")
    product_name: str = Field(..., description="Name of the product")
    category: str = Field(..., description="Category of the product")
    brand: str = Field(..., description="Brand of the product")
    model: Optional[str] = Field(None, description="Model of the product, if applicable")
    seller_name: str = Field(..., description="Name of the seller")
    price: float = Field(..., description="Price of the product")
    currency: str = Field(..., description="Currency of the price")
    availability: bool = Field(..., description="Availability status of the product")
    url: str = Field(..., description="URL to the product page")
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Timestamp when the data was scraped")

class ProductsList(BaseModel):
    products: List[Products] = Field(..., description="List of products")
    limit: int = Field(..., description="Limit on the number of products to return")
    total: int = Field(..., description="Total number of products found")


# in app/schemas/products.py
class ProductInput(BaseModel):
    product_name: str
    limit: int = 10
    prompt: Optional[str] = None



