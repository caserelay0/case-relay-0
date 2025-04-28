"""
Comprehensive test for the Render API connection
"""
import os
import sys
import logging
import io
from utils.api_client import upload_document, generate_case_study, APITimeoutError, APIConnectionError, APIError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_api_upload():
    """Test the API upload functionality with a simple test file"""
    logger.info("Testing document upload to API...")
    
    # Create a simple test file in memory
    test_content = "This is a test document for API testing.\n\nIt has multiple paragraphs and some basic content."
    test_file = io.BytesIO(test_content.encode('utf-8'))
    
    try:
        # Use the actual upload_document function from our API client
        result = upload_document(test_file, "test_document.txt", "txt")
        
        if result and 'document_id' in result:
            logger.info(f"✅ Upload successful! Document ID: {result['document_id']}")
            return True, result
        else:
            logger.error(f"❌ Upload failed. Result: {result}")
            return False, result
    
    except (APITimeoutError, APIConnectionError, APIError) as e:
        logger.error(f"❌ API Error: {str(e)}")
        return False, {'error': str(e)}
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        return False, {'error': str(e)}

def test_generate_case_study(document_id):
    """Test case study generation with a given document ID"""
    logger.info(f"Testing case study generation for document ID: {document_id}")
    
    try:
        # Use the actual generate_case_study function from our API client
        result = generate_case_study(document_id)
        
        if result and ('title' in result or 'challenge' in result):
            logger.info("✅ Case study generation successful!")
            return True, result
        else:
            logger.error(f"❌ Case study generation failed. Result: {result}")
            return False, result
    
    except (APITimeoutError, APIConnectionError, APIError) as e:
        logger.error(f"❌ API Error: {str(e)}")
        return False, {'error': str(e)}
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        return False, {'error': str(e)}

def run_full_test():
    """Run a complete test of the API functionality"""
    logger.info("=== Starting Full API Test ===")
    
    # Test document upload
    upload_success, upload_result = test_api_upload()
    
    if not upload_success:
        logger.error("❌ API test failed at upload stage")
        return False
    
    # Extract document ID
    document_id = upload_result.get('document_id')
    if not document_id:
        logger.error("❌ Could not get document ID from upload result")
        return False
    
    # Test case study generation
    generation_success, generation_result = test_generate_case_study(document_id)
    
    if not generation_success:
        logger.error("❌ API test failed at case study generation stage")
        return False
    
    logger.info("✅ Full API test completed successfully!")
    return True

if __name__ == "__main__":
    success = run_full_test()
    sys.exit(0 if success else 1)