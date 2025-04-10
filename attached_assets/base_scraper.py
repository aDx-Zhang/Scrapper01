import requests
import logging
import random
import time
from abc import ABC, abstractmethod
from requests.exceptions import RequestException, Timeout, TooManyRedirects
from typing import List, Dict, Any, Optional

from app import db
from scraper.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36 Edg/91.0.864.71'
]

class BaseScraper(ABC):
    """Base class for all marketplace scrapers"""
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        self.proxy_manager = proxy_manager
        self.session = requests.Session()
        self.set_random_user_agent()
        
    def set_random_user_agent(self):
        """Set a random user agent for the requests session"""
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS)
        })
    
    def get_with_retry(self, url: str, max_retries: int = 3, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
        """Make a GET request with retry logic and proxy rotation"""
        retries = 0
        proxy = None
        use_direct_connection = False
        
        # Debug info
        logger.debug(f"Making request to URL: {url}")
        logger.debug(f"Using proxy manager: {self.proxy_manager is not None}")
        
        # Check if proxy manager exists before trying to get a proxy
        if self.proxy_manager and not use_direct_connection:
            try:
                proxy = self.proxy_manager.get_proxy()
                if proxy:
                    logger.debug(f"Got proxy: {proxy.ip}:{proxy.port}")
                    # If proxy doesn't have auth credentials, log a warning
                    if not (proxy.username and proxy.password) and proxy.protocol == "http":
                        logger.warning(f"Proxy {proxy.ip}:{proxy.port} has no authentication credentials. May fail with 407 error.")
                else:
                    logger.warning("No proxy available from proxy manager")
            except Exception as e:
                logger.error(f"Error getting proxy: {str(e)}")
                logger.exception("Full proxy acquisition error:")
                proxy = None
        
        while retries < max_retries:
            try:
                proxies = None
                if proxy:
                    try:
                        proxy_url = proxy.get_proxy_url()
                        proxies = {
                            'http': proxy_url,
                            'https': proxy_url
                        }
                        logger.debug(f"Using proxy URL: {proxy_url}")
                    except Exception as e:
                        logger.error(f"Error generating proxy URL: {str(e)}")
                        logger.exception("Full proxy URL generation error:")
                        proxies = None
                
                # Set a new random user agent for every request
                self.set_random_user_agent()
                
                # Add a small delay to respect rate limits
                delay = random.uniform(1, 3)
                logger.debug(f"Waiting {delay:.2f} seconds before request")
                time.sleep(delay)
                
                # Add debug headers to track our requests
                headers = kwargs.get('headers', {})
                headers.update({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                })
                kwargs['headers'] = headers
                
                logger.debug(f"Sending GET request to {url} with timeout={timeout}")
                
                response = self.session.get(
                    url,
                    timeout=timeout,
                    proxies=proxies,
                    **kwargs
                )
                
                # If successful, mark proxy as working
                if proxy and self.proxy_manager:
                    try:
                        self.proxy_manager.mark_success(proxy)
                    except Exception as e:
                        logger.error(f"Error marking proxy as successful: {str(e)}")
                
                logger.debug(f"Got response with status code: {response.status_code}")
                
                if response.status_code == 200:
                    logger.debug(f"Request successful, returning response (content length: {len(response.content)})")
                    return response
                elif response.status_code in [403, 429]:  # Forbidden or Too Many Requests
                    logger.warning(f"Rate limited or blocked (Status code: {response.status_code}). Response: {response.text[:200]}...")
                    if proxy and self.proxy_manager:
                        try:
                            self.proxy_manager.mark_failure(proxy)
                        except Exception as e:
                            logger.error(f"Error marking proxy as failed: {str(e)}")
                    
                    # Try to get a new proxy
                    if self.proxy_manager:
                        try:
                            proxy = self.proxy_manager.get_proxy()
                            logger.debug(f"Got new proxy: {proxy.ip if proxy else None}")
                        except Exception as e:
                            logger.error(f"Error getting new proxy: {str(e)}")
                            proxy = None
                else:
                    logger.warning(f"Request failed with status code: {response.status_code}, response: {response.text[:200]}...")
                    
            except (RequestException, Timeout, TooManyRedirects) as e:
                logger.error(f"Request error for URL {url}: {type(e).__name__}: {str(e)}")
                
                # Check if it's a proxy authentication error (HTTP 407)
                if "407 Proxy Authentication Required" in str(e):
                    logger.warning("Proxy authentication required but credentials not provided. Disabling this proxy and trying direct connection.")
                    if proxy and self.proxy_manager:
                        try:
                            # Mark the proxy as failed with max failures to disable it
                            proxy.failure_count = self.proxy_manager.max_failures
                            proxy.is_active = False
                            db.session.commit()
                            logger.info(f"Disabled proxy {proxy.ip}:{proxy.port} due to authentication requirement")
                        except Exception as deactivate_err:
                            logger.error(f"Error disabling proxy: {str(deactivate_err)}")
                            try:
                                db.session.rollback()
                            except:
                                pass
                    
                    # Try direct connection for this request
                    proxy = None
                    logger.info("Falling back to direct connection due to proxy authentication issues")
                    
                # Regular proxy failure
                elif proxy and self.proxy_manager:
                    try:
                        self.proxy_manager.mark_failure(proxy)
                    except Exception as proxy_e:
                        logger.error(f"Error marking proxy as failed: {str(proxy_e)}")
                
                    # Try to get a new proxy
                    if self.proxy_manager:
                        try:
                            proxy = self.proxy_manager.get_proxy()
                            logger.debug(f"Got new proxy after error: {proxy.ip if proxy else None}")
                        except Exception as e:
                            logger.error(f"Error getting new proxy after request error: {str(e)}")
                            proxy = None
            except Exception as e:
                # Catch any other unexpected exceptions
                logger.error(f"Unexpected error during request: {type(e).__name__}: {str(e)}")
                logger.exception("Full exception details:")
                
            # Increment retry counter and wait
            retries += 1
            wait_time = 2 ** retries  # Exponential backoff
            logger.info(f"Retrying in {wait_time} seconds... (Attempt {retries}/{max_retries})")
            time.sleep(wait_time)
            
        logger.error(f"Failed to fetch {url} after {max_retries} attempts")
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
