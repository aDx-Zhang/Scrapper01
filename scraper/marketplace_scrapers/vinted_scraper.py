"""
Vinted Scraper - For scraping Vinted.pl marketplace
"""
import json
import logging
import re
import urllib.parse
from typing import List, Dict, Any, Optional
from datetime import datetime

import trafilatura
from bs4 import BeautifulSoup

from scraper.base_scraper import BaseScraper, ProxyManager

logger = logging.getLogger(__name__)

class VintedScraper(BaseScraper):
    """Scraper for Vinted.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Vinted scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://www.vinted.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "vinted"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Vinted matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/ubrania?search_text={encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "price_from", filters['price_min'])
        
        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "price_to", filters['price_max'])
        
        if filters.get('brand'):
            brand = urllib.parse.quote(filters['brand'])
            search_url = self._add_url_param(search_url, "brand_id[]", brand)
        
        if filters.get('size'):
            size = urllib.parse.quote(filters['size'])
            search_url = self._add_url_param(search_url, "size_id[]", size)
        
        if filters.get('condition') == 'new':
            search_url = self._add_url_param(search_url, "status_id[]", 6)  # Status 6 is for new items
        
        logger.info(f"Vinted search URL: {search_url}")
        
        # Try to parse search results using various methods
        try:
            # First try with direct HTML parsing
            items = self._parse_search_page(search_url, keywords, filters)
            if items:
                return items
        except Exception as e:
            logger.error(f"Error with direct HTML parsing: {e}")
            
        try:
            # Try with trafilatura if direct parsing fails
            items = self._parse_with_trafilatura(search_url, keywords, filters)
            if items:
                return items
        except Exception as e:
            logger.error(f"Error with trafilatura parsing: {e}")
        
        # If all parsing methods fail, return empty list
        return []
    
    def _add_url_param(self, url: str, param_name: str, param_value: Any) -> str:
        """Add a parameter to the URL"""
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{param_name}={param_value}"
        
    def _parse_search_page(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Vinted search results from the search page directly using HTML parsing"""
        logger.info("Parsing Vinted results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Vinted search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Vinted uses a specific structure for listings
        # Look for catalog items (grid of products)
        listing_containers = soup.select('.feed-grid__item')
        
        if not listing_containers:
            # Fallback to other selectors
            listing_containers = soup.select('.item-box')
            
        if not listing_containers:
            # Another fallback
            listing_containers = soup.select('article')
            
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container.select_one('a')
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title
                title_element = container.select_one('.item-title') or container.select_one('h3')
                title = title_element.text.strip() if title_element else "Unknown Item"
                
                # Extract price
                price_element = container.select_one('.item-price') or container.select_one('.price')
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
                        
                # Extract brand
                brand_element = container.select_one('.item-details .item-brand') or container.select_one('.brand-name')
                brand = brand_element.text.strip() if brand_element else ""
                
                # Extract size
                size_element = container.select_one('.item-details .item-size') or container.select_one('.size')
                size = size_element.text.strip() if size_element else ""
                
                # Extract image
                image_element = container.select_one('img')
                image_url = None
                if image_element:
                    image_url = image_element.get('src') or image_element.get('data-src')
                
                # Create item dictionary
                item = {
                    'title': title,
                    'price': price,
                    'currency': currency,
                    'url': item_url,
                    'image_url': image_url,
                    'marketplace': self.get_marketplace_name(),
                    'location': "Poland",  # Vinted doesn't typically show location in listing cards
                    'description': "",  # Need to get details page for this
                    'brand': brand,
                    'size': size,
                    'seller_name': "Unknown",  # Need to get details page for this
                    'condition': self._extract_condition(container)
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Vinted item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Vinted search results using trafilatura"""
        logger.info("Parsing Vinted results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Vinted search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Try to find product information in JSON
        soup = BeautifulSoup(html_content, 'html.parser')
        script_elements = soup.select('script')
        items = []
        
        for script in script_elements:
            try:
                # Look for window.__INITIAL_STATE__ which usually contains product data in Vinted
                script_text = script.string
                if script_text and "__INITIAL_STATE__" in script_text:
                    # Extract JSON
                    json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', script_text)
                    if json_match:
                        initial_state = json.loads(json_match.group(1))
                        # Vinted's structure varies, need to find the products field
                        if 'catalog' in initial_state and 'items' in initial_state['catalog']:
                            for item_data in initial_state['catalog']['items']:
                                item = self._extract_from_json(item_data)
                                if item and self._passes_filters(item, filters):
                                    items.append(item)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Error parsing JSON: {e}")
        
        # If we got items from JSON, return them
        if items:
            return items
        
        # Otherwise, use trafilatura extracted text to try to identify listings
        listings = re.split(r'\n{2,}', extracted_text)
        
        for listing_text in listings:
            try:
                # Try to extract item information from text
                price_match = re.search(r'(\d+[\s\d]*\d*,?\d*)\s*(?:zł|PLN)', listing_text)
                if not price_match:
                    continue
                
                price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0
                
                # Try to extract brand
                brand_match = re.search(r'(Nike|Adidas|Zara|H&M|Reserved|Mohito|Orsay|New Balance|Puma|Reebok|Calvin Klein)', listing_text)
                brand = brand_match.group(1) if brand_match else ""
                
                # Try to extract size
                size_match = re.search(r'(XS|S|M|L|XL|XXL|36|38|40|42|44|46|48)', listing_text)
                size = size_match.group(1) if size_match else ""
                
                # Create a basic item
                item = {
                    'title': listing_text.split('\n')[0][:100],
                    'price': price,
                    'currency': 'PLN',
                    'url': search_url,  # Don't have specific URL from text extraction
                    'image_url': None,
                    'marketplace': self.get_marketplace_name(),
                    'location': "Poland",
                    'description': listing_text,
                    'brand': brand,
                    'size': size,
                    'seller_name': "Unknown",
                    'condition': "New" if "nowy" in listing_text.lower() or "new" in listing_text.lower() else "Used"
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Vinted text listing: {e}")
                continue
        
        return items
    
    def _extract_from_json(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract product information from JSON data"""
        try:
            item_url = data.get('url', '')
            if item_url and not item_url.startswith('http'):
                item_url = self.base_url + item_url
                
            title = data.get('title', 'Unknown Item')
            
            # Extract price
            price = 0.0
            currency = 'PLN'
            
            if 'price' in data:
                price_str = str(data['price'])
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0
                    
            if 'currency' in data:
                currency = data['currency']
            
            # Extract brand
            brand = data.get('brand', {}).get('title', '') if isinstance(data.get('brand'), dict) else ""
            
            # Extract size
            size = data.get('size', {}).get('title', '') if isinstance(data.get('size'), dict) else ""
            
            # Extract images
            image_url = None
            if 'photos' in data and isinstance(data['photos'], list) and data['photos']:
                photo = data['photos'][0]
                if isinstance(photo, dict):
                    image_url = photo.get('url', None)
            
            # Extract condition
            condition_code = data.get('status_id', 0)
            condition = "New" if condition_code == 6 else "Like new" if condition_code == 1 else "Used"
            
            # Extract seller
            seller_name = "Unknown"
            if 'user' in data and isinstance(data['user'], dict):
                seller_name = data['user'].get('login', "Unknown")
            
            # Create item dict
            return {
                'title': title,
                'price': price,
                'currency': currency,
                'url': item_url,
                'image_url': image_url,
                'marketplace': self.get_marketplace_name(),
                'location': "Poland",
                'description': data.get('description', ''),
                'brand': brand,
                'size': size,
                'seller_name': seller_name,
                'condition': condition
            }
        except Exception as e:
            logger.error(f"Error extracting from JSON: {e}")
            return None
    
    def _extract_condition(self, container) -> str:
        """Extract condition from listing container"""
        condition_element = container.select_one('.item-status .status-text') or container.select_one('.condition')
        if condition_element:
            condition_text = condition_element.text.strip().lower()
            if "now" in condition_text or "nowy" in condition_text:
                return "New"
            elif "idealn" in condition_text:
                return "Like new"
            else:
                return condition_text.capitalize()
                
        # Try to determine from other indicators
        container_text = container.text.lower()
        if "nowy" in container_text or "nowe" in container_text or "new" in container_text:
            return "New"
        elif "idealny" in container_text or "like new" in container_text:
            return "Like new"
            
        return "Used"  # Default to used
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Vinted item"""
        logger.info(f"Getting details for Vinted item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Vinted item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Try to find product data in JSON
        script_elements = soup.select('script')
        for script in script_elements:
            try:
                script_text = script.string
                if script_text and "__INITIAL_STATE__" in script_text:
                    # Extract JSON
                    json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', script_text)
                    if json_match:
                        initial_state = json.loads(json_match.group(1))
                        if 'items' in initial_state and initial_state['items']:
                            # Usually the first item is the main product
                            item_id = list(initial_state['items'].keys())[0]
                            item_data = initial_state['items'][item_id]
                            return self._extract_from_json(item_data)
            except (json.JSONDecodeError, AttributeError, KeyError) as e:
                logger.error(f"Error parsing JSON from script: {e}")
        
        # If JSON extraction fails, try HTML parsing
        
        # Extract title
        title_element = soup.select_one('h1.item-title')
        details['title'] = title_element.text.strip() if title_element else "Unknown Item"
        
        # Extract price
        price_element = soup.select_one('.item-price .price-value')
        price_text = price_element.text.strip() if price_element else "0 zł"
        
        price_match = re.search(r'(\d+[\s\d]*\d*,?\d*)', price_text)
        details['price'] = 0.0
        details['currency'] = "PLN"
        
        if price_match:
            price_str = price_match.group(1).replace(" ", "").replace(",", ".")
            try:
                details['price'] = float(price_str)
            except ValueError:
                details['price'] = 0.0
        
        # Extract description
        description_element = soup.select_one('.item-description-content')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract brand
        brand_element = soup.select_one('.details-list .item-details-list-item:contains("Marka")')
        details['brand'] = ""
        if brand_element:
            brand_value = brand_element.select_one('.item-details-list-item-value')
            if brand_value:
                details['brand'] = brand_value.text.strip()
        
        # Extract size
        size_element = soup.select_one('.details-list .item-details-list-item:contains("Rozmiar")')
        details['size'] = ""
        if size_element:
            size_value = size_element.select_one('.item-details-list-item-value')
            if size_value:
                details['size'] = size_value.text.strip()
        
        # Extract seller information
        seller_element = soup.select_one('.user-login')
        details['seller_name'] = seller_element.text.strip() if seller_element else "Unknown"
        
        # Extract images
        image_elements = soup.select('.item-photos img')
        details['image_urls'] = [img.get('src') for img in image_elements if img.get('src')]
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Extract condition
        condition_element = soup.select_one('.item-details-list-item:contains("Stan")')
        details['condition'] = "Used"  # Default
        if condition_element:
            condition_value = condition_element.select_one('.item-details-list-item-value')
            if condition_value:
                condition_text = condition_value.text.strip().lower()
                if "now" in condition_text or "nowy" in condition_text:
                    details['condition'] = "New"
                elif "idealn" in condition_text:
                    details['condition'] = "Like new"
                else:
                    details['condition'] = condition_value.text.strip()
        
        details['url'] = item_url
        details['marketplace'] = self.get_marketplace_name()
        details['location'] = "Poland"  # Vinted usually doesn't show specific locations
        
        return details
    
    def _passes_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if an item passes all provided filters"""
        # Check price filters
        if filters.get('price_min') is not None and item['price'] < filters['price_min']:
            return False
        
        if filters.get('price_max') is not None and item['price'] > filters['price_max']:
            return False
        
        # Check brand filter
        if filters.get('brand') and item['brand']:
            if filters['brand'].lower() not in item['brand'].lower():
                return False
        
        # Check size filter
        if filters.get('size') and item['size']:
            if filters['size'].lower() != item['size'].lower():
                return False
        
        # Check condition filter
        if filters.get('condition'):
            if filters['condition'] == 'new' and item['condition'] != "New":
                return False
        
        return True