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
from app.service.scraping import scraping_products, update_price_for_sku
from app.db.create import get_db
import uvicorn

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(
    title="Lac Viet AI API",
    description="Scrape structured product pricing data with fixed JSON schema",
    version="1.0.0"
)

@app.post("/scrape-products", response_model=Dict[str, Any])
async def scrape_products(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """ Scrape product data and return structured JSON.
    """
    products = await scraping_products(db=get_db(), input_data=input_data)
    return {"status": "success", "data": products}


    