import os
import json
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from pydantic import BaseModel
from browser_use import Browser, Agent, BrowserConfig
from browser_use.llm import ChatOpenAI
from browser_use import BrowserSession, Controller, ActionResult
import uvicorn

# ================== CONFIG ==================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(
    title="Lac Viet AI API",
    description="Scrape structured product pricing data with fixed JSON schema",
    version="1.0.0"
)

# ================== MODELS ==================
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
    # offers: List[Offer]
    lowest_offer: Optional[Offer]
    notes: Optional[str]

class ScrapeResponse(BaseModel):
    source: Optional[str]
    scrape_timestamp: Optional[str]
    products: List[Product]
    summary: Optional[Dict[str, Any]]

class PromptInput(BaseModel):
    prompt: str



class LowestOffersResponse(BaseModel):
    count: int  # total products found
    products: List[Product]  # up to N lowest-priced products

class LowestOfferInput(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None  # e.g., "laptop" or "server"
    limit: int = 10  # number of products to return
    

# ================== ENDPOINT ==================
@app.post("/browse/", tags=["LVAI_GetItems"], response_model=ScrapeResponse)
async def browse_with_prompt(data: PromptInput):
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

    llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-5")

    # Use prompt from request directly
    task_instruction = f"""
    {data.prompt}

    - Task: Browse the web, visit multiple **official Vietnamese technology retailers**, and collect structured product data.
    - Goal: Return the **most accurate, complete, and deduplicated** product information for comparison.

    ## Search Strategy
    1. Use multiple Google search queries based on the prompt.
    2. Visit **trusted electronics and computer hardware retailers** (e.g., Thế Giới Di Động, FPT Shop, An Phát, Phú An, Mai Hoàng, Hoàng Hà PC, GearVN, Nguyễn Kim, CellphoneS, MemoryZone).
    3. Avoid marketplaces like Shopee, Lazada, Tiki unless official store pages are found.
    4. Skip pages requiring login or CAPTCHA.

    ## Extraction Rules
    For each product found:
    - **product_name**: Full product name from page
    - **model_or_sku**: Model or SKU if available
    - **brand**: Manufacturer name
    - **category**: E.g., Laptop, Server, GPU, CPU, Storage, etc.
    - **specs**: Detailed specs (CPU, RAM, storage, GPU)
    - **price_amount**: Numeric price without currency symbol
    - **price_currency**: VND
    - **seller_name**: Store name
    - **product_url**: Direct URL to product page
    - **availability**: In stock / Out of stock / Pre-order
    - **shipping_cost**: If available
    - **total_price_amount**: price_amount + shipping_cost
    - **scrape_timestamp**: Current time in ISO 8601

    ## Deduplication
    - Deduplicate products by SKU or identical names
    - Keep **only the cheapest offer** per unique SKU

    ## Output Format
    - Output only **valid JSON** strictly matching the output_model schema
    - No markdown, no comments, no extra text
        """

    controller = Controller(exclude_actions=['search_google'],output_model=ScrapeResponse)

    agent = Agent(
        task=task_instruction,
        llm=llm,
        browser=browser,
        controller=controller,
        output_model=ScrapeResponse,
        max_steps=30,  # Limit steps to avoid infinite loops
        save_conversation_path="conversation.json"
    )

    history = await agent.run()
    await browser.close()

    # Get final result
    result = history.final_result()

    # Ensure JSON validation
    if isinstance(result, str):
        parsed_result = ScrapeResponse.model_validate_json(result)
    elif isinstance(result, dict):
        parsed_result = ScrapeResponse(**result)
    else:
        raise ValueError("Unexpected result type from agent.")

    return parsed_result
# @app.post("/lowest-offers/", tags=["LVAI_CompareSellers"], response_model=LowestOffersResponse)
# async def find_lowest_offers(data: LowestOfferInput):
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

#     llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini")
#     def generate_search_variations(term: str):
#         term = term.strip()
#         variations = set()

#         # Always include original
#         variations.add(term)

#         # Common bilingual substitutions & synonyms
#         replacements = {
#             "Laptop": ["Notebook", "Máy tính xách tay", "Laptop"],
#             "Gaming": ["Game", "Gamer", "Chơi game"],
#             "Server": ["Máy chủ"],
#             "PC": ["Máy tính để bàn", "Desktop"],
#             "Workstation": ["Máy trạm"],
#             "Dell": ["DELL"],
#             "Asus": ["ASUS"],
#             "HP": ["Hewlett Packard", "Hewlett-Packard"],
#             "Lenovo": ["ThinkPad", "IdeaPad"],
#             "MacBook": ["Apple MacBook"],
#             "i9": ["Core i9", "Intel i9"],
#             "i7": ["Core i7", "Intel i7"],
#             "i5": ["Core i5", "Intel i5"],
#             "i3": ["Core i3", "Intel i3"],
#             "SSD": ["Solid State Drive"],
#             "HDD": ["Hard Disk Drive"],
#             "RAM": ["Bộ nhớ RAM", "Memory"],
#             "Card đồ họa": ["GPU", "Graphics Card"],
#         }

#         # Apply replacements
#         for word, subs in replacements.items():
#             if word.lower() in term.lower():
#                 for sub in subs:
#                     variations.add(term.replace(word, sub))
#                     variations.add(term.replace(word.lower(), sub))
#                     variations.add(term.replace(word.upper(), sub))

#         # Category expansion (word reorder for common patterns)
#         if "Laptop" in term or "Máy tính xách tay" in term:
#             variations.add(term.replace("Laptop", "Gaming Laptop"))
#             variations.add(term.replace("Laptop", "Laptop Gaming"))
#             variations.add(term.replace("Máy tính xách tay", "Máy tính xách tay chơi game"))

#         if "Gaming" in term:
#             variations.add(term.replace("Gaming", "Laptop Gaming"))
#             variations.add(term.replace("Gaming", "Máy tính chơi game"))

#         # Generate split-based variations
#         keywords = term.split()
#         if len(keywords) > 2:
#             variations.add(" ".join(keywords[:2]))  # First two words
#             variations.add(keywords[0])             # Brand only
#             variations.add(" ".join(sorted(keywords)))  # Word order swap

#         # Model number variations
#         import re
#         model_numbers = re.findall(r"[A-Za-z]*\d{3,5}[A-Za-z]*", term)
#         for m in model_numbers:
#             variations.add(term.replace(m, m.replace("-", " ")))
#             variations.add(term.replace(m, m.replace(" ", "")))

#         # Case variations
#         variations.add(term.lower())
#         variations.add(term.upper())
#         variations.add(term.title())

#         # Clean up spaces and deduplicate
#         cleaned_variations = {v.strip() for v in variations if v.strip()}
#         return list(cleaned_variations)


#     # Example usage with your data
#     # data = {
#     #     "product_name": "string",
#     #     "category": "Dell Laptop Gaming",
#     #     "limit": 10
#     # }

#     # Determine base search target
#     if not data["product_name"] or data["product_name"].strip().lower() in ["string", ""]:
#         base_target = f"all products in category '{data['category']}'"
#     else:
#         base_target = data["product_name"]

#     # Generate variations
#     search_variations = generate_search_variations(base_target)
#     search_target = ", ".join(search_variations)

#     # Build optimized scraping prompt
#     task_instruction = f"""
#     You are a professional e-commerce price-comparison agent using a browser-based tool.

#     ## YOUR GOAL
#     - Use Google search to find **official retailer websites** in Vietnam that sell products matching:
#     {search_target}
#     - Collect prices from multiple trusted sources.
#     - Return the **{data['limit']} cheapest items** across unique sellers.

#     ---

#     ## SEARCH & SCRAPING PROCESS
#     1. Search Google with each variation of "{base_target}" plus the retailer name.
#     2. Visit **only official retailer sites**, starting with:
#     - The Gioi Di Dong
#     - FPT Shop
#     - An Phat Computer
#     - CellphoneS
#     - GearVN
#     - Hoang Ha PC
#     - Nguyen Kim
#     - HACOM
#     - Mai Nguyen
#     - Phong Vu
#     - Ben Computer
#     - Any other relevant Vietnamese tech retailer
#     3. On each retailer’s site:
#     - Try searching for each variation in the search bar.
#     - If no search bar, browse by category.
#     - Collect **all matching products**:
#         - Matches the product name closely, OR
#         - Belongs to the same category: "{data['category']}"
#     4. Compare all matches **within the same seller**.
#     5. Keep only **the single lowest total_price_amount item** from that seller.
#     6. Continue to the next seller until all have been checked.

#     ---

#     ## WHAT TO AVOID
#     - No Shopee, Lazada, Tiki, Sendo, or other general marketplaces.
#     - No platforms requiring login or registration.
#     - No scraping review sites, news articles, or forums.
#     - No more than one product per seller.

#     ---

#     ## DATA TO EXTRACT (per lowest-priced match per seller)
#     - product_name
#     - model_or_sku
#     - brand
#     - category
#     - specs (CPU, RAM, storage, GPU)
#     - price_amount
#     - price_currency
#     - shipping_cost
#     - total_price_amount
#     - availability
#     - seller_name
#     - product_url
#     - scrape_timestamp (ISO 8601)

#     ---

#     ## DEDUPLICATION
#     - One entry per seller only.
#     - If the same product is sold by multiple sellers, keep both.
#     - Always choose the lowest `total_price_amount` for that seller.

#     ---

#     ## FINAL SORT & LIMIT
#     - After all sellers are processed, sort by `total_price_amount` ascending.
#     - Output only the **top {data['limit']} cheapest items** from unique sellers.

#     ---

#     ## OUTPUT FORMAT
#     - Output valid JSON matching the `LowestOffersResponse` schema.
#     - No markdown, no explanations, just the JSON.
#     """




#     controller = Controller(output_model=LowestOffersResponse)

#     agent = Agent(
#         task=task_instruction,
#         llm=llm,
#         browser=browser,
#         controller=controller,
#         output_model=LowestOffersResponse
#     )

#     history = await agent.run()
#     await browser.close()


#     result = history.final_result()

#     # Debug log the raw result
#     print("DEBUG: Raw agent final_result =", repr(result))

#     try:
#         if isinstance(result, str):
#             parsed_result = LowestOffersResponse.model_validate_json(result)
#         elif isinstance(result, dict):
#             parsed_result = LowestOffersResponse(**result)
#         elif result is None:
#             raise ValueError("No result returned from agent — likely scraping failed.")
#         else:
#             raise TypeError(f"Unexpected result type: {type(result)}")
#     except Exception as e:
#         raise ValueError(f"Failed to parse agent result: {e}")

#     return parsed_result

# @app.post("/lowest-offers/", tags=["LVAI_CompareSellers"], response_model=LowestOffersResponse)
# async def find_lowest_offers(data: LowestOfferInput):
#     # Configure browser
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

#     # LLM
#     llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini")

#  # =========================
# # 1. Generate Search Variations
# # =========================
#     def generate_search_variations(term: str):
#         import re
#         import unicodedata

#         def remove_accents(input_str):
#             nfkd_form = unicodedata.normalize('NFKD', input_str)
#             return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])

#         term = term.strip()
#         variations = set([term])

#         replacements = {
#             "Laptop": ["Notebook", "Máy tính xách tay", "Laptop"],
#             "Gaming": ["Game", "Gamer", "Chơi game"],
#             "Server": ["Máy chủ"],
#             "PC": ["Máy tính để bàn", "Desktop"],
#             "Workstation": ["Máy trạm"],
#             "Dell": ["DELL", "Dell Inc."],
#             "Asus": ["ASUS", "Asustek"],
#             "HP": ["Hewlett Packard", "Hewlett-Packard"],
#             "Lenovo": ["ThinkPad", "IdeaPad"],
#             "MacBook": ["Apple MacBook", "MBP", "MBA"],
#             "i9": ["Core i9", "Intel i9"],
#             "i7": ["Core i7", "Intel i7"],
#             "i5": ["Core i5", "Intel i5"],
#             "i3": ["Core i3", "Intel i3"],
#             "SSD": ["Solid State Drive", "Ổ cứng SSD"],
#             "HDD": ["Hard Disk Drive", "Ổ cứng HDD"],
#             "RAM": ["Bộ nhớ RAM", "Memory"],
#             "Card đồ họa": ["GPU", "Graphics Card", "VGA"]
#         }

#         for word, subs in replacements.items():
#             if word.lower() in term.lower():
#                 for sub in subs:
#                     variations.add(term.replace(word, sub))
#                     variations.add(term.replace(word.lower(), sub))
#                     variations.add(term.replace(word.upper(), sub))

#         # Biến thể không dấu
#         no_accent = remove_accents(term)
#         variations.add(no_accent)
#         variations.add(no_accent.lower())
#         variations.add(no_accent.upper())

#         # Tách model number
#         model_numbers = re.findall(r"[A-Za-z]*\d{3,5}[A-Za-z]*", term)
#         for m in model_numbers:
#             variations.add(term.replace(m, m.replace("-", " ")))
#             variations.add(term.replace(m, m.replace(" ", "")))

#         variations.update([term.lower(), term.upper(), term.title()])
#         return list({v.strip() for v in variations if v.strip()})


#     # =========================
#     # 2. Determine Base Target
#     # =========================
#     base_target = (
#         data.product_name
#         if data.product_name.strip().lower() not in ["", "string"]
#         else f"all products in category '{data.category}'"
#     )

#     # =========================
#     # 3. Create Variations
#     # =========================
#     search_variations = generate_search_variations(base_target)
#     search_target = ", ".join(search_variations)


#     # =========================
#     # 4. Prompt Instruction
#     # =========================
#     # task_instruction = f"""
#     # You are a professional e-commerce price-comparison agent using a browser-based tool.

#     # ## GOAL
#     # - Use Google to find **official Vietnamese tech retailers** selling:
#     # {search_target}
#     # - Collect prices from multiple trusted sources.
#     # - Return the **{data.limit} cheapest unique seller offers**.

#     # ## SEARCH LOGIC
#     # 1. **Phase 1 – Broad Search**
#     # - Search Google for each variation of "{base_target}" without site restriction.
#     # - From the first 2–3 pages of results, collect:
#     #     - Product listing URLs matching "{data.product_name}" closely.
#     #     - Or category pages matching "{data.category}".
#     # - If no results found or no prices extracted:
#     #     - Retry search using the next unused keyword from `generate_search_variations`.
#     #     - If still no results, retry using only "{data.category}".

#     # 2. **Phase 2 – Detailed Scraping**
#     # - Visit each retailer from results.
#     # - Use site search with all variations; if no search bar, browse by category.
#     # - For each product:
#     #     - If price is missing → automatically go to next product or next page.
#     #     - Continue until a valid price is found.
#     # - Keep only **lowest total_price_amount per seller**.

#     # 3. **Retailer Priority**
#     # - Always check these sellers first (in order):
#     #     The Gioi Di Dong, FPT Shop, An Phat Computer, CellphoneS, GearVN,
#     #     Hoang Ha PC, Nguyen Kim, HACOM, Mai Nguyen, Phong Vu, Ben Computer
#     # - Then check any other official Vietnamese tech retailer.

#     # 4. **Inclusion Rules**
#     # - Only official retailer websites.
#     # - Skip Shopee, Lazada, Tiki, Sendo, or login-required sites.
#     # - Skip news/review/blog/forum pages.

#     # 5. **Output Rules**
#     # - Required fields:
#     #     product_name, model_or_sku, brand, category, specs,
#     #     price_amount, price_currency, shipping_cost, total_price_amount,
#     #     availability, seller_name, product_url, scrape_timestamp (ISO 8601).
#     # - One entry per seller (lowest price).
#     # - Sort by `total_price_amount` ascending.
#     # - Output exactly {data.limit} items in valid JSON format matching LowestOffersResponse.

#     # ## RETRY STRATEGY
#     # - If after all retailers processed and less than {data.limit} valid offers are found:
#     # - Repeat Google search with unused variations.
#     # - Continue scraping until {data.limit} valid offers are found.

#     # ## OUTPUT
#     # - One entry per seller.
#     # - Sort by `total_price_amount` ascending.
#     # - Return only top {data.limit}.
#     # - Output valid JSON matching LowestOffersResponse.

#     # """
#     task_instruction = f"""
#     You are a professional e-commerce price-comparison agent using a browser-based tool (Browse-Use Agent). 

#     Your task is to automatically search Google, navigate official Vietnamese tech retailer websites, extract product prices, and return exactly the top {data.limit} cheapest offers. Follow all rules and strategies below.

#     ## GOAL
#     - Find **official Vietnamese tech retailers** selling: {search_target}.
#     - Collect product information and pricing.
#     - Return **exactly {data.limit} cheapest unique seller offers** in valid JSON (LowestOffersResponse).

#     ## SEARCH LOGIC

#     1. **Phase 1 – Broad Search**
#     - Search Google for all variations of "{base_target}".
#     - Scrape first 2–3 pages of results for:
#         - Product listing URLs matching "{data.product_name}" closely.
#         - Category pages matching "{data.category}".
#     - If no matching results:
#         - Retry with next unused keyword from `generate_search_variations`.
#         - If still no results, search only by "{data.category}".

#     2. **Phase 2 – Detailed Scraping**
#     - Visit each retailer URL from search results.
#     - Use site search with all product variations.
#         - If search bar unavailable, navigate via category pages.
#     - For each product found:
#         - Skip products with missing price.
#         - Record **lowest total_price_amount per seller**.
#     - If after visiting all URLs less than {data.limit} offers are found:
#         - Continue to next search results page(s) on Google.
#         - Repeat scraping until top {data.limit} cheapest offers are collected.

#     ## RETAILER PRIORITY
#     - Always check these first (in order):  
#     The Gioi Di Dong, FPT Shop, An Phat Computer, CellphoneS, GearVN,  
#     Hoang Ha PC, Nguyen Kim, HACOM, Mai Nguyen, Phong Vu, Ben Computer.
#     - Then check any other official Vietnamese tech retailer.

#     ## INCLUSION RULES
#     - Only include official retailer websites.
#     - Exclude Shopee, Lazada, Tiki, Sendo, or any login-required sites.
#     - Exclude news, review, blog, forum, or unrelated pages.
#     - Skip products without a price.

#     ## DATA EXTRACTION
#     - Required fields per offer:
#         product_name, model_or_sku, brand, category, specs,
#         price_amount, price_currency, shipping_cost, total_price_amount,
#         availability, seller_name, product_url, scrape_timestamp (ISO 8601).
#     - Keep **one entry per seller** (lowest price only).
#     - Sort all offers by `total_price_amount` ascending.
#     - Return **exactly {data.limit} offers**.

#     ## RETRY & CONTINUATION STRATEGY
#     - If after all processed URLs, fewer than {data.limit} offers are found:
#         - Use unused search variations.
#         - Continue to next Google search pages.
#         - Continue scraping until top {data.limit} cheapest offers are found.
#     - Always update output dynamically to ensure **the returned top offers are the cheapest overall**, even if new lower prices are found in subsequent pages.

#     ## OUTPUT
#     - JSON must match **LowestOffersResponse** format.
#     - Only include top {data.limit} cheapest offers.
#     - Sort ascending by `total_price_amount`.
#     - Each offer must have complete required fields.

#     """

#     controller = Controller(output_model=LowestOffersResponse)

#     agent = Agent(
#         task=task_instruction,
#         llm=llm,
#         browser=browser,
#         controller=controller,
#         output_model=LowestOffersResponse
#     )

#     history = await agent.run()
#     await browser.close()

#     result = history.final_result()
#     print("DEBUG: Raw agent final_result =", repr(result))

#     try:
#         if isinstance(result, LowestOffersResponse):
#             parsed_result = result
#         elif isinstance(result, str):
#             parsed_result = LowestOffersResponse.model_validate_json(result)
#         elif isinstance(result, dict):
#             parsed_result = LowestOffersResponse(**result)
#         else:
#             raise TypeError(f"Unexpected result type: {type(result)}")
#     except Exception as e:
#         raise ValueError(f"Failed to parse agent result: {e}")

#     return parsed_result

@app.post("/lowest-offers/", tags=["LVAI_CompareSellers"], response_model=LowestOffersResponse)
async def find_lowest_offers(data: LowestOfferInput):
    # =========================
    # 1. Configure Browser
    # =========================
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

    # =========================
    # 2. Initialize LLM
    # =========================
    llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini")

    # =========================
    # 3. Generate Search Variations
    # =========================
    def generate_search_variations(term: str):
        import re, unicodedata

        def remove_accents(s): 
            nfkd = unicodedata.normalize('NFKD', s)
            return ''.join([c for c in nfkd if not unicodedata.combining(c)])

        term = term.strip()
        variations = set([term])

        replacements = {
            "Laptop": ["Notebook", "Máy tính xách tay"],
            "Gaming": ["Game", "Gamer", "Chơi game"],
            "Server": ["Máy chủ"], "PC": ["Desktop", "Máy tính để bàn"],
            "Workstation": ["Máy trạm"], "Dell": ["DELL", "Dell Inc."],
            "Asus": ["ASUS", "Asustek"], "HP": ["Hewlett Packard"],
            "Lenovo": ["ThinkPad", "IdeaPad"], "MacBook": ["MBP", "MBA"],
            "i9": ["Core i9"], "i7": ["Core i7"], "i5": ["Core i5"], "i3": ["Core i3"],
            "SSD": ["Solid State Drive"], "HDD": ["Hard Disk Drive"],
            "RAM": ["Memory"], "Card đồ họa": ["GPU", "Graphics Card", "VGA"]
        }

        for word, subs in replacements.items():
            if word.lower() in term.lower():
                for sub in subs:
                    variations.add(term.replace(word, sub))
                    variations.add(term.replace(word.lower(), sub))
                    variations.add(term.replace(word.upper(), sub))

        
        no_acc = remove_accents(term)
        variations.update([no_acc, no_acc.lower(), no_acc.upper()])
        # Biến thể model number
        models = re.findall(r"[A-Za-z]*\d{3,5}[A-Za-z]*", term)
        for m in models:
            variations.add(term.replace(m, m.replace("-", " ")))
            variations.add(term.replace(m, m.replace(" ", "")))
        variations.update([term.lower(), term.upper(), term.title()])
        return list({v.strip() for v in variations if v.strip()})
    
    




    # =========================
    # 4. Determine Base Target
    # =========================
    base_target = data.product_name if data.product_name.strip().lower() not in ["", "string"] else f"all products in category '{data.category}'"
    search_variations = generate_search_variations(base_target)
    search_target = ", ".join(search_variations)

    # =========================
    # 5. Task Instruction for Browse-Use Agent
    # =========================
    # task_instruction = f"""
    # You are a professional e-commerce price-comparison agent using a browser-based tool (Browse-Use Agent). 

    # Your task is to automatically search Google, navigate official Vietnamese tech retailer websites, extract product prices, and return exactly the top {data.limit} cheapest offers.

    # - Search Google for the product name: "{base_target}".
    #     - **Step 1: Check Google search results**
    #         - If the price is shown directly on Google (rich snippet, product snippet), **collect it immediately**.
    #         - If the price is not visible, continue to Step 2.
    #     - **Step 2: Visit retailer pages**
    #         - Visit each retailer found in search results.
    #         - Use site search or browse categories to locate the product.
    #         - Extract product details: name, specs, brand, category, price, availability, shipping cost, seller, product URL.
    #         - Skip products without price.
    #         - Record only **one price per seller** (lowest if multiple found).

    # ## GOAL
    # - Find official Vietnamese tech retailers selling: {base_target}.
    # - Visit all retailers asynchronously from search results.
    # - For each retailer:
    #    - Extract product price if available; skip pages without price.
    #    - Record only **one price per seller** (lowest if multiple found).
    #    - Update top {data.limit} cheapest offers **live** as you go.
    # - Compare all prices continuously; always maintain the top {data.limit} cheapest offers.
    # - Collect product information and pricing.
    # - Return **exactly {data.limit} cheapest unique seller offers** in valid JSON (LowestOffersResponse).

    # ## SEARCH & SCRAPING
    # - Search Google for all variations of "{base_target}".
    # - Scrape first 2–3 pages for product pages and category pages.
    # - Visit each retailer, use search or browse categories.
    # - Skip products with missing price.
    # - Keep **lowest total_price_amount per seller**.
    # - Continue to next Google search page if fewer than {data.limit} offers found, until top {data.limit} cheapest offers are collected.

    # ## RETAILER PRIORITY
    # - The Gioi Di Dong, FPT Shop, An Phat Computer, CellphoneS, GearVN, Hoang Ha PC, Nguyen Kim, HACOM, Mai Nguyen, Phong Vu, Ben Computer.
    # - Then other official Vietnamese tech retailers.

    # ## INCLUSION RULES
    # - Only official retailer websites.
    # - Exclude Shopee, Lazada, Tiki, Sendo, login-required sites, news/reviews/blogs/forums.
    
    # ## OUTPUT
    # - Required fields: product_name, model_or_sku, brand, category, specs,
    #   price_amount, price_currency, shipping_cost, total_price_amount,
    #   availability, seller_name, product_url, scrape_timestamp (ISO 8601).
    # - One entry per seller (lowest price only).
    # - Sort by total_price_amount ascending.
    # - Return exactly {data.limit} cheapest offers in JSON.
    # """
    task_instruction = f"""
        You are a professional e-commerce price-comparison agent using a browser-based tool (Browse-Use Agent).

    Your task is to automatically search Google, navigate official Vietnamese tech retailer websites, extract product prices, and return exactly the top {data.limit} cheapest offers.

    - Search Google for the product name: "{base_target}".
        - **Step 1: Check Google search results**
            - If the price is shown directly on Google (rich snippet, product snippet), **collect it immediately**.
            - Do **not** stop at the first lowest price; record all valid prices visible on Google.
        - **Step 2: Visit retailer pages**
            - Visit **all retailer links found in search results**, asynchronously if possible.
            - Use site search or browse categories to locate the product.
            - Extract product details: name, specs, brand, category, price, availability, shipping cost, seller, product URL.
            - Skip products without price.
            - Record only **one price per seller** (lowest if multiple found).
        - Continuously **compare all prices** and maintain top {data.limit} cheapest offers **live**.

    ## GOAL
    - Find official Vietnamese tech retailers selling: {base_target}.
    - Visit all retailers asynchronously from search results.
    - Extract product prices for all valid offers.
    - Keep **one entry per seller** (lowest price only).
    - Return **exactly {data.limit} cheapest unique seller offers** in valid JSON (LowestOffersResponse), sorted by `total_price_amount`.

    ## SEARCH & SCRAPING
    - Search Google for all variations of "{base_target}".
    - Scrape first 2–3 pages of Google results.
    - Visit each retailer, use search or browse categories.
    - Skip products with missing price.
    - Keep **lowest total_price_amount per seller**.
    - Do **not stop at the first page**; continue scraping all valid pages until top {data.limit} cheapest offers are found.

    ## RETAILER PRIORITY
    - The Gioi Di Dong, FPT Shop, An Phat Computer, CellphoneS, GearVN, Hoang Ha PC, Nguyen Kim, HACOM, Mai Nguyen, Phong Vu, Ben Computer.
    - Then other official Vietnamese tech retailers.

    ## INCLUSION RULES
    - Only official retailer websites.
    - Exclude Shopee, Lazada, Tiki, Sendo, login-required sites, news/reviews/blogs/forums.

    ## OUTPUT
    - Required fields: product_name, model_or_sku, brand, category, specs,
    price_amount, price_currency, shipping_cost, total_price_amount,
    availability, seller_name, product_url, scrape_timestamp (ISO 8601).
    - One entry per seller (lowest price only).
    - Sort ascending by `total_price_amount`.
    - Return exactly {data.limit} cheapest offers in JSON.
    """



    # =========================
    # 6. Create Agent & Run
    # =========================
    controller = Controller(output_model=LowestOffersResponse)
    agent = Agent(task=task_instruction, llm=llm, browser=browser, controller=controller, output_model=LowestOffersResponse)

    history = await agent.run()
    await browser.close()
   

    # Get final result
    result = history.final_result()

    # Ensure JSON validation
    if isinstance(result, str):
        parsed_result = LowestOffersResponse.model_validate_json(result)
    elif isinstance(result, dict):
        parsed_result = LowestOffersResponse(**result)
    else:
        raise ValueError("Unexpected result type from agent.")

    return parsed_result

    # =========================
    # 7. Parse Result
    # =========================




        

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8081)
