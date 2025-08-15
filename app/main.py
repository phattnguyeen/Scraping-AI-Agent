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

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(
    title="Lac Viet AI API",
    description="Scrape structured product pricing data with fixed JSON schema",
    version="1.0.0"
)