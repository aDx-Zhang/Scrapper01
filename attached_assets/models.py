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
    items = db.relationship('Item', backref='monitor', lazy=True)

    def get_marketplaces_list(self):
        return self.marketplaces.split(',')

    def get_keywords_list(self):
        return [kw.strip() for kw in self.keywords.split(',')]

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey('monitor.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False)
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
    additional_data = db.Column(JSON, nullable=True)
    is_notified = db.Column(db.Boolean, default=False)
    
    def set_additional_data(self, data_dict):
        """Convert dictionary to JSON string and store it"""
        self.additional_data = data_dict
        
    def get_additional_data(self):
        """Get additional data as dictionary"""
        return self.additional_data if self.additional_data else {}

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_type = db.Column(db.String(20), default='browser')  # browser, email, etc.
    
    item = db.relationship('Item', backref='notifications')
    user = db.relationship('User', backref='notifications')

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
