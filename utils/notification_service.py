import logging
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

try:
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content
    from flask import current_app
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False

try:
    from app import db
    from models import Notification, EmailConfig
except ImportError:
    # For standalone testing
    db = None
    Notification = None
    EmailConfig = None

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for managing and sending notifications (browser, email, desktop)"""
    
    @classmethod
    def create_notification(cls, title: str, message: str, notification_type: str = 'browser',
                           search_term: Optional[str] = None, marketplace: Optional[str] = None,
                           url: Optional[str] = None, item_data: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """
        Create a new notification
        
        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification (browser, email, desktop)
            search_term: Search term that generated this notification
            marketplace: Marketplace where the item was found
            url: URL to the item
            item_data: Additional item data as JSON
            
        Returns:
            Notification object or None if database not available
        """
        if db is not None and Notification is not None:
            try:
                notification = Notification(
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    search_term=search_term,
                    marketplace=marketplace,
                    url=url,
                    item_data=item_data,
                    is_read=False,
                    is_sent=False,
                    created_at=datetime.utcnow()
                )
                db.session.add(notification)
                db.session.commit()
                
                # If it's an email notification, attempt to send it immediately
                if notification_type == 'email':
                    cls.send_email_notification(notification)
                
                return notification
            except Exception as e:
                logger.error(f"Error creating notification: {e}")
        
        return None
    
    @classmethod
    def mark_notification_read(cls, notification_id: int) -> bool:
        """
        Mark a notification as read
        
        Args:
            notification_id: ID of the notification to mark as read
            
        Returns:
            Success flag
        """
        if db is not None and Notification is not None:
            try:
                notification = Notification.query.get(notification_id)
                if notification:
                    notification.is_read = True
                    db.session.commit()
                    return True
            except Exception as e:
                logger.error(f"Error marking notification as read: {e}")
        
        return False
    
    @classmethod
    def send_email_notification(cls, notification: Any) -> bool:
        """
        Send an email notification
        
        Args:
            notification: Notification object to send
            
        Returns:
            Success flag
        """
        if not SENDGRID_AVAILABLE:
            logger.warning("SendGrid library not available, cannot send email notifications")
            return False
            
        # Get SendGrid API key from environment
        api_key = os.environ.get('SENDGRID_API_KEY')
        if not api_key:
            logger.warning("SendGrid API key not set, cannot send email notifications")
            return False
            
        try:
            # Get email configuration
            if EmailConfig is not None:
                email_config = EmailConfig.get_active_config()
                if email_config:
                    from_email = email_config.from_email
                    to_email = email_config.to_email
                else:
                    # Use default values
                    from_email = "noreply@marketplacescraper.pl"
                    to_email = "user@example.com"
            else:
                # Use default values
                from_email = "noreply@marketplacescraper.pl"
                to_email = "user@example.com"
                
            # Create message
            message = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=notification.title,
                html_content=cls._format_email_html(notification)
            )
            
            # Send message
            sg = sendgrid.SendGridAPIClient(api_key)
            response = sg.send(message)
            
            if response.status_code >= 200 and response.status_code < 300:
                # Mark notification as sent
                notification.is_sent = True
                if db is not None:
                    db.session.commit()
                return True
            else:
                logger.error(f"Error sending email notification: {response.status_code} {response.body}")
                return False
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    @classmethod
    def _format_email_html(cls, notification: Any) -> str:
        """
        Format notification as HTML for email
        
        Args:
            notification: Notification object
            
        Returns:
            HTML string
        """
        # Simple HTML template for email notifications
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4a6da7; color: white; padding: 10px 20px; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 20px; }}
                .btn {{ display: inline-block; padding: 10px 20px; background-color: #4a6da7; color: white; 
                       text-decoration: none; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{notification.title}</h2>
                </div>
                <div class="content">
                    <p>{notification.message}</p>
        """
        
        # Add item details if available
        if notification.item_data:
            item = notification.item_data
            html += f"""
                    <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 4px;">
                        <h3>{item.get('title', 'Item Details')}</h3>
                        <p><strong>Price:</strong> {item.get('price', 'N/A')} {item.get('currency', 'PLN')}</p>
                        <p><strong>Marketplace:</strong> {item.get('marketplace', notification.marketplace)}</p>
                        <p><strong>Location:</strong> {item.get('location', 'N/A')}</p>
                        <p><strong>Seller:</strong> {item.get('seller_name', 'N/A')}</p>
            """
            
            if item.get('image_url'):
                html += f"""
                        <p><img src="{item['image_url']}" alt="{item.get('title', 'Item Image')}" style="max-width: 100%; height: auto;"></p>
                """
                
            html += """
                    </div>
            """
            
        # Add link to the item if available
        if notification.url:
            html += f"""
                    <p><a href="{notification.url}" class="btn">View Item</a></p>
            """
            
        # Close the HTML
        html += f"""
                </div>
                <div class="footer">
                    <p>This notification was sent from Polish Marketplace Scraper at {notification.created_at.strftime('%Y-%m-%d %H:%M')}</p>
                    <p>If you don't want to receive these emails, you can change your notification settings.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    @classmethod
    def process_unsent_notifications(cls) -> Dict[str, int]:
        """
        Process all unsent notifications
        
        Returns:
            Dictionary with counts of processed notifications by type
        """
        if db is None or Notification is None:
            return {'error': 'Database not available'}
            
        results = {
            'email': 0,
            'browser': 0,
            'desktop': 0,
            'error': 0
        }
        
        try:
            # Process email notifications
            email_notifications = Notification.get_unsent_by_type('email')
            for notification in email_notifications:
                if cls.send_email_notification(notification):
                    results['email'] += 1
                else:
                    results['error'] += 1
                    
            # Browser and desktop notifications are sent on-demand, not in background processing
            
            return results
        except Exception as e:
            logger.error(f"Error processing unsent notifications: {e}")
            return {'error': str(e)}