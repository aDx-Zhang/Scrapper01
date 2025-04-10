"""
Ogloszenia Online Scraper - For scraping ogloszenia-online.pl marketplace
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

class OgloszeniaOnlineScraper(BaseScraper):
    """Scraper for ogloszenia-online.pl marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Ogloszenia Online scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://www.ogloszenia-online.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "ogloszenia-online"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Ogloszenia Online matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/search.php?q={encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "cena_od", filters['price_min'])
        
        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "cena_do", filters['price_max'])
        
        if filters.get('location'):
            location = urllib.parse.quote(filters['location'])
            search_url = self._add_url_param(search_url, "region", location)
        
        if filters.get('category'):
            category = urllib.parse.quote(filters['category'])
            search_url = self._add_url_param(search_url, "kategoria", category)
        
        logger.info(f"Ogloszenia Online search URL: {search_url}")
        
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
        """Parse Ogloszenia Online search results from the search page directly using HTML parsing"""
        logger.info("Parsing Ogloszenia Online results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Ogloszenia Online search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # Ogloszenia Online uses a specific structure for listings
        # Look for listing containers
        listing_containers = soup.select('.ogloszenie')
        
        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('.offer')
            
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
                title_element = container.select_one('.title') or container.select_one('h2')
                title = title_element.text.strip() if title_element else "Unknown Item"
                
                # Extract price
                price_element = container.select_one('.price')
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
                location_element = container.select_one('.location')
                location = location_element.text.strip() if location_element else "Unknown"
                
                # Extract description
                description_element = container.select_one('.description')
                description = description_element.text.strip() if description_element else ""
                
                # Extract image
                image_element = container.select_one('img')
                image_url = None
                if image_element:
                    image_url = image_element.get('src') or image_element.get('data-src')
                    
                    # Sometimes image URLs might be relative
                    if image_url and not image_url.startswith('http'):
                        image_url = self.base_url + image_url
                
                # Extract category
                category_element = container.select_one('.category')
                category = category_element.text.strip() if category_element else ""
                
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
                    'posted_date': self._extract_posted_date(container),
                    'condition': "Unknown"
                }
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Ogloszenia Online item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Ogloszenia Online search results using trafilatura"""
        logger.info("Parsing Ogloszenia Online results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Ogloszenia Online search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Ogloszenia Online likely doesn't use structured data
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
                    'category': "",
                    'seller_name': "Unknown",
                    'posted_date': None,
                    'condition': "Unknown"
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing Ogloszenia Online text listing: {e}")
                continue
        
        return items
    
    def _extract_seller_name(self, container) -> str:
        """Extract seller name from listing container"""
        seller_element = container.select_one('.seller')
        if seller_element:
            return seller_element.text.strip()
        return "Unknown"
    
    def _extract_posted_date(self, container) -> Optional[str]:
        """Extract posting date from listing container"""
        date_element = container.select_one('.date')
        if date_element:
            return date_element.text.strip()
        return None
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Ogloszenia Online item"""
        logger.info(f"Getting details for Ogloszenia Online item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Ogloszenia Online item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Extract title
        title_element = soup.select_one('h1') or soup.select_one('.title')
        details['title'] = title_element.text.strip() if title_element else "Unknown Item"
        
        # Extract price
        price_element = soup.select_one('.price') or soup.select_one('.offer-price')
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
        description_element = soup.select_one('.description') or soup.select_one('.offer-description')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract location
        location_element = soup.select_one('.location') or soup.select_one('.offer-location')
        details['location'] = location_element.text.strip() if location_element else "Unknown"
        
        # Extract category
        category_element = soup.select_one('.category') or soup.select_one('.offer-category')
        details['category'] = category_element.text.strip() if category_element else ""
        
        # Extract seller information
        seller_element = soup.select_one('.seller') or soup.select_one('.seller-info')
        if seller_element:
            details['seller_name'] = seller_element.text.strip()
            
            # Try to find seller rating/contact if available
            seller_rating_element = soup.select_one('.seller-rating')
            if seller_rating_element:
                details['seller_rating'] = seller_rating_element.text.strip()
                
            seller_contact_element = soup.select_one('.seller-contact')
            if seller_contact_element:
                details['seller_contact'] = seller_contact_element.text.strip()
        else:
            details['seller_name'] = "Unknown"
        
        # Extract images
        image_elements = soup.select('.gallery img') or soup.select('.offer-images img')
        details['image_urls'] = []
        
        for img in image_elements:
            img_src = img.get('src') or img.get('data-src')
            if img_src:
                # Fix relative URLs
                if not img_src.startswith('http'):
                    img_src = self.base_url + img_src
                details['image_urls'].append(img_src)
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Extract posting date
        date_element = soup.select_one('.date') or soup.select_one('.offer-date')
        if date_element:
            details['posted_date'] = date_element.text.strip()
        
        # Extract condition if available
        condition_element = soup.select_one('.condition') or soup.select_one('.offer-condition')
        if condition_element:
            details['condition'] = condition_element.text.strip()
        else:
            details['condition'] = "Unknown"
        
        # Additional attributes
        attributes = {}
        attr_elements = soup.select('.attributes .attribute') or soup.select('.offer-details .detail')
        for attr_elem in attr_elements:
            try:
                label_elem = attr_elem.select_one('.label') or attr_elem.select_one('.name')
                value_elem = attr_elem.select_one('.value')
                
                if label_elem and value_elem:
                    key = label_elem.text.strip().rstrip(':')
                    value = value_elem.text.strip()
                    attributes[key] = value
            except Exception:
                continue
        
        details['attributes'] = attributes
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
        if filters.get('category') and item.get('category'):
            if filters['category'].lower() not in item['category'].lower():
                return False
        
        return True