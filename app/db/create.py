from sqlalchemy import (
    create_engine, Column, String, Integer, Text, Date, ForeignKey, DECIMAL, Time, CheckConstraint, event, Boolean, DateTime
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import text
import random
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid


DATABASE_URL= "postgresql://postgres:Post%3A%21%40%23%2416@172.16.0.75:5442/si_lacviet"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    brand = Column(String, nullable=False)
    model = Column(String, nullable=True)
    seller_name = Column(String, nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String, nullable=False)
    availability = Column(Boolean, nullable=False)
    url = Column(Text, nullable=False)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

def drop_tables(engine):
    """Drop all tables in the database."""
    try:
        # Open a connection to the database
        with engine.connect() as connection:
            # Drop all tables in the public schema
            connection.execute(text("""
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    -- Loop through each table and drop it
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
                    LOOP
                        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """))
        print("Tables dropped successfully!")
    except Exception as e:
        print(f"Error dropping tables: {e}")

def create_tables():
    """Ensure tables are created in the database."""
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

def get_db():
    """Dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # Uncomment the line below to drop all tables before creating them again
    #drop_tables(engine)
    create_tables()
