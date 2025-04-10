import os
import logging
from datetime import datetime
import json
from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import check_password_hash
from app import app, db
from models import SearchResult, Feature, Marketplace, Proxy, EmailConfig, Notification, Monitor, Item, User, APIConfig
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
    telegram_config = APIConfig.query.filter_by(service_type='telegram', is_active=True).first()
    
    return render_template(
        'settings.html',
        title='Settings',
        features=features,
        feature_categories=feature_categories,
        email_config=email_config,
        telegram_config=telegram_config
    )

@app.route('/settings/api/telegram', methods=['POST'])
@login_required
def update_telegram_config():
    """Update Telegram API configuration"""
    token = request.form.get('telegram_token')
    if not token:
        return jsonify({'success': False, 'error': 'Token is required'})
    
    config = APIConfig.query.filter_by(service_type='telegram').first()
    if not config:
        config = APIConfig(
            name='Telegram Bot',
            service_type='telegram'
        )
    
    config.api_key = token
    config.is_active = True
    
    try:
        db.session.add(config)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/settings/test/telegram', methods=['POST'])
@login_required
def test_telegram():
    """Test Telegram configuration"""
    config = APIConfig.query.filter_by(service_type='telegram', is_active=True).first()
    if not config:
        return jsonify({'success': False, 'error': 'Telegram not configured'})
    
    try:
        import telegram
        bot = telegram.Bot(token=config.api_key)
        bot.get_me()  # Verify token is valid
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/settings/test_email', methods=['POST'])
def test_email():
    """Test email configuration"""
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib
    
    try:
        # Get form data
        smtp_server = request.form.get('smtp_server')
        smtp_port = int(request.form.get('smtp_port'))
        smtp_username = request.form.get('smtp_username')
        smtp_password = request.form.get('smtp_password')
        
        # Create test message
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = smtp_username
        msg['Subject'] = 'Test Email from Polish Marketplace Monitor'
        body = 'This is a test email from your marketplace monitor. If you received this, your email configuration is working!'
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
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

@app.template_filter('datetime')
def datetime_filter(value):
    """Format datetime for template display"""
    if not value:
        return "N/A"
    return value.strftime("%Y-%m-%d %H:%M")

@app.template_filter('next_update')
def next_update_filter(last_run, interval_minutes):
    """Calculate next update time"""
    if not last_run:
        return "Not scheduled"
    from datetime import timedelta
    next_run = last_run + timedelta(minutes=interval_minutes)
    return next_run.strftime("%Y-%m-%d %H:%M")

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
    
    # Create default monitor for user if none exists
    monitor = Monitor.query.filter_by(user_id=current_user.id).first()
    if not monitor:
        monitor = Monitor(
            user_id=current_user.id,
            name="Default Monitor",
            marketplaces=data.get('marketplace', ''),
            keywords='',
            is_active=True
        )
        db.session.add(monitor)
        db.session.commit()
    
    # Check if item already exists
    existing_item = Item.query.filter_by(url=data.get('url')).first()
    if existing_item:
        return jsonify({'success': False, 'error': 'Item already being monitored'})
    
    # Create new item
    item = Item(
        monitor_id=monitor.id,
        title=data.get('title'),
        price=float(data.get('price', 0)),
        currency=data.get('currency', 'PLN'),
        url=data.get('url'),
        marketplace=data.get('marketplace'),
        location=data.get('location')
    )
    db.session.add(item)
    db.session.commit()
    
    return jsonify({'success': True})
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

@app.route('/monitor/settings/<int:item_id>', methods=['POST'])
@login_required
def update_monitor_settings(item_id):
    """Update monitoring settings for a specific item"""
    item = Item.query.get_or_404(item_id)
    monitor = Monitor.query.get(item.monitor_id)
    
    # Ensure the monitor belongs to the current user
    if monitor.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    # Update monitor settings
    monitor.interval_minutes = max(5, min(1440, data.get('interval', 30)))  # Between 5 min and 24 hours
    monitor.notification_email = data.get('email_notify', False)
    monitor.notification_browser = data.get('browser_notify', False)
    monitor.notification_telegram = data.get('telegram_notify', False)
    
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/monitor/item/<int:item_id>')
@login_required
def item_details(item_id):
    """Show detailed information about a monitored item"""
    item = Item.query.get_or_404(item_id)
    
    # Ensure the item belongs to the current user's monitor
    monitor = Monitor.query.get(item.monitor_id)
    if monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('monitor'))
    
    # Get notifications related to this item's data
    notifications = Notification.query.filter(
        Notification.item_data.contains({'id': item_id})
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('item_details.html', item=item, notifications=notifications)

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
