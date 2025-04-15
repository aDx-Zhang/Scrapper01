from app import db
from models import Item, Monitor, User, Feature, Marketplace, APIConfig, EmailConfig, Notification, Proxy, SearchResult
import os

def recreate_database():
    # Drop and recreate all tables
    db_path = "instance/database.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create all tables
    db.create_all()

    print("Database recreated successfully")

if __name__ == '__main__':
    recreate_database()