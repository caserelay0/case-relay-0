import os
import logging
from typing import Dict, Any, Optional
import json

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DocumentStorage:
    """
    Class to handle storage of documents and case studies
    """
    
    def __init__(self, storage_dir: str = "storage/data"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
    
    def save_document_data(self, document_id: str, document_data: Dict[str, Any]) -> bool:
        """
        Save document data to storage
        
        Args:
            document_id: Unique identifier for the document
            document_data: Document data to save
            
        Returns:
            True if data was saved successfully, False otherwise
        """
        try:
            # Create filename from document_id
            filename = f"{document_id}_document_data.json"
            filepath = os.path.join(self.storage_dir, filename)
            
            # Save data to file
            with open(filepath, 'w') as f:
                json.dump(document_data, f)
                
            logger.debug(f"Document data saved: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving document data: {str(e)}")
            return False
    
    def save_case_study(self, document_id: str, case_study: Dict[str, Any]) -> bool:
        """
        Save case study to storage
        
        Args:
            document_id: Unique identifier for the document
            case_study: Case study data to save
            
        Returns:
            True if data was saved successfully, False otherwise
        """
        try:
            # Create filename from document_id
            filename = f"{document_id}_case_study.json"
            filepath = os.path.join(self.storage_dir, filename)
            
            # Save data to file
            with open(filepath, 'w') as f:
                json.dump(case_study, f)
                
            logger.debug(f"Case study saved: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving case study: {str(e)}")
            return False
    
    def get_document_data(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document data from storage
        
        Args:
            document_id: Unique identifier for the document
            
        Returns:
            Document data or None if an error occurred
        """
        try:
            # Create filename from document_id
            filename = f"{document_id}_document_data.json"
            filepath = os.path.join(self.storage_dir, filename)
            
            # Check if file exists
            if not os.path.exists(filepath):
                logger.warning(f"Document data not found: {filepath}")
                return None
            
            # Load data from file
            with open(filepath, 'r') as f:
                document_data = json.load(f)
                
            logger.debug(f"Document data loaded: {filepath}")
            return document_data
        except Exception as e:
            logger.error(f"Error loading document data: {str(e)}")
            return None
    
    def get_case_study(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get case study from storage
        
        Args:
            document_id: Unique identifier for the document
            
        Returns:
            Case study or None if an error occurred
        """
        try:
            # Create filename from document_id
            filename = f"{document_id}_case_study.json"
            filepath = os.path.join(self.storage_dir, filename)
            
            # Check if file exists
            if not os.path.exists(filepath):
                logger.warning(f"Case study not found: {filepath}")
                return None
            
            # Load data from file
            with open(filepath, 'r') as f:
                case_study = json.load(f)
                
            logger.debug(f"Case study loaded: {filepath}")
            return case_study
        except Exception as e:
            logger.error(f"Error loading case study: {str(e)}")
            return None