import json
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from browser_use import Browser, Agent, BrowserConfig
from browser_use.llm import ChatOpenAI
from browser_use.controller.service import Controller

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ===== Pydantic Models =====
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
    offers: List[Offer]
    lowest_offer: Optional[Offer]
    notes: Optional[str]

class ScrapeResponse(BaseModel):
    source: Optional[str]
    scrape_timestamp: Optional[str]
    products: List[Product]
    summary: Optional[Dict[str, Any]]

# Controller for output formatting
controller = Controller(output_model=ScrapeResponse)

async def main():
    # Configure browser
    browser_config = BrowserConfig(headless=False, slow_mo=500)
    browser = Browser(config=browser_config)
    await browser.start()

    llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini")

    task_instruction = """
    You are a scraping assistant whose goal is to collect and compare prices of laptops and servers across online sellers.
    ONLY output valid JSON matching the exact output_model schema — no markdown, no explanations.

    Find the product:

    "Máy chủ Dell PowerEdge R760xs 42SVRDR760-S4A (Intel Xeon Silver 4510 2.4G | 16GB RDIMM | 1.2TB HDD | PERC H755 | iDRAC9, Enterprise 16G | DHP PSU 2x800W | BC5720DP 1GbE LOM | BC57414DP 10 | 25GbE | Rails | Bezel | 2xJumpercord | ProSupport 36M)"

    on www.anphatpc.com.vn.

    Requirements:
    1. Extract:
       - product_name
       - model_or_sku
       - brand
       - category
       - specs (CPU, RAM, storage, GPU)
       - price_amount
       - price_currency
       - seller_name
       - product_url
       - availability
       - shipping_cost
       - total_price_amount
       - scrape_timestamp (ISO 8601)
    2. Deduplicate by SKU or name.
    3. Identify lowest_offer per product.
    4. Stop after finding the target product.
    """

    # Pass output_model into Agent
    agent = Agent(
        task=task_instruction,
        llm=llm,
        browser=browser,
        save_conversation_path="conversation.json",
        controller=controller,
        output_model=ScrapeResponse
    )

    history = await agent.run()
    result = history.final_result()

    # Ensure proper JSON parsing
    if isinstance(result, str):
        parsed_result = ScrapeResponse.model_validate_json(result)
    elif isinstance(result, dict):
        parsed_result = ScrapeResponse(**result)
    else:
        raise ValueError("Unexpected result type from agent.")

    # Output clean JSON only
    print(json.dumps(parsed_result.model_dump(), indent=2, ensure_ascii=False))

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
