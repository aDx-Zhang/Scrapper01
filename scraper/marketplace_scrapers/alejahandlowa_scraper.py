"""
Aleja Handlowa Scraper - For scraping alejahandlowa.pl marketplace
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

class AlejaHandlowaScraper(BaseScraper):
    """Scraper for alejahandlowa.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Aleja Handlowa scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://alejahandlowa.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "alejahandlowa"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Aleja Handlowa matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/search?query={encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "price_min", filters['price_min'])
        
        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "price_max", filters['price_max'])
        
        if filters.get('category'):
            category = urllib.parse.quote(filters['category'])
            search_url = self._add_url_param(search_url, "category", category)
        
        logger.info(f"Aleja Handlowa search URL: {search_url}")
        
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
        """Parse Aleja Handlowa search results from the search page directly using HTML parsing"""
        logger.info("Parsing Aleja Handlowa results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Aleja Handlowa search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Aleja Handlowa uses a specific structure for listings
        # Look for product listings
        listing_containers = soup.select('.product-item')
        
        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('.product-card')
            
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
                title_element = container.select_one('.product-title') or container.select_one('h3')
                title = title_element.text.strip() if title_element else "Unknown Item"
                
                # Extract price
                price_element = container.select_one('.product-price')
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
                        
                # Extract description
                description_element = container.select_one('.product-description')
                description = description_element.text.strip() if description_element else ""
                
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
                    'location': "Poland",  # Aleja Handlowa might not show locations
                    'description': description,
                    'seller_name': self._extract_seller_name(container),
                    'condition': "New"  # Typically new items in this marketplace
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Aleja Handlowa item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Aleja Handlowa search results using trafilatura"""
        logger.info("Parsing Aleja Handlowa results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Aleja Handlowa search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Aleja Handlowa might use structured data
        soup = BeautifulSoup(html_content, 'html.parser')
        script_elements = soup.select('script[type="application/ld+json"]')
        items = []
        
        for script in script_elements:
            try:
                data = json.loads(script.string)
                
                # Check for product data
                if isinstance(data, dict) and data.get('@type') == 'ItemList' and 'itemListElement' in data:
                    for item_data in data['itemListElement']:
                        if isinstance(item_data, dict) and 'item' in item_data:
                            product = item_data['item']
                            if product.get('@type') == 'Product':
                                item = self._extract_from_jsonld(product)
                                if item and self._passes_filters(item, filters):
                                    items.append(item)
                
                # Check if it's a single product
                elif isinstance(data, dict) and data.get('@type') == 'Product':
                    item = self._extract_from_jsonld(data)
                    if item and self._passes_filters(item, filters):
                        items.append(item)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Error parsing JSON-LD: {e}")
        
        # If we got items from JSON-LD, return them
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
                    'seller_name': "Unknown",
                    'condition': "New"  # Typically new items in this marketplace
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Aleja Handlowa text listing: {e}")
                continue
        
        return items
    
    def _extract_from_jsonld(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract product information from JSON-LD structured data"""
        try:
            title = data.get('name', 'Unknown Item')
            
            # Extract price
            price = 0.0
            currency = 'PLN'
            
            if 'offers' in data:
                offer = data['offers']
                if isinstance(offer, list) and offer:
                    offer = offer[0]
                
                if isinstance(offer, dict):
                    price_str = str(offer.get('price', '0'))
                    currency = offer.get('priceCurrency', 'PLN')
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
            
            # Extract URL
            url = data.get('url', '')
            if url and not url.startswith('http'):
                url = self.base_url + url
            
            # Extract image
            image_url = None
            if 'image' in data:
                image = data['image']
                if isinstance(image, list) and image:
                    image_url = image[0]
                else:
                    image_url = image
            
            # Extract description
            description = data.get('description', '')
            
            # Extract seller (might not be available in JSON-LD)
            seller_name = "Unknown"
            if 'brand' in data and isinstance(data['brand'], dict):
                seller_name = data['brand'].get('name', "Unknown")
            
            # Create the item
            return {
                'title': title,
                'price': price,
                'currency': currency,
                'url': url,
                'image_url': image_url,
                'marketplace': self.get_marketplace_name(),
                'location': "Poland",
                'description': description,
                'seller_name': seller_name,
                'condition': "New"  # Typically new items in this marketplace
            }
        except Exception as e:
            logger.error(f"Error extracting from JSON-LD: {e}")
            return None
    
    def _extract_seller_name(self, container) -> str:
        """Extract seller name from listing container"""
        seller_element = container.select_one('.seller-name') or container.select_one('.brand')
        if seller_element:
            return seller_element.text.strip()
        return "Unknown"
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Aleja Handlowa item"""
        logger.info(f"Getting details for Aleja Handlowa item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Aleja Handlowa item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Try to get structured data first
        script_elements = soup.select('script[type="application/ld+json"]')
        for script in script_elements:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    extracted = self._extract_from_jsonld(data)
                    if extracted:
                        return extracted
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Extract title
        title_element = soup.select_one('h1')
        details['title'] = title_element.text.strip() if title_element else "Unknown Item"
        
        # Extract price
        price_element = soup.select_one('.product-price')
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
        description_element = soup.select_one('.product-description')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract seller information
        seller_element = soup.select_one('.seller-name') or soup.select_one('.brand')
        details['seller_name'] = seller_element.text.strip() if seller_element else "Unknown"
        
        # Extract images
        image_elements = soup.select('.product-gallery img')
        details['image_urls'] = [img.get('src') for img in image_elements if img.get('src')]
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Product attributes
        attributes = {}
        attribute_elements = soup.select('.product-attributes .attribute')
        for attr_elem in attribute_elements:
            try:
                name_elem = attr_elem.select_one('.attribute-name')
                value_elem = attr_elem.select_one('.attribute-value')
                if name_elem and value_elem:
                    attributes[name_elem.text.strip()] = value_elem.text.strip()
            except Exception:
                continue
        
        details['attributes'] = attributes
        details['url'] = item_url
        details['marketplace'] = self.get_marketplace_name()
        details['location'] = "Poland"
        details['condition'] = "New"  # Typically new items in this marketplace
        
        return details
    
    def _passes_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if an item passes all provided filters"""
        # Check price filters
        if filters.get('price_min') is not None and item['price'] < filters['price_min']:
            return False
        
        if filters.get('price_max') is not None and item['price'] > filters['price_max']:
            return False
        
        # Check category filter - would need to extract from URL or other data
        # if filters.get('category'):
        #    if item.get('category') and filters['category'].lower() not in item['category'].lower():
        #        return False
        
        return True