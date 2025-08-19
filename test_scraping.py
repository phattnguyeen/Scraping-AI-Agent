#!/usr/bin/env python3
"""
Test script for laptop and server product scraping
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "app")))

from app.service.scraping4 import scraping_products
from app.schemas.products import ProductInput
from app.db.create import get_db

async def test_scraping():
    """Test the scraping functionality with different laptop and server queries."""
    
    # Get database session
    db = next(get_db())
    
    # Test queries for different types of products
    test_queries = [
        {
            "name": "Dell Latitude",
            "prompt": "Dell Latitude laptop giá rẻ nhất",
            "limit": 5
        },
        {
            "name": "HP ProBook",
            "prompt": "HP ProBook laptop business giá tốt",
            "limit": 5
        },
        {
            "name": "Lenovo ThinkPad",
            "prompt": "Lenovo ThinkPad T series laptop giá rẻ",
            "limit": 5
        },
        {
            "name": "Dell PowerEdge Server",
            "prompt": "Dell PowerEdge server máy chủ giá tốt",
            "limit": 3
        }
    ]
    
    print("🚀 Starting laptop and server product scraping tests...")
    print("=" * 60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n📋 Test {i}: {query['name']}")
        print(f"Query: {query['prompt']}")
        print("-" * 40)
        
        try:
            input_data = ProductInput(
                product_name=query['name'],
                limit=query['limit'],
                prompt=query['prompt']
            )
            
            start_time = datetime.now()
            results = await scraping_products(db, input_data)
            end_time = datetime.now()
            
            print(f"✅ Completed in {(end_time - start_time).total_seconds():.2f} seconds")
            print(f"📊 Found {results.total} products")
            print(f"🎯 Limit: {results.limit}")
            
            # Display some sample results
            if results.products:
                print("\n📦 Sample Products:")
                for j, product in enumerate(results.products[:3], 1):
                    print(f"  {j}. {product.product_name}")
                    print(f"     Brand: {product.brand}")
                    print(f"     Model: {product.model}")
                    print(f"     Price: {product.price:,} {product.currency}")
                    print(f"     Seller: {product.seller_name}")
                    print(f"     Category: {product.category}")
                    print()
            
        except Exception as e:
            print(f"❌ Error in test {i}: {e}")
        
        print("=" * 60)
    
    print("\n🎉 All tests completed!")
    print("📁 Check the generated CSV files and JSON summaries in the current directory.")

if __name__ == "__main__":
    asyncio.run(test_scraping())
