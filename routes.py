import os
import logging
from datetime import datetime
import json
from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import check_password_hash
from app import app, db
from models import SearchResult, Feature, Marketplace, Proxy, EmailConfig, Notification, Monitor, Item, User
from utils.notification_service import NotificationService
from simple_scraper_manager import SimpleScraperManager

logger = logging.getLogger(__name__)

# Initialize scraper manager (singleton)
scraper_manager = SimpleScraperManager(use_proxies=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/')
def home():
    """Home page route with overview of the application"""
    return render_template('home.html', title='Polish Marketplace Scraper')

@app.route('/dashboard')
def dashboard():
    """Dashboard route with overview of user's monitors and recent items"""
    # Get some statistics for the dashboard
    total_marketplaces = Marketplace.query.count()
    enabled_marketplaces = Marketplace.query.filter_by(is_enabled=True).count()
    recent_searches = SearchResult.query.order_by(SearchResult.created_at.desc()).limit(5).all()
    
    return render_template(
        'dashboard.html',
        title='Dashboard',
        total_marketplaces=total_marketplaces,
        enabled_marketplaces=enabled_marketplaces,
        recent_searches=recent_searches
    )

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Basic search functionality"""
    if request.method == 'POST':
        # Get search parameters
        keywords = request.form.get('keywords', '').strip()
        marketplace = request.form.get('marketplace', 'olx')
        
        if not keywords:
            flash('Please enter search keywords', 'warning')
            return redirect(url_for('search'))
        
        # Parse filters from form
        filters = {
            'price_min': request.form.get('price_min', None),
            'price_max': request.form.get('price_max', None),
            'location': request.form.get('location', None),
            'condition': request.form.get('condition', None)
        }
        
        # Convert price values to float if provided
        if filters['price_min'] and filters['price_min'].strip():
            try:
                filters['price_min'] = float(filters['price_min'])
            except ValueError:
                filters['price_min'] = None
                
        if filters['price_max'] and filters['price_max'].strip():
            try:
                filters['price_max'] = float(filters['price_max'])
            except ValueError:
                filters['price_max'] = None
        
        # Remove empty filters
        filters = {k: v for k, v in filters.items() if v is not None and v != ''}
        
        # Search using scraper manager
        search_keywords = [kw.strip() for kw in keywords.split(',')]
        page = int(request.form.get('page', 1))
        
        results = scraper_manager.search(
            marketplace=marketplace,
            keywords=search_keywords,
            filters=filters,
            page=page
        )
        
        # Save search history
        search_result = SearchResult(
            search_term=keywords,
            marketplace=marketplace,
            filters=filters,
            result_count=len(results.get('results', []))
        )
        db.session.add(search_result)
        db.session.commit()
        
        # Get available marketplaces for dropdown
        marketplaces = Marketplace.get_available_marketplaces()
        
        return render_template(
            'search_results.html',
            title='Search Results',
            search_term=keywords,
            marketplace=marketplace,
            filters=filters,
            results=results.get('results', []),
            total=results.get('total', 0),
            page=results.get('page', 1),
            has_more=results.get('has_more', False),
            error=results.get('error', None),
            marketplaces=marketplaces
        )
    
    # GET request - show search form
    marketplaces = Marketplace.get_available_marketplaces()
    recent_searches = SearchResult.query.order_by(SearchResult.created_at.desc()).limit(5).all()
    
    return render_template(
        'search.html',
        title='Search Marketplaces',
        marketplaces=marketplaces,
        recent_searches=recent_searches
    )

@app.route('/marketplaces')
def marketplaces():
    """Displays available marketplaces and their status"""
    all_marketplaces = Marketplace.query.order_by(Marketplace.priority.desc()).all()
    return render_template(
        'marketplaces.html',
        title='Available Marketplaces',
        marketplaces=all_marketplaces
    )

@app.route('/settings')
def settings():
    """Settings page with feature toggles and global configurations"""
    features = Feature.query.order_by(Feature.category).all()
    feature_categories = set([f.category for f in features])
    
    email_config = EmailConfig.query.first()
    
    return render_template(
        'settings.html',
        title='Settings',
        features=features,
        feature_categories=feature_categories,
        email_config=email_config
    )

@app.route('/notifications')
def notifications():
    """Display notifications page with all notifications"""
    notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    unread_count = Notification.query.filter_by(is_read=False).count()
    
    return render_template(
        'notifications.html',
        title='Notifications',
        notifications=notifications,
        unread_count=unread_count
    )

@app.route('/mark_notification_read/<int:notification_id>')
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    success = NotificationService.mark_notification_read(notification_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': success})
    
    return redirect(url_for('notifications'))

@app.route('/api/search', methods=['POST'])
def api_search():
    """API endpoint for searching (for potential AJAX usage)"""
    data = request.get_json()
    
    keywords = data.get('keywords', '').strip()
    marketplace = data.get('marketplace', 'olx')
    filters = data.get('filters', {})
    page = int(data.get('page', 1))
    
    if not keywords:
        return jsonify({'error': 'No keywords provided', 'results': [], 'total': 0}), 400
    
    search_keywords = [kw.strip() for kw in keywords.split(',')]
    
    results = scraper_manager.search(
        marketplace=marketplace,
        keywords=search_keywords,
        filters=filters,
        page=page
    )
    
    return jsonify(results)

@app.context_processor
def utility_processor():
    """Make utility functions available to templates"""
    def format_datetime(dt):
        """Format datetime for display"""
        if not dt:
            return "N/A"
        return dt.strftime("%Y-%m-%d %H:%M")
        
    def format_price(price, currency="PLN"):
        """Format price for display"""
        if not price:
            return "N/A"
        return f"{price:.2f} {currency}"
        
    def is_feature_enabled(feature_name):
        """Check if a feature is enabled"""
        return Feature.is_feature_enabled(feature_name)
        
    def get_unread_notifications_count():
        """Get count of unread notifications"""
        return Notification.query.filter_by(is_read=False).count()
        
    return dict(
        format_datetime=format_datetime,
        format_price=format_price,
        is_feature_enabled=is_feature_enabled,
        get_unread_notifications_count=get_unread_notifications_count
    )
@app.route('/monitor')
@login_required
def monitor():
    """Monitor page showing tracked items"""
    monitored_items = Item.query.join(Monitor).filter(Monitor.user_id == current_user.id).all()
    return render_template('monitor.html', monitored_items=monitored_items)

@app.route('/monitor/add', methods=['POST'])
@login_required
def add_to_monitor():
    """Add item to monitor"""
    data = request.get_json()
    
    # Create or get monitor
    monitor = Monitor.query.filter_by(user_id=current_user.id).first()
    if not monitor:
        monitor = Monitor(
            user_id=current_user.id,
            name="Default Monitor",
            is_active=True
        )
        db.session.add(monitor)
    
    # Check if item already exists
    existing_item = Item.query.filter_by(url=data.get('url')).first()
    
    if existing_item:
        new_price = data.get('price')
        if existing_item.price != new_price:
            existing_item.previous_price = existing_item.price
            existing_item.price = new_price
            existing_item.price_changed = True
            
            # Create price change notification
            notification = Notification.create_from_item(
                existing_item,
                title=f"Price Change: {existing_item.title}",
                message=f"Price changed from {existing_item.previous_price} to {new_price} {existing_item.currency}"
            )
            
        db.session.commit()
    else:
        # Create new item
        item = Item(
            monitor_id=monitor.id,
            title=data.get('title'),
            price=data.get('price'),
            currency=data.get('currency', 'PLN'),
            url=data.get('url'),
            marketplace=data.get('marketplace'),
            location=data.get('location'),
        )
        db.session.add(item)
        db.session.commit()
    
    return jsonify({'success': True})

@app.route('/monitor/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_monitor(item_id):
    """Remove item from monitor"""
    item = Item.query.get_or_404(item_id)
    monitor = Monitor.query.get(item.monitor_id)
    
    if monitor.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({'success': True})
