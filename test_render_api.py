"""
Test script to check if the Render API is working
"""
import requests
import json
import logging
import io
from utils.api_client import API_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_render_api():
    """Test connection to the Render API"""
    # Test if the API is responding
    test_url = f"{API_URL}/upload"
    logger.info(f"Testing API connection to: {test_url}")
    
    try:
        # Use POST method with a minimal payload
        files = {'file': ('test.txt', io.StringIO('This is a test file'), 'text/plain')}
        response = requests.post(test_url, files=files, timeout=10)
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response: {response.text}")
        
        if response.status_code == 200:
            return True, "API is working properly"
        else:
            return False, f"API returned status code {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error: {str(e)}")
        return False, f"Connection error: {str(e)}"

if __name__ == "__main__":
    success, message = test_render_api()
    if success:
        print(f"✅ SUCCESS: {message}")
    else:
        print(f"❌ ERROR: {message}")