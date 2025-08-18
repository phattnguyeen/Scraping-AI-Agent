import os
import sys
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.schemas.products import Products, ProductsList, ProductInput
import asyncio
from app.db.create import get_db
from browser_use import Agent, BrowserConfig, Browser, Controller, ActionResult
from urllib.parse import urlparse
import pandas as pd
from browser_use.llm import ChatOpenAI
from datetime import datetime
import uuid
import json
from typing import Any

# Load .env
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Helpers ---
def save_product_to_db(db: Session, item: dict):
    """
    Normalize and save product to DB if not exists.
    """
    try:
        product = Products(
            id=uuid.uuid4(),
            product_name=item.get("productName") or item.get("title", ""),
            category="Laptop",  # TODO: detect dynamically
            brand="Lenovo",     # TODO: detect dynamically
            model=item.get("sku", None),
            seller_name=item.get("seller", item.get("retailer", "")),
            price=item.get("finalPriceVND", item.get("currentPriceVND", item.get("price", 0.0))),
            currency="VND",
            availability="in stock" in str(item.get("stockStatus", "")).lower(),
            url=item.get("url", ""),
            scraped_at=datetime.utcnow()
        )

        existing = db.query(Products).filter(
            Products.model == product.model,
            Products.seller_name == product.seller_name
        ).first()

        if not existing:
            db.add(product)
            db.commit()
            print(f"✅ Saved {product.product_name} from {product.seller_name} - {product.price}")
            return True
        else:
            print(f"⚠️ Skipped duplicate {product.product_name} from {product.seller_name}")
    except Exception as e:
        print(f"❌ Error saving product: {e}")
    return False


async def scraping_products(db: Session, input_data: ProductInput) -> ProductsList:
    """
    Scrape product data and save to DB in real-time.
    """
    browser_config = BrowserConfig(
        headless=True,
        slow_mo=500,
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
    @controller.action("search_google")
    async def search_google(page, query: str):
        await page.goto("https://www.google.com/?hl=vi", timeout=30000)
        await page.wait_for_selector("textarea[name='q'], input[name='q']", timeout=10000)
        await page.fill("textarea[name='q'], input[name='q']", query)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("div[data-sokoban-container]", timeout=15000)
        return {"status": "success", "query": query}

    @controller.action("extract_tech_results")
    async def extract_tech_results(page, limit: int = 10):
        results = []
        seen_urls = set()
        retailer_map = {
            "fptshop.com.vn": "FPT Shop",
            "thegioididong.com": "Thế Giới Di Động",
            "cellphones.com.vn": "CellphoneS",
            "hoanghamobile.com": "Hoàng Hà Mobile",
            "phongvu.vn": "Phong Vũ"
        }
        containers = await page.query_selector_all("div[data-sokoban-container], div.sh-dgr__content")
        for container in containers:
            if len(results) >= limit:
                break
            if await container.query_selector(":text('Quảng cáo'), :text('Sponsored')"):
                continue
            link = await container.query_selector("a")
            if not link:
                continue
            url = await link.get_attribute("href")
            if not url or not url.startswith("http") or url in seen_urls:
                continue
            seen_urls.add(url)
            domain = urlparse(url).netloc.replace("www.", "")
            seller = retailer_map.get(domain, domain.split('.')[0].title())
            title_el = await container.query_selector("h3, .tAxDx, .sh-np__product-title")
            title = (await title_el.inner_text()).strip() if title_el else ""
            price_text = ""
            price_el = await container.query_selector(".T4OwTb, .e10twf, .sh-np__price, .a8Pemb, .price")
            if price_el:
                price_text = (await price_el.inner_text()).strip()
            price_value = None
            if price_text:
                clean_price = ''.join(c for c in price_text if c.isdigit())
                if clean_price:
                    try:
                        price_value = float(clean_price)
                    except ValueError:
                        price_value = None
            if title and price_value:
                item = {
                    "title": title,
                    "url": url,
                    "price": price_value,
                    "seller": seller
                }
                results.append(item)
                # 👇 Save immediately when found
                save_product_to_db(db, item)

        return ActionResult(extracted_json={"products": results[:limit]})

    # --- Task instruction ---
    search_query = input_data.prompt or input_data.product_name
    limit = input_data.limit
    task_instruction = f"""
    1. Use 'search_google' with query: "{search_query} giá rẻ hoặc tốt nhất"
    
    2. Find the best price for {search_query} across major Vietnamese tech retailers such as:
       FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, and more.
       For each retailer:
           1. Navigate to their website and search for the exact product
           2. Record the current price, original price if on sale, and any available discounts
           3. Calculate the final price after discounts and promotions
           4. Note shipping costs and estimated delivery time
           5. Check if the product is in stock
           6. Record the product's name, model, and seller information, url website and time when the data was scraped
    3. Use 'extract_tech_results' with limit={limit}
    4. Return the extracted results as your final answer.
    5. Deduplicate results by product name or SKU.
    6. Identify the lowest offer per product.
    7. Stop after finding the target product.
    8. Output only valid JSON matching the ProductList schema — no markdown, no explanations.
    9. Export the results to a CSV file named 'agent_output.csv' with columns:
       - productName
       - sku
       - finalPriceVND
       - brand
       - retailer
       - url
       - stockStatus
       - scrapedAt
    """

    agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller)
    agent_result = await agent.run()

    final_result_obj = agent_result.final_result()
    print("=== RAW AGENT OUTPUT ===")
    print(final_result_obj)
   # Ensure it's a dict, not a raw string
    if isinstance(final_result_obj, str):
        try:
            final_result_obj = json.loads(final_result_obj)
        except json.JSONDecodeError:
            print("⚠️ Could not decode final_result_obj, got raw string")
            final_result_obj = {}

    # Now safe to use .get()
    products = final_result_obj.get("products", [])
    return ProductsList(products=products, total=len(products), limit=limit)

    # return ProductsList(products=final_result_obj.get("products", []))


if __name__ == "__main__":
    db = next(get_db())
    input_data = ProductInput(product_name="R760xs", limit=5, prompt="R760xs giá rẻ nhất")
    results = asyncio.run(scraping_products(db, input_data))
    print(" Done scraping")
