from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import JSON
import json

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    monitors = db.relationship('Monitor', backref='user', lazy=True)

class Feature(db.Model):
    """Model for features that can be enabled/disabled"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_enabled = db.Column(db.Boolean, default=False)
    is_premium = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='general')

    @classmethod
    def is_feature_enabled(cls, feature_name):
        """Check if a feature is enabled"""
        feature = cls.query.filter_by(name=feature_name).first()
        return feature and feature.is_enabled

    @classmethod
    def get_by_category(cls, category=None):
        """Get features by category"""
        if category:
            return cls.query.filter_by(category=category).all()
        return cls.query.all()

class Marketplace(db.Model):
    """Model for marketplace configurations"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    base_url = db.Column(db.String(255), nullable=False)
    logo_url = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_enabled = db.Column(db.Boolean, default=True)
    is_premium = db.Column(db.Boolean, default=False)
    country = db.Column(db.String(50), default='PL')
    priority = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def get_available_marketplaces(cls, include_premium=False):
        """Get available marketplaces"""
        query = cls.query.filter_by(is_enabled=True)
        if not include_premium:
            query = query.filter_by(is_premium=False)
        return query.order_by(cls.priority.desc()).all()

class Monitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    marketplaces = db.Column(db.String(255), nullable=False)  # Comma-separated list of marketplaces
    keywords = db.Column(db.String(500), nullable=False)
    price_min = db.Column(db.Float, nullable=True)
    price_max = db.Column(db.Float, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    condition = db.Column(db.String(100), nullable=True)
    min_seller_rating = db.Column(db.Float, nullable=True)
    interval_minutes = db.Column(db.Integer, default=30)  # Default check every 30 minutes
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_run = db.Column(db.DateTime, nullable=True)
    notification_email = db.Column(db.Boolean, default=True)
    notification_browser = db.Column(db.Boolean, default=True)
    notification_telegram = db.Column(db.Boolean, default=False)
    items = db.relationship('Item', backref='monitor', lazy=True)

    def __init__(self, **kwargs):
        super(Monitor, self).__init__(**kwargs)
        if 'notification_telegram' not in kwargs:
            self.notification_telegram = False

class APIConfig(db.Model):
    """Model for API configurations"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(500), nullable=False)
    api_secret = db.Column(db.String(500), nullable=True)
    service_type = db.Column(db.String(50), nullable=False)  # telegram, email, etc.
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_marketplaces_list(self):
        return self.marketplaces.split(',')

    def get_keywords_list(self):
        return [kw.strip() for kw in self.keywords.split(',')]

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey('monitor.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False)
    previous_price = db.Column(db.Float, nullable=True)
    price_changed = db.Column(db.Boolean, default=False)
    currency = db.Column(db.String(10), nullable=False, default='PLN')
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(1024), nullable=False)
    image_url = db.Column(db.String(1024), nullable=True)
    marketplace = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=True)
    seller_name = db.Column(db.String(100), nullable=True)
    seller_rating = db.Column(db.Float, nullable=True)
    condition = db.Column(db.String(50), nullable=True)
    found_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_fetched = db.Column(db.DateTime, nullable=True)
    additional_data = db.Column(JSON, nullable=True)
    is_notified = db.Column(db.Boolean, default=False)

    def set_additional_data(self, data_dict):
        """Convert dictionary to JSON string and store it"""
        self.additional_data = data_dict

    def get_additional_data(self):
        """Get additional data as dictionary"""
        return self.additional_data if self.additional_data else {}

class Notification(db.Model):
    """Model for notifications (browser, email, desktop)"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(20), nullable=False, default='browser')  # browser, email, desktop
    is_read = db.Column(db.Boolean, default=False)
    is_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    search_term = db.Column(db.String(255), nullable=True)
    marketplace = db.Column(db.String(50), nullable=True)
    url = db.Column(db.String(1024), nullable=True)
    item_data = db.Column(JSON, nullable=True)

    @classmethod
    def get_unread(cls, limit=10):
        """Get unread notifications"""
        return cls.query.filter_by(is_read=False).order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def get_unsent_by_type(cls, notification_type):
        """Get unsent notifications of a specific type"""
        return cls.query.filter_by(notification_type=notification_type, is_sent=False).all()

    @classmethod
    def create_from_item(cls, item, notification_type='browser', title=None, message=None):
        """Create a notification from an item"""
        notification = cls(
            title=title or f"New Item: {item.title}",
            message=message or f"Found a new item on {item.marketplace}: {item.title} for {item.price} {item.currency}",
            notification_type=notification_type,
            search_term=None,
            marketplace=item.marketplace,
            url=item.url,
            item_data={
                'id': item.id,
                'title': item.title,
                'price': item.price,
                'currency': item.currency,
                'marketplace': item.marketplace,
                'location': item.location,
                'image_url': item.image_url,
                'url': item.url
            }
        )
        db.session.add(notification)
        db.session.commit()
        return notification

class Proxy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(50), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    protocol = db.Column(db.String(10), default='http')
    is_active = db.Column(db.Boolean, default=True)
    last_used = db.Column(db.DateTime, nullable=True)
    failure_count = db.Column(db.Integer, default=0)
    country = db.Column(db.String(50), default='PL')

    def get_proxy_url(self):
        """Generate proxy URL with authentication if provided"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{self.protocol}://{self.ip}:{self.port}"

class SearchResult(db.Model):
    """Model to store search results history"""
    id = db.Column(db.Integer, primary_key=True)
    search_term = db.Column(db.String(255), nullable=False)
    marketplace = db.Column(db.String(50), nullable=False)
    filters = db.Column(JSON, nullable=True)
    result_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def filters_display(self):
        """Format filters for display"""
        if not self.filters:
            return "No filters"
        display = []
        for key, value in self.filters.items():
            if key in ['price_min', 'price_max'] and value:
                display.append(f"{key.replace('_', ' ').title()}: {value} PLN")
            elif value:
                display.append(f"{key.replace('_', ' ').title()}: {value}")
        return ", ".join(display) if display else "No filters"

class EmailConfig(db.Model):
    """Model for email configuration"""
    id = db.Column(db.Integer, primary_key=True)
    smtp_server = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False, default=587)
    smtp_username = db.Column(db.String(255), nullable=False)
    smtp_password = db.Column(db.String(255), nullable=False)
    from_email = db.Column(db.String(255), nullable=False)
    to_email = db.Column(db.String(255), nullable=False)
    use_tls = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_active_config(cls):
        """Get the active email configuration"""
        return cls.query.filter_by(is_active=True).first()