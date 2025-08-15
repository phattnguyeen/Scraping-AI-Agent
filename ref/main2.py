import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

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
    product_name: Optional[str] = None
    category: Optional[str] = None
    limit: int = 10  # số link sẽ mở từ trang kết quả Google (độ sâu search)


class Offer(BaseModel):
    seller_name: Optional[str]
    price_amount: Optional[float]
    price_currency: Optional[str]
    shipping_cost: Optional[float]
    total_price_amount: Optional[float]
    availability: Optional[str]
    product_url: Optional[str]
    scrape_timestamp: Optional[str]


class Product(BaseModel):
    product_name: Optional[str]
    model_or_sku: Optional[str]
    brand: Optional[str]
    category: Optional[str]
    specs: Optional[Dict[str, Any]]
    lowest_offer: Optional[Offer]
    notes: Optional[str]


class ScrapeResponse(BaseModel):
    source: str
    scrape_timestamp: str
    products: list
    summary: str



# ===============================
# Controller Actions
# ===============================
controller = Controller()

@controller.action("search_google")
async def search_google(page, query: str):
    """
    Mở Google và tìm kiếm với query đưa vào.
    """
    await page.goto("https://www.google.com/?hl=vi")
    # textbox mới của Google là <textarea name="q">
    q = "textarea[name='q'], input[name='q']"
    await page.fill(q, query)
    await page.keyboard.press("Enter")
    # chờ kết quả
    await page.wait_for_selector("h3")
    return {"status": "searched", "query": query}


@controller.action("extract_search_results")
async def extract_search_results(page, limit: int = 10):
    """
    Lấy link + title từ trang kết quả Google (bỏ quảng cáo / liên kết không hợp lệ).
    Trả về list dict {title, url, snippet?}
    """
    results = []

    # Các container kết quả phổ biến
    selectors = ["div.MjjYud", "div.g", "div#search .g"]
    seen = set()

    for sel in selectors:
        blocks = await page.query_selector_all(sel)
        for b in blocks:
            # bỏ quảng cáo
            ad_badge = await b.query_selector("span:has-text('Quảng cáo')")
            if ad_badge:
                continue

            a = await b.query_selector("a")
            if not a:
                continue
            href = await a.get_attribute("href")
            if not href or not href.startswith("http"):
                continue

            # tránh trùng
            if href in seen:
                continue
            seen.add(href)

            title_el = await b.query_selector("h3")
            title = (await title_el.inner_text()) if title_el else None
            if not title:
                # fallback
                title = (await b.inner_text())[:120]

            results.append({"title": title.strip(), "url": href.strip()})
            if len(results) >= limit:
                return results

    return results[:limit]


@controller.action("extract_search_results")
async def extract_search_results(page, limit: int = 10):
    results = []
    seen = set()
    selectors = ["div.MjjYud", "div.g", "div#search .g"]

    while len(results) < limit:
        for sel in selectors:
            blocks = await page.query_selector_all(sel)
            for b in blocks:
                ad_badge = await b.query_selector("span:has-text('Quảng cáo')")
                if ad_badge:
                    continue
                a = await b.query_selector("a")
                if not a:
                    continue
                href = await a.get_attribute("href")
                if not href or not href.startswith("http") or href in seen:
                    continue
                seen.add(href)
                title_el = await b.query_selector("h3")
                title = (await title_el.inner_text()) if title_el else None
                if not title:
                    title = (await b.inner_text())[:120]
                # Try to extract price directly from the block
                price_text = None
                price_el = await b.query_selector(":text-matches('([0-9\.,]+ ?(₫|đ|VND))', 'i')")
                if price_el:
                    price_text = await price_el.inner_text()
                from urllib.parse import urlparse
                domain = urlparse(href).netloc.replace("www.", "")
                results.append({
                    "title": title.strip(),
                    "url": href.strip(),
                    "price": price_text,
                    "seller": domain
                })
                if len(results) >= limit:
                    return results
        # Try to go to next page if not enough results
        next_btn = await page.query_selector('a#pnnext, a:has-text("Tiếp")')
        if next_btn:
            await next_btn.click()
            await page.wait_for_selector("h3")
        else:
            break  # No more pages
    return results[:limit]

# ===============================
# Parsing Helpers
# ===============================
def parse_price(price_str: Optional[str]) -> Optional[float]:
    if not price_str:
        return None
    # giữ số, đổi phẩy->chấm khi cần
    digits = "".join(ch for ch in price_str if ch.isdigit())
    if not digits:
        return None
    try:
        return float(digits)
    except:
        return None


def to_products(raw_items: List[Dict[str, Any]]) -> List[Product]:
    products: List[Product] = []
    for item in raw_items:
        price_val = parse_price(item.get("price"))
        offer = Offer(
            seller_name=item.get("seller"),
            price_amount=price_val,
            price_currency="VND" if price_val is not None else None,
            shipping_cost=None,
            total_price_amount=price_val,
            availability="In stock" if price_val else "Unknown",
            product_url=item.get("url"),
            scrape_timestamp=datetime.utcnow().isoformat()
        )
        product = Product(
            product_name=item.get("title") or item.get("product_name"),
            model_or_sku=None,
            brand=None,
            category=None,
            specs={},
            lowest_offer=offer,
            notes=None
        )
        products.append(product)
    return products

# def safe_parse_json(output: str):
#     """
#     Try to parse JSON safely from agent output.
#     """
#     if not output or not output.strip():
#         raise ValueError("Empty output from agent")

#     try:
#         # First try direct parsing
#         return json.loads(output)
#     except json.JSONDecodeError:
#         # Try to extract JSON from text
#         import re
#         match = re.search(r'(\[.*\]|\{.*\})', output, re.DOTALL)
#         if match:
#             try:
#                 return json.loads(match.group(1))
#             except json.JSONDecodeError:
#                 pass
#         raise ValueError("Output is not valid JSON")

def parse_products_from_result(raw_results):
    """Convert raw LLM output (dict/list) into Product objects."""
    products = []
    if isinstance(raw_results, list):
        for item in raw_results:
            try:
                name = item.get("name") or item.get("product_name")
                price = float(item.get("price") or item.get("price_amount"))
                seller = item.get("seller") or item.get("store")
                url = item.get("url") or item.get("link")

                products.append(
                    Product(
                        name=name,
                        lowest_offer=Offer(
                            price_amount=price,
                            seller=seller,
                            url=url
                        )
                    )
                )
            except Exception:
                continue
    return products

# ===============================
# Scraping Logic
# ===============================
async def scrape_lowest_offers(input_data: LowestOfferInput) -> Product:
    if not input_data.product_name and not input_data.category:
        raise HTTPException(status_code=400, detail="Must provide product_name or category")

    
    search_term = input_data.product_name if input_data.product_name else input_data.category
    google_query = f"{search_term} cheapest price "

    
    browser = Browser(config=BrowserConfig(headless=False, slow_mo=450))
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

    task_instruction = f"""
    Task: Search for the cheapest product '{search_term}' on Google.

    Steps:
    1. Using multiple Google Chrome and search for '{google_query}'.
    - Exclude 'site:' filters and avoid clicking on "Images" or other tabs.
    2. On the first page of results, focus on major Vietnamese tech retailers such as:
    FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, etc.
   
    3. For each result, extract product name, price (numeric only, no currency symbols), seller name (from domain or title), and product URL directly from the Google results if possible.
     - If the price is displayed, there's no need to visit the product page.
    4. Only visit the product page if the price is not available in the Google result.
    5. Avoid duplicate products (by URL).
    4. Prioritize products with the **lowest prices first**.
    5. Collect up to {input_data.limit} products.
    - If multiple products share the same price, include enough to reach the limit.
    6. For each product, gather the following information:
    - "product_name": the exact product title
    - "lowest_price": numeric only, no currency symbols
    - "seller_name": seller name from domain or title
    - "product_url": link to the product

    8. If no results are found, return an empty array.
    9. The output JSON must strictly match the schema above; do not include explanations or Markdown.
    10. Ensure all products come from **official Vietnamese tech retailers** whenever possible.
    """


    await browser.start()
    agent = Agent(
        task=task_instruction,
        llm=llm,
        browser=browser,
        controller=controller,
        max_steps=40,
        save_conversation_path="conversation.json"
    )

   # Example usage in your API endpoint
    history = await agent.run()
    history.save_to_file("agentResults.json")
    result = history.final_result()
    if not result:
        # Return an empty ScrapeResponse if nothing found
        return ScrapeResponse(
            source="google",
            scrape_timestamp=datetime.utcnow().isoformat(),
            products=[],
            summary="No products found."
        )

    # Parse the result into a list of products
    if isinstance(result, str):
        result_list = json.loads(result)
    elif isinstance(result, list):
        result_list = result
    elif isinstance(result, dict):
        # If dict, try to extract list from known keys or wrap as list
        if "products" in result:
            result_list = result["products"]
        else:
            result_list = [result]
    else:
        result_list = []

    # Convert to Product objects
    products = to_products(result_list)

    return ScrapeResponse(
        source="google",
        scrape_timestamp=datetime.utcnow().isoformat(),
        products=products,
        summary=f"Found {len(products)} products."
    )

    



# ===============================
# FastAPI Setup
# ===============================
app = FastAPI(title="Lowest Price Finder API")

@app.post("/lowest-offers", response_model=ScrapeResponse)
async def get_lowest_offers(input_data: LowestOfferInput):
    return await scrape_lowest_offers(input_data)


# ===============================
# Uvicorn entrypoint (localhost)
# ===============================
if __name__ == "__main__":
    import uvicorn
    # chạy: python main.py
    uvicorn.run(app, host="localhost", port=8082)
