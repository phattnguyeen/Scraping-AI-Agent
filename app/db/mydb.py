import pyodbc
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, MetaData, Table, select

# Database connection info
DATABASE_URL = "mssql+pyodbc://sa:nopCommerce_db_password@172.16.7.106/mydb?driver=ODBC+Driver+17+for+SQL+Server"


# Create engine
engine = create_engine(DATABASE_URL, echo=True)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

# Reflect metadata
metadata = MetaData()
# metadata.reflect(engine)

def get_db():
    """Dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

