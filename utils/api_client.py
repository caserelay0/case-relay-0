import io
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List, BinaryIO, Union

import httpx

# Import configuration
try:
    import config
    API_URL = config.RENDER_API_URL
    API_KEY = config.RENDER_API_KEY
    TIMEOUT_SHORT = config.API_TIMEOUT_SHORT
    TIMEOUT_MEDIUM = config.API_TIMEOUT_MEDIUM
    TIMEOUT_LONG = config.API_TIMEOUT_LONG
except (ImportError, AttributeError):
    # Fallback if config module is not available
    API_URL = os.environ.get("RENDER_API_URL", "https://your-render-api.onrender.com")
    API_KEY = os.environ.get("RENDER_API_KEY")
    TIMEOUT_SHORT = 30    # 30 seconds for simple operations
    TIMEOUT_MEDIUM = 120  # 2 minutes for uploads
    TIMEOUT_LONG = 300    # 5 minutes for processing

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base error for API-related issues"""
    pass


class APITimeoutError(APIError):
    """Raised when an API request times out"""
    pass


class APIConnectionError(APIError):
    """Raised when there's a network connection error"""
    pass


class ProcessingError(APIError):
    """Raised when document processing fails on the server"""
    pass


def upload_document(file_data: BinaryIO, filename: str, file_type: str = None) -> Dict[str, Any]:
    """
    Uploads a document to the Render API for processing
    
    Args:
        file_data: File-like object containing the document data
        filename: Name of the file
        file_type: Optional file type override (pdf, docx, pptx)
        
    Returns:
        Dictionary with the document_id and status
    """
    if not file_type and '.' in filename:
        file_type = filename.split('.')[-1].lower()
    
    logger.info(f"Uploading document to API: {filename} (type: {file_type})")
    
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    try:
        # Create a more detailed multipart form with the file and metadata
        mime_type = 'application/octet-stream'  # Default safer MIME type
        
        # Set correct MIME type based on file_type
        if file_type == 'pdf':
            mime_type = 'application/pdf'
        elif file_type == 'docx':
            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif file_type == 'pptx':
            mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        elif file_type == 'txt':
            mime_type = 'text/plain'
            
        files = {
            'file': (filename, file_data, mime_type),
        }
        
        data = {
            'document_type': file_type,
            'process_images': 'true',  # Explicitly request image processing
        }
        
        # Make the request with a reasonable timeout and more robust settings
        with httpx.Client(timeout=TIMEOUT_MEDIUM) as client:
            # Use follow_redirects but without max_redirects which isn't supported in our version
            response = client.post(
                f"{API_URL}/api/process",
                files=files,
                data=data,
                headers=headers,
                follow_redirects=True
            )
            
        if response.status_code == 413:
            raise APIError("File too large. The maximum file size is 50MB.")
        
        if response.status_code not in (200, 201, 202):
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', error_detail)
            except:
                error_detail = response.text[:100]
                
            raise APIError(f"Error uploading document: HTTP {response.status_code} - {error_detail}")
            
        result = response.json()
        document_id = result.get('document_id')
        
        if not document_id:
            raise APIError("Invalid response from server: missing document_id")
            
        logger.info(f"Document uploaded successfully with ID: {document_id}")
        return result
        
    except httpx.TimeoutException:
        logger.error(f"Timeout while uploading document: {filename}")
        raise APITimeoutError("Request timed out while uploading document. The server might be busy.")
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error while uploading document: {str(e)}")
        raise APIConnectionError(f"Connection error while uploading document: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error while uploading document: {str(e)}")
        raise APIError(f"Error uploading document: {str(e)}")


def generate_case_study(document_id: str, audience: str = "general") -> Dict[str, Any]:
    """
    Requests case study generation for a previously uploaded document
    
    Args:
        document_id: The ID of the previously uploaded document
        audience: Target audience for the case study
        
    Returns:
        Dictionary containing the case study data
    """
    logger.info(f"Requesting case study generation for document {document_id}")
    
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    data = {
        "document_id": document_id,
        "audience": audience
    }
    
    try:
        # Make request with longer timeout since generation takes time
        with httpx.Client(timeout=TIMEOUT_LONG) as client:
            response = client.post(
                f"{API_URL}/case-studies",
                json=data,
                headers=headers
            )
            
        if response.status_code not in (200, 201, 202):
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', error_detail)
            except:
                error_detail = response.text[:100]
                
            raise APIError(f"Error generating case study: HTTP {response.status_code} - {error_detail}")
            
        result = response.json()
        
        if 'case_study_id' not in result:
            raise APIError("Invalid response from server: missing case_study_id")
            
        logger.info(f"Case study generation requested with ID: {result.get('case_study_id')}")
        
        # If the result contains the complete case study (not async), return it
        if 'case_study' in result:
            return result['case_study']
            
        # Otherwise, we need to poll for results
        case_study_id = result.get('case_study_id')
        status = result.get('status', 'processing')
        
        # Poll for results with timeout
        start_time = time.time()
        max_wait_time = 300  # 5 minutes max wait
        poll_interval = 5  # Poll every 5 seconds
        
        # Keep polling until we get a result or timeout
        while status == 'processing' and time.time() - start_time < max_wait_time:
            time.sleep(poll_interval)
            
            # Check status
            status_response = client.get(
                f"{API_URL}/case-studies/{case_study_id}",
                headers=headers
            )
            
            if status_response.status_code != 200:
                error_detail = "Unknown error"
                try:
                    error_data = status_response.json()
                    error_detail = error_data.get('error', error_detail)
                except:
                    error_detail = status_response.text[:100]
                    
                raise APIError(f"Error checking case study status: HTTP {status_response.status_code} - {error_detail}")
                
            status_result = status_response.json()
            status = status_result.get('status', 'processing')
            
            if status == 'completed' and 'case_study' in status_result:
                logger.info(f"Case study generation completed for document {document_id}")
                return status_result['case_study']
                
            if status == 'failed':
                error_message = status_result.get('error', 'Unknown error during processing')
                raise ProcessingError(f"Case study generation failed: {error_message}")
                
            logger.debug(f"Still waiting for case study generation... Status: {status}")
            
        if status != 'completed':
            raise APITimeoutError("Timed out waiting for case study generation")
                
        return result
        
    except httpx.TimeoutException:
        logger.error(f"Timeout while generating case study for document {document_id}")
        raise APITimeoutError("Request timed out while generating case study. The server might be busy.")
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during case study generation: {str(e)}")
        raise APIConnectionError(f"Connection error during case study generation: {str(e)}")
        
    except Exception as e:
        if isinstance(e, APIError):
            raise
        logger.error(f"Unexpected error during case study generation: {str(e)}")
        raise APIError(f"Error generating case study: {str(e)}")


def improve_text(text: str, improvement_type: str = "improve") -> str:
    """
    Use the API to improve a text segment using OpenAI
    
    Args:
        text: The text to improve
        improvement_type: Type of improvement (improve, simplify, extend)
        
    Returns:
        Improved text string
    """
    logger.info(f"Requesting text improvement ({improvement_type})")
    
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    data = {
        "text": text,
        "improvement_type": improvement_type
    }
    
    try:
        with httpx.Client(timeout=TIMEOUT_SHORT) as client:
            response = client.post(
                f"{API_URL}/text/improve",
                json=data,
                headers=headers
            )
            
        if response.status_code != 200:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', error_detail)
            except:
                error_detail = response.text[:100]
                
            raise APIError(f"Error improving text: HTTP {response.status_code} - {error_detail}")
            
        result = response.json()
        
        if 'improved_text' not in result:
            raise APIError("Invalid response from server: missing improved_text")
            
        return result['improved_text']
        
    except httpx.TimeoutException:
        logger.error("Timeout while improving text")
        raise APITimeoutError("Request timed out while improving text")
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during text improvement: {str(e)}")
        raise APIConnectionError(f"Connection error during text improvement: {str(e)}")
        
    except Exception as e:
        if isinstance(e, APIError):
            raise
        logger.error(f"Unexpected error during text improvement: {str(e)}")
        raise APIError(f"Error improving text: {str(e)}")


def regenerate_case_study(case_study_id: str, audience: str) -> Dict[str, Any]:
    """
    Request regeneration of an existing case study with a different audience
    
    Args:
        case_study_id: ID of the existing case study
        audience: New target audience
        
    Returns:
        Dictionary containing the regenerated case study
    """
    logger.info(f"Requesting case study regeneration for {case_study_id}, audience: {audience}")
    
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    data = {
        "audience": audience
    }
    
    try:
        with httpx.Client(timeout=TIMEOUT_LONG) as client:
            response = client.post(
                f"{API_URL}/case-studies/{case_study_id}/regenerate",
                json=data,
                headers=headers
            )
            
        if response.status_code != 200:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', error_detail)
            except:
                error_detail = response.text[:100]
                
            raise APIError(f"Error regenerating case study: HTTP {response.status_code} - {error_detail}")
            
        result = response.json()
        
        if 'case_study' not in result:
            raise APIError("Invalid response from server: missing case_study data")
            
        return result['case_study']
        
    except httpx.TimeoutException:
        logger.error(f"Timeout while regenerating case study {case_study_id}")
        raise APITimeoutError("Request timed out while regenerating case study")
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during case study regeneration: {str(e)}")
        raise APIConnectionError(f"Connection error during case study regeneration: {str(e)}")
        
    except Exception as e:
        if isinstance(e, APIError):
            raise
        logger.error(f"Unexpected error during case study regeneration: {str(e)}")
        raise APIError(f"Error regenerating case study: {str(e)}")


def save_case_study(case_study_id: str, content: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save edited content for a case study
    
    Args:
        case_study_id: ID of the case study to update
        content: Dictionary with the updated content
        
    Returns:
        Dictionary with the success status
    """
    logger.info(f"Saving updated content for case study {case_study_id}")
    
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    try:
        with httpx.Client(timeout=TIMEOUT_SHORT) as client:
            response = client.put(
                f"{API_URL}/case-studies/{case_study_id}",
                json=content,
                headers=headers
            )
            
        if response.status_code != 200:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('error', error_detail)
            except:
                error_detail = response.text[:100]
                
            raise APIError(f"Error saving case study: HTTP {response.status_code} - {error_detail}")
            
        return response.json()
        
    except httpx.TimeoutException:
        logger.error(f"Timeout while saving case study {case_study_id}")
        raise APITimeoutError("Request timed out while saving case study")
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error while saving case study: {str(e)}")
        raise APIConnectionError(f"Connection error while saving case study: {str(e)}")
        
    except Exception as e:
        if isinstance(e, APIError):
            raise
        logger.error(f"Unexpected error while saving case study: {str(e)}")
        raise APIError(f"Error saving case study: {str(e)}")