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
from app.crud.products import get_all_skus
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import time

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

RETAILER_CONFIG = {
    "Google": {"search_url": "https://www.google.com/search?q={query}"},
    # "Hoàng Hà Mobile": {"search_url": "https://hoanghamobile.com/tim-kiem/{query}"},
    # "GearVN": {"search_url": "https://www.gearvn.com/search?type=product&q={query}"},
    # "FPT Shop": {"search_url": "https://fptshop.com.vn/tim-kiem/{query}"},
    # "CellphoneS": {"search_url": "https://cellphones.com.vn/tim-kiem?q={query}"},
    # "Thế Giới Di Động": {"search_url": "https://www.thegioididong.com/tim-kiem?key={query}"},
    # "Phong Vũ": {"search_url": "https://phongvu.vn/search?q={query}"},
    # "An Phát PC": {"search_url": "https://www.anphatpc.com.vn/tim?scat_id=&q={query}"},
    # "Phúc Anh": {"search_url": "https://www.phucanh.vn/tim?q={query}"}
    # Add all other retailers from your laptop and server lists here...
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
# @controller.action("search_google_laptop_server")
# async def search_google_laptop_server(page, query: str):
#         """Search Google specifically for laptop and server products."""
#         search_query = f"{query} laptop server máy tính xách tay máy chủ giá rẻ"
#         await page.goto("https://www.google.com/?hl=vi", timeout=30000)
#         await page.wait_for_selector("textarea[name='q'], input[name='q']", timeout=10000)
#         await page.fill("textarea[name='q'], input[name='q']", search_query)
#         await page.keyboard.press("Enter")
#         await page.wait_for_selector("div[data-sokoban-container], div.sh-dgr__content", timeout=15000)
#         return {"status": "success", "query": search_query}

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

import logging
from typing import Dict, List
from playwright.async_api import Page, TimeoutError

logger = logging.getLogger(__name__)

@controller.action("scan_google_for_products")
async def scan_google_for_products(page, query: str) -> Dict:
    """
    Scans the Google SERP for a given query to find all product candidates.
    This includes organic results, Shopping results, and Google Ads.
    
    Args:
        page: The Playwright page object.
        query (str): The product search query.

    Returns:
        A dictionary with a list of candidate products.
    """
    logger.info(f"Scanning Google for all product candidates for: '{query}'")
    candidates = []
    seen_urls = set()
    
    try:
        # Use Vietnamese Google for local results, can be changed to google.com
        search_query_encoded = query.replace(' ', '+')
        await page.goto(f"https://www.google.com.vn/search?q={search_query_encoded}&hl=en", timeout=30000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        # A robust composite selector for all types of product/ad containers on Google
        # This is the key to finding organic, shopping, and ad results together.
        containers = await page.query_selector_all(
            "div.u-L-Y, div.sh-dgr__gr-auto, .com-a, .pla-unit-container, div[data-text-ad]"
        )
        
        logger.info(f"Found {len(containers)} potential containers on Google SERP.")

        for container in containers:
            link_element = await container.query_selector("a[href]")
            if not link_element:
                continue

            url = await link_element.get_attribute("href")
            if not url or not url.startswith("http") or url in seen_urls:
                continue

            # Skip internal Google links
            if "google.com/" in url:
                continue
            
            seen_urls.add(url)

            # Extract title using a composite selector for different result types
            title_el = await container.query_selector("h3, .sh-np__product-title, .pymv4e, .b1AbGallery-item-title")
            title = await title_el.inner_text() if title_el else "Unknown Product"

            # Extract price text
            price_el = await container.query_selector(".a8Pemb, .T4OwTb")
            price_text = await price_el.inner_text() if price_el else "0"

            candidates.append({
                "productName": title.strip(),
                "priceText": price_text,
                "url": url
            })

        logger.info(f"Successfully extracted {len(candidates)} unique product candidates from Google.")
        return {"status": "success", "candidates": candidates}

    except TimeoutError:
        logger.error("Timeout while trying to scan Google. The page may be blocked or slow.")
        return {"status": "failure", "error": "Timeout on Google SERP"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during Google scan: {e}")
        return {"status": "failure", "error": str(e)}

RETAILER_DIRECT_SEARCH_CONFIG = {
    "FPT Shop": "https://fptshop.com.vn/tim-kiem/{query}",
    "Thế Giới Di Động": "https://www.thegioididong.com/tim-kiem?key={query}",
    "CellphoneS": "https://cellphones.com.vn/tim-kiem?q={query}",
    "Phong Vũ": "https://phongvu.vn/search?q={query}",
    "An Phát PC": "https://www.anphatpc.com.vn/tim-kiem?q={query}",
    "Phúc Anh": "https://www.phucanh.vn/tim-kiem?q={query}",
    # Add ALL other target retailers from your master list here...
}

@controller.action("find_product_urls_directly_from_retailers")
async def find_product_urls_directly_from_retailers(page, query: str, retailer_list: List[str]) -> Dict:
    """
    Bypasses Google and finds product URLs by searching directly on each retailer's website.
    This is the robust fallback plan.

    Args:
        page: The Playwright page object.
        query (str): The product search query.
        retailer_list (List[str]): The names of retailers to search (e.g., ["FPT Shop", "Phong Vũ"]).

    Returns:
        A dictionary with a list of product URLs found.
    """
    logger.info(f"Executing FALLBACK PLAN: Searching directly on {len(retailer_list)} retailer sites.")
    found_urls = []
    
    for retailer_name in retailer_list:
        if retailer_name not in RETAILER_DIRECT_SEARCH_CONFIG:
            logger.warning(f"No direct search config for '{retailer_name}'. Skipping.")
            continue
        
        try:
            search_url = RETAILER_DIRECT_SEARCH_CONFIG[retailer_name].format(query=query.replace(' ', '+'))
            logger.info(f"--> Searching directly on {retailer_name} via: {search_url}")
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")

            # --- CRITICAL: CUSTOM PARSING LOGIC REQUIRED ---
            # Every website is different. You MUST develop a robust parser for each one.
            # This example is a GENERIC placeholder that looks for links containing '/p/'.
            # You should replace this with selectors specific to each retailer's product links.
            # --------------------------------------------------------------------------
            urls_on_page = await page.evaluate("""
                () => {
                    const links = new Set();
                    // Generic selectors for product links. YOU MUST CUSTOMIZE THIS.
                    document.querySelectorAll('a[href*="/p/"], a[href*="/products/"], a.product-link-selector').forEach(a => {
                        links.add(a.href);
                    });
                    return Array.from(links);
                }
            """)
            
            logger.info(f"Found {len(urls_on_page)} URLs on {retailer_name}.")
            found_urls.extend(urls_on_page)

        except TimeoutError:
            logger.error(f"Timeout while searching directly on {retailer_name}. Site may be down or slow.")
        except Exception as e:
            logger.error(f"Error searching on {retailer_name}: {e}")
        # Continue to the next retailer even if one fails
        continue

    return {"status": "success", "urls": found_urls}

async def scrape_product_data(searchQuery: list, limit: int) -> list[ProductCreate]:
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


        # Define the task instruction for the agent
   
    

# #     task_instruction = f"""
# #     You are a specialized and highly efficient scraper for Vietnamese retailers, optimized to find the single cheapest available product based on its SKU.

# #     **TASK:** Identify and return the CHEAPEST **in-stock** offerings for `{searchQuery}` using the search on Google or google.com  from a curated list of Vietnamese retailers, up to the specified `limit`.
# #             Given a specific {searchQuery} (which is an SKU), identify and return only the single CHEAPEST in-stock offering from a curated list of Vietnamese retailers.

# #     **INSTRUCTIONS:**

# #    1. CRITICAL - SKU Discovery and Categorization: Since the {searchQuery} is an SKU and its category is unknown, you must first perform a Discovery Search to determine the product type.
# #     * A. Perform a Broad Search: Conduct a general Google search or using search on Google or google.com for the {searchQuery} SKU.
# #     * B. Analyze Search Results: Look for keywords in the page titles and descriptions of the top results.
# #     * If you see terms like "Laptop," "Máy tính xách tay," "MacBook," etc. -> Categorize as 'Laptop'.
# #     * If you see terms like "Server," "Máy chủ," "Workstation," "Máy trạm," etc. -> Categorize as 'Server'.
# #     * C. Select Retailer List based on Discovery:
# #     * If categorized as 'Laptop', use this list: FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
# #     * If categorized as 'Server', use this list: An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.
# #     * D. FALLBACK - If Ambiguous: If the Discovery Search is inconclusive or returns mixed results, combine both lists into one master list and search all of them. This ensures you do not miss the product.

# #     2.  **Select Retailer List:** Based on the category determined in Step 1, use one of the following specialized lists:
# #         *   **If 'Laptop':**
# #             *   FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
# #         *   **If 'Server':**
# #             *   An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.

# #     3.  **Targeted Google Search:** Use the search on Google or google.com with queries designed to find the lowest prices. Use a variety of terms, such as:
# #         *   "giá rẻ nhất {searchQuery}" (cheapest price)
# #         *   "khuyến mãi {searchQuery}" (promotion)
# #         *   "thanh lý {searchQuery}" (clearance)
# #         *   "{searchQuery} giá tốt nhất" (best price)

# #     4.  **Wider Data Extraction:** Use the `extract_laptop_server_results_DIRECT` function with an expanded number of results to create a large pool of products for analysis.

# #     5.  **Extract Key Fields:**
# #         *   ProductName
# #         *   Brand
# #         *   SKU
# #         *   **FinalPriceVND** (Critical)
# #         *   Retailer
# #         *   Url
# #         *   **StockStatus** (Critical)
# #         *   Category ('Laptop' or 'Server')
# #         *   ScrapedAt

# #     6.  **Normalize Price Data:** Ensure `FinalPriceVND` is a normalized numerical value (integer or float). This price must be the final, payable amount after any instant discounts are applied.

# #     7.  **Deduplicate:** Remove duplicate entries to ensure there is only one result per unique product model from each distinct retailer.

# #     8.  **CRITICAL - Prioritize and Sort:**
# #         *   **A. Prioritize In-Stock:** First, filter your collected data to create a primary list containing ONLY products where the `StockStatus` is 'In Stock', 'Available', or a similar positive confirmation.
# #         *   **B. Sort by Price:** Sort this primary **in-stock** list by `FinalPriceVND` in ascending order.
# #         *   **C. Fallback for Out-of-Stock:** If, and ONLY if, no in-stock products are found, create a secondary list of out-of-stock items and sort it by `FinalPriceVND` in ascending order.

# #     9.  **Final Output Logic:**
# #         *   **Return the cheapest available products:** From the sorted list (prioritizing the in-stock list), return the top products up to the specified `{limit}`.
# #         *   **Handle No Results:** If the search yields zero products from any retailer after extraction, return an empty `products` array.

# #     10. **Format:** The final output MUST be a valid JSON object with a `products` array. This array will contain the cheapest product(s) up to the `{limit}` or be empty.
# #     """
#     # task_instruction = f"""
#     #     You are a specialized and highly efficient scraper for Vietnamese retailers, optimized to find the single cheapest available product.

#     #     **TASK:** Identify and return the CHEAPEST **in-stock** offering for `{searchQuery}` from a curated list of Vietnamese retailers, up to the specified `limit`.

#     #     **CORE STRATEGY: ADAPTIVE SEARCH**
#     #     Your primary goal is to get product data. Google is a tool for discovery, not a mandatory gate. You must adapt if it fails. Follow this logic:

#     #     **1. Primary Path - Google Discovery (Attempt First):**
#     #     *   A. **Attempt Discovery:** Perform a quick Google search for the `{searchQuery}` to determine if it's a 'Laptop' or 'Server'.
#     #     *   B. **CRITICAL - HANDLE FAILURES:** If you are blocked by a **reCAPTCHA**, the search is inconclusive, or Google is otherwise unavailable, **IMMEDIATELY ABANDON THE PRIMARY PATH** and proceed directly to the **Fallback Path (Step 2)**. Do not waste time retrying Google.
#     #     *   C. **If Successful:**
#     #         *   **If 'Laptop': Search the following retailers:**
#     #         *       FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
#     #         *   **If 'Server': Search the following retailers:**
#     #         *       An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA
#     #         *   Proceed to Step 3.

#     #     **2. Fallback Path - Direct Wide Extraction (Use if Step 1 Fails or is Ambiguous):**
#     #     *   This is your most reliable method and ensures the task completes.
#     #     *   A. **Combine Lists:** Use the **master combined list** of all retailers (both Laptop and Server).
#     #     *   B. **Execute Extraction:** 
#     #         - Directly extract product information for `{searchQuery}` from the combined retailer list.
#     #         - Collect detailed attributes for each candidate product, including:
#     #             - `productName`
#     #             - `sku`
#     #             - `brand`
#     #             - `finalPriceVND`
#     #             - `oldPriceVND` (if available)
#     #             - `stockStatus` (e.g., "in stock" / "out of stock")
#     #             - `retailer`
#     #             - `url`
#     #         - Normalize all numeric prices to integers in VND.
#     #         - If multiple results from the same retailer exist, keep the cheapest one.
#     #     *   C. Proceed to Step 3.

#     #     **Retailer Lists:**
#     #     *   **Laptop List:** FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.
#     #     *   **Server List:** An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA.

#     #     ---
#     #     **SHARED INSTRUCTIONS (Follow After Step 1 or 2 is Complete)**
#     #     ---

#     #     **3. Extract Key Fields:** From the data you collected, extract the following:
#     #     *   ProductName
#     #     *   Brand
#     #     *   SKU
#     #     *   **FinalPriceVND** (Critical: the final, payable price)
#     #     *   Retailer
#     #     *   Url
#     #     *   **StockStatus** (Critical)
#     #     *   Category ('Laptop', 'Server', or 'Fallback/Ambiguous')
#     #     *   ScrapedAt

#     #     **4. Normalize and Deduplicate:**
#     #     *   Ensure `FinalPriceVND` is a clean numerical value.
#     #     *   Remove duplicate entries (one result per unique product/SKU from each retailer).

#     #     **5. CRITICAL - Prioritize and Sort:**
#     #     *   **A. Prioritize In-Stock:** First, filter your data to create a list of ONLY products with a positive `StockStatus` (e.g., 'In Stock', 'Available').
#     #     *   **B. Sort by Price:** Sort this **in-stock** list by `FinalPriceVND` in ascending order.
#     #     *   **C. Fallback for Out-of-Stock:** If, AND ONLY IF, no in-stock products are found, use the out-of-stock items and sort them by price as a fallback.

#     #     **6. Final Output Logic:**
#     #     *   From your sorted list (prioritizing in-stock), return the top products up to the specified `{limit}`.
#     #     *   If no products are found at all, return an empty `products` array.
#     #     *   The final output MUST be a valid JSON object with a `products` array.
#     # """
#     task_instruction = f"""
#         You are a meticulous and highly accurate scraping expert for Vietnamese retailers. Your mission is to find the single CHEAPEST **in-stock** offering for `{searchQuery}`, extract its detailed information, and return the top results up to the specified `{limit}`.

#         **CORE MISSION: VISION-FIRST PRICE HUNTING WORKFLOW**
#         You MUST follow this two-phase process: Phase 1 (Google Reconnaissance) and Phase 2 (Retailer Verification).

#         ---
#         **PHASE 1: GOOGLE VISION RECONNAISSANCE**
#         ---
#         Your first goal is to use Google to build a prioritized list of the cheapest candidate products.

#         *   **A. Execute Vision Tool:** You MUST execute the `vision_google_search_and_extract` tool with the search query `{searchQuery}`. This tool will "look" at the entire Google results page to find products.
#         *   **B. Collect Preliminary Results:** The tool will return a list of products, each containing `productName`, `priceText`, `url`, and `retailer`.
#         *   **C. Process and Sort:**
#             1.  **Clean Prices:** Normalize the `priceText` from each product into a numerical integer value.
#             2.  **SORT BY PRICE:** Sort this list of products by the cleaned price in **ascending order** (cheapest first).
#         *   **D. CRITICAL - HANDLE FAILURES:** If the `vision_google_search_and_extract` tool fails (e.g., is blocked by a reCAPTCHA), you must **IMMEDIATELY** switch to the **FALLBACK PLAN** below.

#         ---
#         **PHASE 2: RETAILER VERIFICATION & DETAILED EXTRACTION**
#         ---
#         You now have a sorted list of the most promising candidates. Your goal is to visit each page to get accurate, detailed information.

#         *   **A. Iterate and Extract:** Take the URLs from the sorted list you created in Phase 1 (starting with the cheapest). For **each URL**, you MUST execute the `extract_product_details_from_url` tool.
#         *   **B. Collect Detailed Information:** For each product, you MUST extract the following specific fields from the retailer's page:
#             *   `productName` (the full and accurate name)
#             *   `sku` (the product's SKU or model code)
#             *   `finalPriceVND` (CRITICAL: the final, payable price)
#             *   `oldPriceVND` (the original/list price before discounts, if available)
#             *   `stockStatus` (CRITICAL: must be accurately determined, e.g., "In Stock" / "Out of Stock")
#             *   `retailer`
#             *   `url`
#         *   **C. Collect Until Limit Reached:** Continue this process until you have gathered detailed information for up to `{limit}` products.

#         ---
#         **FINAL ANALYSIS AND OUTPUT**
#         ---
#         Once you have collected enough detailed data, perform the final analysis.

#         *   **1. Prioritize In-Stock:** Filter your final list to keep ONLY the products where `stockStatus` is 'In Stock'.
#         *   **2. Final Sort:** Sort this 'In Stock' list one last time by `finalPriceVND` in ascending order.
#         *   **3. Format Output:** Return the top products from the final sorted list, up to the `{limit}`. If no in-stock products are found, return an empty `products` array.
#         *   **4. CRITICAL - Prioritize and Sort:**
#             *   **A. Prioritize In-Stock:** First, filter your data to create a list of ONLY products with a positive `StockStatus` (e.g., 'In Stock', 'Available').
#             *   **B. Sort by Price:** Sort this **in-stock** list by `FinalPriceVND` in ascending order.
#             *   **C. Fallback for Out-of-Stock:** If, AND ONLY IF, no in-stock products are found, use the out-of-stock items and sort them by price as a fallback.
#         **5. Final Output Logic:**
#         *   From your sorted list (prioritizing in-stock), return the top products up to the specified `{limit}`.
#         *   If no products are found at all, return an empty `products` array.
#         *   The final output MUST be a valid JSON object with a `products` array.

#         ---
#         **FALLBACK PLAN (If Phase 1 Fails)**
#         ---
#         If Google is blocked, ignore Phase 1 and 2 and proceed directly with this plan:
#         *   **A. Select Retailer List:** Use the master combined list of both Laptop and Server retailers.
#         *   **B. Execute `find_product_urls`:** Run this tool to get a list of URLs directly from the retailers.
#         *   **C. Continue with Phase 2:** Use the list of URLs you just gathered and proceed with the detailed extraction process as described in Phase 2 above.
#     """
    # task_instruction = f"""
    #     You are a master scraping agent, expert in finding the lowest prices at Vietnamese retailers. Your mission is to find the single CHEAPEST **in-stock** offering for `{searchQuery}`, including offers from Google Ads.

    #     **CORE MISSION: TWO-PHASE PRICE HUNTING (Reconnaissance & Verification)**
    #     You MUST follow this strategic two-phase process. Do not attempt to complete the task in a single step.

    #     ---
    #     **PHASE 1: GOOGLE RECONNAISSANCE (FIND CANDIDATES)**
    #     ---
    #     Your first goal is to build a comprehensive list of all potential product candidates by scanning the entire Google search results page.

    #     *   **A. Execute Google Scan:** You MUST execute the `scan_google_for_products` tool with the search query `{searchQuery}`. This powerful tool is designed to find all product links, including regular results, shopping results, and **Google Ads** ("Quảng cáo" / "Sponsored").
    #     *   **B. Collect Preliminary Results:** The tool will return a list of candidates. Each candidate will have a preliminary `productName`, `priceText`, and, most importantly, the `url` to the retailer's product page.
    #     *   **C. Process and Prioritize:**
    #         1.  **Clean Preliminary Prices:** Normalize the `priceText` from each candidate into a numerical integer.
    #         2.  **SORT BY CHEAPEST PRICE:** Sort the entire list of candidates by their cleaned price in **ascending order** (cheapest first). This sorted list is your priority queue for the next phase.
    #     *   **D. CRITICAL - HANDLE FAILURES:** If the `scan_google_for_products` tool fails (e.g., is blocked by a reCAPTCHA, or returns no results), you must **IMMEDIATELY ABANDON GOOGLE** and switch to the **FALLBACK PLAN** below.

    #     ---
    #     **PHASE 2: RETAILER VERIFICATION (GET ACCURATE DETAILS)**
    #     ---
    #     You now have a prioritized list of URLs. Your goal is to visit them to get verified, up-to-date, and detailed information.

    #     *   **A. Iterate and Extract:** Start from the top of your sorted list (the cheapest candidates). For **each URL**, you MUST execute the `extract_product_details_from_url` tool.
    #     *   **B. Collect Detailed Information:** From each retailer's page, you MUST extract the following specific fields. This data is the "ground truth."
    #         *   `productName` (the full and accurate name from the retailer)
    #         *   `sku` (the product's SKU, model, or part number)
    #         *   `finalPriceVND` (CRITICAL: the final, payable price)
    #         *   `oldPriceVND` (the original/list price before discounts, if available)
    #         *   `stockStatus` (CRITICAL: must be accurately determined as "In Stock" or "Out of Stock")
    #         *   `retailer` (the store name)
    #         *   `url` (the page you are on)
    #     *   **C. Collect Strategically:** Continue this process down your list until you have found at least `{limit}` products that are confirmed to be **in stock**.

    #     ---
    #     **FINAL ANALYSIS AND OUTPUT**
    #     ---
    #     After you have collected a sufficient number of detailed, in-stock products, perform the final analysis.

    #     *   **1. Final Filter:** Ensure your collected list contains ONLY products where `stockStatus` is 'In Stock'.
    #     *   **2. Final Sort:** Sort this final 'in-stock' list one last time by the verified `finalPriceVND` in ascending order.
    #     *   **3. Format Output:** Return the top products from the final sorted list, up to the specified `{limit}`. If no in-stock products are found after checking all candidates, return an empty `products` array. The output must be a valid JSON object.

    #     ---
    #     **FALLBACK PLAN (If Google Reconnaissance Fails)**
    #     ---
    #     If the `scan_google_for_products` tool is blocked, abandon Phase 1 entirely and execute this robust backup plan:
    #     *   **A. Select Retailers:** Decide to use the master combined list of all Laptop and Server retailers.
    #     *   **B. Find URLs Directly:** Use the `find_product_urls_directly_from_retailers` tool. This tool bypasses Google and gets product URLs from each retailer's own search function.
    #     *   **C. Proceed to Phase 2:** Use the list of URLs you just gathered from the fallback tool and begin the verification and detailed extraction process exactly as described in Phase 2.
    # """
    # task_instruction = f"""
    #     You are a master scraping agent, expert in finding the lowest prices at Vietnamese retailers. Your mission is to find the single CHEAPEST  offering for `{searchQuery}`(which is an SKU). , including offers from Google Ads.
    #     You are a specialized scraper for Vietnamese e-commerce, optimized to find the single CHEAPEST **in-stock** product for `{searchQuery}` (which is an SKU).  
    #     You must return the cheapest verified product(s), up to `{limit}`, in valid JSON.

    #     ---
    #     ## STEP 1: DISCOVERY (Google + Category Classification)
    #     ---

    #     1. **Primary Path – Google Search (with Ads included):**
    #     * Run a Google search for `{searchQuery}`.  
    #     * Inspect page titles, descriptions, and Google Ads results.  
    #     * Detect category:
    #         - If keywords include "Laptop", "Máy tính xách tay", "MacBook" → **Laptop**.  
    #         - If keywords include "Server", "Máy chủ", "Workstation", "Máy trạm" → **Server**.  

    #     2. **Select Retailer List based on Category:**
    #     * If Laptop → Retailers = FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.  
    #     * If Server → Retailers = An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA. , Thành Nhân Computer, An Khang Computer, Hitech Pro, Đỉnh Vàng Computer 

    #     3. **Fallback – If Google blocked/inconclusive:**  
    #     * Use the **Master Combined Retailer List** (Laptop + Server).  
    #     * Do NOT retry Google if it fails; move forward immediately.

    #     ---
    #     ## STEP 2: RETRIEVAL & EXTRACTION
    #     ---

    #     1. **Candidate Collection:**  
    #     * Run targeted Google queries (include ads):  
    #         - "giá rẻ nhất {searchQuery}"  
    #         - "{searchQuery} khuyến mãi"  
    #         - "{searchQuery} thanh lý"  
    #         - "{searchQuery} giá tốt nhất"  
    #     * Use these to collect retailer URLs.  

    #     2. **Detailed Extraction:**  
    #     * For each candidate URL, extract:  
    #         - `productName`  
    #         - `sku`  
    #         - `brand`  
    #         - `finalPriceVND` (clean integer, after discounts)  
    #         - `oldPriceVND` (if available)  
    #         - `stockStatus` ("In Stock" / "Out of Stock")  
    #         - `retailer`  
    #         - `url`  
    #         - `category` ("Laptop" / "Server")  
    #         - `scrapedAt`  

    #     ---
    #     ## STEP 3: CLEANING & DEDUPLICATION
    #     ---

    #     1. Normalize all `finalPriceVND` → integers in VND.  
    #     2. Deduplicate: keep only one cheapest entry per SKU per retailer.  

    #     ---
    #     ## STEP 4: PRIORITIZATION & OUTPUT
    #     ---

    #     1. Filter to only **In-Stock** items.  
    #     2. Sort by `finalPriceVND` ascending.  
    #     3. If no in-stock items → fallback to cheapest out-of-stock.  
    #     4. Return up to `{limit}` items.  

    #     ---
    #     ## OUTPUT FORMAT
    #     ---

    #     Final output MUST be valid JSON:

    #     ```json
    #     {{
    #     "products": [
    #         {{
    #         "productName": "...",
    #         "sku": "...",
    #         "brand": "...",
    #         "finalPriceVND": 12345678,
    #         "oldPriceVND": 13500000,
    #         "stockStatus": "In Stock",
    #         "retailer": "Phong Vũ",
    #         "url": "https://...",
    #         "category": "Laptop",
    #         "scrapedAt": "2025-08-21T12:34:56Z"
    #         }}
    #     ]
    #     }}
    #     ```
    # """

    task_instruction = f"""
        You are a master scraping agent, expert in finding the **lowest possible prices** at Vietnamese retailers.  
        Your mission is to find the single **CHEAPEST in-stock offering** for `{searchQuery}` (which is an SKU), including offers from Google Ads and Vietnamese price comparison websites.  
        You must return the cheapest verified product(s), up to `{limit}`, in valid JSON.

        ---
        ## STEP 1: DISCOVERY (Google + Category Classification)
        ---

        1. **Primary Path – Google Search (with Ads included):**
        * Run a Google search for `{searchQuery}`.  
        * Inspect page titles, descriptions, Google Ads, and price comparison sites.  
        * Detect category:
        - If keywords include "Laptop", "Máy tính xách tay", "MacBook" → **Laptop**.  
        - If keywords include "Server", "Máy chủ", "Workstation", "Máy trạm" → **Server**.  

        2. **Select Retailer List based on Category:**
        * **Laptop (Cheap-focused):** FPT Shop, Thế Giới Di Động, CellphoneS, Hoàng Hà Mobile, Phong Vũ, GearVN, An Phát PC, Phúc Anh, Nguyễn Kim, MediaMart, Điện Máy Xanh, Viettel Store.  
        * **Server (Workstation/Enterprise-focused):** An Phát PC, Phúc Anh, Phong Vũ, Máy Chủ Việt, Thế Giới Máy Chủ, Việt Nam Server, KDATA, Thành Nhân Computer, An Khang Computer, Hitech Pro, Đỉnh Vàng Computer.  

        3. **Fallback – If Google blocked/inconclusive:**  
        * Use the **Master Combined Retailer List** (Laptop + Server).  
        * Do NOT retry Google if it fails; move forward immediately.  

        ---
        ## STEP 2: RETRIEVAL & EXTRACTION
        ---

        1. **Candidate Collection:**  
        * Run targeted Google queries (include ads):  
        - "giá rẻ nhất {searchQuery}"  
        - "{searchQuery} khuyến mãi"  
        - "{searchQuery} thanh lý"  
        - "{searchQuery} giá tốt nhất"  
        * Collect from:
        - Retailer websites (based on category list).  
        - Price comparison platforms (e.g., websosanh.vn, sosanhgia.com, vnsale.vn).  

        2. **Detailed Extraction:**  
        * For each candidate URL, extract:  
        - `productName`  
        - `sku`  
        - `brand`  
        - `finalPriceVND` (clean integer, after discounts & coupons applied)  
        - `oldPriceVND` (if available)  
        - `stockStatus` ("In Stock" / "Out of Stock")  
        - `retailer`  
        - `url`  
        - `category` ("Laptop" / "Server")  
        - `scrapedAt`  

        ---
        ## STEP 3: CLEANING & DEDUPLICATION
        ---

        1. Normalize all `finalPriceVND` → integers in VND.  
        2. Deduplicate: keep only one cheapest entry per SKU per retailer.  
        3. If coupons/discount codes are available, apply them to compute the **lowest final price**.  

        ---
        ## STEP 4: PRIORITIZATION & OUTPUT
        ---

        1. Filter to only **In-Stock** items.  
        2. Sort by `finalPriceVND` **ascending** (lowest price first).  
        3. If no in-stock items → fallback to cheapest out-of-stock.  
        4. Return up to `{limit}` items.  

        ---
        ## OUTPUT FORMAT
        ---

        Final output MUST be valid JSON:

        ```json
        {{
        "products": [
            {{
            "productName": "...",
            "sku": "...",
            "brand": "...",
            "finalPriceVND": 12345678,
            "oldPriceVND": 13500000,
            "stockStatus": "In Stock",
            "retailer": "Phong Vũ",
            "url": "https://...",
            "category": "Laptop",
            "scrapedAt": "2025-08-21T12:34:56Z"
            }}
        ]
        }}
    ```
    """
    # Create the agent with the browser, LLM, task instruction, and controller

    agent = Agent(
        browser=browser,
        llm=llm,
        task=task_instruction,
        controller=controller,
        use_vision= True
    )

    try:
        # 1. Run the agent to get the result
        print("Running the agent...")
        agent_result = await agent.run()
        raw_result = agent_result.final_result() # Get the raw output

        print("\nRAW AGENT RESULT:")
        print(f"Agent Result: {raw_result}")
        print("-" * 30)

        # --- JSON Parsing Block ---
        # This block ensures 'data' is always a dictionary, regardless of raw_result type.
        data = {}
        if isinstance(raw_result, str) and raw_result:
            try:
                print("Result is a string. Parsing from JSON...")
                data = json.loads(raw_result)
            except json.JSONDecodeError:
                print(f"Critical Error: Agent result is not a valid JSON string. Cannot process.")
                raise  # Stop execution if JSON is invalid
        elif isinstance(raw_result, dict):
            # If it's already a dictionary, we can use it directly
            print("Result is already a dictionary/object.")
            data = raw_result
        else:
            print("Result is not a valid format (string or dictionary). Cannot save.")
            # We can raise an error or just let it finish without saving
            raise TypeError("Agent result is not a processable type.")
        
        # --- CORRECTLY INDENTED FILE SAVING LOGIC STARTS HERE ---
        # This code is now OUTSIDE the 'else' block and will run after 'data' is prepared.
        
        # 2. Define and create the output directory
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        print(f"Output directory '{output_dir}' is ready.")

        # Generate a timestamp for unique filenames
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # 3. Save the parsed data to a JSON file (full result)
        json_filepath = os.path.join(output_dir, f"agent_output_{timestamp}.json")
        try:
            with open(json_filepath, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
            print(f"Successfully saved full result to JSON: {json_filepath}")
        except Exception as e:
            print(f"Error saving to JSON: {e}")

        # Save only the extracted products list to JSON
        json_products_filepath = os.path.join(output_dir, f"agent_products_{timestamp}.json")
        try:
            if 'products' in data and isinstance(data['products'], list):
                products_to_save = data['products']
                with open(json_products_filepath, 'w', encoding='utf-8') as json_file:
                    json.dump(products_to_save, json_file, ensure_ascii=False, indent=4)
                print(f"Successfully saved EXTRACTED product list to JSON: {json_products_filepath}")
            else:
                print("ℹNo 'products' key found in the result. JSON file will not be created.")
        except Exception as e:
            print(f"Error saving extracted data to JSON: {e}")

        # 4. Extract product data and save it to a CSV file
        csv_filepath = os.path.join(output_dir, f"products_output_{timestamp}.csv")
        try:
            if 'products' in data and isinstance(data['products'], list) and data['products']:
                products_data = data['products']
                headers = products_data[0].keys()
                with open(csv_filepath, 'w', newline='', encoding='utf-8') as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(products_data)
                print(f"Successfully saved product data to CSV: {csv_filepath}")
            else:
                print("ℹNo product data found in the parsed result to write to CSV.")
        except Exception as e:
            print(f"Error saving to CSV: {e}")

    except Exception as e:
        # This will catch any errors, including from parsing or file saving
        print(f"\nAn error occurred during the process: {e}")

    finally:
        # 5. This block ensures the browser is always closed safely
        print("-" * 30)
        print("Stopping browser...")
        await browser.stop()
        print("Browser stopped. Process finished.")

# --- FIX ENDS HERE ---
        

            

# async def run_price_update_job():
#     """
#     The main job that orchestrates fetching SKUs, scraping prices,
#     and updating the database.
#     """
#     print("\n--- Starting Price Update Job ---")
#     db: Session = next(get_db()) # Get a database session

#     try:
#         # 1. Get all SKUs from your database
#         skus_to_update = get_all_skus(db)
#         if not skus_to_update:
#             print("No SKUs to process. Exiting job.")
#             return

#         # 2. Loop through each SKU and scrape its data
#         for sku in skus_to_update:
#             print(f"\n--- Processing SKU: {sku} ---")
            
#             # The scrape function returns a list of products, we only need the cheapest (the first one)
#             scraped_products = await scrape_product_data(searchQuery=sku, limit=4)
#             return scraped_products
        
            
#             # # 3. Check the result and update the database
#             # if scraped_products:
#             #     # Assuming the first result is the cheapest as per the prompt's sorting logic
#             #     cheapest_product = scraped_products[0]
#             #     new_price = cheapest_product.FinalPriceVND
                
#             #     # Call the function to update the price in the DB
#             #     update_price_for_sku(db, sku=sku, new_price=new_price)
#             # else:
#             #     print(f"Scraping returned no results for SKU: {sku}. Skipping update.")
                
#     finally:
#         # Ensure the database session is closed
#         db.close()
#         print("\n--- Price Update Job Scraped ---")

async def run_price_update_job():
    """
    Orchestrates fetching active SKUs, scraping prices for each one,
    and updating the database sequentially.
    """
    print("\n--- Starting Price Update Job ---")
    db: Session = next(get_db()) # Get a database session

    try:
        # 1. Get all active SKUs from your database
        # The function `get_all_skus` is already correctly filtered for Published=1, Deleted=0.
        skus_to_update = get_all_skus(db)
        if not skus_to_update:
            print("No active SKUs to process. Exiting job.")
            return

        print(f"\nFound {len(skus_to_update)} SKUs to process. Starting loop...")

        # 2. Loop through each SKU, scrape its data, and update the DB one by one
        for sku in skus_to_update:
            print(f"\n--- Processing SKU: {sku} ---")
            
            try:
                # Scrape function returns a list of products
                scraped_products = await scrape_product_data(searchQuery=sku, limit=4)
                
                # 3. Check the result and update the database for the current SKU
                if scraped_products and isinstance(scraped_products, list) and len(scraped_products) > 0:
                    # Assuming the first result is the cheapest as per the prompt's sorting logic
                    cheapest_product = scraped_products[0]
                    
                    # Ensure the product dictionary and price key exist before accessing
                    if cheapest_product and 'finalPriceVND' in cheapest_product:
                        new_price = cheapest_product['finalPriceVND']
                        
                        # Call the function to update the price in the DB
                        # update_price_for_sku(db, sku=sku, new_price=new_price)
                    else:
                        print(f"Scraped data for {sku} is malformed or missing 'finalPriceVND'. Skipping update.")
                else:
                    print(f"Scraping returned no results for SKU: {sku}. Skipping update.")

            except Exception as e:
                print(f"An error occurred while processing SKU {sku}: {e}")
                # Continue to the next SKU even if one fails
                continue
                
    finally:
        # Ensure the database session is closed
        db.close()
        print("\n--- Price Update Job Completed ---")

        
    
    
    
    



    


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
    # search_query = "30GS00G7VA"
    # limit = 2
    loop = asyncio.get_event_loop()
    products = loop.run_until_complete(run_price_update_job())




