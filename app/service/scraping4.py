import os
import sys
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.schemas.products import Products, ProductsList, ProductInput
import asyncio
from app.db.create import get_db, Product
from browser_use import Agent, BrowserConfig, Browser, Controller, ActionResult
from urllib.parse import urlparse
import pandas as pd
from browser_use.llm import ChatOpenAI
from datetime import datetime
import uuid
import json
from typing import Any
import re

# Load .env
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Vietnamese laptop and server retailers
LAPTOP_SERVER_RETAILERS = {
    "fptshop.com.vn": "FPT Shop",
    "thegioididong.com": "Thế Giới Di Động", 
    "cellphones.com.vn": "CellphoneS",
    "hoanghamobile.com": "Hoàng Hà Mobile",
    "phongvu.vn": "Phong Vũ",
    "gearvn.com": "GearVN",
    "anphatpc.com.vn": "An Phát PC",
    "phucanh.vn": "Phúc Anh",
    "trananh.vn": "Trần Anh",
    "nguyenkim.com": "Nguyễn Kim",
    "mediamart.vn": "MediaMart",
    "dienmayxanh.com": "Điện Máy Xanh",
    "tgdđ.com": "Thế Giới Di Động",
    "fpt.com.vn": "FPT",
    "viettelstore.vn": "Viettel Store",
    "vinaphone.com.vn": "Vinaphone"
}

# --- Helpers ---
def extract_brand_from_title(title: str) -> str:
    """Extract brand from product title."""
    brands = [
        "Dell", "HP", "Lenovo", "Asus", "Acer", "MSI", "Gigabyte", "Apple", "Samsung",
        "Toshiba", "Fujitsu", "Sony", "LG", "Huawei", "Xiaomi", "Microsoft", "Razer",
        "Alienware", "ROG", "Predator", "ThinkPad", "IdeaPad", "Inspiron", "Latitude",
        "Precision", "EliteBook", "ProBook", "Pavilion", "Envy", "Spectre", "Omen",
        "Legion", "Yoga", "ThinkBook", "Vostro", "XPS", "MacBook", "Mac", "iMac"
    ]
    
    title_lower = title.lower()
    for brand in brands:
        if brand.lower() in title_lower:
            return brand
    return "Unknown"

def extract_model_from_title(title: str) -> str:
    """Extract model/SKU from product title."""
    # Common laptop/server model patterns
    patterns = [
        r'\b[A-Z]{2,4}\d{3,4}[A-Z]?\b',  # HP 15, Dell XPS 13, etc.
        r'\b[A-Z]{2,4}-\d{3,4}[A-Z]?\b',  # HP-15, Dell-XPS-13, etc.
        r'\b[A-Z]{2,4}\s+\d{3,4}[A-Z]?\b',  # HP 15, Dell XPS 13, etc.
        r'\b[A-Z]{2,4}\d{2,3}[A-Z]{1,2}\d{1,2}\b',  # ThinkPad T14, etc.
        r'\b[A-Z]{2,4}\d{2,3}[A-Z]{1,2}\b',  # ThinkPad T14, etc.
        r'\b[A-Z]{2,4}\d{2,3}\b',  # HP 15, etc.
        r'\b[A-Z]{2,4}\d{2,3}[A-Z]{1,2}\d{1,2}[A-Z]{1,2}\b',  # ThinkPad T14s Gen 2, etc.
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, title.upper())
        if matches:
            return matches[0]
    return ""

def clean_price(price_text: str) -> float:
    """Clean and extract price from text."""
    if not price_text:
        return 0.0
    
    # Remove all non-digit characters except decimal point
    clean_price = re.sub(r'[^\d.]', '', price_text)
    
    try:
        price = float(clean_price)
        # If price seems too small (less than 1000), it might be in thousands
        if price < 1000 and len(clean_price) > 3:
            price *= 1000
        return price
    except ValueError:
        return 0.0

def save_product_to_db(db: Session, item: dict) -> bool:
    """Normalize and save product to DB if not exists."""
    try:
        # Extract brand and model from title
        title = item.get("productName") or item.get("title", "")
        brand = item.get("brand") or extract_brand_from_title(title)
        model = item.get("sku") or extract_model_from_title(title)
        
        # Determine category based on keywords
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in ["server", "rack", "blade", "tower server"]):
            category = "Server"
        elif any(keyword in title_lower for keyword in ["laptop", "notebook", "ultrabook"]):
            category = "Laptop"
        else:
            category = "Computer"
        
        product = Product(
            id=uuid.uuid4(),
            product_name=title,
            category=category,
            brand=brand,
            model=model,
            seller_name=item.get("retailer") or item.get("seller", ""),
            price=item.get("finalPriceVND") or item.get("currentPriceVND") or item.get("price", 0.0),
            currency="VND",
            availability="in stock" in str(item.get("stockStatus", "")).lower(),
            url=item.get("url", ""),
            scraped_at=item.get("scrapedAt", datetime.now(datetime.UTC))
        )

        # Check for existing product by model and seller
        existing = db.query(Product).filter(
            Product.model == product.model,
            Product.seller_name == product.seller_name,
            Product.brand == product.brand
        ).first()

        if not existing:
            db.add(product)
            db.commit()
            print(f"✅ Saved {product.product_name} ({product.brand} {product.model}) from {product.seller_name} - {product.price:,} VND")
            return True
        else:
            print(f"⚠️ Skipped duplicate {product.product_name} from {product.seller_name}")
            return False
    except Exception as e:
        print(f"❌ Error saving product: {e}")
        db.rollback()
        return False

async def scraping_products(db: Session, input_data: ProductInput) -> ProductsList:
    """Scrape laptop/server product data, save to DB, and export to CSV."""
    browser_config = BrowserConfig(
        headless=True,
        slow_mo=1000,
        disable_security=False,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    browser = Browser(config=browser_config)
    await browser.start()

    llm = ChatOpenAI(
        model="gpt-5",
        temperature=0,
        api_key=OPENAI_API_KEY
    )
    controller = Controller()

    # --- Custom Actions ---
    @controller.action("search_google_laptop_server")
    async def search_google_laptop_server(page, query: str):
        """Search Google specifically for laptop and server products."""
        search_query = f"{query} laptop server máy tính xách tay máy chủ giá rẻ"
        await page.goto("https://www.google.com/?hl=vi", timeout=30000)
        await page.wait_for_selector("textarea[name='q'], input[name='q']", timeout=10000)
        await page.fill("textarea[name='q'], input[name='q']", search_query)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("div[data-sokoban-container], div.sh-dgr__content", timeout=15000)
        return {"status": "success", "query": search_query}

    @controller.action("extract_laptop_server_results")
    async def extract_laptop_server_results(page, limit: int = 10):
        """Extract laptop and server product results from Google Shopping."""
        results = []
        seen_urls = set()
        
        # Wait for results to load
        await page.wait_for_timeout(3000)
        
        containers = await page.query_selector_all("div[data-sokoban-container], div.sh-dgr__content, div.sh-dlr__product-result")
        
        for container in containers:
            if len(results) >= limit:
                break
                
            # Skip ads
            if await container.query_selector(":text('Quảng cáo'), :text('Sponsored'), :text('Ad')"):
                continue
                
            link = await container.query_selector("a")
            if not link:
                continue
                
            url = await link.get_attribute("href")
            if not url or not url.startswith("http") or url in seen_urls:
                continue
                
            seen_urls.add(url)
            domain = urlparse(url).netloc.replace("www.", "")
            
            # Only process known retailers
            if domain not in LAPTOP_SERVER_RETAILERS:
                continue
                
            seller = LAPTOP_SERVER_RETAILERS[domain]
            
            # Extract title
            title_el = await container.query_selector("h3, .tAxDx, .sh-np__product-title, .sh-dlr__product-title")
            title = (await title_el.inner_text()).strip() if title_el else ""
            
            # Extract price
            price_text = ""
            price_el = await container.query_selector(".T4OwTb, .e10twf, .sh-np__price, .a8Pemb, .price, .sh-dlr__price")
            if price_el:
                price_text = (await price_el.inner_text()).strip()
            
            price_value = clean_price(price_text)
            
            # Extract brand and model
            brand = extract_brand_from_title(title)
            model = extract_model_from_title(title)
            
            if title and price_value > 0:
                item = {
                    "product_name": title,
                    "url": url,
                    "finalPriceVND": price_value,
                    "brand": brand,
                    "model": model,
                    "retailer": seller,
                    "category": "Laptop" if "laptop" in title.lower() else "Server" if "server" in title.lower() else "Computer",
                    "scrapedAt": datetime.now(datetime.UTC).isoformat(),
                    "stockStatus": "in stock"
                }
                results.append(item)
                save_product_to_db(db, item)

        return ActionResult(extracted_json={"products": results[:limit]})

    # --- Task instruction ---
    search_query = input_data.prompt or input_data.product_name
    limit = input_data.limit
    
    # task_instruction = f"""
    # You are a specialized laptop and server product scraper for Vietnamese retailers.
    
    # TASK: Search for "{search_query}" across major Vietnamese laptop and server retailers.
    
    # INSTRUCTIONS:
    # 1. Use 'search_google_laptop_server' with query: "{search_query}"
    # 2. Use 'extract_laptop_server_results' with limit={limit}
    # 3. Focus on these retailers: FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Trần Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Tiki, Shopee, Lazada, Sendo, Viettel Store, Vinaphone
    # 4. Extract product information including:
    #    - Product name and title
    #    - Brand (Dell, HP, Lenovo, Asus, Acer, MSI, etc.)
    #    - Model/SKU number
    #    - Current price in VND
    #    - Retailer/seller name
    #    - Product URL
    #    - Stock status
    #    - Category (Laptop/Server/Computer)
    # 5. Ensure all prices are in VND currency
    # 6. Deduplicate by brand, model, and seller
    # 7. Return only valid JSON with products array
    # 8. Export results to 'laptop_server_products.csv'
    
    # OUTPUT FORMAT:
    # {{
    #     "products": [
    #         {{
    #             "productName": "Product full name",
    #             "brand": "Brand name",
    #             "sku": "Model/SKU",
    #             "finalPriceVND": 15000000,
    #             "retailer": "Retailer name",
    #             "url": "Product URL",
    #             "stockStatus": "in stock",
    #             "category": "Laptop/Server/Computer",
    #             "scrapedAt": "2024-01-01T00:00:00"
    #         }}
    #     ]
    # }}
    # """
    task_instruction = f"""
    You are a specialized scraper for Vietnamese retailers focusing ONLY on **servers and laptops**.
    
    TASK: Search for "{search_query}" across major Vietnamese laptop and server retailers.
    
    INSTRUCTIONS:
    1. Use 'search_google_laptop_server' with query: "{search_query}"
    2. Use 'extract_laptop_server_results' with limit={limit}
    3. Focus ONLY on these retailers (skip others): 
       FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, 
       An Phát PC, Phúc Anh, Trần Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store, Vinaphone
    4. Extract product information **only if category is Laptop or Server**. 
       Ignore unrelated categories such as smartphones, tablets, TVs, appliances, accessories.
    5. Extract these fields:
       - Product name and title
       - Brand (Dell, HP, Lenovo, Asus, Acer, MSI, Supermicro, etc.)
       - Model/SKU number
       - Current price in VND
       - Retailer/seller name
       - Product URL
       - Stock status/ Availability
       - Category (Laptop or Server)
    6. Ensure all prices are in VND currency.
    7. Deduplicate by brand, model, and seller.
    8. Return only valid JSON with products array.
    9. Export results to 'laptop_server_products.csv'.
    
    OUTPUT FORMAT:
    {{
        "products": [
            {{
                "productName": "Product full name",
                "brand": "Brand name",
                "sku": "Model/SKU",
                "finalPriceVND": 15000000,
                "retailer": "Retailer name",
                "url": "Product URL",
                "stockStatus": "in stock",
                "category": "Laptop/Server",
                "scrapedAt": "{{datetime.now(datetime.UTC).isoformat()}}"
            }}
        ]
    }}
    """


    agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller, use_vision=True)
    agent_result = await agent.run()

    final_result_obj = agent_result.final_result()
    print("=== RAW AGENT OUTPUT ===")
    print(final_result_obj)
    # if isinstance(final_result_obj, str):
    #     try:
    #         data = json.loads(final_result_obj)
    #     except json.JSONDecodeError:
    #         print("⚠️ Could not decode final_result_obj as JSON")
    #         data = final_result_obj
    # if data:
    #     parsed: ProductsList = ProductsList.model_validate_json(data)
    #     for product in parsed.products:
    #         print(f"Product: {product.product_name}, Price: {product.price} {product.currency}, URL: {product.url}")
    # else:
    #     print("No products found or final result is empty.")
    # Nếu final_result_obj là JSON string
        
    if isinstance(final_result_obj, str):
        # Remove anything after the last closing brace "}"
        cleaned_json = re.split(r'}\s*$', final_result_obj, maxsplit=1)[0] + "}"

        try:
            parsed: ProductsList = ProductsList.model_validate_json(cleaned_json)
            print("✅ Parsed ProductsList:", parsed)
        except Exception as e:
            print("❌ Still cannot parse:", e)
            print("Raw string was:\n", final_result_obj)
    else:
        # If already dict
        parsed: ProductsList = ProductsList.model_validate(final_result_obj)

            


    # # Ensure it's a dict
    # if isinstance(final_result_obj, str):
    #     try:
    #         final_result_obj = json.loads(final_result_obj)
    #     except json.JSONDecodeError:
    #         print("⚠️ Could not decode final_result_obj")
    #         final_result_obj = {}

    # products = final_result_obj.get("products", [])
    # print(products
    # os.makedirs("outputs", exist_ok=True)

    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # json_filename = f"outputs/products_{timestamp}.json"

    
    # with open(json_filename, "w", encoding="utf-8") as f:
    #     json.dump(final_result_obj, f, ensure_ascii=False, indent=4)

    # print(f"✅ File JSON đã lưu tại: {json_filename}")


    # --- Save to CSV with enhanced data ---
    # if products:
    #     # Enhance the data before saving
    #     enhanced_products = []
    #     for item in products:
    #         title = item.get("productName", "")
    #         enhanced_item = {
    #             "productName": title,
    #             "brand": item.get("brand") or extract_brand_from_title(title),
    #             "sku": item.get("sku") or extract_model_from_title(title),
    #             "category": item.get("category") or ("Laptop" if "laptop" in title.lower() else "Server" if "server" in title.lower() else "Computer"),
    #             "finalPriceVND": item.get("finalPriceVND", 0),
    #             "retailer": item.get("retailer", ""),
    #             "url": item.get("url", ""),
    #             "stockStatus": item.get("stockStatus", "unknown"),
    #             "scrapedAt": item.get("scrapedAt", datetime.now(datetime.UTC).isoformat())
    #         }
    #         enhanced_products.append(enhanced_item)
        
    #     df = pd.DataFrame(enhanced_products)
    #     csv_filename = f"laptop_server_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    #     df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    #     print(f"✅ Exported {len(enhanced_products)} products to {csv_filename}")

    #     # Save to JSON (products only, no summary)
    #     json_filename = f"laptop_server_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    #     with open(json_filename, "w", encoding="utf-8") as f:
    #         json.dump({"products": enhanced_products}, f, indent=2, ensure_ascii=False)
    #     print(f"✅ Exported {len(enhanced_products)} products to {json_filename}")
    # file_paths = {}
    # if products:
    #     enhanced_products = []
    #     for item in products:
    #         title = item.get("productName", "")
    #         enhanced_products.append({
    #             "productName": title,
    #             "brand": item.get("brand") or extract_brand_from_title(title),
    #             "sku": item.get("sku") or extract_model_from_title(title),
    #             "category": item.get("category") or ("Laptop" if "laptop" in title.lower()
    #                                                 else "Server" if "server" in title.lower()
    #                                                 else "Computer"),
    #             "finalPriceVND": item.get("finalPriceVND", 0),
    #             "retailer": item.get("retailer", ""),
    #             "url": item.get("url", ""),
    #             "stockStatus": item.get("stockStatus", "unknown"),
    #             "scrapedAt": item.get("scrapedAt", datetime.now(datetime.UTC).isoformat())
    #         })

    #     df = pd.DataFrame(enhanced_products)
    #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    #     csv_filename = os.path.join(OUTPUT_DIR, f"laptop_server_products_{timestamp}.csv")
    #     json_filename = os.path.join(OUTPUT_DIR, f"laptop_server_products_{timestamp}.json")

    #     df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    #     with open(json_filename, "w", encoding="utf-8") as f:
    #         json.dump({"products": enhanced_products}, f, indent=2, ensure_ascii=False)

    #     print(f"✅ Exported {len(enhanced_products)} products")
    #     print(f"   CSV: {csv_filename}")
    #     print(f"   JSON: {json_filename}")

    #     file_paths = {"csv": csv_filename, "json": json_filename}

    # await browser.close()
    # return ProductsList(products=products, total=len(products), limit=limit)

if __name__ == "__main__":
    db = next(get_db())
    input_data = ProductInput(product_name="83F5008WVN", limit=2, prompt="83F5008WVN laptop giá rẻ nhất")
    results = asyncio.run(scraping_products(db, input_data))
    print("Done scraping")
