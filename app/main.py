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