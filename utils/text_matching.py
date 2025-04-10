import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def clean_text(text):
    """
    Clean text for comparison by removing special characters and extra spaces
    """
    if not text:
        return ""
    # Remove special characters and convert to lowercase
    text = re.sub(r'[^\w\s]', '', text.lower())
    # Remove extra whitespace and trim
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def simple_match(text, keywords):
    """
    Check if all keywords are in the text (case insensitive)
    
    Args:
        text: Text to search in
        keywords: List of keywords to search for
        
    Returns:
        bool: True if all keywords are found, False otherwise
    """
    if not text or not keywords:
        return False
        
    text_lower = text.lower()
    return all(keyword.lower() in text_lower for keyword in keywords)

def fuzzy_match_keywords(text, keywords, threshold=0.8):
    """
    Check if any keyword has a fuzzy match in the text
    
    Args:
        text: Text to search in
        keywords: List of keywords to search for
        threshold: Similarity threshold (0.0-1.0) for a match
        
    Returns:
        bool: True if any keyword matches above threshold, False otherwise
    """
    if not text or not keywords:
        return False
        
    text_clean = clean_text(text)
    
    for keyword in keywords:
        keyword_clean = clean_text(keyword)
        
        # Skip empty keywords
        if not keyword_clean:
            continue
            
        # First check for exact match
        if keyword_clean in text_clean:
            return True
            
        # Check if keyword is multiple words
        if ' ' in keyword_clean:
            # For multi-word keywords, we'll check them as a phrase
            similarity = SequenceMatcher(None, text_clean, keyword_clean).ratio()
            if similarity >= threshold:
                logger.debug(f"Fuzzy phrase match for '{keyword}' in '{text}': {similarity}")
                return True
        else:
            # For single words, check each word in the text
            for word in text_clean.split():
                similarity = SequenceMatcher(None, word, keyword_clean).ratio()
                if similarity >= threshold:
                    logger.debug(f"Fuzzy word match for '{keyword}' in '{word}': {similarity}")
                    return True
    
    return False

def extract_price(text):
    """
    Extract price from text
    
    Args:
        text: Text containing a price
        
    Returns:
        tuple: (price_value, currency) or (None, None) if not found
    """
    if not text:
        return None, None
        
    # Match common price patterns with currency
    # This handles formats like "100 zł", "100,50 zł", "100.50 zł", "100 PLN", "€100", "100€", etc.
    price_pattern = r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)\s*([zł€$£]|PLN|EUR|USD|GBP)'
    
    match = re.search(price_pattern, text)
    if match:
        price_str = match.group(1).replace(" ", "").replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            return None, None
            
        # Determine currency
        currency_str = match.group(2).strip()
        currency = 'PLN'  # Default
        
        if currency_str in ['€', 'EUR']:
            currency = 'EUR'
        elif currency_str in ['$', 'USD']:
            currency = 'USD'
        elif currency_str in ['£', 'GBP']:
            currency = 'GBP'
            
        return price, currency
        
    # If no match with currency, try to match just a number
    number_pattern = r'(\d+[\s\d]*[,.]\d+|\d+[\s\d]*)'
    match = re.search(number_pattern, text)
    if match:
        price_str = match.group(1).replace(" ", "").replace(",", ".")
        try:
            price = float(price_str)
            return price, 'PLN'  # Default to PLN
        except ValueError:
            return None, None
    
    return None, None