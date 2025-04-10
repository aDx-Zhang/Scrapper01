import logging
import json
import traceback
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import app, db
from models import User, Monitor, Item, Notification
from scraper import AllegroScraper, OLXScraper, VintedScraper, FacebookMarketplaceScraper, ProxyManager
from scheduler import run_monitor
from utils.notification import NotificationManager

logger = logging.getLogger(__name__)

@app.route('/')
def home():
    """Home page route"""
    return render_template('base.html')
    
@app.route('/test_scraper', methods=['GET', 'POST'])
def test_scraper():
    """Test scraper functionality for all marketplaces with pagination"""
    from simple_scraper_manager import SimpleScraperManager
    
    results = []
    marketplace = "olx"
    search_term = ""
    price_min = ""
    price_max = ""
    page = request.args.get('page', 1, type=int)
    
    # Store search parameters in session for pagination
    if request.method == 'POST':
        # New search, reset to page 1
        page = 1
        marketplace = request.form.get('marketplace', 'olx')
        search_term = request.form.get('search_term', '')
        price_min = request.form.get('price_min', '')
        price_max = request.form.get('price_max', '')
        
        # Store in session
        session['marketplace'] = marketplace
        session['search_term'] = search_term
        session['price_min'] = price_min
        session['price_max'] = price_max
    else:
        # GET request, retrieve from session if available
        marketplace = session.get('marketplace', 'olx')
        search_term = session.get('search_term', '')
        price_min = session.get('price_min', '')
        price_max = session.get('price_max', '')
    
    total_results = 0
    has_more = False
    
    if search_term:
        # Parse search parameters
        keywords = [keyword.strip() for keyword in search_term.split(',') if keyword.strip()]
        
        # Parse filters
        filters = {}
        if price_min:
            try:
                filters['price_min'] = float(price_min)
            except ValueError:
                flash('Invalid minimum price', 'danger')
        
        if price_max:
            try:
                filters['price_max'] = float(price_max)
            except ValueError:
                flash('Invalid maximum price', 'danger')
        
        try:
            # Initialize and execute scraper manager
            manager = SimpleScraperManager()
            logger.info(f"Testing {marketplace} scraper with keywords: {keywords}, filters: {filters}, page: {page}")
            
            # Execute the search with pagination
            search_results = manager.search(
                marketplace=marketplace,
                keywords=keywords,
                filters=filters,
                page=page,
                items_per_page=20
            )
            
            results = search_results['results']
            total_results = search_results['total']
            has_more = search_results['has_more']
            current_page = search_results['page']
            
            if results:
                if has_more:
                    flash(f'Showing results {(page-1)*20+1}-{(page-1)*20+len(results)} out of {total_results}', 'info')
                else:
                    flash(f'Found {total_results} results', 'success')
            else:
                flash('No results found. Try different search terms or filters.', 'info')
                
        except Exception as e:
            logger.error(f"Error testing scraper: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f'Error testing scraper: {str(e)}', 'danger')
    
    return render_template(
        'test_scraper.html', 
        results=results, 
        marketplace=marketplace, 
        search_term=search_term, 
        price_min=price_min, 
        price_max=price_max,
        page=page,
        has_more=has_more,
        total_results=total_results
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if username or email already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'danger')
            return render_template('register.html')
            
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Email already registered', 'danger')
            return render_template('register.html')
            
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """Log out the current user"""
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with monitor overview"""
    monitors = Monitor.query.filter_by(user_id=current_user.id).all()
    
    # Get some stats for each monitor
    monitor_stats = []
    for monitor in monitors:
        # Count total items found by this monitor
        items_count = Item.query.filter_by(monitor_id=monitor.id).count()
        
        # Count items found in the last 24 hours
        recent_items_count = Item.query.filter_by(monitor_id=monitor.id).filter(
            Item.found_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        monitor_stats.append({
            'monitor': monitor,
            'items_count': items_count,
            'recent_items_count': recent_items_count
        })
    
    # Get unread notifications count
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return render_template(
        'dashboard.html', 
        monitor_stats=monitor_stats,
        unread_count=unread_count
    )

@app.route('/monitors/new', methods=['GET', 'POST'])
@login_required
def create_monitor():
    """Create a new monitor"""
    if request.method == 'POST':
        name = request.form.get('name')
        marketplaces = request.form.getlist('marketplaces')
        keywords = request.form.get('keywords')
        price_min = request.form.get('price_min')
        price_max = request.form.get('price_max')
        location = request.form.get('location')
        condition = request.form.get('condition')
        min_seller_rating = request.form.get('min_seller_rating')
        interval_minutes = request.form.get('interval_minutes', 30)
        notification_email = 'notification_email' in request.form
        notification_browser = 'notification_browser' in request.form
        
        # Validate inputs
        if not name or not marketplaces or not keywords:
            flash('Name, marketplaces and keywords are required', 'danger')
            return render_template('monitor_form.html')
            
        # Create monitor
        new_monitor = Monitor(
            name=name,
            user_id=current_user.id,
            marketplaces=','.join(marketplaces),
            keywords=keywords,
            price_min=float(price_min) if price_min else None,
            price_max=float(price_max) if price_max else None,
            location=location,
            condition=condition,
            min_seller_rating=float(min_seller_rating) if min_seller_rating else None,
            interval_minutes=int(interval_minutes),
            notification_email=notification_email,
            notification_browser=notification_browser
        )
        
        db.session.add(new_monitor)
        db.session.commit()
        
        flash(f'Monitor "{name}" created successfully', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('monitor_form.html')

@app.route('/monitors/<int:monitor_id>')
@login_required
def monitor_detail(monitor_id):
    """Show monitor details and results"""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Make sure the monitor belongs to the current user
    if monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
        
    # Get all items for this monitor, sorted by newest first
    items = Item.query.filter_by(monitor_id=monitor.id).order_by(Item.found_at.desc()).all()
    
    return render_template('monitor_detail.html', monitor=monitor, items=items)

@app.route('/monitors/<int:monitor_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_monitor(monitor_id):
    """Edit an existing monitor"""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Make sure the monitor belongs to the current user
    if monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        monitor.name = request.form.get('name')
        monitor.marketplaces = ','.join(request.form.getlist('marketplaces'))
        monitor.keywords = request.form.get('keywords')
        monitor.price_min = float(request.form.get('price_min')) if request.form.get('price_min') else None
        monitor.price_max = float(request.form.get('price_max')) if request.form.get('price_max') else None
        monitor.location = request.form.get('location')
        monitor.condition = request.form.get('condition')
        monitor.min_seller_rating = float(request.form.get('min_seller_rating')) if request.form.get('min_seller_rating') else None
        monitor.interval_minutes = int(request.form.get('interval_minutes', 30))
        monitor.is_active = 'is_active' in request.form
        monitor.notification_email = 'notification_email' in request.form
        monitor.notification_browser = 'notification_browser' in request.form
        
        db.session.commit()
        
        flash(f'Monitor "{monitor.name}" updated successfully', 'success')
        return redirect(url_for('monitor_detail', monitor_id=monitor.id))
        
    return render_template('monitor_form.html', monitor=monitor)

@app.route('/monitors/<int:monitor_id>/delete', methods=['POST'])
@login_required
def delete_monitor(monitor_id):
    """Delete a monitor"""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Make sure the monitor belongs to the current user
    if monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
        
    # Delete all items associated with this monitor
    Item.query.filter_by(monitor_id=monitor.id).delete()
    
    # Delete the monitor
    db.session.delete(monitor)
    db.session.commit()
    
    flash(f'Monitor "{monitor.name}" deleted successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/monitors/<int:monitor_id>/run', methods=['POST'])
@login_required
def run_monitor_now(monitor_id):
    """Run a monitor immediately"""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Make sure the monitor belongs to the current user
    if monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
        
    # Run the monitor
    run_monitor(monitor.id)
    
    flash(f'Monitor "{monitor.name}" executed successfully', 'success')
    return redirect(url_for('monitor_detail', monitor_id=monitor.id))

@app.route('/items/<int:item_id>')
@login_required
def item_detail(item_id):
    """Show item details"""
    item = Item.query.get_or_404(item_id)
    
    # Make sure the item belongs to the current user
    monitor = Monitor.query.get(item.monitor_id)
    if not monitor or monitor.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
        
    return render_template('item_detail.html', item=item)

@app.route('/notifications')
@login_required
def notifications():
    """Show user notifications"""
    # Get all notifications for the current user
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/api/notifications/unread')
@login_required
def get_unread_notifications():
    """API endpoint to get unread notifications"""
    notifications = NotificationManager.get_unread_notifications(current_user.id)
    return jsonify(notifications)

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """API endpoint to mark a notification as read"""
    notification = Notification.query.get_or_404(notification_id)
    
    # Make sure the notification belongs to the current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
        
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/items/search', methods=['POST'])
@login_required
def search_items():
    """API endpoint to search for items across monitored sources"""
    data = request.get_json()
    
    keywords = data.get('keywords', [])
    if isinstance(keywords, str):
        keywords = [keywords]
        
    filters = {
        'price_min': data.get('price_min'),
        'price_max': data.get('price_max'),
        'location': data.get('location'),
        'condition': data.get('condition'),
        'min_seller_rating': data.get('min_seller_rating')
    }
    
    marketplaces = data.get('marketplaces', ['allegro', 'olx', 'vinted', 'facebook'])
    
    # Initialize scrapers
    proxy_manager = ProxyManager()
    scrapers = {
        'allegro': AllegroScraper(proxy_manager),
        'olx': OLXScraper(proxy_manager),
        'vinted': VintedScraper(proxy_manager),
        'facebook': FacebookMarketplaceScraper(proxy_manager)
    }
    
    results = []
    
    # Search each marketplace
    for marketplace in marketplaces:
        if marketplace.lower() in scrapers:
            try:
                scraper = scrapers[marketplace.lower()]
                items = scraper.search(keywords, filters)
                results.extend(items)
            except Exception as e:
                logger.error(f"Error searching {marketplace}: {str(e)}")
                
    return jsonify(results)

@app.context_processor
def utility_processor():
    """Make utility functions available to templates"""
    def format_datetime(dt):
        if not dt:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M")
        
    def format_price(price, currency="PLN"):
        if not price:
            return "-"
        return f"{price:.2f} {currency}"
        
    return {
        'format_datetime': format_datetime,
        'format_price': format_price
    }
