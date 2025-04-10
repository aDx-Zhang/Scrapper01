"""
OtoMoto Scraper - For scraping OtoMoto.pl automotive marketplace
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

class OtoMotoScraper(BaseScraper):
    """Scraper for OtoMoto.pl automotive marketplace"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the OtoMoto scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://www.otomoto.pl"
        
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "otomoto"
    
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for vehicles on OtoMoto matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        # Build the search URL with query
        search_url = f"{self.base_url}/osobowe"
        if encoded_query:
            search_url = f"{search_url}/q-{encoded_query}"
        
        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "search[filter_float_price:from]", filters['price_min'])
        
        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "search[filter_float_price:to]", filters['price_max'])
        
        if filters.get('location'):
            location = urllib.parse.quote(filters['location'])
            search_url = self._add_url_param(search_url, "search[filter_enum_city_id]", location)
        
        # Add vehicle specific filters
        if filters.get('make'):
            make = urllib.parse.quote(filters['make'])
            search_url = self._add_url_param(search_url, "search[filter_enum_make]", make)
            
        if filters.get('model'):
            model = urllib.parse.quote(filters['model'])
            search_url = self._add_url_param(search_url, "search[filter_enum_model]", model)
            
        if filters.get('year_from'):
            search_url = self._add_url_param(search_url, "search[filter_float_year:from]", filters['year_from'])
            
        if filters.get('year_to'):
            search_url = self._add_url_param(search_url, "search[filter_float_year:to]", filters['year_to'])
            
        if filters.get('mileage_to'):
            search_url = self._add_url_param(search_url, "search[filter_float_mileage:to]", filters['mileage_to'])
        
        logger.info(f"OtoMoto search URL: {search_url}")
        
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
        """Parse OtoMoto search results from the search page directly using HTML parsing"""
        logger.info("Parsing OtoMoto results with direct HTML parsing")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get OtoMoto search page")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        
        # OtoMoto uses a specific structure for listings
        # Look for listing articles
        listing_containers = soup.select('article')
        
        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('.offer-item')
            
        if not listing_containers:
            # Another fallback to more generic selectors
            listing_containers = soup.select('[data-testid="listing-ad"]')
            
        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container.select_one('a[href]')
                if not link_element:
                    continue
                
                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url
                
                # Extract title - using multiple potential selectors
                title_selectors = [
                    '[data-testid="listing-ad-title"]',
                    '.offer-title a', 
                    '.ooa-1hab6wx h2',
                    '.eqfsxdx0',
                    'h1.ef0v5pb0',
                    '.offer-item__title'
                ]
                
                title = "Unknown Vehicle"
                for selector in title_selectors:
                    title_element = container.select_one(selector)
                    if title_element and title_element.text.strip():
                        title = title_element.text.strip()
                        break
                
                # Extract price with enhanced selectors
                price_selectors = [
                    '[data-testid="ad-price"]',
                    '.offer-price__number span',
                    '.ooa-1w94hq4',
                    '.offer-price',
                    '.price-wrapper'
                ]
                
                price_text = "0 PLN"
                for selector in price_selectors:
                    price_element = container.select_one(selector)
                    if price_element and price_element.text.strip():
                        price_text = price_element.text.strip()
                        break
                
                # Enhanced price extraction with multiple formats
                price = 0.0
                currency = "PLN"
                price_patterns = [
                    r'(\d+[\s\d]*\d*[,.]\d+|\d+[\s\d]*\d*)\s*(?:PLN|zł)',
                    r'(\d+[\s\d]*\d*[,.]\d+|\d+[\s\d]*\d*)',
                ]
                
                for pattern in price_patterns:
                    price_match = re.search(pattern, price_text, re.IGNORECASE)
                    if price_match:
                        price_str = price_match.group(1).replace(" ", "").replace(",", ".")
                        try:
                            price = float(price_str)
                            break
                        except ValueError:
                            continue
                
                # Extract location with enhanced selectors
                location_selectors = [
                    '[data-testid="location-date"]',
                    '.offer-item__location',
                    '.ooa-1w5ghgi',
                    '.seller-box__seller-address'
                ]
                
                location = ""
                for selector in location_selectors:
                    location_element = container.select_one(selector)
                    if location_element:
                        location_text = location_element.text.strip()
                        # Usually format is "Location (Date)"
                        location_match = re.search(r'^(.*?)(?:\s+\(|$)', location_text)
                        if location_match:
                            location = location_match.group(1).strip()
                            break
                        else:
                            location = location_text
                            break
                
                if not location:
                    location = "Unknown"
                
                # Extract vehicle details with enhanced selectors
                details_selectors = [
                    '[data-testid="ad-params"]',
                    '.offer-params__list',
                    '.offer-features__list',
                    '.parameter-feature-list',
                    '.ooa-1t4mudi'
                ]
                
                details_text = ""
                for selector in details_selectors:
                    details_elements = container.select(selector)
                    if details_elements:
                        details_text = " ".join([elem.text.strip() for elem in details_elements])
                        break
                
                # Extract image
                image_element = container.select_one('img')
                image_url = None
                if image_element:
                    image_url = image_element.get('src') or image_element.get('data-src')
                
                # Get full details for better extraction
                full_details = self.get_item_details(item_url) if item_url else {}
                
                # Create item dictionary with vehicle specific fields
                item = {
                    'title': full_details.get('title') or title,
                    'price': full_details.get('price') or price,
                    'currency': full_details.get('currency') or currency,
                    'url': item_url,
                    'image_url': full_details.get('image_url') or image_url,
                    'marketplace': self.get_marketplace_name(),
                    'location': full_details.get('location') or location,
                    'description': full_details.get('description') or details_text,
                    # Vehicle specific fields
                    'make': full_details.get('make') or self._extract_make(title, details_text),
                    'model': full_details.get('model') or self._extract_model(title, details_text),
                    'year': full_details.get('year') or self._extract_year(details_text),
                    'mileage': full_details.get('mileage') or self._extract_mileage(details_text),
                    'fuel_type': full_details.get('fuel_type') or self._extract_fuel_type(details_text),
                    'transmission': full_details.get('transmission') or self._extract_transmission(details_text),
                    'engine_capacity': full_details.get('engine_capacity') or self._extract_engine_capacity(details_text),
                    'seller_name': full_details.get('seller_name', "Click for Details"),
                    'seller_type': full_details.get('seller_type', "Click for Details"),
                    'condition': full_details.get('condition') or ("Used" if "używany" in details_text.lower() else "New" if "nowy" in details_text.lower() else "Click for Details"),
                }
                
                # Final validation to ensure we have valid data
                if item['title'] == "Unknown Vehicle" or not item['title']:
                    item['title'] = "Click for Details"
                if item['price'] == 0.0 or not item['price']:
                    item['price'] = "Click for Details"
                if not item['description']:
                    item['description'] = "Click for Details"
                
                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing OtoMoto item: {e}")
                continue
        
        return items
    
    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OtoMoto search results using trafilatura"""
        logger.info("Parsing OtoMoto results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get OtoMoto search page")
            return []
        
        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)
        
        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []
        
        # Parse the HTML directly since trafilatura might not get all structured data
        soup = BeautifulSoup(html_content, 'html.parser')
        items = []
        
        # Look for structured data in script tags (JSON-LD)
        script_elements = soup.select('script[type="application/ld+json"]')
        for script in script_elements:
            try:
                data = json.loads(script.string)
                
                # Look for vehicle listings in the structured data
                if isinstance(data, list):
                    for item_data in data:
                        if item_data.get('@type') in ['Product', 'Vehicle', 'Car', 'MotorVehicle']:
                            item = self._extract_from_jsonld(item_data)
                            if item and self._passes_filters(item, filters):
                                items.append(item)
                elif isinstance(data, dict):
                    if data.get('@type') in ['Product', 'Vehicle', 'Car', 'MotorVehicle']:
                        item = self._extract_from_jsonld(data)
                        if item and self._passes_filters(item, filters):
                            items.append(item)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Error parsing JSON-LD: {e}")
        
        # If we got items from JSON-LD, return them
        if items:
            return items
        
        # Otherwise, use trafilatura extracted text to try to identify listings
        # This is more of a fallback and less structured
        listings = re.split(r'\n{2,}', extracted_text)
        for listing_text in listings:
            try:
                # Try to extract vehicle information from text
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
                    'make': self._extract_make(listing_text, listing_text),
                    'model': self._extract_model(listing_text, listing_text),
                    'year': self._extract_year(listing_text),
                    'mileage': self._extract_mileage(listing_text),
                    'fuel_type': self._extract_fuel_type(listing_text),
                    'transmission': self._extract_transmission(listing_text),
                    'engine_capacity': self._extract_engine_capacity(listing_text),
                    'seller_name': "Unknown",
                    'seller_type': "Unknown",
                    'condition': "Used" if "używany" in listing_text.lower() else "New" if "nowy" in listing_text.lower() else "Unknown",
                }
                
                if self._passes_filters(item, filters):
                    items.append(item)
            
            except Exception as e:
                logger.error(f"Error parsing OtoMoto text listing: {e}")
                continue
        
        return items
    
    def _extract_from_jsonld(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract vehicle information from JSON-LD structured data"""
        try:
            title = data.get('name', 'Unknown Vehicle')
            
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
            
            # Extract image
            image_url = None
            if 'image' in data:
                image = data['image']
                if isinstance(image, list) and image:
                    image_url = image[0]
                else:
                    image_url = image
            
            # Extract location
            location = "Unknown"
            if 'availableAtOrFrom' in data:
                location_data = data['availableAtOrFrom']
                if isinstance(location_data, dict) and 'address' in location_data:
                    address = location_data['address']
                    if isinstance(address, dict):
                        location_parts = []
                        if 'addressLocality' in address:
                            location_parts.append(address['addressLocality'])
                        if 'addressRegion' in address:
                            location_parts.append(address['addressRegion'])
                        location = ", ".join(location_parts) if location_parts else "Unknown"
            
            # Extract description
            description = data.get('description', '')
            
            # Extract vehicle details
            make = None
            model = None
            
            if 'brand' in data:
                brand = data['brand']
                if isinstance(brand, dict):
                    make = brand.get('name')
            
            if 'model' in data:
                model_data = data['model']
                if isinstance(model_data, dict):
                    model = model_data.get('name')
            
            # Create the item
            return {
                'title': title,
                'price': price,
                'currency': currency,
                'url': url,
                'image_url': image_url,
                'marketplace': self.get_marketplace_name(),
                'location': location,
                'description': description,
                'make': make or self._extract_make(title, description),
                'model': model or self._extract_model(title, description),
                'year': self._extract_year(description),
                'mileage': self._extract_mileage(description),
                'fuel_type': self._extract_fuel_type(description),
                'transmission': self._extract_transmission(description),
                'engine_capacity': self._extract_engine_capacity(description),
                'seller_name': data.get('seller', {}).get('name', "Unknown") if isinstance(data.get('seller'), dict) else "Unknown",
                'seller_type': "Unknown",
                'condition': "Used" if "używany" in description.lower() else "New" if "nowy" in description.lower() else "Unknown",
            }
        except Exception as e:
            logger.error(f"Error extracting from JSON-LD: {e}")
            return None
    
    def _extract_make(self, title: str, details: str) -> str:
        """Extract vehicle make from title and details"""
        # List of common car makes
        car_makes = [
            'audi', 'bmw', 'mercedes', 'volkswagen', 'opel', 'toyota', 'ford', 'renault', 
            'peugeot', 'citroen', 'fiat', 'skoda', 'honda', 'hyundai', 'kia', 'mazda', 
            'nissan', 'volvo', 'seat', 'dacia', 'mitsubishi', 'suzuki', 'lexus', 'alfa romeo',
            'chevrolet', 'jeep', 'land rover', 'mini', 'porsche', 'subaru'
        ]
        
        combined_text = (title + ' ' + details).lower()
        
        for make in car_makes:
            if make in combined_text:
                return make.title()  # Return with title case
        
        return "Unknown"
    
    def _extract_model(self, title: str, details: str) -> str:
        """Extract vehicle model from title and details"""
        # This is complex as models vary widely
        # For common makes, we can try to extract common models
        make = self._extract_make(title, details)
        if make == "Unknown":
            return "Unknown"
            
        combined_text = (title + ' ' + details).lower()
        
        # Define common models for popular makes
        common_models = {
            'Audi': ['a1', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'q3', 'q5', 'q7', 'tt', 'rs'],
            'BMW': ['1', '2', '3', '4', '5', '6', '7', 'x1', 'x3', 'x5', 'x6', 'z4', 'm'],
            'Mercedes': ['klasa a', 'klasa b', 'klasa c', 'klasa e', 'klasa s', 'cla', 'clk', 'cls', 'glc', 'gle', 'ml'],
            'Volkswagen': ['golf', 'passat', 'polo', 'tiguan', 'touran', 'arteon', 'caddy', 'transporter', 'sharan'],
            'Toyota': ['aygo', 'yaris', 'corolla', 'avensis', 'rav4', 'auris', 'camry', 'prius', 'land cruiser'],
            'Ford': ['fiesta', 'focus', 'mondeo', 'kuga', 'ecosport', 'edge', 'mustang', 's-max', 'galaxy'],
            'Opel': ['astra', 'corsa', 'insignia', 'mokka', 'zafira', 'meriva', 'adam', 'vectra'],
        }
        
        # Try to find model for the identified make
        if make in common_models:
            for model in common_models[make]:
                model_pattern = r'\b' + re.escape(model) + r'\b'
                if re.search(model_pattern, combined_text):
                    return model.title()  # Return with title case
        
        # If no specific model found, try generic extraction
        # Often the model follows the make
        make_pos = combined_text.find(make.lower())
        if make_pos >= 0:
            # Look for next word after make
            model_match = re.search(r'\b' + re.escape(make.lower()) + r'\s+([a-z0-9\-]+)', combined_text)
            if model_match:
                return model_match.group(1).title()
        
        return "Unknown"
    
    def _extract_year(self, details: str) -> Optional[int]:
        """Extract vehicle production year"""
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', details)
        if year_match:
            try:
                year = int(year_match.group(1))
                # Validate year is reasonable (1970-current)
                current_year = datetime.now().year
                if 1970 <= year <= current_year:
                    return year
            except ValueError:
                pass
        return None
    
    def _extract_mileage(self, details: str) -> Optional[int]:
        """Extract vehicle mileage in kilometers"""
        mileage_match = re.search(r'(\d+[\s\d]*\d*)\s*(?:km|tys\.)', details)
        if mileage_match:
            try:
                mileage_str = mileage_match.group(1).replace(" ", "")
                return int(mileage_str)
            except ValueError:
                pass
        return None
    
    def _extract_fuel_type(self, details: str) -> str:
        """Extract vehicle fuel type"""
        fuel_types = {
            'benzyna': 'petrol',
            'diesel': 'diesel',
            'lpg': 'lpg',
            'hybryda': 'hybrid',
            'elektryczny': 'electric',
            'cng': 'cng',
            'petrol': 'petrol',
            'hybrid': 'hybrid',
            'electric': 'electric',
        }
        
        details_lower = details.lower()
        
        for key, value in fuel_types.items():
            if key in details_lower:
                return value
        
        return "unknown"
    
    def _extract_transmission(self, details: str) -> str:
        """Extract vehicle transmission type"""
        details_lower = details.lower()
        
        if 'automatyczna' in details_lower or 'automatic' in details_lower:
            return 'automatic'
        elif 'manualna' in details_lower or 'manual' in details_lower:
            return 'manual'
        elif 'półautomat' in details_lower or 'semi-automatic' in details_lower:
            return 'semi-automatic'
        
        return 'unknown'
    
    def _extract_engine_capacity(self, details: str) -> Optional[float]:
        """Extract engine capacity in liters"""
        capacity_match = re.search(r'(\d+[.,]?\d*)\s*(?:l|liter|litre)', details, re.IGNORECASE)
        if capacity_match:
            try:
                return float(capacity_match.group(1).replace(',', '.'))
            except ValueError:
                pass
                
        # Alternative format in cm³
        capacity_match = re.search(r'(\d+)\s*cm3', details, re.IGNORECASE)
        if capacity_match:
            try:
                cm3 = int(capacity_match.group(1))
                return round(cm3 / 1000, 1)  # Convert to liters
            except ValueError:
                pass
                
        return None
    
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific OtoMoto vehicle"""
        logger.info(f"Getting details for OtoMoto item: {item_url}")
        
        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get OtoMoto item details for URL: {item_url}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        details = {}
        
        # Try to get structured data first
        script_elements = soup.select('script[type="application/ld+json"]')
        for script in script_elements:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') in ['Product', 'Vehicle', 'Car', 'MotorVehicle']:
                    extracted = self._extract_from_jsonld(data)
                    if extracted:
                        return extracted
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Extract title
        title_element = soup.select_one('h1')
        details['title'] = title_element.text.strip() if title_element else "Unknown Vehicle"
        
        # Extract price
        price_element = soup.select_one('[data-testid="price"]')
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
        description_element = soup.select_one('[data-testid="description"]')
        details['description'] = description_element.text.strip() if description_element else ""
        
        # Extract location
        location_element = soup.select_one('[data-testid="location"]')
        details['location'] = location_element.text.strip() if location_element else "Unknown"
        
        # Extract vehicle details
        params_section = soup.select('[data-testid="advert-details-item"]')
        vehicle_details = {}
        
        for param in params_section:
            try:
                label_element = param.select_one('p')
                value_element = param.select_one('h2, div:not(p)')
                
                if label_element and value_element:
                    key = label_element.text.strip()
                    value = value_element.text.strip()
                    vehicle_details[key] = value
                    
                    # Extract specific vehicle details
                    if 'Marka pojazdu' in key:
                        details['make'] = value
                    elif 'Model pojazdu' in key:
                        details['model'] = value
                    elif 'Rok produkcji' in key:
                        try:
                            details['year'] = int(value)
                        except ValueError:
                            details['year'] = None
                    elif 'Przebieg' in key:
                        try:
                            details['mileage'] = int(re.sub(r'[^\d]', '', value))
                        except ValueError:
                            details['mileage'] = None
                    elif 'Rodzaj paliwa' in key:
                        details['fuel_type'] = value.lower()
                    elif 'Skrzynia biegów' in key:
                        details['transmission'] = 'automatic' if 'automat' in value.lower() else 'manual' if 'manual' in value.lower() else 'unknown'
                    elif 'Pojemność skokowa' in key:
                        try:
                            details['engine_capacity'] = float(re.sub(r'[^\d.]', '', value.replace(',', '.')))
                        except ValueError:
                            details['engine_capacity'] = None
                    elif 'Stan' in key:
                        details['condition'] = value
            except Exception as e:
                logger.error(f"Error extracting vehicle param: {e}")
                continue
        
        # Extract seller information
        seller_element = soup.select_one('[data-testid="aside-seller-info"]')
        if seller_element:
            seller_name_element = seller_element.select_one('h2')
            details['seller_name'] = seller_name_element.text.strip() if seller_name_element else "Unknown"
            
            # Determine seller type (dealer or private)
            if 'Firma' in seller_element.text or 'Dealer' in seller_element.text:
                details['seller_type'] = "Dealer"
            else:
                details['seller_type'] = "Private"
        else:
            details['seller_name'] = "Unknown"
            details['seller_type'] = "Unknown"
        
        # Extract images
        image_elements = soup.select('[data-testid="gallery"] img')
        details['image_urls'] = [img.get('src') for img in image_elements if img.get('src')]
        
        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None
        
        # Set vehicle specific fields
        if 'make' not in details:
            details['make'] = self._extract_make(details['title'], details['description'])
            
        if 'model' not in details:
            details['model'] = self._extract_model(details['title'], details['description'])
            
        if 'year' not in details:
            details['year'] = self._extract_year(details['description'])
            
        if 'mileage' not in details:
            details['mileage'] = self._extract_mileage(details['description'])
            
        if 'fuel_type' not in details:
            details['fuel_type'] = self._extract_fuel_type(details['description'])
            
        if 'transmission' not in details:
            details['transmission'] = self._extract_transmission(details['description'])
            
        if 'engine_capacity' not in details:
            details['engine_capacity'] = self._extract_engine_capacity(details['description'])
            
        if 'condition' not in details:
            details['condition'] = "Used" if "używany" in details['description'].lower() else "New" if "nowy" in details['description'].lower() else "Unknown"
        
        details['additional_data'] = vehicle_details
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
        
        # Check make filter
        if filters.get('make') and item['make'] != "Unknown":
            if filters['make'].lower() != item['make'].lower():
                return False
                
        # Check model filter
        if filters.get('model') and item['model'] != "Unknown":
            if filters['model'].lower() != item['model'].lower():
                return False
        
        # Check year range
        if filters.get('year_from') is not None and item['year'] is not None:
            if item['year'] < int(filters['year_from']):
                return False
                
        if filters.get('year_to') is not None and item['year'] is not None:
            if item['year'] > int(filters['year_to']):
                return False
        
        # Check mileage
        if filters.get('mileage_to') is not None and item['mileage'] is not None:
            if item['mileage'] > int(filters['mileage_to']):
                return False
        
        # Check fuel type
        if filters.get('fuel_type') and item['fuel_type'] != "unknown":
            if filters['fuel_type'].lower() != item['fuel_type'].lower():
                return False
        
        # Check transmission type
        if filters.get('transmission') and item['transmission'] != "unknown":
            if filters['transmission'].lower() != item['transmission'].lower():
                return False
        
        return True