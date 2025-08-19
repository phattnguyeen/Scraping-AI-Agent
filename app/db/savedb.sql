use mydb

select * from Product

CREATE TABLE CrawledProduct (
    Id INT IDENTITY PRIMARY KEY,
    ExternalSku NVARCHAR(100),       -- SKU ngoài web crawl
    ProductId INT NULL,              -- Map tới Product trong nopCommerce (nếu có)
    ProductName NVARCHAR(500),
    Retailer NVARCHAR(200),
    Price DECIMAL(18,2),
    OriginalPrice DECIMAL(18,2) NULL,
    Url NVARCHAR(MAX),
    StockStatus NVARCHAR(100),
    CreatedAt DATETIME DEFAULT GETDATE(),
    UpdatedAt DATETIME DEFAULT GETDATE()
)
