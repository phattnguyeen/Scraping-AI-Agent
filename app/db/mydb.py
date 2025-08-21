import pyodbc
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, MetaData, Table, select

# Database connection info
#DATABASE_URL = "mssql+pyodbc://sa:nopCommerce_db_password@172.16.7.106/mydb?driver=ODBC+Driver+17+for+SQL+Server"

DATABASE_URL = (
    "mssql+pyodbc://@localhost/mydb"
    "?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)




# Create engine
engine = create_engine(DATABASE_URL, echo=True)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

# Reflect metadata
metadata = MetaData()
# metadata.reflect(engine)
# metadata.reflect(bind=engine)

# # Load CrawledProduct table
# try:
#     CrawledProduct = Table("CrawledProduct", metadata, autoload_with=engine)

#     # Run test query: select Id, ProductName, Price
#     with engine.connect() as conn:
#         stmt = select(
#             CrawledProduct.c.Id,
#             CrawledProduct.c.ProductName,
#             CrawledProduct.c.Price
#         ).limit(5)

#         result = conn.execute(stmt)
#         for row in result:
#             print(row)

# except Exception as e:
#     print("❌ Error:", e)

# finally:
#     session.close()
def get_db():
    """Dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

