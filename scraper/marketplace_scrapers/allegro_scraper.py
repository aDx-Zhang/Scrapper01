"""
Allegro Scraper - For scraping AllegroLokalnie.pl marketplace
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

class AllegroScraper(BaseScraper):
    """Scraper for AllegroLokalnie.pl marketplace"""

    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """Initialize the Allegro scraper"""
        super().__init__(proxy_manager)
        self.base_url = "https://allegrolokalnie.pl"
        self.driver = None
        self._setup_selenium()

    def _setup_selenium(self):
        """Setup Selenium WebDriver"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--remote-debugging-port=9222')
        chrome_options.add_argument('--window-size=1920x1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--proxy-server="direct://"')
        chrome_options.add_argument('--proxy-bypass-list=*')
        chrome_options.add_argument('--start-maximized')

        try:
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            self.driver = None

    def __del__(self):
        """Cleanup Selenium WebDriver"""
        if self.driver:
            self.driver.quit()

    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        return "allegro"

    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for items on Allegro matching the given keywords and filters"""
        # Combine keywords into search query
        query = " ".join(keywords)
        encoded_query = urllib.parse.quote(query)

        # Build the search URL with query
        search_url = f"{self.base_url}/oferty/q/{encoded_query}"

        # Apply filters if provided
        if filters.get('price_min'):
            search_url = self._add_url_param(search_url, "price_from", filters['price_min'])

        if filters.get('price_max'):
            search_url = self._add_url_param(search_url, "price_to", filters['price_max'])

        if filters.get('location'):
            location = urllib.parse.quote(filters['location'])
            search_url = self._add_url_param(search_url, "city", location)

        if filters.get('condition') == 'new':
            search_url = self._add_url_param(search_url, "state", "nowe")
        elif filters.get('condition') == 'used':
            search_url = self._add_url_param(search_url, "state", "uzywane")

        logger.info(f"Allegro search URL: {search_url}")

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
        """Parse Allegro search results using Selenium"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        logger.info("Parsing Allegro results with Selenium")
        try:
            self.driver.get(search_url)
            # Wait for listings to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "mx-offer"))
            )

            # Get the page source after JavaScript has rendered
            html_content = self.driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logger.error(f"Error loading page with Selenium: {e}")
            return []

        items = []

        # Allegro uses a specific structure for listings
        # Look for listing containers
        listing_containers = soup.select('.mx-offer')

        if not listing_containers:
            # Fallback to alternative selectors
            listing_containers = soup.select('article')

        if not listing_containers:
            # Another fallback
            listing_containers = soup.select('.offer')

        for container in listing_containers:
            try:
                # Extract item URL
                link_element = container.select_one('a')
                if not link_element:
                    continue

                item_url = link_element.get('href', '')
                if item_url and not item_url.startswith('http'):
                    item_url = self.base_url + item_url

                # Extract title with enhanced selectors
                title = "Unknown Item"
                title_selectors = [
                    '[data-box-name="allegro.listing.title"] h2',
                    '[data-testid="listing-title"]',
                    '.mx-offer__title',
                    '.listing-title',
                    'article h2'
                ]
                for selector in title_selectors:
                    title_element = container.select_one(selector)
                    if title_element and title_element.text.strip():
                        title = title_element.text.strip()
                        break

                # Extract price with enhanced selectors
                price_text = "0 zł"
                price_selectors = [
                    '[data-box-name="allegro.price"] span',
                    '[data-testid="listing-price"]',
                    '.mx-offer__price-wrapper span',
                    '.price-wrapper',
                    'span[data-price]'
                ]
                for selector in price_selectors:
                    price_element = container.select_one(selector)
                    if price_element and price_element.text.strip():
                        price_text = price_element.text.strip()
                        break

                # Try to get price from data attribute if available
                if price_text == "0 zł":
                    price_element = container.select_one('[data-price]')
                    if price_element:
                        try:
                            price = float(price_element.get('data-price', '0'))
                            price_text = f"{price} zł"
                        except (ValueError, TypeError):
                            pass

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
                location_element = container.select_one('.mx-offer__location')
                if not location_element:
                    location_element = container.select_one('.location')
                location = location_element.text.strip() if location_element else "Unknown"

                # Extract description (might not be available on search page)
                description = ""

                # Enhanced image extraction
                image_url = None
                image_selectors = [
                    'img[data-box-name="image"]',
                    'img[data-testid="listing-image"]',
                    '.mx-offer__photos img',
                    '.swiper-slide img',
                    '.offer-photos img',
                    'img[data-role="offer-photo"]',
                    '[data-testid="gallery"] img',
                    '.photo-item img'
                ]

                for selector in image_selectors:
                    image_element = container.select_one(selector)
                    if image_element:
                        # Try different image attributes in order of preference
                        for attr in ['data-original', 'data-src', 'src', 'srcset']:
                            img_url = image_element.get(attr)
                            if img_url:
                                # Handle srcset format
                                if attr == 'srcset':
                                    srcset_urls = [u.strip().split(' ')[0] for u in img_url.split(',')]
                                    # Get the largest image (usually last in srcset)
                                    img_url = srcset_urls[-1] if srcset_urls else None

                                # Clean up URL
                                if img_url:
                                    # Handle relative URLs
                                    if img_url.startswith('//'):
                                        img_url = 'https:' + img_url
                                    elif not img_url.startswith(('http://', 'https://')):
                                        img_url = self.base_url + img_url

                                    # Handle placeholders and resize parameters
                                    img_url = re.sub(r'\{width\}x\{height\}', '800x600', img_url)
                                    img_url = re.sub(r'\/\d+x\d+\/', '/800x600/', img_url)

                                    image_url = img_url
                                    break

                    if image_url:
                        break

                # Fallback to JSON-LD image data
                if not image_url:
                    scripts = container.find_all('script', {'type': 'application/ld+json'})
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict):
                                image_data = data.get('image', [])
                                if isinstance(image_data, list) and image_data:
                                    url_data = image_data[0]
                                    image_url = url_data['url'] if isinstance(url_data, dict) else url_data
                                elif isinstance(image_data, dict):
                                    image_url = image_data.get('url') or image_data.get('contentUrl', '')
                                elif isinstance(image_data, str):
                                    image_url = image_data
                                break
                        except (json.JSONDecodeError, AttributeError):
                            continue

                # Try to get data from window.__INITIAL_STATE__
                initial_state = None
                for script in soup.find_all('script'):
                    if script.string and 'window.__INITIAL_STATE__' in script.string:
                        try:
                            initial_state_text = script.string.split('window.__INITIAL_STATE__ = ')[1].split('};')[0] + '}'
                            initial_state = json.loads(initial_state_text)
                            if initial_state and 'offers' in initial_state:
                                offer_data = initial_state['offers'].get(item_url, {})
                                if offer_data:
                                    if not title or title == "Unknown Item":
                                        title = offer_data.get('name', title)
                                    if price == 0.0:
                                        price = float(offer_data.get('price', {}).get('amount', 0))
                                        currency = offer_data.get('price', {}).get('currency', 'PLN')
                        except Exception as e:
                            logger.error(f"Error parsing initial state: {e}")

                # Fallback to JSON-LD
                if not initial_state:
                    script_element = container.find('script', {'type': 'application/ld+json'})
                    if script_element:
                        try:
                            data = json.loads(script_element.string)
                            if isinstance(data, dict):
                                if not title or title == "Unknown Item":
                                    title = data.get('name', title)
                                if price == 0.0 and 'offers' in data:
                                    offer = data['offers']
                                    if isinstance(offer, dict):
                                        price = float(offer.get('price', 0))
                                        currency = offer.get('priceCurrency', currency)
                        except (json.JSONDecodeError, AttributeError) as e:
                            logger.error(f"Error parsing JSON-LD: {e}")

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
                    'seller_name': self._extract_seller_name(container),
                    'condition': self._extract_condition(container)
                }

                # Check if item passes filters
                if self._passes_filters(item, filters):
                    items.append(item)

            except Exception as e:
                logger.error(f"Error parsing Allegro item: {e}")
                continue

        return items

    def _parse_with_trafilatura(self, search_url: str, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Allegro search results using trafilatura"""
        logger.info("Parsing Allegro results with trafilatura")
        response = self.get_with_retry(search_url)
        if not response:
            logger.error("Failed to get Allegro search page")
            return []

        # Extract the main content using trafilatura
        html_content = response.text
        extracted_text = trafilatura.extract(html_content)

        if not extracted_text:
            logger.warning("No content extracted with trafilatura")
            return []

        # Allegro might use JSON-LD for some listings
        soup = BeautifulSoup(html_content, 'html.parser')
        script_elements = soup.select('script[type="application/ld+json"]')
        items = []

        for script in script_elements:
            try:
                data = json.loads(script.string)

                # Check if it's a product list
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

        # Otherwise, try to extract from text
        # Split the text into potential listings
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

                # Try to extract location
                location_match = re.search(r'(Warszawa|Kraków|Łódź|Wrocław|Poznań|Gdańsk|Szczecin|Bydgoszcz|Lublin|Białystok|Katowice)[\s,]', listing_text)
                location = location_match.group(1) if location_match else "Unknown"

                # Try to extract title (first line or sentence)
                title_match = re.match(r'^([^\n\.]+)', listing_text)
                title = title_match.group(1).strip() if title_match else "Unknown Item"

                # Create a basic item
                item = {
                    'title': title,
                    'price': price,
                    'currency': 'PLN',
                    'url': search_url,  # Don't have specific URL from text extraction
                    'image_url': None,
                    'marketplace': self.get_marketplace_name(),
                    'location': location,
                    'description': listing_text,
                    'seller_name': "Unknown",
                    'condition': "nowe" if "nowe" in listing_text.lower() else "używane" if "używane" in listing_text.lower() else "Unknown"
                }

                if self._passes_filters(item, filters):
                    items.append(item)

            except Exception as e:
                logger.error(f"Error parsing Allegro text listing: {e}")
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
                    url_data = image[0]
                    image_url = url_data['url'] if isinstance(url_data, dict) else url_data
                elif isinstance(image, dict):
                    image_url = image.get('url') or image.get('contentUrl', '')
                elif isinstance(image, str):
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

            # Extract seller info
            seller_name = "Unknown"
            if 'seller' in data and isinstance(data['seller'], dict):
                seller_name = data['seller'].get('name', "Unknown")

            # Extract condition
            condition = "Unknown"
            if 'itemCondition' in data:
                condition_url = data['itemCondition']
                if isinstance(condition_url, str):
                    if 'NewCondition' in condition_url:
                        condition = "nowe"
                    elif 'UsedCondition' in condition_url:
                        condition = "używane"

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
                'seller_name': seller_name,
                'condition': condition
            }
        except Exception as e:
            logger.error(f"Error extracting from JSON-LD: {e}")
            return None

    def _extract_seller_name(self, container) -> str:
        """Extract seller name from listing container"""
        seller_element = container.select_one('.mx-offer__user')
        if not seller_element:
            seller_element = container.select_one('.seller')
        if seller_element:
            return seller_element.text.strip()
        return "Unknown"

    def _extract_condition(self, container) -> str:
        """Extract condition from listing container"""
        # Try to find condition badge
        condition_element = container.select_one('.mx-offer__status')
        if condition_element:
            condition_text = condition_element.text.strip().lower()
            if "now" in condition_text:
                return "nowe"
            elif "uży" in condition_text:
                return "używane"

        # Try to determine from text content
        container_text = container.text.lower()
        if "nowy" in container_text or "nowe" in container_text:
            return "nowe"
        elif "używan" in container_text:
            return "używane"

        return "Unknown"

    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """Get detailed information about a specific Allegro item"""
        logger.info(f"Getting details for Allegro item: {item_url}")

        response = self.get_with_retry(item_url)
        if not response:
            logger.error(f"Failed to get Allegro item details for URL: {item_url}")
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
        price_element = soup.select_one('.price')
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
        description_element = soup.select_one('.offer-description')
        details['description'] = description_element.text.strip() if description_element else ""

        # Extract location
        location_element = soup.select_one('.seller-location')
        details['location'] = location_element.text.strip() if location_element else "Unknown"

        # Extract seller information
        seller_element = soup.select_one('.seller-info')
        if seller_element:
            name_element = seller_element.select_one('.seller-name')
            details['seller_name'] = name_element.text.strip() if name_element else "Unknown"
        else:
            details['seller_name'] = "Unknown"

        # Extract images
        image_elements = soup.select('.gallery img')
        details['image_urls'] = [img.get('src') for img in image_elements if img.get('src')]

        if details['image_urls']:
            details['image_url'] = details['image_urls'][0]
        else:
            details['image_url'] = None

        # Extract condition
        condition_element = soup.select_one('.condition')
        if condition_element:
            condition_text = condition_element.text.strip().lower()
            if "now" in condition_text:
                details['condition'] = "nowe"
            elif "uży" in condition_text:
                details['condition'] = "używane"
            else:
                details['condition'] = condition_text
        else:
            details['condition'] = "Unknown"

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

        # Check condition filter
        if filters.get('condition'):
            if filters['condition'] == 'new' and item['condition'] != "nowe":
                return False
            elif filters['condition'] == 'used' and item['condition'] != "używane":
                return False

        return True