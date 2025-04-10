"""
Base Scraper Module - Foundation for marketplace scrapers
"""
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

# Proxy manager might be imported from different places
try:
    from utils.proxy_manager import ProxyManager
except ImportError:
    try:
        from attached_assets.proxy_manager import ProxyManager
    except ImportError:
        # Create a simple proxy manager class that doesn't actually use proxies
        class ProxyManager:
            def get_proxy(self, country_code: Optional[str] = None) -> Optional[str]:
                return None
            
            def report_proxy_failure(self, proxy_url: str) -> None:
                pass
            
            def reset_failure_count(self, proxy_url: str) -> None:
                pass
            
            def count_active_proxies(self) -> int:
                return 0

logger = logging.getLogger(__name__)

# List of User-Agent strings for request randomization
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59",
]

class BaseScraper(ABC):
    """Base class for all marketplace scrapers"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        """
        Initialize the scraper
        
        Args:
            proxy_manager: Optional proxy manager for rotating IPs
        """
        self.session = requests.Session()
        self.proxy_manager = proxy_manager
        self.set_random_user_agent()
        
    def set_random_user_agent(self):
        """Set a random user agent for the requests session"""
        user_agent = random.choice(USER_AGENTS)
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
    
    def get_with_retry(self, url: str, max_retries: int = 3, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
        """Make a GET request with retry logic and proxy rotation"""
        current_retry = 0
        current_proxy = None
        
        if self.proxy_manager:
            current_proxy = self.proxy_manager.get_proxy(country_code="PL")
            if current_proxy:
                kwargs['proxies'] = {
                    'http': current_proxy,
                    'https': current_proxy
                }
        
        while current_retry < max_retries:
            try:
                response = self.session.get(url, timeout=timeout, **kwargs)
                
                # If successful and we used a proxy, reset its failure count
                if response.status_code == 200 and current_proxy and self.proxy_manager:
                    self.proxy_manager.reset_failure_count(current_proxy)
                
                # Check if we got blocked or rate limited
                if response.status_code in (403, 429):
                    # If we're using a proxy, report failure and get a new one
                    if current_proxy and self.proxy_manager:
                        self.proxy_manager.report_proxy_failure(current_proxy)
                        current_proxy = self.proxy_manager.get_proxy(country_code="PL")
                        if current_proxy:
                            kwargs['proxies'] = {
                                'http': current_proxy,
                                'https': current_proxy
                            }
                    
                    # Switch user agent
                    self.set_random_user_agent()
                    current_retry += 1
                    time.sleep(random.uniform(1, 5))
                    continue
                
                return response
                
            except (RequestException, Timeout, ConnectionError) as e:
                logger.warning(f"Request failed: {str(e)}, retrying ({current_retry+1}/{max_retries})")
                
                # If we're using a proxy and it failed, report the failure
                if current_proxy and self.proxy_manager:
                    self.proxy_manager.report_proxy_failure(current_proxy)
                    current_proxy = self.proxy_manager.get_proxy(country_code="PL")
                    if current_proxy:
                        kwargs['proxies'] = {
                            'http': current_proxy,
                            'https': current_proxy
                        }
                
                current_retry += 1
                # Exponential backoff
                time.sleep(random.uniform(1, 2**current_retry))
        
        logger.error(f"Failed to get {url} after {max_retries} retries")
        return None
    
    @abstractmethod
    def search(self, keywords: List[str], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for items matching the given keywords and filters
        
        Args:
            keywords: List of keywords to search for
            filters: Dictionary of filters to apply (price range, location, etc.)
            
        Returns:
            List of items found matching the criteria
        """
        pass
    
    @abstractmethod
    def get_item_details(self, item_url: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific item
        
        Args:
            item_url: URL of the item to get details for
            
        Returns:
            Dictionary containing detailed item information
        """
        pass
    
    @abstractmethod
    def get_marketplace_name(self) -> str:
        """Return the name of the marketplace this scraper handles"""
        pass