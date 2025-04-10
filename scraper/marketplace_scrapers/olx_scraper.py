import logging
import re
import json
import time
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs
import traceback

from bs4 import BeautifulSoup
import trafilatura
import requests

from scraper.base_scraper import BaseScraper
from scraper.proxy_manager import ProxyManager
from utils.text_matching import fuzzy_match_keywords

logger = logging.getLogger(__name__)

class OLXScraper(BaseScraper):
    """Scraper for OLX.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        super().__init__(proxy_manager)
        self.base_url = "https://www.olx.pl"
        
    def get_marketplace_name(self) -> str:
        return "OLX"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on OLX matching the given keywords and filters"""
        logger.info(f"Searching OLX for: {keywords} with filters: {filters}")
        
        items = []
        query = " ".join(keywords)
        logger.debug(f"Constructed search query: {query}")
        
        # Build search URL with filters
        params = {
            "q": query
        }
        
        # Add price filters
        if filters.get("price_min") is not None:
            params["search[filter_float_price:from]"] = filters["price_min"]
            logger.debug(f"Added min price filter: {filters['price_min']}")
        if filters.get("price_max") is not None:
            params["search[filter_float_price:to]"] = filters["price_max"]
            logger.debug(f"Added max price filter: {filters['price_max']}")
            
        # Add location filter
        if filters.get("location"):
            params["search[city_id]"] = filters["location"]
            logger.debug(f"Added location filter: {filters['location']}")
            
        search_url = f"{self.base_url}/oferty/q-{query}/"
        if len(params) > 1:  # If we have more params than just the query
            search_url = f"{self.base_url}/oferty/?{urlencode(params)}"
        
        logger.info(f"Searching with URL: {search_url}")
        
        # Try advanced trafilatura approach first
        try:
            items = self._parse_with_trafilatura(search_url, keywords, filters)
            if items:
                logger.info(f"Successfully parsed {len(items)} items with trafilatura")
                return items
        except Exception as e:
            logger.warning(f"Trafilatura parsing failed: {str(e)}")
            logger.debug(traceback.format_exc())
        
        # Try different parsing approaches as a fallback
        return self._parse_with_api(search_url, keywords, filters)
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OLX search results using trafilatura"""
        items = []
        
        # Use trafilatura to download the content
        downloaded = trafilatura.fetch_url(search_url)
        if not downloaded:
            logger.warning("Failed to download content with trafilatura")
            return []
            
        # Save the raw HTML for debugging
        with open('olx_search_response.html', 'w') as f:
            f.write(downloaded)
        
        # Extract all links that could be ads
        soup = BeautifulSoup(downloaded, 'html.parser')
        ad_links = []
        
        # Find all anchors with href containing "/d/", which is typical for OLX ad URLs
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/d/' in href and href.startswith('https://www.olx.pl'):
                ad_links.append(href)
                
        logger.info(f"Found {len(ad_links)} potential ad links on page")
        
        # Process unique links only
        unique_links = list(set(ad_links))
        
        for i, link in enumerate(unique_links[:20]):  # Limit to first 20 to avoid too many requests
            logger.debug(f"Processing link {i+1}/{len(unique_links[:20])}: {link}")
            try:
                # Get item details for each link
                item_details = self.get_item_details(link)
                
                # Apply filters
                passes_filters = self._passes_filters(item_details, filters)
                
                # Check if title matches keywords
                title = item_details.get("title", "")
                matches_keywords = any(keyword.lower() in title.lower() for keyword in keywords)
                
                if passes_filters and matches_keywords:
                    logger.info(f"Found matching item: {title} - {item_details.get('price', 0)} {item_details.get('currency', 'PLN')}")
                    items.append(item_details)
                
                # Add a small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing link {link}: {str(e)}")
                continue
                
        return items
    
    def _parse_with_api(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Try to parse results using OLX API endpoints"""
        items = []
        
        try:
            # Extract query parameters
            parsed_url = urlparse(search_url)
            query_params = parse_qs(parsed_url.query)
            
            # Create API URL
            api_url = f"{self.base_url}/api/v1/offers/"
            
            # Add query parameters
            api_params = {}
            if 'q' in query_params:
                api_params['query'] = query_params['q'][0]
            
            # Add price filters
            if filters.get("price_min") is not None:
                api_params['filter_float_price:from'] = filters["price_min"]
            if filters.get("price_max") is not None:
                api_params['filter_float_price:to'] = filters["price_max"]
                
            # Add location
            if filters.get("location"):
                api_params['city_id'] = filters["location"]
                
            # Add sorting and limit
            api_params['sort_by'] = 'created_at:desc'
            api_params['limit'] = 50
            
            # Make API request
            headers = {
                'User-Agent': self.session.headers['User-Agent'],
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Making API request to: {api_url} with params: {api_params}")
            
            response = self.session.get(api_url, params=api_params, headers=headers)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Debug the entire data structure
                    logger.info(f"API response structure keys: {data.keys() if isinstance(data, dict) else 'Not a dict'}")
                    if isinstance(data, dict):
                        data_content = data.get('data', [])
                        logger.info(f"Data content type: {type(data_content)}")
                        if isinstance(data_content, list) and data_content:
                            logger.info(f"First item keys: {data_content[0].keys() if isinstance(data_content[0], dict) else 'Not a dict'}")
                            
                            # Log detailed info about the first offer
                            first_offer = data_content[0]
                            if isinstance(first_offer, dict):
                                logger.info(f"Example offer details:")
                                logger.info(f"  Title: {first_offer.get('title')}")
                                logger.info(f"  URL: {first_offer.get('url')}")
                                
                                # Check params structure
                                params = first_offer.get('params', [])
                                if isinstance(params, list):
                                    logger.info(f"  Params count: {len(params)}")
                                    for idx, param in enumerate(params):
                                        if isinstance(param, dict):
                                            if param.get('type') == 'price' or param.get('key') == 'price':
                                                logger.info(f"  PRICE PARAM FOUND: {param}")
                                                
                        elif isinstance(data_content, dict):
                            logger.info(f"Data content keys: {data_content.keys()}")
                    
                    offers = data.get('data', [])
                    if isinstance(offers, dict):
                        # Handle the case where data is a dict instead of a list
                        offers = [offers]
                    
                    for offer in offers:
                        try:
                            # Debug the structure
                            logger.debug(f"API offer structure: {type(offer)}")
                            if isinstance(offer, list):
                                logger.debug("Offer is a list, skipping")
                                continue
                                
                            # Extract price from key_params
                            price = 0.0
                            currency = 'PLN'
                            # Debug all offer data to understand structure
                            logger.info(f"Full offer keys: {offer.keys()}")
                            
                            # Try to find price in different locations
                            # 1. First check key_params
                            key_params = offer.get('key_params', [])
                            logger.info(f"key_params type: {type(key_params)}, content: {key_params}")
                            
                            if isinstance(key_params, list) and key_params:
                                for param in key_params:
                                    logger.info(f"Processing param: {param}")
                                    if isinstance(param, dict) and param.get('key') == 'price':
                                        price_text = param.get('value', '0')
                                        logger.info(f"Found price text in key_params: {price_text}")
                                        # Parse price from string like "1 900 zł"
                                        price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_text)
                                        if price_match:
                                            price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                            logger.info(f"Extracted price string: {price_str}")
                                            try:
                                                price = float(price_str)
                                                logger.info(f"Converted to float: {price}")
                                            except ValueError:
                                                logger.error(f"Could not convert price string to float: {price_str}")
                                                price = 0.0
                                        # Extract currency
                                        if 'zł' in price_text:
                                            currency = 'PLN'
                                        elif '€' in price_text:
                                            currency = 'EUR'
                                        logger.info(f"Set currency to: {currency}")
                            
                            # 2. Check regular params if key_params didn't work
                            if price == 0.0:
                                params = offer.get('params', [])
                                logger.info(f"Params type: {type(params)}, length: {len(params) if isinstance(params, list) else 'N/A'}")
                                
                                if isinstance(params, list):
                                    for param in params:
                                        if isinstance(param, dict):
                                            # Check for price parameter - different ways to detect it
                                            param_type = param.get('type')
                                            param_key = param.get('key')
                                            
                                            # OLX stores price in a param with type=price
                                            if param_type in ['price', 'arranged'] or (param_key and 'price' in param_key):
                                                logger.info(f"Found price parameter: {param}")
                                                # Get the raw value - could be number or string
                                                price_value = param.get('value')
                                                
                                                # Handle numeric price directly
                                                if isinstance(price_value, (int, float)):
                                                    price = float(price_value)
                                                    logger.info(f"Found direct numeric price in params: {price}")
                                                    
                                                    # Also get currency if available
                                                    param_currency = param.get('currency')
                                                    if param_currency:
                                                        currency = param_currency
                                                        logger.info(f"Found currency in params: {currency}")
                                                
                                                # Handle dictionary price (which has a 'value' key)
                                                elif isinstance(price_value, dict) and 'value' in price_value:
                                                    dict_value = price_value.get('value')
                                                    if isinstance(dict_value, (int, float)):
                                                        price = float(dict_value)
                                                        logger.info(f"Found nested numeric price in params: {price}")
                                                        
                                                        # Check for currency in the nested dict
                                                        nested_currency = price_value.get('currency')
                                                        if nested_currency:
                                                            currency = nested_currency
                                                            logger.info(f"Found nested currency in params: {currency}")
                                                
                                                # Handle string price
                                                elif isinstance(price_value, str):
                                                    logger.info(f"Found price text in params: {price_value}")
                                                    price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_value)
                                                    if price_match:
                                                        price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                                        try:
                                                            price = float(price_str)
                                                            logger.info(f"Converted string to float from params: {price}")
                                                        except ValueError:
                                                            logger.error(f"Could not convert price string from params to float: {price_str}")
                                                
                                                # Try to get formatted price label if we haven't found a price yet
                                                if price == 0.0 and param.get('label'):
                                                    label = param.get('label')
                                                    logger.info(f"Trying to extract price from label: {label}")
                                                    price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', label)
                                                    if price_match:
                                                        price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                                        try:
                                                            price = float(price_str)
                                                            logger.info(f"Extracted price from label: {price}")
                                                        except ValueError:
                                                            logger.error(f"Could not convert label price string to float: {price_str}")
                                
                            # 3. Look for price in the title as a last resort
                            if price == 0.0:
                                title = offer.get('title', '')
                                logger.info(f"Searching for price in title: {title}")
                                price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)\s*zł', title)
                                if price_match:
                                    price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                    try:
                                        price = float(price_str)
                                        logger.info(f"Extracted price from title: {price}")
                                    except ValueError:
                                        logger.error(f"Could not convert price string from title to float: {price_str}")
                            
                            item = {
                                "title": offer.get('title', ''),
                                "price": price,
                                "currency": currency,
                                "url": offer.get('url', ''),
                                "image_url": offer.get('photos', [{}])[0].get('url', '') if isinstance(offer.get('photos'), list) and offer.get('photos') else '',
                                "location": offer.get('location', {}).get('city', {}).get('name', '') if isinstance(offer.get('location'), dict) else '',
                                "seller_name": offer.get('user', {}).get('name', '') if isinstance(offer.get('user'), dict) else '',
                                "seller_rating": None,
                                "marketplace": "OLX",
                                "description": offer.get('description', ''),
                                "condition": '',
                                "additional_data": {}
                            }
                            
                            # Try to extract condition and other parameters from params
                            params = offer.get('params', [])
                            if isinstance(params, list):
                                for param in params:
                                    if isinstance(param, dict):
                                        if param.get('key') == 'state':
                                            item["condition"] = param.get('value', '')
                                        # Store other parameters in additional_data
                                        key = param.get('key')
                                        value = param.get('value')
                                        if key and value:
                                            item["additional_data"][key] = value
                            
                            passes_filters = self._passes_filters(item, filters)
                            matches_keywords = fuzzy_match_keywords(item['title'], keywords, threshold=70)
                            
                            if passes_filters and matches_keywords:
                                logger.info(f"Found matching item from API: {item['title']} - {item['price']} {item['currency']}")
                                items.append(item)
                                
                        except Exception as e:
                            logger.error(f"Error processing API offer: {str(e)}")
                            continue
                            
                except json.JSONDecodeError:
                    logger.error("Failed to parse API response as JSON")
            else:
                logger.warning(f"API request failed with status code: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error using API method: {str(e)}")
            logger.debug(traceback.format_exc())
            
        # If API approach failed, try backup approach - directly parse search page
        if not items:
            logger.info("API approach failed, trying to parse search results page directly")
            items = self._parse_search_page(search_url, keywords, filters)
            
        return items
    
    def _parse_search_page(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OLX search results from the search page directly"""
        items = []
        
        response = self.get_with_retry(search_url)
        if not response:
            logger.error(f"Failed to get response from URL: {search_url}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Look for any links that might be ads
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/d/' in href and href.startswith('https://www.olx.pl'):
                try:
                    # Get the title from the nearest heading element
                    title_elem = a_tag.find('h6') or a_tag.find('h5') or a_tag.find('h4') or a_tag.find('h3')
                    title = title_elem.text.strip() if title_elem else ""
                    
                    # Check if title matches keywords
                    if not any(keyword.lower() in title.lower() for keyword in keywords):
                        continue
                    
                    # Extract price if available
                    price_text = "0 zł"
                    price_elem = a_tag.find('p', {'data-testid': 'ad-price'})
                    if price_elem:
                        price_text = price_elem.text.strip()
                    
                    # Parse price with regex
                    price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_text)
                    price_str = price_match.group(1) if price_match else "0"
                    try:
                        price = float(price_str.replace(" ", "").replace(",", "."))
                    except ValueError:
                        price = 0.0
                    
                    # Extract currency
                    currency = "PLN"
                    if "zł" in price_text:
                        currency = "PLN"
                    elif "€" in price_text:
                        currency = "EUR"
                    
                    # Extract location
                    location = ""
                    location_elem = a_tag.find('p', {'data-testid': 'location-date'})
                    if location_elem:
                        location_text = location_elem.text.strip()
                        location = location_text.split(" - ")[0] if " - " in location_text else location_text
                    
                    # Extract image if available
                    image_url = ""
                    img_elem = a_tag.find('img')
                    if img_elem and img_elem.has_attr('src'):
                        image_url = img_elem['src']
                    
                    # Create item dictionary
                    item = {
                        "title": title,
                        "price": price,
                        "currency": currency,
                        "url": href,
                        "image_url": image_url,
                        "location": location,
                        "seller_name": "",
                        "seller_rating": None,
                        "marketplace": "OLX",
                        "description": "",
                        "condition": "",
                        "additional_data": {}
                    }
                    
                    # Apply price filters
                    if filters.get("price_min") is not None and price < filters["price_min"]:
                        continue
                    if filters.get("price_max") is not None and price > filters["price_max"]:
                        continue
                    
                    # Apply location filter
                    if filters.get("location") and location and filters["location"].lower() not in location.lower():
                        continue
                    
                    logger.info(f"Found matching item from page: {title} - {price} {currency}")
                    items.append(item)
                    
                except Exception as e:
                    logger.error(f"Error processing search page item: {str(e)}")
                    continue
        
        return items
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific OLX item"""
        logger.info(f"Getting details for OLX item: {item_url}")
        
        item_details = {
            "title": "",
            "price": 0.0,
            "currency": "PLN",
            "url": item_url,
            "image_url": "",
            "location": "",
            "seller_name": "",
            "seller_rating": None,
            "marketplace": "OLX",
            "description": "",
            "condition": "",
            "additional_data": {}
        }
        
        try:
            # Try using trafilatura for extraction first
            downloaded = trafilatura.fetch_url(item_url)
            if downloaded:
                # Extract main text content
                extracted_text = trafilatura.extract(downloaded)
                if extracted_text:
                    item_details["description"] = extracted_text
                
                # Parse with BeautifulSoup for structured data
                soup = BeautifulSoup(downloaded, "html.parser")
                
                # Try to find JSON-LD data which often contains structured product information
                json_ld = None
                for script in soup.find_all("script", {"type": "application/ld+json"}):
                    try:
                        data = json.loads(script.string)
                        if "@type" in data and data["@type"] in ["Product", "Offer"]:
                            json_ld = data
                            break
                    except (json.JSONDecodeError, AttributeError):
                        continue
                
                if json_ld:
                    if "name" in json_ld:
                        item_details["title"] = json_ld["name"]
                    if "offers" in json_ld and "price" in json_ld["offers"]:
                        try:
                            item_details["price"] = float(json_ld["offers"]["price"])
                        except (ValueError, TypeError):
                            pass
                    if "offers" in json_ld and "priceCurrency" in json_ld["offers"]:
                        item_details["currency"] = json_ld["offers"]["priceCurrency"]
                    if "image" in json_ld:
                        if isinstance(json_ld["image"], list) and json_ld["image"]:
                            item_details["image_url"] = json_ld["image"][0]
                        elif isinstance(json_ld["image"], str):
                            item_details["image_url"] = json_ld["image"]
                
                # Extract title if not found in JSON-LD
                if not item_details["title"]:
                    title_elem = soup.find("h1") or soup.find("h2")
                    if title_elem:
                        item_details["title"] = title_elem.text.strip()
                
                # Extract price if not found in JSON-LD
                if item_details["price"] == 0.0:
                    price_elems = soup.find_all(["span", "div", "h3"], string=re.compile(r'\d+\s*zł|\d+\s*PLN'))
                    if price_elems:
                        price_text = price_elems[0].text.strip()
                        price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_text)
                        if price_match:
                            price_str = price_match.group(1)
                            try:
                                item_details["price"] = float(price_str.replace(" ", "").replace(",", "."))
                            except ValueError:
                                pass
                
                # Extract image if not found in JSON-LD
                if not item_details["image_url"]:
                    img_elems = soup.find_all("img")
                    for img in img_elems:
                        if img.get("src") and img.get("alt") and item_details["title"].lower() in img.get("alt").lower():
                            item_details["image_url"] = img.get("src")
                            break
                    
                    # If still no image, take the first large image
                    if not item_details["image_url"] and img_elems:
                        for img in img_elems:
                            if img.get("src") and (img.get("width") is None or int(img.get("width", "0")) > 200):
                                item_details["image_url"] = img.get("src")
                                break
                
                # Extract location
                location_patterns = [
                    re.compile(r'Lokalizacja:?\s*([^,]+)'),
                    re.compile(r'Location:?\s*([^,]+)')
                ]
                
                for pattern in location_patterns:
                    if extracted_text:
                        match = pattern.search(extracted_text)
                        if match:
                            item_details["location"] = match.group(1).strip()
                            break
                
                # Extract seller name
                seller_patterns = [
                    re.compile(r'Sprzedający:?\s*([^\n]+)'),
                    re.compile(r'Seller:?\s*([^\n]+)')
                ]
                
                for pattern in seller_patterns:
                    if extracted_text:
                        match = pattern.search(extracted_text)
                        if match:
                            item_details["seller_name"] = match.group(1).strip()
                            break
                
                # Extract condition
                condition_patterns = [
                    re.compile(r'Stan:?\s*([^\n]+)'),
                    re.compile(r'Condition:?\s*([^\n]+)')
                ]
                
                for pattern in condition_patterns:
                    if extracted_text:
                        match = pattern.search(extracted_text)
                        if match:
                            item_details["condition"] = match.group(1).strip()
                            break
            
            # If trafilatura extraction failed, try classic request and parsing approach
            if not item_details["title"]:
                response = self.get_with_retry(item_url)
                if response:
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # Extract title
                    title_elem = soup.select_one("h1.css-1soizd2") or soup.select_one("h1") or soup.select_one("h2")
                    if title_elem:
                        item_details["title"] = title_elem.text.strip()
                    
                    # Extract price
                    price_elem = soup.select_one("h3.css-12vqlj3") or soup.select_one("div.price-label")
                    if price_elem:
                        price_text = price_elem.text.strip()
                        price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_text)
                        if price_match:
                            price_str = price_match.group(1)
                            try:
                                item_details["price"] = float(price_str.replace(" ", "").replace(",", "."))
                            except ValueError:
                                pass
                        
                        # Extract currency
                        if "zł" in price_text:
                            item_details["currency"] = "PLN"
                        elif "€" in price_text:
                            item_details["currency"] = "EUR"
                    
                    # Extract image
                    img_elem = soup.select_one("div.swiper-zoom-container img") or soup.select_one("img.css-1bmvjcs")
                    if img_elem and img_elem.has_attr("src"):
                        item_details["image_url"] = img_elem["src"]
                    
                    # Extract description
                    desc_elem = soup.select_one("div[data-cy='ad_description']") or soup.select_one("div.css-g5mtbi-Text")
                    if desc_elem:
                        item_details["description"] = desc_elem.text.strip()
                    
                    # Extract location
                    location_elem = soup.select_one("a[data-testid='map-link']") or soup.select_one("p.css-7layhd")
                    if location_elem:
                        item_details["location"] = location_elem.text.strip()
                    
                    # Extract seller name
                    seller_elem = soup.select_one("h2.css-owpmn2-Text") or soup.select_one("h4.css-1rbjef7-Text")
                    if seller_elem:
                        item_details["seller_name"] = seller_elem.text.strip()
                    
                    # Extract condition if available (in parameters table)
                    params = soup.select("ul.css-1k5cqfg li") or soup.select("ul.css-sfcl1s li")
                    for param in params:
                        param_text = param.text.strip()
                        if "Stan:" in param_text:
                            item_details["condition"] = param_text.replace("Stan:", "").strip()
        
        except Exception as e:
            logger.error(f"Error parsing OLX item details: {str(e)}")
            logger.debug(traceback.format_exc())
            
        return item_details
        
    def _passes_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if an item passes all provided filters"""
        # Price filter
        if filters.get("price_min") is not None and item["price"] < filters["price_min"]:
            return False
        if filters.get("price_max") is not None and item["price"] > filters["price_max"]:
            return False
            
        # Location filter
        if filters.get("location") and filters["location"].lower() not in item.get("location", "").lower():
            return False
            
        # We can't filter by seller rating on OLX as it's not available
            
        # Condition filter - will be checked when we have item details
        if filters.get("condition") and item.get("condition") and filters["condition"].lower() not in item["condition"].lower():
            return False
            
        return True
