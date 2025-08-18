import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# browser-use
from browser_use import Browser, Agent, BrowserConfig
from browser_use.controller.service import Controller
from browser_use.llm import ChatOpenAI

load_dotenv()

# ===============================
# Pydantic Models
# ===============================
class LowestOfferInput(BaseModel):
    product_name: str
    limit: int = 10

class Offer(BaseModel):
    seller_name: str
    price_amount: float
    price_currency: str = "VND"
    product_url: str
    scrape_timestamp: str = datetime.utcnow().isoformat()

class Product(BaseModel):
    product_name: str
    lowest_offer: Offer
    category: Optional[str] = None
    brand: Optional[str] = None

class ScrapeResponse(BaseModel):
    scrape_timestamp: str = datetime.utcnow().isoformat()
    products: List[Product]
    search_term: str
    product_count: int

# ===============================
# Controller Actions (Improved)
# ===============================
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
    return results[:limit]

# ===============================
# Scraping Logic (Fixed)
# ===============================
# async def scrape_lowest_offers(input_data: LowestOfferInput) -> ScrapeResponse:
#     browser = Browser(config=BrowserConfig(
#         headless=True,
#         slow_mo=100,
#         timeout=30000,
#         user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
#     ))
#     llm = ChatOpenAI(
#         model="gpt-5",
#         temperature=0,
#         api_key=os.getenv("OPENAI_API_KEY")
#     )
#     task_instruction = f"""
#     1. Use 'search_google' with query: "{input_data.product_name} giá rẻ nhất"
#     2. Use 'extract_tech_results' with limit={input_data.limit}
#     3. Return the extracted results as your final answer.
#     Ensure the output is valid JSON matching the ScrapeResponse schema.
#     """
#     await browser.start()
#     agent = Agent(
#         task=task_instruction,
#         llm=llm,
#         browser=browser,
#         controller=controller,
#         max_steps=5,
#         save_conversation_path="scrape_log.json"
#     )
#     history = await agent.run()
#     result = history.final_result()
#     # Always try to parse the result into the expected format
#     products = []
#     if isinstance(result, list):
#         raw_items = result
#     elif isinstance(result, dict) and "result" in result:
#         raw_items = result["result"]
#     else:
#         raw_items = []
#     for item in raw_items:
#         try:
#             title = item.get("title") or item.get("product_name") or "Unknown Product"
#             price = item.get("price") or item.get("price_amount")
#             seller = item.get("seller") or item.get("seller_name") or "Unknown Seller"
#             url = item.get("url") or item.get("product_url") or ""
#             if not all([title, price, url]):
#                 continue
#             offer = Offer(
#                 seller_name=seller,
#                 price_amount=price,
#                 product_url=url
#             )
#             products.append(Product(
#                 product_name=title,
#                 lowest_offer=offer
#             ))
#         except Exception:
#             continue
#     products.sort(key=lambda p: p.lowest_offer.price_amount)
#     final_products = products[:input_data.limit]
#     return ScrapeResponse(
#         products=final_products,
#         search_term=input_data.product_name,
#         product_count=len(final_products)
#     )
async def scrape_lowest_offers(input_data: LowestOfferInput) -> ScrapeResponse:
    browser = Browser(config=BrowserConfig(
        headless=True,
        slow_mo=100,
        timeout=30000,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ))
    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY")
    )

    task_instruction = f"""
   
    1. Use 'search_google' with query: "{input_data.product_name} giá rẻ nhất"
    2. Find the best price for {input_data.product_name} across on major Vietnamese tech retailers such as:
    FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, and more
    For each retailer:
        1. Navigate to their website and search for the exact product
        2. Record the current price, original price if on sale, and any available discounts
        3. Note shipping costs and estimated delivery time
        4. Check if the product is in stock
    3. Use 'extract_tech_results' with limit={input_data.limit}
    4. Return the extracted results as your final answer.
    5. Deduplicate results by product name or SKU.
    6. Identify the lowest offer per product.
    7. Stop after finding the target product.
    8. Output only valid JSON matching the ScrapeResponse schema — no markdown, no explanations.
   
    """

    await browser.start()
    agent = Agent(
        task=task_instruction,
        llm=llm,
        browser=browser,
        controller=controller,
        max_steps=5,
        save_conversation_path="scrape_log.json"
    )

    history = await agent.run()
    result = history.final_result()
    print(f"Scraping result: {result}")

    # --- Robust result parsing ---
    products = []
    raw_items = []
    # Try to parse all possible result types
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "products" in parsed:
                raw_items = parsed["products"]
            elif isinstance(parsed, list):
                raw_items = parsed
            else:
                raw_items = []
        except Exception:
            raw_items = []
    elif isinstance(result, dict):
        if "products" in result:
            raw_items = result["products"]
        elif "result" in result:
            raw_items = result["result"]
        elif isinstance(result, list):
            raw_items = result
        else:
            raw_items = []
    elif isinstance(result, list):
        raw_items = result
    else:
        raw_items = []

    for item in raw_items:
        try:
            title = item.get("title") or item.get("product_name") or "Unknown Product"
            price = item.get("price") or item.get("price_amount")
            seller = item.get("seller") or item.get("seller_name") or "Unknown Seller"
            url = item.get("url") or item.get("product_url") or ""
            if not all([title, price, url]):
                continue
            offer = Offer(
                seller_name=seller,
                price_amount=float(price),
                product_url=url
            )
            products.append(Product(
                product_name=title,
                lowest_offer=offer
            ))
        except Exception:
            continue

    products.sort(key=lambda p: p.lowest_offer.price_amount)
    final_products = products[:input_data.limit]

    return ScrapeResponse(
        products=final_products,
        search_term=input_data.product_name,
        product_count=len(final_products),
        scrape_timestamp=datetime.utcnow().isoformat()
    )

    # # --- Parse kết quả ---
    # raw_items = []
    # if isinstance(result, dict):
    #     if "results" in result:
    #         raw_items = result["results"]
    #     elif "result" in result:
    #         raw_items = result["result"]
    # elif isinstance(result, list):
    #     raw_items = result

    # products = []
    # for item in raw_items:
    #     try:
    #         title = item.get("title") or item.get("product_name") or "Unknown Product"
    #         price = item.get("price") or item.get("price_amount")
    #         seller = item.get("seller") or item.get("seller_name") or "Unknown Seller"
    #         url = item.get("url") or item.get("product_url") or ""
    #         if not all([title, price, url]):
    #             continue
    #         offer = Offer(
    #             seller_name=seller,
    #             price_amount=float(price),
    #             product_url=url
    #         )
    #         products.append(Product(
    #             product_name=title,
    #             lowest_offer=offer
    #         ))
    #     except Exception as e:
    #         print(f"Error parsing item: {e}")
    #         continue

    # products.sort(key=lambda p: p.lowest_offer.price_amount)
    # final_products = products[:input_data.limit]

    # return ScrapeResponse(
    #     products=final_products,
    #     search_term=input_data.product_name,
    #     product_count=len(final_products),
    #     scrape_timestamp=datetime.utcnow().isoformat()
    # )

# ===============================
# FastAPI Setup
# ===============================
app = FastAPI(title="Tech Price Scraper API")

@app.post("/lowest-offers", response_model=ScrapeResponse)
async def get_lowest_offers(input_data: LowestOfferInput):
    try:
        return await scrape_lowest_offers(input_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8084)