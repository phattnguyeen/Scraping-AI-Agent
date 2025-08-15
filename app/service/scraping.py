import os
import sys
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.schemas.products import Products, ProductsList, ProductInput
import asyncio
from app.db.create import get_db
# from app.service.scraping import ScrapeResponse
from browser_use import Agent, BrowserConfig, Browser, Controller
from urllib.parse import urlparse

from browser_use.llm import ChatOpenAI

# Load .env
load_dotenv()

# Fix import paths if running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

import json

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
        model="gpt-4.1-mini",
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
        return results[:limit]

    # Use prompt if provided, otherwise product name
    search_query = input_data.product_name if input_data.prompt else input_data.prompt
    limit = input_data.limit

    task_instruction = f"""
    1. Use 'search_google' with query: "{search_query} giá rẻ nhất"
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
    """

    agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller)
    agent_result = await agent.run()
    # if hasattr(agent_result, "final_result"):
    #     result_json = agent_result.final_result
    # elif hasattr(agent_result, "all_results") and agent_result.all_results:
    #     # Try to get the last result's 'result' field
    #     last = agent_result.all_results[-1]
    #     result_json = last.get("result", "{}")
    # else:
    #     result_json = "{}"
    # try:
    #     products_data = ProductsList.model_validate_json(result_json)
    #     print(f"Scraped {len(products_data.products)} products successfully.")
    # except Exception as e:
    #     print(f"Error parsing result JSON: {e}")
    #     products_data = ProductsList(products=[], limit=limit, total=0)
    # finally:
    #     await browser.stop()
    # return products_data
    result_json = extract_final_json(agent_result)
    try:
        products_data = ProductsList.model_validate_json(result_json)
        print(f"Scraped {len(products_data.products)} products successfully.")
    except Exception as e:
        print(f"Error parsing result JSON: {e}")
        products_data = ProductsList(products=[], limit=limit, total=0)
    finally:
        await browser.stop()
    return products_data
    
if __name__ == "__main__":
    # Example run
    db = next(get_db())
    input_data = ProductInput(product_name="iphone 15", limit=5, prompt="iPhone 15 Pro Max, 256GB, Silver")
    results = asyncio.run(scraping_products(db, input_data))

    print("\nFinal scraped products:")
    for p in results.products:
        print(p)

# async def scraping_products(
#     db: Session,
#     input_data: ProductInput
# ) -> ProductsList:
#     """
#     Scrape product data using the provided prompt or product name
#     and return a validated ProductsList.
#     """
#     browser_config = BrowserConfig(
#         headless=False,
#         slow_mo=500,
#         disable_security=False,
#         user_agent=(
#             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#             "AppleWebKit/537.36 (KHTML, like Gecko) "
#             "Chrome/120.0.0.0 Safari/537.36"
#         )
#     )
#     browser = Browser(config=browser_config)
#     await browser.start()

#     llm = ChatOpenAI(
#         model="gpt-5",  # upgraded from gpt-4.1-mini for better reasoning
#         temperature=0,
#         api_key=os.getenv("OPENAI_API_KEY")
#     )
#     controller = Controller()

#     @controller.action("search_google")
#     async def search_google(page, query: str):
#         await page.goto("https://www.google.com/?hl=vi", timeout=30000)
#         await page.wait_for_selector("textarea[name='q'], input[name='q']", timeout=10000)
#         await page.fill("textarea[name='q'], input[name='q']", query)
#         await page.keyboard.press("Enter")
#         await page.wait_for_selector("div[data-sokoban-container]", timeout=15000)
#         return {"status": "success", "query": query}

#     @controller.action("extract_tech_results")
#     async def extract_tech_results(page, limit: int = 10):
#         results = []
#         seen_urls = set()
#         retailer_map = {
#             "fptshop.com.vn": "FPT Shop",
#             "thegioididong.com": "Thế Giới Di Động",
#             "cellphones.com.vn": "CellphoneS",
#             "hoanghamobile.com": "Hoàng Hà Mobile",
#             "phongvu.vn": "Phong Vũ"
#         }
#         containers = await page.query_selector_all("div[data-sokoban-container], div.sh-dgr__content")
#         for container in containers:
#             if len(results) >= limit:
#                 break
#             if await container.query_selector(":text('Quảng cáo'), :text('Sponsored')"):
#                 continue
#             link = await container.query_selector("a")
#             if not link:
#                 continue
#             url = await link.get_attribute("href")
#             if not url or not url.startswith("http") or url in seen_urls:
#                 continue
#             seen_urls.add(url)
#             domain = urlparse(url).netloc.replace("www.", "")
#             seller = retailer_map.get(domain, domain.split('.')[0].title())
#             title_el = await container.query_selector("h3, .tAxDx, .sh-np__product-title")
#             title = (await title_el.inner_text()).strip() if title_el else ""
#             price_selectors = [
#                 ".T4OwTb, .e10twf, .sh-np__price, .tAxDx, .a8Pemb, .price",
#                 ":text-matches('([0-9,.]+\\s*[₫đVND]?)', 'i')"
#             ]
#             price_text = ""
#             for selector in price_selectors:
#                 price_el = await container.query_selector(selector)
#                 if price_el:
#                     price_text = (await price_el.inner_text()).strip()
#                     if price_text:
#                         break
#             price_value = None
#             if price_text:
#                 clean_price = ''.join(c for c in price_text if c.isdigit())
#                 if clean_price:
#                     try:
#                         price_value = float(clean_price)
#                     except ValueError:
#                         price_value = None
#             if title and price_value:
#                 results.append({
#                     "title": title,
#                     "url": url,
#                     "price": price_value,
#                     "seller": seller
#                 })
#         return results[:limit]

#     # Proper fallback for search query

#     # task_instruction = f"""
#     #     1. Use 'search_google' with query: "{search_query} giá rẻ nhất"
#     #     2. Find the best price for {search_query} across major Vietnamese tech retailers such as:
#     #     FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, and more.
#     #     For each retailer:
#     #         1. Navigate to their website and search for the exact product
#     #         2. Record the current price, original price if on sale, and any available discounts
#     #         3. Calculate the final price after discounts and promotions
#     #         4. Note shipping costs and estimated delivery time
#     #         5. Check if the product is in stock
#     #         6. Record the product's name, model, and seller information, url website and time when the data was scraped
#     #     3. Use 'extract_tech_results' with limit={limit}
#     #     4. Return the extracted results as your final answer.
#     #     5. Deduplicate results by product name or SKU.
#     #     6. Identify the lowest offer per product.
#     #     7. Stop after finding the target product.
#     #     8. Output only valid JSON matching the ProductList schema — no markdown, no explanations.
#     # """
#     search_query = input_data.prompt or input_data.product_name
#     limit = input_data.limit
#     # task_instruction = f"""
#     #     1. Use 'search_google' with query: "{search_query} giá rẻ nhất".
#     #     2. Leverage top Vietnamese price-comparison websites to quickly identify the best (cheapest) sellers for {search_query}, for example:
#     #     - Websosanh.vn
#     #     - 2momart.vn
#     #     - Sosanhgia.com
#     #     (These are among the most reliable and accurate price-comparison websites in Vietnam as of mid-July 2025.) :contentReference[oaicite:0]
#     #     3. Then, for each major tech retailer (FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, and others found via comparisons):
#     #         a. Go to their site, search for the exact product.
#     #         b. Record current price, original price (if on sale), and any discounts.
#     #         c. Calculate the final price after discounts/promotions.
#     #         d. Note shipping cost and estimated delivery time.
#     #         e. Check stock availability.
#     #         f. Capture product name, model, seller info, website URL, and scraping timestamp.
#     #     4. Return results as JSON conforming to the ProductList schema—no markdown or explanations.
#     #     5. Deduplicate entries by product name or SKU.
#     #     6. Identify the lowest-priced offer per product.
#     #     7. Stop once the target product’s best (cheapest) offer is found.
#     # """
#     task_instruction = f"""
#         1. Use 'search_google' with query: "{search_query} giá rẻ nhất"
#         2. Find the best price for {search_query} across major Vietnamese tech retailers such as:
#         FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, and more.
#         For each retailer:
#             1. Navigate to their website and search for the exact product
#             2. Record the current price, original price if on sale, and any available discounts
#             3. Calculate the final price after discounts and promotions
#             4. Note shipping costs and estimated delivery time
#             5. Check if the product is in stock
#             6. Record the product's name, model, and seller information, url website and time when the data was scraped
#         3. Use 'extract_tech_results' with limit={limit}
#         4. Return the extracted results as your final answer.
#         5. Deduplicate results by product name or SKU.
#         6. Identify the lowest offer per product.
#         7. Stop after finding the target product.
#         8. Output only valid JSON matching the ProductList schema — no markdown, no explanations.
#     """


#     agent = Agent(browser=browser, llm=llm, task=task_instruction, controller=controller)
#     agent_result = await agent.run()

#     # --- Our safe JSON extraction ---
#     raw_data = extract_final_json(agent_result)
#     try:
#     # Try parsing JSON from LLM
#         parsed = json.loads(raw_data)

#         # Get products from parsed data
#         if isinstance(parsed, dict) and "products" in parsed:
#             products_list = parsed["products"]
#         elif isinstance(parsed, list):
#             products_list = parsed
#         else:
#             products_list = []
#     except Exception:
#         products_list = []

#     validated_products = []
#     for p in products_list:
#         try:
#             validated_products.append(Products.model_validate(p).model_dump())
#         except Exception as e:
#             print(f"Skipping invalid product: {e}")

#     final_data = {
#         "products": validated_products,
#         "limit": limit,
#         "total": len(validated_products)
#     }
#     print(f"Scraped {len(final_data['products'])} products successfully.")
#     print(f"Total products found: {final_data['total']}")
#     print (final_data)


#     try:
#         products_data = ProductsList.model_validate(final_data)
#         print(f"Scraped {len(products_data.products)} products successfully.")
#     except Exception as e:
#         print(f"Error validating data: {e}")
#         products_data = ProductsList(products=[], limit=limit, total=0)

#     await browser.stop()
#     return products_data
# if __name__ == "__main__":
#     # Example run
#     db = next(get_db())
#     input_data = ProductInput(product_name="iphone 15", limit=5, prompt="iPhone 15 Pro Max, 256GB, Silver")
#     results = asyncio.run(scraping_products(db, input_data))

#     print("\nFinal scraped products:")
#     for p in results.products:
#         print(p)

    