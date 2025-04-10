import logging
import random
from datetime import datetime
from typing import Optional, List, Dict

# Import proxy models (try both potential paths)
try:
    from app import db
    from models import Proxy
except ImportError:
    # For testing in standalone mode
    db = None
    Proxy = None

logger = logging.getLogger(__name__)

class ProxyManager:
    """Manages proxy selection and rotation for scrapers"""
    
    def __init__(self, auto_refresh: bool = True, country_code: str = 'PL'):
        """
        Initialize proxy manager
        
        Args:
            auto_refresh: Whether to automatically refresh proxy list when running low
            country_code: Default country code for proxies (PL for Poland)
        """
        self.auto_refresh = auto_refresh
        self.country_code = country_code
        self.local_proxies = []  # For cases where database isn't accessible
        
        # Try to load proxies from database
        self._load_proxies()
        
    def _load_proxies(self) -> List[Dict]:
        """Load active proxies from database"""
        if db is not None and Proxy is not None:
            try:
                active_proxies = Proxy.query.filter_by(is_active=True).all()
                logger.info(f"Loaded {len(active_proxies)} active proxies from database")
                return active_proxies
            except Exception as e:
                logger.error(f"Error loading proxies from database: {e}")
        return []
        
    def get_proxy(self, country_code: Optional[str] = None) -> Optional[str]:
        """
        Get a random proxy URL
        
        Args:
            country_code: Filter proxies by country code
            
        Returns:
            Proxy URL string or None if no proxies available
        """
        # Use provided country or default
        country = country_code or self.country_code
        
        if db is not None and Proxy is not None:
            try:
                # Try to get proxies from database
                query = Proxy.query.filter_by(is_active=True)
                if country:
                    query = query.filter_by(country=country)
                    
                # Order by last used and failure count
                query = query.order_by(Proxy.failure_count.asc(), Proxy.last_used.asc())
                proxy = query.first()
                
                if proxy:
                    # Update last_used time
                    proxy.last_used = datetime.utcnow()
                    db.session.commit()
                    
                    # Return the proxy URL
                    return proxy.get_proxy_url()
            except Exception as e:
                logger.error(f"Error getting proxy from database: {e}")
        
        # If we get here, either database access failed or no proxies available
        # Try using local cache
        if self.local_proxies:
            proxy_url = random.choice(self.local_proxies)
            logger.info(f"Using cached proxy: {proxy_url}")
            return proxy_url
            
        return None
    
    def report_proxy_failure(self, proxy_url: str) -> None:
        """
        Report a proxy failure to increase its failure count
        
        Args:
            proxy_url: The proxy URL that failed
        """
        if db is not None and Proxy is not None:
            try:
                # Extract IP from proxy URL
                # Format could be protocol://user:pass@ip:port or protocol://ip:port
                proxy_parts = proxy_url.split('@')
                ip_port = proxy_parts[-1].split(':')
                ip = ip_port[0]
                
                # Find proxy by IP
                proxy = Proxy.query.filter_by(ip=ip).first()
                if proxy:
                    proxy.failure_count += 1
                    
                    # Disable proxy if it has failed too many times
                    if proxy.failure_count >= 5:
                        proxy.is_active = False
                        logger.warning(f"Disabled proxy {proxy.ip} after {proxy.failure_count} failures")
                    
                    db.session.commit()
            except Exception as e:
                logger.error(f"Error reporting proxy failure: {e}")
    
    def reset_failure_count(self, proxy_url: str) -> None:
        """
        Reset failure count for a proxy after successful use
        
        Args:
            proxy_url: The proxy URL that was successful
        """
        if db is not None and Proxy is not None:
            try:
                # Extract IP from proxy URL
                proxy_parts = proxy_url.split('@')
                ip_port = proxy_parts[-1].split(':')
                ip = ip_port[0]
                
                # Find proxy by IP
                proxy = Proxy.query.filter_by(ip=ip).first()
                if proxy and proxy.failure_count > 0:
                    proxy.failure_count = 0
                    db.session.commit()
            except Exception as e:
                logger.error(f"Error resetting proxy failure count: {e}")
    
    def add_proxy(self, ip: str, port: int, username: Optional[str] = None, 
                 password: Optional[str] = None, protocol: str = 'http',
                 country: str = 'PL') -> bool:
        """
        Add a new proxy to the database
        
        Args:
            ip: Proxy IP address
            port: Proxy port
            username: Optional proxy username
            password: Optional proxy password
            protocol: Proxy protocol (http, https, socks4, socks5)
            country: Country code for the proxy
            
        Returns:
            Success flag
        """
        if db is not None and Proxy is not None:
            try:
                # Check if proxy already exists
                existing = Proxy.query.filter_by(ip=ip, port=port).first()
                if existing:
                    # Update existing proxy if needed
                    if not existing.is_active:
                        existing.is_active = True
                        existing.failure_count = 0
                        db.session.commit()
                    return True
                
                # Create new proxy
                proxy = Proxy(
                    ip=ip,
                    port=port,
                    username=username,
                    password=password,
                    protocol=protocol,
                    is_active=True,
                    country=country
                )
                db.session.add(proxy)
                db.session.commit()
                
                # Also add to local cache
                proxy_url = proxy.get_proxy_url()
                if proxy_url not in self.local_proxies:
                    self.local_proxies.append(proxy_url)
                
                logger.info(f"Added new proxy: {ip}:{port}")
                return True
            except Exception as e:
                logger.error(f"Error adding proxy to database: {e}")
        
        # If database not available, just add to local cache
        elif ip and port:
            protocol = protocol or 'http'
            if username and password:
                proxy_url = f"{protocol}://{username}:{password}@{ip}:{port}"
            else:
                proxy_url = f"{protocol}://{ip}:{port}"
                
            if proxy_url not in self.local_proxies:
                self.local_proxies.append(proxy_url)
            return True
            
        return False
    
    def count_active_proxies(self) -> int:
        """
        Count active proxies
        
        Returns:
            Number of active proxies
        """
        if db is not None and Proxy is not None:
            try:
                return Proxy.query.filter_by(is_active=True).count()
            except Exception:
                pass
        
        return len(self.local_proxies)