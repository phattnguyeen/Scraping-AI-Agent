import os
import sys
from dotenv import load_dotenv
load_dotenv()
from app.db.models import Product
from app.schemas.products import ProductCreate, ProductUpdate
from app.db.mydb import get_db
from sqlalchemy.orm import Session
from browser_use import Agent, BrowserConfig, Browser, Controller, ActionResult
from urllib.parse import urlparse
import pandas as pd
from browser_use.llm import ChatOpenAI
from datetime import datetime
import uuid
import json
from typing import Any
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
RETAILER_SELECTORS = {
    "thegioididong": "div.bs_price strong",
    "fptshop": ".st-price-main",
    "cellphones": ".product__price--show",
    "hoanghamobile": ".product-detail__price--special",
    "phongvu": ".css-1q4h2nb",
    "anphatpc": ".price-box span.special-price",
}

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
controller = Controller()
# --- Custom Action ---
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

@controller.action("extract_final_price")
async def extract_final_price(page, url: str, retailer: str):
    """Extract the final product price from a retailer product page."""

    selector = RETAILER_SELECTORS.get(retailer.lower())
    if not selector:
        raise ValueError(f"No selector defined for retailer: {retailer}")

    # Go to product page
    await page.goto(url)

    # Wait for the price element
    await page.wait_for_selector(selector, timeout=10000)

    # Extract the HTML
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Get price text
    price_tag = soup.select_one(selector)
    if not price_tag:
        raise ValueError(f"Price not found for {retailer}")

    price_str = price_tag.get_text(strip=True)
    price_value = clean_price(price_str)

    return {"url": url, "retailer": retailer, "finalPriceVND": price_value}
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

        return ActionResult(extracted_json={"products": results[:limit]})


async def scrape_product_data(searchQuery: str, limit: int) -> list[ProductCreate]:
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

    task_instruction = f"""
    You are a specialized scraper for Vietnamese retailers focusing ONLY on servers and laptops.

    TASK: Search for "{searchQuery}" across major Vietnamese laptop and server retailers.

    INSTRUCTIONS:
    1. Use 'search_google_laptop_server' with query: "{searchQuery}"
    2. Use 'extract_laptop_server_results' with limit={limit}
    3. Focus ONLY on these retailers (skip others): 
       FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, 
       An Phát PC, Phúc Anh, Trần Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store, Vinaphone
    4. Extract only Laptops and Servers.
    5. Extract fields:
       - ProductName
       - Brand
       - SKU
       - FinalPriceVND
       - Retailer
       - Url
       - StockStatus
       - Category (Laptop/Server)
       - ScrapedAt
    6. Ensure all prices are in VND.
    7. Deduplicate by brand, model, seller.
    8. Return only valid JSON with `products` array.
    """

    
    agent = Agent(
        browser=browser,
        llm=llm,
        task=task_instruction,
        controller=controller
    )

    agent_result = await agent.run()
    await browser.stop()

    # # Extract JSON string from agent_result
    # if hasattr(agent_result, "final_result"):
    #     result_json = agent_result.final_result
    # elif hasattr(agent_result, "all_results") and agent_result.all_results:
    #     last = agent_result.all_results[-1]
    #     result_json = last.get("result", "{}")
    # else:
    #     result_json = "{}"

    # # Parse JSON and convert to ProductCreate list
    # try:
    #     data = json.loads(result_json)
    #     products = data.get("products", [])
    #     product_objs = [ProductCreate(**p) for p in products]
    # except Exception as e:
    #     print(f"Error parsing products: {e}")
    #     product_objs = []
    # Extract JSON string from agent_result
    if hasattr(agent_result, "final_result"):
        # if final_result is a method, call it
        result_json = agent_result.final_result() if callable(agent_result.final_result) else agent_result.final_result
    elif hasattr(agent_result, "all_results") and agent_result.all_results:
        last = agent_result.all_results[-1]
        result_json = last.get("result", "{}")
    else:
        result_json = "{}"

    # Parse JSON and convert to ProductCreate list
    try:
        if isinstance(result_json, (dict, list)):
            # Already a dict/list, no need to json.loads
            data = result_json
        else:
            data = json.loads(result_json)
        products = data.get("products", [])
        product_objs = [ProductCreate(**p) for p in products]
    except Exception as e:
        print(f"Error parsing products: {e}")
        print("⚠️ result_json:", result_json)  # debug print
        product_objs = []


    return product_objs
async def save_products_to_db(products: list[ProductCreate], db: Session):
    """Save scraped products to the database."""
    saved_products = []
    for product in products:
        db_product = Product(
            product_name=product.product_name,
            external_sku=product.external_sku,
            brand=product.brand,
            retailer=product.retailer,
            url=product.url,
            original_price=product.original_price,
            price=product.price,
            stock_status=product.stock_status,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        saved_products.append(db_product)
    return saved_products

async def scrape_and_save_products(searchQuery: str, limit: int = 10):
    """Main function to scrape and save products."""
    db: Session = get_db()
    try:
        products = await scrape_product_data(searchQuery, limit)
        if not products:
            print("No products found.")
            return []
        saved_products = await save_products_to_db(products, db)
        print(f"Saved {len(saved_products)} products to the database.")
        return saved_products
    except Exception as e:
        print(f"Error during scraping or saving: {e}")
        return []
if __name__ == "__main__":
    import asyncio
    search_query = "máy chủ server Dell PowerEdge T140 giá rẻ"
    limit = 10
    loop = asyncio.get_event_loop()
    products = loop.run_until_complete(scrape_and_save_products(search_query, limit))




