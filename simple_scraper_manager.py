import logging
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# Define a basic proxy manager
class DummyProxyManager:
    """A simple proxy manager that doesn't actually use proxies"""
    def get_proxy(self, country_code: Optional[str] = None) -> Optional[str]:
        return None
    
    def report_proxy_failure(self, proxy_url: str) -> None:
        pass
    
    def reset_failure_count(self, proxy_url: str) -> None:
        pass
    
    def count_active_proxies(self) -> int:
        return 0

# We'll use our proxy manager if available, otherwise use dummy proxy manager
try:
    from utils.proxy_manager import ProxyManager
except ImportError:
    try:
        from attached_assets.proxy_manager import ProxyManager
    except ImportError:
        ProxyManager = DummyProxyManager

# Import scrapers
try:
    from scraper.olx_scraper import OLXScraper
except ImportError:
    try:
        from attached_assets.olx_scraper import OLXScraper
    except ImportError:
        OLXScraper = None

# Import OtoDom scraper
try:
    from scraper.marketplace_scrapers.otodom_scraper import OtoDomScraper
except ImportError:
    OtoDomScraper = None

# Import OtoMoto scraper
try:
    from scraper.marketplace_scrapers.otomoto_scraper import OtoMotoScraper
except ImportError:
    OtoMotoScraper = None

# Import Gumtree scraper
try:
    from scraper.marketplace_scrapers.gumtree_scraper import GumtreeScraper
except ImportError:
    GumtreeScraper = None

# Import Sprzedajemy scraper
try:
    from scraper.marketplace_scrapers.sprzedajemy_scraper import SprzedajemyScraper
except ImportError:
    SprzedajemyScraper = None

# Import Allegro scraper
try:
    from scraper.marketplace_scrapers.allegro_scraper import AllegroScraper
except ImportError:
    AllegroScraper = None

# Import Vinted scraper
try:
    from scraper.marketplace_scrapers.vinted_scraper import VintedScraper
except ImportError:
    VintedScraper = None

# Import Emaito scraper
try:
    from scraper.marketplace_scrapers.emaito_scraper import EmaitoScraper
except ImportError:
    EmaitoScraper = None

# Import Aleja Handlowa scraper
try:
    from scraper.marketplace_scrapers.alejahandlowa_scraper import AlejaHandlowaScraper
except ImportError:
    AlejaHandlowaScraper = None

# Import Ogloszenia Online scraper
try:
    from scraper.marketplace_scrapers.ogloszenia_online_scraper import OgloszeniaOnlineScraper
except ImportError:
    OgloszeniaOnlineScraper = None

logger = logging.getLogger(__name__)

class SimpleScraperManager:
    """Manages scraper instances for different marketplaces"""
    
    def __init__(self, use_proxies: bool = False):
        """
        Initialize the scraper manager
        
        Args:
            use_proxies: Whether to use proxies for scraping
        """
        logger.info(f"Initialized SimpleScraperManager with proxies: {use_proxies}")
        self.use_proxies = use_proxies
        self.proxy_manager = ProxyManager() if use_proxies else None
        
        # Initialize marketplace scrapers
        self.scrapers = {}
        
        # Load OLX scraper if available
        if OLXScraper:
            self.scrapers['olx'] = OLXScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load OtoDom scraper if available
        if OtoDomScraper:
            self.scrapers['otodom'] = OtoDomScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load OtoMoto scraper if available
        if OtoMotoScraper:
            self.scrapers['otomoto'] = OtoMotoScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Gumtree scraper if available
        if GumtreeScraper:
            self.scrapers['gumtree'] = GumtreeScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Sprzedajemy scraper if available
        if SprzedajemyScraper:
            self.scrapers['sprzedajemy'] = SprzedajemyScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Allegro scraper if available
        if AllegroScraper:
            self.scrapers['allegro'] = AllegroScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Vinted scraper if available
        if VintedScraper:
            self.scrapers['vinted'] = VintedScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Emaito scraper if available
        if EmaitoScraper:
            self.scrapers['emaito'] = EmaitoScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Aleja Handlowa scraper if available
        if AlejaHandlowaScraper:
            self.scrapers['alejahandlowa'] = AlejaHandlowaScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Ogloszenia Online scraper if available
        if OgloszeniaOnlineScraper:
            self.scrapers['ogloszenia-online'] = OgloszeniaOnlineScraper(proxy_manager=self.proxy_manager if use_proxies else None)

    def get_scraper(self, marketplace: str):
        """Get scraper instance for given marketplace"""
        return self.scrapers.get(marketplace)
        
        # Load OLX scraper if available
        if OLXScraper:
            self.scrapers['olx'] = OLXScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load OtoDom scraper if available
        if OtoDomScraper:
            self.scrapers['otodom'] = OtoDomScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load OtoMoto scraper if available
        if OtoMotoScraper:
            self.scrapers['otomoto'] = OtoMotoScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Gumtree scraper if available
        if GumtreeScraper:
            self.scrapers['gumtree'] = GumtreeScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Sprzedajemy scraper if available
        if SprzedajemyScraper:
            self.scrapers['sprzedajemy'] = SprzedajemyScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Allegro scraper if available
        if AllegroScraper:
            self.scrapers['allegro'] = AllegroScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Vinted scraper if available
        if VintedScraper:
            self.scrapers['vinted'] = VintedScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Emaito scraper if available
        if EmaitoScraper:
            self.scrapers['emaito'] = EmaitoScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Aleja Handlowa scraper if available
        if AlejaHandlowaScraper:
            self.scrapers['alejahandlowa'] = AlejaHandlowaScraper(proxy_manager=self.proxy_manager if use_proxies else None)
            
        # Load Ogloszenia Online scraper if available
        if OgloszeniaOnlineScraper:
            self.scrapers['ogloszenia-online'] = OgloszeniaOnlineScraper(proxy_manager=self.proxy_manager if use_proxies else None)
    
    def search(self, marketplace: str, keywords: List[str], filters: Dict[str, Any], 
               page: int = 1, items_per_page: int = 20) -> Dict[str, Any]:
        """
        Search for items on the specified marketplace
        
        Args:
            marketplace: Name of the marketplace to search (olx, allegro, vinted, facebook, sprzedajemy, 
                        otodom, otomoto, gumtree, emaito, alejahandlowa, ogloszenia-online)
            keywords: List of keywords to search for
            filters: Dictionary of filters to apply
            page: Page number to fetch (for pagination)
            items_per_page: Number of items per page
            
        Returns:
            Dictionary with search results and pagination info
        """
        # Check if we have a scraper for this marketplace
        if marketplace in self.scrapers:
            try:
                # Try to search using the real scraper
                scraper = self.scrapers[marketplace]
                results = scraper.search(keywords, filters)
                
                # Apply pagination
                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                paginated_results = results[start_idx:end_idx] if start_idx < len(results) else []
                
                return {
                    'results': paginated_results,
                    'total': len(results),
                    'page': page,
                    'items_per_page': items_per_page,
                    'has_more': end_idx < len(results),
                }
            except Exception as e:
                logger.error(f"Error searching {marketplace}: {e}")
                # Fall back to mock results
                mock_results = self._generate_mock_results(marketplace, keywords, filters, random.randint(5, 15))
                return {
                    'results': mock_results,
                    'total': len(mock_results),
                    'page': page,
                    'items_per_page': items_per_page,
                    'has_more': False,
                    'error': str(e)
                }
        else:
            # Generate mock results for testing
            logger.warning(f"No scraper implementation for {marketplace}, using mock data")
            mock_results = self._generate_mock_results(marketplace, keywords, filters, random.randint(5, 15))
            return {
                'results': mock_results,
                'total': len(mock_results),
                'page': page,
                'items_per_page': items_per_page,
                'has_more': False,
            }
    
    def _generate_mock_results(self, marketplace: str, keywords: List[str], 
                             filters: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
        """Generate mock results for development/testing when real scrapers fail"""
        results = []
        
        # Get price ranges from filters
        price_min = filters.get('price_min', 0)
        price_max = filters.get('price_max', 10000)
        if price_min is None:
            price_min = 0
        if price_max is None:
            price_max = 10000
            
        # Ensure we have some range to work with
        if price_max <= price_min:
            price_max = price_min + 1000
            
        current_time = datetime.now()
        
        for i in range(count):
            # Generate a random price within the filter range
            price = round(random.uniform(price_min, price_max), 2)
            
            # Generate a random title using the keywords
            main_keyword = random.choice(keywords) if keywords else "Product"
            title = f"{main_keyword.title()} - Sample Item {i+1}"
            
            # Random location based on filters or default to major Polish cities
            locations = ["Warsaw", "Krakow", "Gdansk", "Poznan", "Wroclaw", "Lodz", "Katowice"]
            if filters.get('location'):
                locations = [filters['location']]
            location = random.choice(locations)
            
            # Random condition
            conditions = ["new", "used", "damaged"]
            if filters.get('condition'):
                conditions = [filters['condition']]
            condition = random.choice(conditions)
            
            # Random posted time (within the last week)
            days_ago = random.randint(0, 7)
            hours_ago = random.randint(0, 23)
            posted_time = current_time - timedelta(days=days_ago, hours=hours_ago)
            
            # Generate a mock item
            item = {
                'title': title,
                'price': price,
                'currency': 'PLN',
                'description': f"This is a sample description for {title}. Generated for testing purposes.",
                'url': f"https://{marketplace}.pl/item/{i+1}",
                'image_url': f"https://picsum.photos/seed/{marketplace}{i}/300/200",
                'marketplace': marketplace,
                'location': location,
                'seller_name': f"Sample Seller {i+1}",
                'seller_rating': round(random.uniform(1, 5), 1),
                'condition': condition,
                'posted_at': posted_time.strftime("%Y-%m-%d %H:%M"),
                'is_promoted': random.choice([True, False]),
                'additional_data': {
                    'views': random.randint(10, 1000),
                    'favorites': random.randint(0, 50),
                    'shipping_options': random.choice(["Courier", "InPost", "Personal Pickup", "Multiple options"]),
                    'payment_options': random.choice(["Cash", "Bank Transfer", "Payment on Delivery", "Multiple options"])
                }
            }
            
            results.append(item)
            
        return results