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
import csv
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

    # task_instruction = f"""
    # You are a specialized scraper for Vietnamese retailers focusing ONLY on servers and laptops.

    # TASK: Search for "{searchQuery}" across major Vietnamese laptop and server retailers.

    # INSTRUCTIONS:
    # 1. Use 'search_google_laptop_server' with query: "{searchQuery}"
    # 2. Use 'extract_laptop_server_results' with limit={limit}
    # 3. Focus ONLY on these retailers (skip others): 
    #    FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, 
    #    An Phát PC, Phúc Anh, Trần Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store, Vinaphone
    # 4. Extract only Laptops and Servers.
    # 5. Extract fields:
    #    - ProductName
    #    - Brand
    #    - SKU
    #    - FinalPriceVND
    #    - Retailer
    #    - Url
    #    - StockStatus
    #    - Category (Laptop/Server)
    #    - ScrapedAt
    # 6. Ensure all prices are in VND.
    # 7. Deduplicate by brand, model, seller.
    # 8. Return only valid JSON with `products` array.
    # """
    # task_instruction = f"""
    # You are a specialized and highly efficient scraper for Vietnamese retailers, optimized to find the single cheapest available Laptop or Server.

    # TASK: Identify and return only the single CHEAPEST **in-stock** offering for "{searchQuery}" from a curated list of Vietnamese retailers.

    # INSTRUCTIONS:

    # 1.  **Analyze and Categorize:** First, determine if the `"{searchQuery}"` refers to a 'Laptop' or a 'Server'. This is crucial for selecting the correct list of retailers to search.

    # 2.  **Select Retailer List:** Based on the category determined in Step 1, use one of the following specialized lists:
    #     *   **If 'Laptop':**
    #         *   FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
    #     *   **If 'Server':**
    #         *   An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.

    # 3.  **Targeted Google Search:** Use the `search_google_laptop_server` function with queries designed to find the lowest price. Use a variety of terms, such as:
    #     *   "giá rẻ nhất {searchQuery}" (cheapest price)
    #     *   "khuyến mãi {searchQuery}" (promotion)
    #     *   "thanh lý {searchQuery}" (clearance)
    #     *   "{searchQuery} giá tốt nhất" (best price)

    # 4.  **Wider Data Extraction:** Use the `extract_laptop_server_results` function with an expanded `limit={limit}` to create a large pool of products for analysis.

    # 5.  **Extract Key Fields:**
    #     *   ProductName
    #     *   Brand
    #     *   SKU
    #     *   **FinalPriceVND** (Critical)
    #     *   Retailer
    #     *   Url
    #     *   **StockStatus** (Critical)
    #     *   Category ('Laptop' or 'Server')
    #     *   ScrapedAt

    # 6.  **Normalize Price Data:** Ensure `FinalPriceVND` is a normalized numerical value (integer or float). This price must be the final, payable amount after any instant discounts are applied.

    # 7.  **Deduplicate:** Remove duplicate entries to ensure there is only one result per unique product model from each distinct retailer.

    # 8.  **CRITICAL - Prioritize and Sort:**
    #     *   **A. Prioritize In-Stock:** First, filter your collected data to create a primary list containing ONLY products where the `StockStatus` is 'In Stock', 'Available', or similar positive confirmation.
    #     *   **B. Sort by Price:** Sort this primary **in-stock** list by `FinalPriceVND` in ascending order.
    #     *   **C. Fallback for Out-of-Stock:** If, and ONLY if, no in-stock products are found, create a secondary list of out-of-stock items and sort it by `FinalPriceVND` in ascending order.

    # 9.  **Final Output Logic:**
    #     *   **Return the cheapest available product:** From the sorted list (prioritizing the in-stock list), return ONLY the single product at the very top.
    #     *   **Handle No Results:** If the search yields zero products from any retailer after extraction, return an empty `products` array.

    # 10. **Format:** The final output MUST be a valid JSON object with a `products` array. This array will contain either the single cheapest product or be empty.```
    # """
    task_instruction = f"""
    You are a specialized and highly efficient scraper for Vietnamese retailers, optimized to find the single cheapest available product based on its SKU.

    **TASK:** Identify and return the CHEAPEST **in-stock** offerings for `{searchQuery}` using the `search_google_laptop_server` function  from a curated list of Vietnamese retailers, up to the specified `limit`.
            Given a specific {searchQuery} (which is an SKU), identify and return only the single CHEAPEST in-stock offering from a curated list of Vietnamese retailers.

    **INSTRUCTIONS:**

   1. CRITICAL - SKU Discovery and Categorization: Since the {searchQuery} is an SKU and its category is unknown, you must first perform a Discovery Search to determine the product type.
    * A. Perform a Broad Search: Conduct a general Google search or using `search_google_laptop_server` function for the {searchQuery} SKU.
    * B. Analyze Search Results: Look for keywords in the page titles and descriptions of the top results.
    * If you see terms like "Laptop," "Máy tính xách tay," "MacBook," etc. -> Categorize as 'Laptop'.
    * If you see terms like "Server," "Máy chủ," "Workstation," "Máy trạm," etc. -> Categorize as 'Server'.
    * C. Select Retailer List based on Discovery:
    * If categorized as 'Laptop', use this list: FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
    * If categorized as 'Server', use this list: An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.
    * D. FALLBACK - If Ambiguous: If the Discovery Search is inconclusive or returns mixed results, combine both lists into one master list and search all of them. This ensures you do not miss the product.

    2.  **Select Retailer List:** Based on the category determined in Step 1, use one of the following specialized lists:
        *   **If 'Laptop':**
            *   FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
        *   **If 'Server':**
            *   An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.

    3.  **Targeted Google Search:** Use the `search_google_laptop_server` function with queries designed to find the lowest prices. Use a variety of terms, such as:
        *   "giá rẻ nhất {searchQuery}" (cheapest price)
        *   "khuyến mãi {searchQuery}" (promotion)
        *   "thanh lý {searchQuery}" (clearance)
        *   "{searchQuery} giá tốt nhất" (best price)

    4.  **Wider Data Extraction:** Use the `extract_laptop_server_results` function with an expanded number of results to create a large pool of products for analysis.

    5.  **Extract Key Fields:**
        *   ProductName
        *   Brand
        *   SKU
        *   **FinalPriceVND** (Critical)
        *   Retailer
        *   Url
        *   **StockStatus** (Critical)
        *   Category ('Laptop' or 'Server')
        *   ScrapedAt

    6.  **Normalize Price Data:** Ensure `FinalPriceVND` is a normalized numerical value (integer or float). This price must be the final, payable amount after any instant discounts are applied.

    7.  **Deduplicate:** Remove duplicate entries to ensure there is only one result per unique product model from each distinct retailer.

    8.  **CRITICAL - Prioritize and Sort:**
        *   **A. Prioritize In-Stock:** First, filter your collected data to create a primary list containing ONLY products where the `StockStatus` is 'In Stock', 'Available', or a similar positive confirmation.
        *   **B. Sort by Price:** Sort this primary **in-stock** list by `FinalPriceVND` in ascending order.
        *   **C. Fallback for Out-of-Stock:** If, and ONLY if, no in-stock products are found, create a secondary list of out-of-stock items and sort it by `FinalPriceVND` in ascending order.

    9.  **Final Output Logic:**
        *   **Return the cheapest available products:** From the sorted list (prioritizing the in-stock list), return the top products up to the specified `{limit}`.
        *   **Handle No Results:** If the search yields zero products from any retailer after extraction, return an empty `products` array.

    10. **Format:** The final output MUST be a valid JSON object with a `products` array. This array will contain the cheapest product(s) up to the `{limit}` or be empty.
    """
    agent = Agent(
        browser=browser,
        llm=llm,
        task=task_instruction,
        controller=controller,
        use_vision= True
    )

    # agent_result = await agent.run()
    # result = agent_result.final_result()
    # print("RAW AGENT RESULT:")
    # print(f"Agent Result: {result}")
    
    #  # 2. Define and create the output directory
    # output_dir = "output"
    # os.makedirs(output_dir, exist_ok=True)
    # print(f"Output directory '{output_dir}' is ready.")

    # # 3. Save the full agent result to a JSON file
    # # This gives you a complete, machine-readable record of the output.
    # json_filepath = os.path.join(output_dir, "agent_output.json")
    # try:
    #     with open(json_filepath, 'w', encoding='utf-8') as json_file:
    #         # The 'result' variable (a dictionary) is dumped into the JSON file
    #         # ensure_ascii=False correctly handles Vietnamese characters.
    #         # indent=4 makes the file easy to read for humans.
    #         json.dump(result, json_file, ensure_ascii=False, indent=4)
    #     print(f"✅ Successfully saved full result to JSON: {json_filepath}")
    # except Exception as e:
    #     print(f"❌ Error saving to JSON: {e}")

    # # 4. Extract product data and save it to a CSV file
    # # This gives you a spreadsheet-friendly format.
    # csv_filepath = os.path.join(output_dir, "products_output.csv")
    # try:
    #     # Check if the 'products' key exists and contains a list of products
    #     if 'products' in result and isinstance(result['products'], list) and result['products']:
    #         products_data = result['products']
            
    #         # Use the keys from the first product dictionary as the CSV headers
    #         headers = products_data[0].keys()

    #         with open(csv_filepath, 'w', newline='', encoding='utf-8') as csv_file:
    #             # DictWriter is perfect for writing a list of dictionaries to CSV
    #             writer = csv.DictWriter(csv_file, fieldnames=headers)
    #             writer.writeheader()  # Writes the column titles
    #             writer.writerows(products_data) # Writes all the product data
    #         print(f"✅ Successfully saved product data to CSV: {csv_filepath}")
    #     else:
    #         print("ℹ️ No product data found in the result to write to CSV.")
    # except Exception as e:
    #     print(f"❌ Error saving to CSV: {e}")

    # except Exception as e:
    #     print(f"An critical error occurred during the agent run: {e}")

    # finally:
    #     # 5. This 'finally' block ensures the browser is always closed,
    #     #    preventing leftover processes, even if the script above fails.
    #     print("-" * 30)
    #     print("Stopping browser...")
    #     await browser.stop()
    #     print("Browser stopped. Process finished.")

    try:
        # 1. Run the agent to get the result
        print("Running the agent...")
        agent_result = await agent.run()
        raw_result = agent_result.final_result() # Get the raw output

        print("\nRAW AGENT RESULT:")
        print(f"Agent Result: {raw_result}")
        print("-" * 30)

        # --- FIX STARTS HERE ---
        # The agent's result might be a string. We must parse it into a Python object (dictionary).
        data = {}
        if isinstance(raw_result, str):
            try:
                print("Result is a string. Parsing from JSON...")
                data = json.loads(raw_result)
            except json.JSONDecodeError:
                print(f"Critical Error: Agent result is not a valid JSON string. Cannot process.")
                # Exit the 'try' block gracefully, browser will still stop in 'finally'
                raise
        else:
            # If it's already a dictionary, we can use it directly
            print("Result is already a dictionary/object.")
            data = raw_result
        # --- FIX ENDS HERE ---


        # 2. Define and create the output directory
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        print(f"Output directory '{output_dir}' is ready.")


        # 3. Save the parsed data to a JSON file
        # (We use the 'data' variable from now on, not 'raw_result')
        json_filepath = os.path.join(output_dir, "agent_output.json")
        try:
            with open(json_filepath, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
            print(f"Successfully saved full result to JSON: {json_filepath}")
        except Exception as e:
            print(f"Error saving to JSON: {e}")
        json_filepath_json = os.path.join(output_dir, "agent_output_json.json")
        try:
    # First, check if the 'products' key exists and contains a list
            if 'products' in data and isinstance(data['products'], list):
                
                # Extract the list of products from the main data object
                products_to_save = data['products']
                
                # Now, save ONLY the extracted list to the file
                with open(json_filepath_json, 'w', encoding='utf-8') as json_file:
                    json.dump(products_to_save, json_file, ensure_ascii=False, indent=4)
                    
                print(f"Successfully saved EXTRACTED product list to JSON: {json_filepath_json}")
                
            else:
                # This handles cases where the agent result had no 'products' key
                print("ℹNo 'products' key found in the result. JSON file will not be created.")

        except Exception as e:
            print(f"Error saving extracted data to JSON: {e}")
              


        # 4. Extract product data and save it to a CSV file
        csv_filepath = os.path.join(output_dir, "products_output.csv")
        try:
            # Check for the 'products' key in our newly parsed 'data' dictionary
            if 'products' in data and isinstance(data['products'], list) and data['products']:
                products_data = data['products']
                
                # The header keys are taken from the first product dictionary in the list
                headers = products_data[0].keys()

                with open(csv_filepath, 'w', newline='', encoding='utf-8') as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(products_data)
                print(f"✅ Successfully saved product data to CSV: {csv_filepath}")
            else:
                print("ℹNo product data found in the parsed result to write to CSV.")
        except Exception as e:
            print(f"Error saving to CSV: {e}")

    except Exception as e:
        # This will now also catch the json.JSONDecodeError if parsing fails
        print(f"\nAn error occurred during the process: {e}")

    finally:
        # 5. This block ensures the browser is always closed safely
        print("-" * 30)
        print("Stopping browser...")
        await browser.stop()
        print("Browser stopped. Process finished.")

    


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
    
if __name__ == "__main__":
    import asyncio
    search_query = "30GS00G7VA"
    limit = 2
    loop = asyncio.get_event_loop()
    products = loop.run_until_complete(scrape_product_data(search_query, limit))




