import os
import sys
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.schemas.products import Products, ProductsList, ProductInput
import asyncio
from app.db.create import get_db
# from app.service.scraping import ScrapeResponse
from browser_use import Agent, BrowserConfig, Browser, Controller, ActionResult
from urllib.parse import urlparse
import pandas as pd

from browser_use.llm import ChatOpenAI
from datetime import datetime
import uuid

# Load .env
load_dotenv()

# Fix import paths if running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

import json
import json
from typing import Any

def handle_llm_response(raw_response: str) -> ActionResult:
    """
    Parse the LLM response into an ActionResult, 
    trying JSON first if possible.
    """
    result = ActionResult()

    try:
        # Try to parse as JSON
        parsed: Any = json.loads(raw_response)
        if isinstance(parsed, dict):
            result.extracted_json = parsed
        else:
            result.extracted_content = raw_response  # fallback
    except json.JSONDecodeError:
        # Not valid JSON → fallback to plain text
        result.extracted_content = raw_response

    return result


def extract_final_json(agent_result):
    # If final_result is already a dict
    if hasattr(agent_result, "final_result"):
        fr = agent_result.final_result
        if isinstance(fr, dict):
            return json.dumps(fr)
        elif isinstance(fr, str):
            return fr
        elif hasattr(fr, "model_dump_json"):  # Pydantic model or similar
            return fr.model_dump_json()
    
    # Fallback: try from last all_results entry
    if hasattr(agent_result, "all_results") and agent_result.all_results:
        last = agent_result.all_results[-1]
        if isinstance(last, dict) and "result" in last:
            if isinstance(last["result"], dict):
                return json.dumps(last["result"])
            elif isinstance(last["result"], str):
                return last["result"]
    
    return "{}"



async def scraping_products(
    db: Session,
    input_data: ProductInput
) -> ProductsList:
    """
    Scrape product data using the provided prompt or product name and return a list of products.
    """
    browser_config = BrowserConfig(
        headless=False,
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
        api_key=os.getenv("OPENAI_API_KEY")
    )
    controller = Controller()

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
            price_selectors = [
                ".T4OwTb, .e10twf, .sh-np__price, .tAxDx, .a8Pemb, .price",
                ":text-matches('([0-9,.]+\\s*[₫đVND]?)', 'i')"
            ]
            price_text = ""
            for selector in price_selectors:
                price_el = await container.query_selector(selector)
                if price_el:
                    price_text = (await price_el.inner_text()).strip()
                    if price_text:
                        break
            price_value = None
            if price_text:
                clean_price = ''.join(c for c in price_text if c.isdigit())
                if clean_price:
                    try:
                        price_value = float(clean_price)
                    except ValueError:
                        price_value = None
            if title and price_value:
                results.append({
                    "title": title,
                    "url": url,
                    "price": price_value,
                    "seller": seller
                })
        return ActionResult(extracted_json={"products": results[:limit]})

    # Use prompt if provided, otherwise product name
    search_query = input_data.product_name if input_data.prompt else input_data.prompt
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

    # agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller)
    # agent_result = await agent.run()
    # final_json = agent_result.final_result()
    # final_result = extract_final_json(final_json)
    # print("=== RAW AGENT OUTPUT ===")
    # print(final_json)
    # Run the agent
    agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller)
    agent_result = await agent.run()
    final_result_obj = agent_result.final_result()


    print("=== RAW AGENT OUTPUT ===")
    print(final_result_obj)
    print("Data exported to agent_output.csv")

    # --- Step 3: Normalize results (extract product list) ---
    if isinstance(final_result_obj, dict) and "products" in final_result_obj:
        product_list = final_result_obj["products"]
    else:
        product_list = final_result_obj if isinstance(final_result_obj, list) else []
    
    print(f"Found {len(product_list)} products in the results")
    print("=== Normalized Product List ===")
    for item in product_list:
        print(f"Product: {item.get('title', 'N/A')}, Price: {item.get('price', 'N/A')}, URL: {item.get('url', 'N/A')}")
    # If no products found, return empty list
    if not product_list:
        print("No products found in the results.")
        return ProductsList(products=[])

    # --- Step 4: Save to DB ---
    saved_rows = []
    for item in product_list:
        try:
            product = Products(
                id=uuid.uuid4(),
                product_name=item.get("productName", ""),
                category="Laptop",  # TODO: parse category dynamically if possible
                brand="Lenovo",     # TODO: detect from productName (now hardcoded)
                model=item.get("sku", None),
                seller_name=item.get("seller", item.get("retailer", "")),
                price=item.get("finalPriceVND", item.get("currentPriceVND", 0.0)),
                currency="VND",
                availability="in stock" in item.get("stockStatus", "").lower(),
                url=item.get("url", ""),
                scraped_at=datetime.fromisoformat(item.get("scrapedAt").replace("Z", "+00:00"))
            )

            # Prevent duplicate insert (check by model + seller)
            existing = db.query(Products).filter(
                Products.model == product.model,
                Products.seller_name == product.seller_name
            ).first()

            if not existing:
                db.add(product)
                saved_rows.append({
                    "product_name": product.product_name,
                    "model": product.model,
                    "seller": product.seller_name,
                    "price": float(product.price),
                    "url": product.url
                })

        except Exception as e:
            print(f"⚠️ Error saving product: {e}")

    db.commit()
    print(f" {len(saved_rows)} new products saved to DB")

    # --- Step 5: Export the DB-inserted records to CSV (normalized view) ---
    if saved_rows:
        pd.DataFrame(saved_rows).to_csv("db_saved_products.csv", index=False, encoding="utf-8-sig")
        print("Normalized DB-saved products exported to db_saved_products.csv")



if __name__ == "__main__":
     # Example run
    db = next(get_db())
    input_data = ProductInput(product_name="83LK0079VN", limit=5, prompt="83LK0079VN giá rẻ nhất")
    results = asyncio.run(scraping_products(db, input_data))
    # print("Scraped Products:")
    # print(results)


    