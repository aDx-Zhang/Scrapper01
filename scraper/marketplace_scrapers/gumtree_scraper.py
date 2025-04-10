"""
Gumtree Scraper - For scraping Gumtree.pl marketplace
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

class GumtreeScraper(BaseScraper):
    """Scraper for Gumtree.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Gumtree scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://www.gumtree.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "gumtree"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Gumtree matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/s-q-{encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "pr", f"{filters['price_min']},")
        
        if filters.get('price_max'):
            # If min price is not set but max is
            if not filters.get('price_min'):
                search_url = self._add_url_param(search_url, "pr", f",{filters['price_max']}")
            else:
                # Replace the existing pr parameter
                search_url = search_url.replace(f"pr={filters['price_min']},", f"pr={filters['price_min']},{filters['price_max']}")
        
        if filters.get('location'):
            location = urllib.parse.quote(filters['location'])
            search_url = self._add_url_param(search_url, "l", location)
        
        if filters.get('category'):
            category = urllib.parse.quote(filters['category'])
            search_url = f"{self.base_url}/{category}/{search_url.split('gumtree.pl/')[1]}"
        
        logger.info(f"Gumtree search URL: {search_url}")
        
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
        """Parse Gumtree search results from the search page directly using HTML parsing"""
        logger.info("Parsing Gumtree results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Gumtree search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Gumtree uses a specific structure for listings
        # Look for listing containers
        listing_containers = soup.select('.tileV1')
        
        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('.result')
            
        if not listing_containers:
            # Another fallback
            listing_containers = soup.select('article')
            
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container.select_one('a.href-link')
                if not link_element:
                    link_element = container.select_one('a[href*="/a-"]')
                    
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title
                title_element = container.select_one('.title') or container.select_one('h2')
                title = title_element.text.strip() if title_element else "Unknown Item"
                
                # Extract price
                price_element = container.select_one('.price') or container.select_one('.amount')
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
                location_element = container.select_one('.category-location') or container.select_one('.location')
                location = "Unknown"
                if location_element:
                    location_text = location_element.text.strip()
                    # Location might contain date
                    location_parts = location_text.split(' - ')
                    if location_parts and location_parts[0]:
                        location = location_parts[0].strip()
                
                # Extract description
                description_element = container.select_one('.description')
                description = description_element.text.strip() if description_element else ""
                
                # Extract image
                image_element = container.select_one('img')
                image_url = None
                if image_element:
                    image_url = image_element.get('src') or image_element.get('data-src')
                
                # Extract category
                category_element = container.select_one('.category-location span')
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
                    'seller_name': "Unknown",  # Need to get details page for this
                    'seller_rating': None,
                    'condition': "Unknown",
                    'posted_time': self._extract_posted_time(container)
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Gumtree item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Gumtree search results using trafilatura"""
        logger.info("Parsing Gumtree results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Gumtree search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Gumtree doesn't typically use JSON-LD for listings
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
                    'seller_rating': None,
                    'condition': "Unknown",
                    'posted_time': None
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Gumtree text listing: {e}")
                continue
        
        return items
    
    def _extract_posted_time(self, container) -> Optional[str]:
        """Extract when the item was posted"""
        time_element = container.select_one('.creation-date') or container.select_one('.date-time')
        if time_element:
            return time_element.text.strip()
        return None
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Gumtree item"""
        logger.info(f"Getting details for Gumtree item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Gumtree item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Extract title
        title_element = soup.select_one('h1')
        details['title'] = title_element.text.strip() if title_element else "Unknown Item"
        
        # Extract price
        price_element = soup.select_one('.price-value') or soup.select_one('.vip-price')
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
        description_element = soup.select_one('.description')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract location
        location_element = soup.select_one('.location') or soup.select_one('.address')
        details['location'] = location_element.text.strip() if location_element else "Unknown"
        
        # Extract category
        category_element = soup.select_one('.breadcrumb')
        details['category'] = ""
        if category_element:
            category_items = category_element.select('li')
            if len(category_items) > 1:  # Skip 'Home'
                details['category'] = category_items[1].text.strip()
        
        # Extract seller information
        seller_element = soup.select_one('.seller-box')
        if seller_element:
            name_element = seller_element.select_one('a') or seller_element.select_one('.name')
            details['seller_name'] = name_element.text.strip() if name_element else "Unknown"
            
            # Seller rating/stats if available
            stats_element = seller_element.select_one('.user-statistics')
            if stats_element:
                details['seller_stats'] = stats_element.text.strip()
        else:
            details['seller_name'] = "Unknown"
        
        # Extract images
        image_elements = soup.select('.vip-gallery img')
        if not image_elements:
            image_elements = soup.select('.carousel img')
            
        details['image_urls'] = [img.get('src') or img.get('data-src') for img in image_elements if img.get('src') or img.get('data-src')]
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Extract condition if available
        attributes_section = soup.select('.attribute')
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
        
        # Extract posting date
        date_element = soup.select_one('.creation-date') or soup.select_one('.sellerinfo-row:contains("Date")')
        if date_element:
            details['posted_time'] = date_element.text.strip()
        
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