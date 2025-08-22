from sqlalchemy.orm import Session
from app.db import models
from app.schemas.products import ProductCreate, ProductUpdate
from typing import List

# Create product
def create_product(db: Session, product: ProductCreate):
    db_product = models.Product(
        product_name=product.product_name,
        external_sku=product.external_sku,
        brand=product.brand,
        retailer=product.retailer,
        url=product.url,
        original_price=product.original_price,
        final_price_vnd=product.final_price_vnd,
        price=product.price,
        stock_status=product.stock_status,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)  # now db_product.id will be auto-filled from SQL Server
    return db_product

# Get product by SKU
def get_product_by_sku(db: Session, sku: str):
    return db.query(models.Product).filter(models.Product.Sku == sku).first()

# def get_all_skus(db: Session):
#     return [row.sku for row in db.query(models.Product.Sku).all()]

def get_all_skus(db: Session) -> List[str]:
    """
    Connects to the database and fetches a simple list of all product SKUs.
    """
    print("Connecting to the database to get the list of SKUs...")
    try:
        # Query the 'sku' column from the 'Product' table
        skus_in_db = db.query(models.Product.Sku).filter(
            models.Product.Published == 1,
            models.Product.Deleted == 0
        ).all()

        # The result from SQLAlchemy is a list of tuples: [('SKU1',), ('SKU2',)]
        # We need to flatten it into a simple list of strings: ['SKU1', 'SKU2']
        sku_list = [item[0] for item in skus_in_db]

        print(f"Found {len(sku_list)} SKUs to process.")
        return sku_list
    except Exception as e:
        print(f"DATABASE ERROR: Could not fetch SKUs. Error: {e}")
        return [] 


# Get all products
def get_products(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Product).offset(skip).limit(limit).all()

def update_price_for_sku(db: Session, sku: str, new_price: float):
    """
    Finds a product by its SKU and updates its 'OldPrice' column with a new price.

    Args:
        db (Session): The active SQLAlchemy database session.
        sku (str): The SKU of the product to update.
        new_price (float): The new price to set for the product's OldPrice.
    """
    print(f"DATABASE: Attempting to update SKU '{sku}' with new price: {new_price}...")
    
    try:
        # Step 1: Find the product in the database that matches the SKU.
        # We use .first() because we expect the SKU to be unique.
        product_to_update = db.query(models.Product).filter(models.Product.Sku == sku).first()

        # Step 2: Check if the product was actually found.
        if product_to_update:
            # Step 3a: If found, update the OldPrice field on the product object.
            # IMPORTANT: This assumes your SQLAlchemy model's column is named 'OldPrice'.
            # Adjust the field name if yours is different (e.g., product_to_update.old_price).
            product_to_update.Price = new_price
            
            # Step 4: Commit the changes to the database to make them permanent.
            db.commit()
            
            print(f"DATABASE: Successfully updated SKU '{sku}'. New Price is now {new_price}.")
        else:
            # Step 3b: If no product was found, print a warning and do nothing.
            print(f"DATABASE: SKU '{sku}' not found in the database. No update was performed.")

    except Exception as e:
        # Step 5: If any database error occurs during the process, roll back the transaction.
        # This prevents the database from being left in a partially updated, inconsistent state.
        print(f"DATABASE ERROR: Could not update SKU {sku}. Transaction rolled back. Error: {e}")
        db.rollback()

# Update product
def update_product(db: Session, product_id: int, update: ProductUpdate):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        return None
    for key, value in update.dict(exclude_unset=True).items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product

# Delete product
def delete_product(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product
