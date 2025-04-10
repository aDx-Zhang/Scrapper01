"""
Sprzedajemy Scraper - For scraping Sprzedajemy.pl marketplace
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

class SprzedajemyScraper(BaseScraper):
    """Scraper for Sprzedajemy.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Sprzedajemy scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://sprzedajemy.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "sprzedajemy"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Sprzedajemy matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/szukaj?string={encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "price_min", filters['price_min'])
        
        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "price_max", filters['price_max'])
        
        if filters.get('location'):
            location = urllib.parse.quote(filters['location'])
            search_url = self._add_url_param(search_url, "location", location)
        
        if filters.get('category_id'):
            search_url = self._add_url_param(search_url, "category_id", filters['category_id'])
        
        logger.info(f"Sprzedajemy search URL: {search_url}")
        
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
        """Parse Sprzedajemy search results from the search page directly using HTML parsing"""
        logger.info("Parsing Sprzedajemy results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Sprzedajemy search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Sprzedajemy uses a specific structure for listings
        # Look for listing containers
        listing_containers = soup.select('.offer')
        
        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('.listing-item')
            
        if not listing_containers:
            # Another fallback
            listing_containers = soup.select('article')
            
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container.select_one('a.offer__title') or container.select_one('a[href*="/ogloszenie/"]')
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title
                title_element = container.select_one('.offer__title') or container.select_one('h2')
                title = title_element.text.strip() if title_element else "Unknown Item"
                
                # Extract price
                price_element = container.select_one('.offer__price') or container.select_one('.price')
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
                location_element = container.select_one('.offer__location') or container.select_one('.location')
                location = location_element.text.strip() if location_element else "Unknown"
                
                # Extract description
                description_element = container.select_one('.offer__description') or container.select_one('.description')
                description = description_element.text.strip() if description_element else ""
                
                # Extract image
                image_element = container.select_one('img') or container.select_one('.offer__image img')
                image_url = None
                if image_element:
                    image_url = image_element.get('src') or image_element.get('data-src')
                
                # Extract category
                category_element = container.select_one('.offer__category') or container.select_one('.category')
                category = category_element.text.strip() if category_element else "Unknown"
                
                # Create item dictionary
                item = {
                    'title': title,
                    'price': price,
                    'currency': currency,
                    'url': item_url,
                    'image_url': image_url,
                    'marketplace': self.get_marketplace_name(),
                    'location': location,
                    'description': description,
                    'category': category,
                    'seller_name': self._extract_seller_name(container),
                    'condition': "Unknown"
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Sprzedajemy item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Sprzedajemy search results using trafilatura"""
        logger.info("Parsing Sprzedajemy results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Sprzedajemy search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Sprzedajemy doesn't typically use JSON-LD for listings
        # We'll need to rely on text extraction and pattern matching
        
        # Split the text into potential listings
        listings = re.split(r'\n{2,}', extracted_text)
        items = []
        
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
                
                # Try to extract location
                location_match = re.search(r'(Warszawa|Kraków|Łódź|Wrocław|Poznań|Gdańsk|Szczecin|Bydgoszcz|Lublin|Białystok|Katowice)[\s,]', listing_text)
                location = location_match.group(1) if location_match else "Unknown"
                
                # Create a basic item
                item = {
                    'title': listing_text.split('\n')[0][:100],
                    'price': price,
                    'currency': 'PLN',
                    'url': search_url,  # Don't have specific URL from text extraction
                    'image_url': None,
                    'marketplace': self.get_marketplace_name(),
                    'location': location,
                    'description': listing_text,
                    'category': "Unknown",
                    'seller_name': "Unknown",
                    'condition': "Unknown"
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Sprzedajemy text listing: {e}")
                continue
        
        return items
    
    def _extract_seller_name(self, container) -> str:
        """Extract seller name from listing container"""
        seller_element = container.select_one('.offer__seller') or container.select_one('.seller')
        if seller_element:
            return seller_element.text.strip()
        return "Unknown"
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Sprzedajemy item"""
        logger.info(f"Getting details for Sprzedajemy item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Sprzedajemy item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Extract title
        title_element = soup.select_one('h1')
        details['title'] = title_element.text.strip() if title_element else "Unknown Item"
        
        # Extract price
        price_element = soup.select_one('.price-wrapper .price') or soup.select_one('.offer-price')
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
        description_element = soup.select_one('.description-wrapper .description-content')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract location
        location_element = soup.select_one('.location')
        details['location'] = location_element.text.strip() if location_element else "Unknown"
        
        # Extract category
        category_element = soup.select_one('.breadcrumbs')
        details['category'] = ""
        if category_element:
            category_items = category_element.select('li')
            if len(category_items) > 1:  # Skip 'Home'
                details['category'] = category_items[1].text.strip()
        
        # Extract seller information
        seller_element = soup.select_one('.user-details')
        if seller_element:
            name_element = seller_element.select_one('.name')
            details['seller_name'] = name_element.text.strip() if name_element else "Unknown"
            
            # Extract seller rating/stats if available
            rating_element = seller_element.select_one('.rating')
            if rating_element:
                details['seller_rating'] = rating_element.text.strip()
        else:
            details['seller_name'] = "Unknown"
        
        # Extract images
        image_elements = soup.select('.gallery img')
        details['image_urls'] = [img.get('src') or img.get('data-src') for img in image_elements if img.get('src') or img.get('data-src')]
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Extract additional details (attributes)
        attributes_section = soup.select('.attributes .attribute')
        details['attributes'] = {}
        
        for attribute in attributes_section:
            try:
                label_element = attribute.select_one('.name')
                value_element = attribute.select_one('.value')
                
                if label_element and value_element:
                    key = label_element.text.strip().rstrip(':')
                    value = value_element.text.strip()
                    details['attributes'][key] = value
                    
                    # Extract specific attributes
                    if 'Stan' in key or 'Condition' in key:
                        details['condition'] = value
            except Exception:
                continue
        
        # Extract post date
        date_element = soup.select_one('.created-at')
        if date_element:
            details['posted_date'] = date_element.text.strip()
        
        details['url'] = item_url
        details['marketplace'] = self.get_marketplace_name()
        
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
        
        # Check category filter
        if filters.get('category') and item.get('category') and item['category'] != "Unknown":
            if filters['category'].lower() not in item['category'].lower():
                return False
        
        # Check condition filter
        if filters.get('condition') and item.get('condition') and item['condition'] != "Unknown":
            if filters['condition'].lower() not in item['condition'].lower():
                return False
        
        return True