import logging
from app import app
import routes  # This imports all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Polish Marketplace Scraper initialized")
    app.run(host="0.0.0.0", port=5000, debug=True)