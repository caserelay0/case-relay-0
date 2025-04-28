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
    test_url = f"{API_URL}/api/process"  # Updated to use the /api/process endpoint
    logger.info(f"Testing API connection to: {test_url}")
    
    try:
        # Create a test file with minimal content
        test_content = "This is a test document for API testing."
        files = {
            'file': ('test_document.txt', io.StringIO(test_content), 'text/plain'),
        }
        
        # Include metadata as required by the API
        data = {
            'document_type': 'txt',
            'process_images': 'true',
        }
        
        # Make the request with appropriate headers
        headers = {}
        response = requests.post(
            test_url,
            files=files,
            data=data,
            headers=headers,
            timeout=10,
        )
        
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response: {response.text[:200]}...")  # Show first 200 chars
        
        # Check if we got a successful response
        if response.status_code in (200, 201, 202):
            try:
                result = response.json()
                if 'document_id' in result:
                    return True, f"API is working properly. Document ID: {result['document_id']}"
                else:
                    return False, "API returned success status but no document_id in response"
            except ValueError:
                # If response isn't JSON, check if it's HTML containing success message
                if 'success' in response.text.lower() and 'document' in response.text.lower():
                    return True, "API appears to be working (HTML response)"
                else:
                    return False, "API returned non-JSON response"
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