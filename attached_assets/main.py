from app import app
import routes  # This line is necessary to register all the routes
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
