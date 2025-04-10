import logging
import os
from datetime import datetime

# Try to import database models
try:
    from app import db
    from models import Feature, Marketplace
except ImportError:
    db = None
    Feature = None
    Marketplace = None

logger = logging.getLogger(__name__)

def initialize_database():
    """Initialize database with default data (features, marketplaces, etc.)"""
    if db is None or Feature is None or Marketplace is None:
        logger.error("Database models not available, cannot initialize database")
        return False
        
    logger.info("Initializing database...")
    
    # Create default admin user if it doesn't exist
    try:
        from models import User
        from werkzeug.security import generate_password_hash
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(admin)
            db.session.commit()
            logger.info("Created default admin user")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
    
    # Initialize features
    initialize_features()
    
    # Initialize marketplaces
    initialize_marketplaces()
    
    logger.info("Database initialization complete")
    return True

def initialize_features():
    """Initialize feature flags"""
    features = [
        {
            'name': 'use_proxies',
            'display_name': 'Use Proxies',
            'description': 'Use proxy servers for web scraping to avoid IP bans',
            'is_enabled': True,
            'is_premium': False,
            'category': 'scraping'
        },
        {
            'name': 'email_notifications',
            'display_name': 'Email Notifications',
            'description': 'Send notifications via email when new items are found',
            'is_enabled': True,
            'is_premium': False,
            'category': 'notifications'
        },
        {
            'name': 'browser_notifications',
            'display_name': 'Browser Notifications',
            'description': 'Show notifications in the browser when new items are found',
            'is_enabled': True,
            'is_premium': False,
            'category': 'notifications'
        },
        {
            'name': 'desktop_notifications',
            'display_name': 'Desktop Notifications',
            'description': 'Send notifications to desktop when new items are found',
            'is_enabled': False,
            'is_premium': True,
            'category': 'notifications'
        },
        {
            'name': 'advanced_filters',
            'display_name': 'Advanced Filters',
            'description': 'Enable advanced filtering options for searches',
            'is_enabled': True,
            'is_premium': False,
            'category': 'search'
        },
        {
            'name': 'premium_marketplaces',
            'display_name': 'Premium Marketplaces',
            'description': 'Access to premium marketplaces with advanced search capabilities',
            'is_enabled': False,
            'is_premium': True,
            'category': 'search'
        },
        {
            'name': 'scheduled_searches',
            'display_name': 'Scheduled Searches',
            'description': 'Schedule automatic searches at regular intervals',
            'is_enabled': False,
            'is_premium': True,
            'category': 'search'
        },
        {
            'name': 'export_results',
            'display_name': 'Export Results',
            'description': 'Export search results to CSV, Excel, etc.',
            'is_enabled': True,
            'is_premium': False,
            'category': 'results'
        },
        {
            'name': 'price_history',
            'display_name': 'Price History',
            'description': 'Track price history for items over time',
            'is_enabled': False,
            'is_premium': True,
            'category': 'results'
        }
    ]
    
    for feature_data in features:
        # Check if feature already exists
        feature = Feature.query.filter_by(name=feature_data['name']).first()
        if feature:
            logger.info(f"Feature already exists: {feature_data['name']}")
        else:
            feature = Feature(**feature_data)
            db.session.add(feature)
            db.session.commit()
            logger.info(f"Created feature: {feature_data['name']}")
    
    logger.info("Features initialized")

def initialize_marketplaces():
    """Initialize marketplace data"""
    marketplaces = [
        {
            'name': 'olx',
            'display_name': 'OLX.pl',
            'base_url': 'https://www.olx.pl',
            'logo_url': 'https://logo.clearbit.com/olx.pl',
            'description': 'Poland\'s largest classified ads site with millions of items',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 100
        },
        {
            'name': 'allegro',
            'display_name': 'Allegro.pl',
            'base_url': 'https://allegro.pl',
            'logo_url': 'https://logo.clearbit.com/allegro.pl',
            'description': 'The largest Polish online marketplace with auction and buy-now options',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 90
        },
        {
            'name': 'vinted',
            'display_name': 'Vinted.pl',
            'base_url': 'https://www.vinted.pl',
            'logo_url': 'https://logo.clearbit.com/vinted.pl',
            'description': 'Buy and sell second-hand clothing and accessories',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 80
        },
        {
            'name': 'facebook',
            'display_name': 'Facebook Marketplace',
            'base_url': 'https://www.facebook.com/marketplace',
            'logo_url': 'https://logo.clearbit.com/facebook.com',
            'description': 'Local marketplace from Facebook with items from nearby sellers',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 70
        },
        {
            'name': 'sprzedajemy',
            'display_name': 'Sprzedajemy.pl',
            'base_url': 'https://sprzedajemy.pl',
            'logo_url': 'https://logo.clearbit.com/sprzedajemy.pl',
            'description': 'Popular Polish classifieds site with a wide range of categories',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 60
        },
        {
            'name': 'otodom',
            'display_name': 'OtoDom.pl',
            'base_url': 'https://www.otodom.pl',
            'logo_url': 'https://logo.clearbit.com/otodom.pl',
            'description': 'Real estate marketplace for buying, selling, and renting properties',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 50
        },
        {
            'name': 'otomoto',
            'display_name': 'OtoMoto.pl',
            'base_url': 'https://www.otomoto.pl',
            'logo_url': 'https://logo.clearbit.com/otomoto.pl',
            'description': 'Automotive marketplace for cars, motorcycles, and other vehicles',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 50
        },
        {
            'name': 'gumtree',
            'display_name': 'Gumtree.pl',
            'base_url': 'https://www.gumtree.pl',
            'logo_url': 'https://logo.clearbit.com/gumtree.pl',
            'description': 'Free classifieds platform with local listings',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 40
        },
        {
            'name': 'emaito',
            'display_name': 'Emaito.pl',
            'base_url': 'https://emaito.pl',
            'logo_url': 'https://emaito.pl/img/emaito-logo.png',
            'description': 'Smaller Polish classifieds site with a focus on local listings',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 30
        },
        {
            'name': 'alejahandlowa',
            'display_name': 'AlejaHandlowa.pl',
            'base_url': 'https://alejahandlowa.pl',
            'logo_url': 'https://alejahandlowa.pl/logo.png',
            'description': 'Marketplace with a focus on business listings and wholesale items',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 20
        },
        {
            'name': 'ogloszenia-online',
            'display_name': 'Ogloszenia-Online.pl',
            'base_url': 'https://ogloszenia-online.pl',
            'logo_url': 'https://ogloszenia-online.pl/logo.png',
            'description': 'Online classifieds portal with various categories',
            'is_enabled': True,
            'is_premium': False,
            'country': 'PL',
            'priority': 10
        }
    ]
    
    for marketplace_data in marketplaces:
        # Check if marketplace already exists
        marketplace = Marketplace.query.filter_by(name=marketplace_data['name']).first()
        if marketplace:
            logger.info(f"Marketplace already exists: {marketplace_data['name']}")
        else:
            marketplace = Marketplace(**marketplace_data)
            db.session.add(marketplace)
            db.session.commit()
            logger.info(f"Created marketplace: {marketplace_data['name']}")
    
    logger.info("Marketplaces initialized")