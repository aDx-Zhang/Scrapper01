import logging
import random
import requests
import socket
import concurrent.futures
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import List, Optional, Dict, Tuple, Any
from functools import lru_cache
from collections import defaultdict

from app import db
from models import Proxy

logger = logging.getLogger(__name__)

class ProxyManager:
    """Manages a pool of proxies for rotation during scraping"""
    
    def __init__(self, max_failures: int = 3, cooldown_minutes: int = 10):
        self.max_failures = max_failures
        self.cooldown_minutes = cooldown_minutes
        logger.debug(f"Initialized ProxyManager with max_failures={max_failures}, cooldown_minutes={cooldown_minutes}")
        
        # Check if we actually have any proxies configured
        try:
            proxy_count = Proxy.query.count()
            logger.debug(f"Found {proxy_count} total proxies in database")
            
            # Check for proxies with authentication required
            auth_proxies = Proxy.query.filter(
                (Proxy.username.is_(None) | Proxy.username == '') & 
                Proxy.is_active == True
            ).all()
            
            # Log warning for proxies without auth that might need it
            for proxy in auth_proxies:
                logger.warning(f"Proxy {proxy.ip}:{proxy.port} has no authentication credentials. "
                              "This may cause '407 Proxy Authentication Required' errors.")
            
            # If no proxies exist, we'll just return None from get_proxy
            if proxy_count == 0:
                logger.warning("No proxies found in database. Using direct connections.")
                
        except Exception as e:
            logger.error(f"Error checking proxy count: {str(e)}")
        
    def get_proxy(self) -> Optional[Proxy]:
        """Get a working proxy from the database"""
        try:
            # Get a proxy that is active, hasn't failed too much, and hasn't been used recently
            cooldown_time = datetime.utcnow() - timedelta(minutes=self.cooldown_minutes)
            
            # First check if we have any proxies at all
            total_proxies = Proxy.query.count()
            if total_proxies == 0:
                logger.debug("No proxies configured in database. Using direct connection.")
                return None
            
            logger.debug(f"Searching for available proxy from {total_proxies} total proxies")
            
            # Get active proxies that haven't failed too much
            available_proxies = Proxy.query.filter(
                Proxy.is_active == True,
                Proxy.failure_count < self.max_failures
            ).all()
            
            if not available_proxies:
                logger.warning("No available active proxies found. Using direct connection.")
                return None
            
            logger.debug(f"Found {len(available_proxies)} active proxies with acceptable failure count")
            
            # Prefer proxies that aren't in cooldown, but use a proxy in cooldown if none are available
            fresh_proxies = [p for p in available_proxies if p.last_used is None or p.last_used <= cooldown_time]
            
            if fresh_proxies:
                logger.debug(f"Found {len(fresh_proxies)} proxies not in cooldown")
                
                # Prefer proxies with authentication credentials set
                auth_proxies = [p for p in fresh_proxies if p.username and p.password]
                if auth_proxies:
                    logger.debug(f"Found {len(auth_proxies)} proxies with authentication credentials")
                    proxy = random.choice(auth_proxies)
                else:
                    # If no auth proxies available, use any fresh proxy
                    proxy = random.choice(fresh_proxies)
            else:
                logger.warning("All proxies are in cooldown. Using least recently used proxy.")
                # Sort by last_used time (oldest first)
                available_proxies.sort(key=lambda p: p.last_used if p.last_used else datetime.min)
                proxy = available_proxies[0]
            
            logger.debug(f"Selected proxy: {proxy.ip}:{proxy.port}")
            
            # Update last used time
            try:
                proxy.last_used = datetime.utcnow()
                db.session.commit()
                logger.debug(f"Updated last_used time for proxy {proxy.id}")
            except Exception as commit_err:
                logger.error(f"Error updating proxy last_used time: {str(commit_err)}")
                db.session.rollback()
            
            return proxy
            
        except Exception as e:
            logger.error(f"Error getting proxy: {str(e)}")
            logger.exception("Full proxy selection error:")
            try:
                db.session.rollback()
            except:
                pass
            return None
    
    def mark_success(self, proxy: Proxy) -> None:
        """Mark a proxy as successfully used"""
        try:
            proxy.last_used = datetime.utcnow()
            # Reset failure count on success
            if proxy.failure_count > 0:
                proxy.failure_count = 0
            db.session.commit()
        except Exception as e:
            logger.error(f"Error marking proxy success: {str(e)}")
            db.session.rollback()
    
    def mark_failure(self, proxy: Proxy) -> None:
        """Mark a proxy as failed"""
        try:
            proxy.failure_count += 1
            proxy.last_used = datetime.utcnow()
            
            # Deactivate proxy if it has failed too many times
            if proxy.failure_count >= self.max_failures:
                logger.warning(f"Deactivating proxy {proxy.ip}:{proxy.port} due to too many failures")
                proxy.is_active = False
                
            db.session.commit()
        except Exception as e:
            logger.error(f"Error marking proxy failure: {str(e)}")
            db.session.rollback()
            
    def add_proxy(self, ip: str, port: int, protocol: str = 'http', 
                 username: Optional[str] = None, password: Optional[str] = None,
                 country: str = 'PL') -> bool:
        """Add a new proxy to the database"""
        try:
            new_proxy = Proxy(
                ip=ip,
                port=port,
                protocol=protocol,
                username=username,
                password=password,
                is_active=True,
                failure_count=0,
                country=country
            )
            db.session.add(new_proxy)
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding proxy: {str(e)}")
            db.session.rollback()
            return False
            
    def get_active_proxies_count(self) -> int:
        """Get count of active proxies"""
        return Proxy.query.filter_by(is_active=True).count()
        
    @lru_cache(maxsize=32)
    def test_proxy(self, proxy: Proxy, test_url: str = "https://www.google.com", timeout: int = 10) -> Tuple[bool, float]:
        """
        Test if a proxy is working and measure its response time
        
        Args:
            proxy: Proxy to test
            test_url: URL to test the proxy with
            timeout: Request timeout in seconds
            
        Returns:
            Tuple of (is_working, response_time_in_seconds)
        """
        try:
            proxy_url = proxy.get_proxy_url()
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            start_time = datetime.now()
            response = requests.get(
                test_url, 
                proxies=proxies, 
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            )
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds()
            
            # Check if the response is valid
            if response.status_code == 200:
                logger.debug(f"Proxy {proxy.ip}:{proxy.port} working. Response time: {response_time:.2f}s")
                return True, response_time
            else:
                logger.warning(f"Proxy {proxy.ip}:{proxy.port} returned status code {response.status_code}")
                return False, response_time
                
        except Exception as e:
            logger.error(f"Proxy {proxy.ip}:{proxy.port} test failed: {str(e)}")
            return False, float('inf')
            
    def verify_proxies(self, test_url: str = "https://www.google.com") -> Dict[str, List[Proxy]]:
        """
        Test all active proxies and sort them by working status and speed
        
        Args:
            test_url: URL to test the proxies with
            
        Returns:
            Dictionary with 'working' and 'failed' proxy lists
        """
        proxies = Proxy.query.filter_by(is_active=True).all()
        if not proxies:
            logger.warning("No active proxies to verify")
            return {'working': [], 'failed': []}
            
        # Create dictionary to store results
        results = {
            'working': [],
            'failed': []
        }
        
        # Use ThreadPoolExecutor to test proxies in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(proxies))) as executor:
            # Start the proxy tests and mark each future with its proxy
            future_to_proxy = {
                executor.submit(self.test_proxy, proxy, test_url): proxy for proxy in proxies
            }
            
            # Process the completed futures as they complete
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    is_working, response_time = future.result()
                    if is_working:
                        results['working'].append((proxy, response_time))
                        # Update proxy status in database
                        self.mark_success(proxy)
                    else:
                        results['failed'].append(proxy)
                        # Update proxy status in database
                        self.mark_failure(proxy)
                except Exception as e:
                    logger.error(f"Error testing proxy {proxy.ip}:{proxy.port}: {str(e)}")
                    results['failed'].append(proxy)
                    self.mark_failure(proxy)
        
        # Sort working proxies by response time
        results['working'] = [p[0] for p in sorted(results['working'], key=lambda x: x[1])]
        
        logger.info(f"Proxy verification complete. Working: {len(results['working'])}, Failed: {len(results['failed'])}")
        return results
    
    def find_proxies_from_public_sources(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find public proxies from various sources
        
        Args:
            limit: Maximum number of proxies to return
            
        Returns:
            List of proxy dictionaries with ip, port, protocol, country info
        """
        try:
            logger.info(f"Searching for public proxies (limit: {limit})...")
            proxies = []
            
            # Try to get proxies from public APIs
            # Note: These APIs may have usage limits or may change over time
            sources = [
                "https://www.proxy-list.download/api/v1/get?type=http",
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
            ]
            
            for source in sources:
                try:
                    response = requests.get(source, timeout=10)
                    if response.status_code == 200:
                        # Parse the response based on format
                        content = response.text
                        if ':' in content:
                            # Format is usually IP:PORT
                            for line in content.strip().split('\n'):
                                if ':' in line:
                                    ip, port = line.strip().split(':')
                                    proxies.append({
                                        'ip': ip,
                                        'port': int(port),
                                        'protocol': 'http',
                                        'country': 'unknown'
                                    })
                                    
                                    if len(proxies) >= limit:
                                        break
                except Exception as e:
                    logger.error(f"Error fetching proxies from {source}: {str(e)}")
                    
                if len(proxies) >= limit:
                    break
                    
            logger.info(f"Found {len(proxies)} public proxies")
            return proxies[:limit]
            
        except Exception as e:
            logger.error(f"Error finding public proxies: {str(e)}")
            return []
            
    def import_proxies_from_list(self, proxy_list: List[Dict[str, Any]]) -> int:
        """
        Import proxies from a list of dictionaries
        
        Args:
            proxy_list: List of proxy dictionaries with keys: ip, port, protocol, 
                      username (optional), password (optional), country (optional)
                      
        Returns:
            Number of proxies successfully imported
        """
        imported_count = 0
        for proxy_data in proxy_list:
            try:
                # Check if proxy already exists
                existing = Proxy.query.filter_by(
                    ip=proxy_data['ip'],
                    port=proxy_data['port']
                ).first()
                
                if existing:
                    logger.debug(f"Proxy {proxy_data['ip']}:{proxy_data['port']} already exists")
                    continue
                    
                # Add the new proxy
                new_proxy = Proxy(
                    ip=proxy_data['ip'],
                    port=proxy_data['port'],
                    protocol=proxy_data.get('protocol', 'http'),
                    username=proxy_data.get('username'),
                    password=proxy_data.get('password'),
                    country=proxy_data.get('country', 'unknown'),
                    is_active=True,
                    failure_count=0
                )
                
                db.session.add(new_proxy)
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Error importing proxy {proxy_data.get('ip')}:{proxy_data.get('port')}: {str(e)}")
                
        if imported_count > 0:
            try:
                db.session.commit()
                logger.info(f"Successfully imported {imported_count} new proxies")
            except Exception as e:
                logger.error(f"Error committing proxy imports: {str(e)}")
                db.session.rollback()
                imported_count = 0
                
        return imported_count
