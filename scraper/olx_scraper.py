"""
OLX Scraper - For scraping OLX.pl marketplace
"""
import json
import logging
import re
import traceback
import time
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

import trafilatura
from bs4 import BeautifulSoup
import requests

from scraper.base_scraper import BaseScraper, ProxyManager

logger = logging.getLogger(__name__)

class OLXScraper(BaseScraper):
    """Scraper for OLX.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the OLX scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://www.olx.pl"
        self.search_url = f"{self.base_url}/oferty/q-"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "olx"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on OLX matching the given keywords and filters"""
        logger.info(f"Searching OLX for: {keywords} with filters: {filters}")
        
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build search URL with filters
        search_url = f"{self.search_url}{encoded_query}/"
        
        # Add price filters if available
        params = {}
        if filters.get('price_min') is not None:
            params["search[filter_float_price:from]"] = filters["price_min"]
            logger.debug(f"Added min price filter: {filters['price_min']}")
        if filters.get('price_max') is not None:
            params["search[filter_float_price:to]"] = filters["price_max"]
            logger.debug(f"Added max price filter: {filters['price_max']}")
        
        # Add location filter if available
        if filters.get('location'):
            # For OLX, we would need to convert the location to their ID format
            location = urllib.parse.quote(filters['location'])
            search_url = f"{self.base_url}/{location}/q-{encoded_query}/"
            logger.debug(f"Added location filter: {filters['location']}")
        
        # Combine URL with price parameters
        if params:
            search_url += "?" + urllib.parse.urlencode(params)
        
        logger.info(f"OLX search URL: {search_url}")
        
        # First try API method which usually gives the best results
        try:
            items = self._parse_with_api(search_url, keywords, filters)
            if items:
                logger.info(f"Successfully found {len(items)} items with API method")
                return items
        except Exception as e:
            logger.error(f"Error with API parsing: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Then try trafilatura parsing as a fallback
        try:
            items = self._parse_with_trafilatura(search_url, keywords, filters)
            if items:
                logger.info(f"Successfully found {len(items)} items with trafilatura method")
                return items
        except Exception as e:
            logger.error(f"Error with trafilatura parsing: {e}")
        
        # Finally, try direct HTML parsing as a last resort
        try:
            items = self._parse_search_page(search_url, keywords, filters)
            if items:
                logger.info(f"Successfully found {len(items)} items with direct HTML parsing")
                return items
        except Exception as e:
            logger.error(f"Error with direct HTML parsing: {e}")
            
        # If all parsing methods fail, return empty list
        logger.warning("All parsing methods failed, returning empty list")
        return []
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OLX search results using trafilatura"""
        logger.info("Parsing OLX results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get OLX search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Parse the extracted text to identify items
        items = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all listing containers - try different selectors
        listing_containers = soup.select('div[data-cy="l-card"]')
        
        if not listing_containers:
            # Try alternative selectors
            listing_containers = soup.select('div.css-1sw7q4x')
        
        if not listing_containers:
            # Try another alternative selector
            listing_containers = soup.select('a[data-testid="listing-ad"]')
        
        logger.info(f"Found {len(listing_containers)} OLX listing containers")
        
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container
                if not container.name == 'a':
                    link_element = container.select_one('a')
                
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title - try multiple selectors
                title = "Unknown Title"
                for title_selector in ['h6', 'h5', 'h4', '.css-16v5mdi', '[data-testid="ad-title"]', '.title']:
                    title_element = container.select_one(title_selector)
                    if title_element and title_element.text.strip():
                        title = title_element.text.strip()
                        break
                
                # If title is still unknown, try to find any header element
                if title == "Unknown Title":
                    for header in container.select('h1, h2, h3, h4, h5, h6'):
                        if header.text.strip():
                            title = header.text.strip()
                            break
                
                # Get title from URL as last resort
                if title == "Unknown Title" and 'iphone' in item_url.lower():
                    url_parts = item_url.split('/')
                    for part in url_parts:
                        if 'iphone' in part.lower():
                            # Convert hyphens to spaces and capitalize
                            title = ' '.join(part.split('-')).title()
                            break
                
                # Extract price
                price_element = container.select_one('[data-testid="ad-price"]')
                if not price_element:
                    price_element = container.select_one('.price')
                if not price_element:
                    price_element = container.select_one('.css-10b0gli')
                
                price_text = price_element.text.strip() if price_element else "0 zł"
                
                # Extract price value and currency
                price_match = re.search(r'(\d+[\s\d]*\d*,?\d*)', price_text)
                price = 0.0
                currency = "PLN"
                
                if price_match:
                    price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
                
                # Extract location
                location_element = container.select_one('[data-testid="location-date"]')
                if not location_element:
                    location_element = container.select_one('.css-veheph')
                if not location_element:
                    location_element = container.select_one('.css-p6wsjo')
                
                location = "Unknown"
                posted_at = "Unknown"
                
                if location_element:
                    location_text = location_element.text.strip()
                    location_parts = location_text.split(' - ')
                    if len(location_parts) > 0:
                        location = location_parts[0].strip()
                    if len(location_parts) > 1:
                        posted_at = location_parts[1].strip()
                
                # Extract image URL - try multiple selectors and attributes
                image_url = None
                image_element = container.select_one('img')
                
                if image_element:
                    # Try different image attributes
                    for attr in ['src', 'data-src', 'data-original', 'srcset']:
                        image_url = image_element.get(attr)
                        if image_url:
                            # If it's a srcset, extract the first URL
                            if attr == 'srcset' and ' ' in image_url:
                                image_url = image_url.split(' ')[0]
                            break
                
                # Create item dictionary
                item = {
                    'title': title,
                    'price': price,
                    'currency': currency,
                    'url': item_url,
                    'image_url': image_url,
                    'marketplace': self.get_marketplace_name(),
                    'location': location,
                    'posted_at': posted_at,
                    'seller_name': "Unknown",  # Need to get details page for this
                    'seller_rating': None,     # Need to get details page for this
                    'condition': "Unknown",    # Need to get details page for this
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing OLX item: {e}")
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
            # If we have a keyword query, use it
            if len(keywords) > 0:
                api_params['query'] = " ".join(keywords)
            
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
                    logger.debug(f"API response: {data}")
                    
                    if not isinstance(data, dict):
                        logger.error("API response is not a dictionary")
                        return []
                        
                    offers = data.get('data', [])
                    logger.info(f"Found {len(offers)} offers in API response")
                    
                    if not offers:
                        logger.warning("No offers found in API response")
                        return []
                    
                    # Handle case where data is a dict instead of a list
                    if isinstance(offers, dict):
                        offers = [offers]
                    
                    for offer in offers:
                        try:
                            if not isinstance(offer, dict):
                                logger.debug(f"Skipping non-dict offer: {type(offer)}")
                                continue
                                
                            # Get basic attributes
                            item_id = offer.get('id', '')
                            title = offer.get('title', 'Unknown Title')
                            item_url = offer.get('url', '')
                            
                            # If URL doesn't start with http, add base url
                            if item_url and not item_url.startswith('http'):
                                item_url = self.base_url + item_url
                            
                            # Extract price from different possible locations
                            price = 0.0
                            currency = 'PLN'
                            price_found = False
                            
                            # 1. Try first in key_params
                            key_params = offer.get('key_params', [])
                            if isinstance(key_params, list):
                                for param in key_params:
                                    if isinstance(param, dict) and param.get('key') == 'price':
                                        price_text = param.get('value', '0')
                                        price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', price_text)
                                        if price_match:
                                            price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                            try:
                                                price = float(price_str)
                                                price_found = True
                                            except ValueError:
                                                price = 0.0
                                                
                                        # Extract currency
                                        if 'zł' in price_text:
                                            currency = 'PLN'
                                        elif '€' in price_text:
                                            currency = 'EUR'
                            
                            # 2. Try in regular params if not found yet
                            if not price_found:
                                params = offer.get('params', [])
                                if isinstance(params, list):
                                    for param in params:
                                        if isinstance(param, dict):
                                            param_type = param.get('type')
                                            param_key = param.get('key')
                                            param_name = param.get('name', '')
                                            param_value = param.get('value', {})
                                            
                                            # Different ways price might be represented
                                            is_price = (param_type == 'price' or 
                                                       param_key == 'price' or 
                                                       'price' in param_name.lower() or
                                                       'cena' in param_name.lower())
                                                       
                                            if is_price:
                                                # Extract price based on different structures
                                                if isinstance(param_value, dict):
                                                    value = param_value.get('value')
                                                    if value is not None:
                                                        try:
                                                            price = float(value)
                                                            currency = param_value.get('currency', 'PLN')
                                                            price_found = True
                                                        except (ValueError, TypeError):
                                                            pass
                                                elif 'value' in param:
                                                    value = param.get('value')
                                                    if isinstance(value, (int, float)):
                                                        price = float(value)
                                                        price_found = True
                                                    elif isinstance(value, str):
                                                        # Try to extract number from string
                                                        price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)', value)
                                                        if price_match:
                                                            price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                                            try:
                                                                price = float(price_str)
                                                                price_found = True
                                                            except ValueError:
                                                                pass
                            
                            # 3. Look directly in price field
                            if not price_found and 'price' in offer:
                                price_data = offer.get('price')
                                if isinstance(price_data, dict):
                                    value = price_data.get('value')
                                    if value is not None:
                                        try:
                                            price = float(value)
                                            currency = price_data.get('currency', 'PLN')
                                            price_found = True
                                        except (ValueError, TypeError):
                                            pass
                                elif isinstance(price_data, (int, float)):
                                    price = float(price_data)
                                    price_found = True
                            
                            # 4. Last resort: look at description for price
                            if not price_found:
                                description = offer.get('description', '')
                                if description:
                                    price_match = re.search(r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)\s*zł', description, re.IGNORECASE)
                                    if price_match:
                                        price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                                        try:
                                            price = float(price_str)
                                            price_found = True
                                        except ValueError:
                                            pass
                            
                            # Extract location
                            location = "Unknown"
                            location_data = offer.get('location')
                            if isinstance(location_data, dict):
                                city = location_data.get('city', {})
                                if isinstance(city, dict):
                                    location = city.get('name', "Unknown")
                                elif isinstance(city, str):
                                    location = city
                            
                            # Extract image URL
                            image_url = None
                            photos = offer.get('photos', [])
                            if isinstance(photos, list) and photos:
                                for photo in photos:
                                    if isinstance(photo, dict):
                                        for size in ['link', 'large', 'medium', 'small']:
                                            if size in photo:
                                                image_url = photo[size]
                                                # Fix OLX image URLs with placeholder dimensions
                                                if image_url and '{width}x{height}' in image_url:
                                                    # Use standard size of 640x480 for display
                                                    image_url = image_url.replace('{width}x{height}', '640x480')
                                                break
                                        if image_url:
                                            break
                            
                            # Extract seller info
                            seller_name = "Unknown"
                            seller_rating = None
                            seller_data = offer.get('user', {})
                            if isinstance(seller_data, dict):
                                seller_name = seller_data.get('name', "Unknown")
                                seller_rating_data = seller_data.get('rating')
                                if isinstance(seller_rating_data, dict):
                                    seller_rating = seller_rating_data.get('rating')
                                    if seller_rating is not None:
                                        try:
                                            seller_rating = float(seller_rating)
                                        except (ValueError, TypeError):
                                            seller_rating = None
                            
                            # Extract condition
                            condition = "Unknown"
                            # Check params for condition
                            params = offer.get('params', [])
                            if isinstance(params, list):
                                for param in params:
                                    if isinstance(param, dict):
                                        param_name = param.get('name', '').lower()
                                        if 'condition' in param_name or 'stan' in param_name:
                                            if isinstance(param.get('value'), dict):
                                                condition = param['value'].get('key', "Unknown")
                                            else:
                                                condition = str(param.get('value', "Unknown"))
                            
                            # Create item dictionary
                            item = {
                                'title': title,
                                'price': price,
                                'currency': currency,
                                'url': item_url,
                                'image_url': image_url,
                                'marketplace': self.get_marketplace_name(),
                                'location': location,
                                'posted_at': "Unknown",  # API doesn't provide this directly
                                'seller_name': seller_name,
                                'seller_rating': seller_rating,
                                'condition': condition,
                                'description': offer.get('description', 'No description'),
                            }
                            
                            # Apply filters
                            if self._passes_filters(item, filters):
                                items.append(item)
                        
                        except Exception as e:
                            logger.error(f"Error processing API offer: {e}")
                            logger.debug(traceback.format_exc())
                            continue
                
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding API response: {e}")
                    logger.debug(traceback.format_exc())
            else:
                logger.error(f"API request failed with status code: {response.status_code}")
                logger.debug(f"Response content: {response.text[:500]}")
        
        except Exception as e:
            logger.error(f"Error in API parsing: {e}")
            logger.debug(traceback.format_exc())
        
        return items
    
    def _parse_search_page(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OLX search results from the search page directly"""
        logger.info("Parsing OLX results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get OLX search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Look for the listing cards - try multiple selectors
        listing_containers = soup.select('[data-testid="listing-grid"] > div')
        
        if not listing_containers:
            # Try alternative selectors used on OLX
            listing_containers = soup.select('a[data-cy="listing-ad"]')
        
        if not listing_containers:
            listing_containers = soup.select('div.css-1sw7q4x')
            
        if not listing_containers:
            listing_containers = soup.select('a[href*="/d/oferta/"]')
            
        logger.info(f"Found {len(listing_containers)} OLX listing containers with direct HTML parsing")
        
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container
                if not container.name == 'a':
                    link_element = container.select_one('a[href]')
                
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title - try multiple selectors
                title = "Unknown Title"
                for title_selector in ['h6', 'h5', 'h4', '.css-16v5mdi', '[data-testid="ad-title"]', '.title', 'h1']:
                    title_element = container.select_one(title_selector)
                    if title_element and title_element.text.strip():
                        title = title_element.text.strip()
                        break
                
                # If title is still unknown, try to find any header element
                if title == "Unknown Title":
                    for header in container.select('h1, h2, h3, h4, h5, h6'):
                        if header.text.strip():
                            title = header.text.strip()
                            break
                
                # Try alternate approach by looking at all text nodes for likely titles
                if title == "Unknown Title":
                    for element in container.select('span, p, div'):
                        text = element.text.strip()
                        # Check if text looks like a title (not too short, not too long)
                        if text and len(text) > 10 and len(text) < 100 and not text.startswith('zł') and not re.match(r'^\d+', text):
                            title = text
                            break
                            
                # Get title from URL as last resort
                if title == "Unknown Title" and 'iphone' in item_url.lower():
                    url_parts = item_url.split('/')
                    for part in url_parts:
                        if 'iphone' in part.lower():
                            # Convert hyphens to spaces and capitalize
                            title = ' '.join([word.capitalize() for word in part.split('-')])
                            break
                
                # Extract price - try multiple selectors
                price_element = container.select_one('[data-testid="ad-price"]')
                if not price_element:
                    price_element = container.select_one('.price')
                if not price_element:
                    price_element = container.select_one('.css-10b0gli')
                if not price_element:
                    # Look for anything that might contain price information
                    for element in container.select('p, span, div'):
                        if 'zł' in element.text or 'PLN' in element.text:
                            price_element = element
                            break
                
                price_text = price_element.text.strip() if price_element else "0 zł"
                
                # Extract price value and currency
                price_match = re.search(r'(\d+[\s\d]*\d*,?\d*)', price_text)
                price = 0.0
                currency = "PLN"
                
                if price_match:
                    price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
                
                # Extract location and date
                location_element = container.select_one('[data-testid="location-date"]')
                if not location_element:
                    location_element = container.select_one('.css-veheph')
                if not location_element:
                    location_element = container.select_one('.css-p6wsjo')
                if not location_element:
                    # Try finding any element that might contain location info
                    for element in container.select('p, span'):
                        if any(city in element.text for city in ['Warszawa', 'Kraków', 'Poznań', 'Gdańsk', 'Wrocław', 'Lublin', 'Katowice']):
                            location_element = element
                            break
                
                location = "Unknown"
                posted_at = "Unknown"
                
                if location_element:
                    location_text = location_element.text.strip()
                    # Look for common date patterns
                    date_patterns = [
                        r'(\d{1,2} \w+ \d{4})',
                        r'(\d{1,2} \w+)',
                        r'(dzisiaj|wczoraj)',
                        r'(today|yesterday)'
                    ]
                    
                    for pattern in date_patterns:
                        date_match = re.search(pattern, location_text, re.IGNORECASE)
                        if date_match:
                            posted_at = date_match.group(1)
                            location = location_text.replace(posted_at, '').strip(' -')
                            break
                    
                    if posted_at == "Unknown":
                        # If no date pattern matches, just use the first part as location
                        location_parts = location_text.split(' - ')
                        if len(location_parts) > 0:
                            location = location_parts[0].strip()
                        if len(location_parts) > 1:
                            posted_at = location_parts[1].strip()
                
                # Extract image URL - try different ways
                image_url = None
                for img_selector in ['img', 'source', 'picture img', 'figure img']:
                    image_elements = container.select(img_selector)
                    if image_elements:
                        for image_element in image_elements:
                            # Try different image attributes
                            for attr in ['src', 'data-src', 'data-original', 'srcset']:
                                attr_value = image_element.get(attr)
                                if attr_value:
                                    # If it's a srcset, extract the first URL
                                    if attr == 'srcset' and ' ' in attr_value:
                                        image_url = attr_value.split(' ')[0]
                                    else:
                                        image_url = attr_value
                                        
                                    # Fix OLX image URLs with placeholder dimensions
                                    if image_url and '{width}x{height}' in image_url:
                                        # Use standard size of 640x480 for display
                                        image_url = image_url.replace('{width}x{height}', '640x480')
                                    break
                            
                            if image_url:
                                break
                        
                        if image_url:
                            break
                
                # Create item dictionary
                item = {
                    'title': title,
                    'price': price,
                    'currency': currency,
                    'url': item_url,
                    'image_url': image_url,
                    'marketplace': self.get_marketplace_name(),
                    'location': location,
                    'posted_at': posted_at,
                    'seller_name': "Unknown",  # Need to get details page for this
                    'seller_rating': None,     # Need to get details page for this
                    'condition': "Unknown",    # Need to get details page for this
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing OLX item: {e}")
                continue
        
        return items
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific OLX item"""
        logger.info(f"Getting details for OLX item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get OLX item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Extract title - try multiple selectors
        title = "Unknown Title"
        for title_selector in ['h1.css-1soizd2', 'h1.css-1ld8fwi', 'h1', '[data-cy="ad_title"]', '.css-1oarkq2']:
            title_element = soup.select_one(title_selector)
            if title_element and title_element.text.strip():
                title = title_element.text.strip()
                break
                
        # If still unknown, try to extract from URL
        if title == "Unknown Title" and 'iphone' in item_url.lower():
            url_parts = item_url.split('/')
            for part in url_parts:
                if 'iphone' in part.lower():
                    # Convert hyphens to spaces and capitalize
                    title = ' '.join([word.capitalize() for word in part.split('-')])
                    break
                    
        details['title'] = title
        
        # Extract price - try multiple selectors
        price_text = "0 zł"
        for price_selector in ['h3.css-12vqlj3', 'h3.css-okktvh-text', '.price-label', '[data-testid="ad-price"]']:
            price_element = soup.select_one(price_selector)
            if price_element and price_element.text.strip():
                price_text = price_element.text.strip()
                break
        
        # Extract price value and currency
        price_match = re.search(r'(\d+[\s\d]*\d*,?\d*)', price_text)
        details['price'] = 0.0
        details['currency'] = "PLN"
        
        if price_match:
            price_str = price_match.group(1).replace(" ", "").replace(",", ".")
            try:
                details['price'] = float(price_str)
            except ValueError:
                details['price'] = 0.0
        
        # Extract description - try multiple selectors
        description = "No description available"
        for desc_selector in ['div[data-cy="ad_description"]', '.css-g5mtbi-text', '.descriptioncontent']:
            description_element = soup.select_one(desc_selector)
            if description_element and description_element.text.strip():
                description = description_element.text.strip()
                break
                
        details['description'] = description
        
        # Extract location - try multiple selectors
        location = "Unknown"
        for location_selector in ['p.css-1cju8pu', '.css-1cju8pu', '[data-testid="location-date"]']:
            location_element = soup.select_one(location_selector)
            if location_element and location_element.text.strip():
                location = location_element.text.strip()
                break
                
        details['location'] = location
        
        # Extract seller information - try multiple selectors
        seller_name = "Unknown"
        for seller_selector in ['h2.css-u8mbra-text', '.userdetails .username', '[data-testid="user-name"]']:
            seller_element = soup.select_one(seller_selector)
            if seller_element and seller_element.text.strip():
                seller_name = seller_element.text.strip()
                break
                
        details['seller_name'] = seller_name
        
        # Extract images - try multiple selectors
        image_urls = []
        for img_container in ['div.swiper-zoom-container img', '.swiper-slide img', '.photo-item img', '[data-testid="gallery"] img']:
            image_elements = soup.select(img_container)
            if image_elements:
                for img in image_elements:
                    for attr in ['src', 'data-src', 'data-original', 'srcset']:
                        img_url = img.get(attr)
                        if img_url:
                            # If it's a srcset, extract the first URL
                            if attr == 'srcset' and ' ' in img_url:
                                img_url = img_url.split(' ')[0]
                            
                            # Fix OLX image URLs with placeholder dimensions
                            if img_url and '{width}x{height}' in img_url:
                                # Use standard size of 640x480 for display
                                img_url = img_url.replace('{width}x{height}', '640x480')
                                
                            # Only add unique URLs
                            if img_url not in image_urls:
                                image_urls.append(img_url)
                                
                            break
                                
        details['image_urls'] = image_urls
        details['image_url'] = image_urls[0] if image_urls else None
        
        # Extract additional details - try multiple selectors
        additional_details = {}
        for details_table_selector in ['ul.css-sfcl1s li', '.descriptioncontent table tr', '.details-list li']:
            details_table = soup.select(details_table_selector)
            
            for detail in details_table:
                try:
                    # Try different selector patterns for key-value pairs
                    key_element = None
                    value_element = None
                    
                    # Pattern 1: p.css-b5m1rv + p.css-1bcbe4x
                    key_element = detail.select_one('p.css-b5m1rv') or detail.select_one('.key')
                    value_element = detail.select_one('p.css-1bcbe4x') or detail.select_one('.value')
                    
                    # Pattern 2: th + td 
                    if not (key_element and value_element):
                        key_element = detail.select_one('th')
                        value_element = detail.select_one('td')
                    
                    # Pattern 3: strong + text
                    if not (key_element and value_element) and detail.select_one('strong'):
                        key_element = detail.select_one('strong')
                        # Get the text after the strong element
                        if key_element and key_element.next_sibling:
                            value_element = key_element.next_sibling
                    
                    if key_element and value_element:
                        key = key_element.text.strip() if hasattr(key_element, 'text') else str(key_element).strip()
                        value = value_element.text.strip() if hasattr(value_element, 'text') else str(value_element).strip()
                        
                        if key and value:
                            additional_details[key] = value
                            
                            # Try to extract condition information
                            if key.lower() in ['stan', 'state', 'condition']:
                                details['condition'] = value
                except Exception as e:
                    logger.error(f"Error parsing detail element: {e}")
                    continue
            
            # If we found some details, no need to try other selectors
            if additional_details:
                break
                
        details['additional_data'] = additional_details
        details['url'] = item_url
        details['marketplace'] = self.get_marketplace_name()
        
        # Set condition to "Unknown" if not found
        if 'condition' not in details:
            details['condition'] = "Unknown"
        
        return details
    
    def _passes_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if an item passes all provided filters"""
        # Check price filters
        if filters.get('price_min') is not None and item['price'] < filters['price_min']:
            return False
        
        if filters.get('price_max') is not None and item['price'] > filters['price_max']:
            return False
        
        # Check location filter (case insensitive partial match)
        if filters.get('location') and filters['location'].lower() not in item['location'].lower():
            return False
        
        # Check condition filter
        if filters.get('condition') and item['condition'] != "Unknown":
            if filters['condition'].lower() not in item['condition'].lower():
                return False
        
        return True