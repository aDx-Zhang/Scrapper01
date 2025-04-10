#!/usr/bin/env python
import sys
import logging
from app import app
from scraper import (
    AllegroScraper, OLXScraper, VintedScraper, 
    FacebookMarketplaceScraper
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_scraper(scraper_name, keywords, filters=None):
    """
    Test a specific scraper with given keywords and filters
    """
    if filters is None:
        filters = {}
    
    logger.info(f"Testing {scraper_name} scraper with keywords: {keywords}")
    
    # Create scraper instance
    scraper = None
    if scraper_name.lower() == 'olx':
        scraper = OLXScraper()
    elif scraper_name.lower() == 'allegro':
        scraper = AllegroScraper()
    elif scraper_name.lower() == 'vinted':
        scraper = VintedScraper()
    elif scraper_name.lower() == 'facebook':
        scraper = FacebookMarketplaceScraper()
    else:
        logger.error(f"Unknown scraper: {scraper_name}")
        return
    
    # Search for items
    try:
        logger.info(f"Searching with keywords: {keywords} and filters: {filters}")
        items = scraper.search(keywords, filters)
        
        print(f"\nDEBUG: Got response from scraper, items type: {type(items)}, len: {len(items) if items else 0}")
        
        # Debug the raw API price discovery issue for OLX
        if scraper_name.lower() == 'olx':
            print("\nDEBUG: Examining offers directly from OLX API for price structure:")
            try:
                import requests
                import json
                
                # Construct the same API URL used in the OLX scraper
                url = "https://www.olx.pl/api/v1/offers/"
                params = {
                    'query': ",".join(keywords),
                    'filter_float_price:from': filters.get('price_min', 0),
                    'filter_float_price:to': filters.get('price_max', 1000),
                    'sort_by': 'created_at:desc',
                    'limit': 5
                }
                
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and isinstance(data["data"], list) and data["data"]:
                        print(f"API returned {len(data['data'])} offer(s)")
                        for i, offer in enumerate(data["data"][:3]):  # Only examine first 3
                            print(f"\nAPI Offer #{i+1} - {offer.get('title', 'No title')}")
                            
                            # Check params array for price
                            params = offer.get('params', [])
                            if isinstance(params, list):
                                print(f"  Params count: {len(params)}")
                                for idx, param in enumerate(params):
                                    if isinstance(param, dict):
                                        param_type = param.get('type')
                                        if param_type == 'price' or 'price' in str(param).lower():
                                            print(f"  FOUND PRICE PARAM: {param}")
                                            
                    else:
                        print("No offers in API response data")
                else:
                    print(f"API request failed with status code: {response.status_code}")
            except Exception as e:
                print(f"Error during API debugging: {str(e)}")
        
        if items:
            # Print first item keys for debugging
            if len(items) > 0:
                print(f"First item keys: {list(items[0].keys())}")
                print(f"First item: {items[0]}")
            
            logger.info(f"RESULTS: Found {len(items)} items")
            # Save first 5 items to a file for easier inspection
            with open(f"{scraper_name}_test_results.txt", "w") as f:
                f.write(f"Found {len(items)} items\n\n")
                
                # Display first 5 items
                for i, item in enumerate(items[:10]):
                    title = item.get('title', 'N/A')
                    price = item.get('price', 'N/A')
                    currency = item.get('currency', 'N/A')
                    url = item.get('url', 'N/A')
                    
                    # Log and write to file
                    logger.info(f"Item {i+1}:")
                    logger.info(f"  Title: {title}")
                    logger.info(f"  Price: {price} {currency}")
                    logger.info(f"  URL: {url}")
                    logger.info(f"  Marketplace: {item.get('marketplace', 'N/A')}")
                    logger.info(f"  Location: {item.get('location', 'N/A')}")
                    logger.info("---")
                    
                    f.write(f"Item {i+1}:\n")
                    f.write(f"  Title: {title}\n")
                    f.write(f"  Price: {price} {currency}\n")
                    f.write(f"  URL: {url}\n")
                    f.write(f"  Marketplace: {item.get('marketplace', 'N/A')}\n")
                    f.write(f"  Location: {item.get('location', 'N/A')}\n")
                    f.write("---\n")
            
            print(f"\n*** RESULTS SUMMARY: Found {len(items)} items for '{' '.join(keywords)}' on {scraper_name} ***\n")
        else:
            logger.warning("No items found")
            print(f"\n*** NO RESULTS: Found 0 items for '{' '.join(keywords)}' on {scraper_name} ***\n")
    
    except Exception as e:
        logger.error(f"Error searching with {scraper_name}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    if len(sys.argv) < 3:
        print("Usage: python test_scrapers.py <scraper_name> <keyword1,keyword2,...> [<price_min> <price_max>]")
        return
    
    scraper_name = sys.argv[1]
    keywords = sys.argv[2].split(',')
    
    filters = {}
    if len(sys.argv) > 3:
        filters['price_min'] = float(sys.argv[3])
    if len(sys.argv) > 4:
        filters['price_max'] = float(sys.argv[4])
    
    with app.app_context():
        test_scraper(scraper_name, keywords, filters)

if __name__ == "__main__":
    main()