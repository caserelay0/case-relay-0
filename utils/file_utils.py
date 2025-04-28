
import os
import logging
from werkzeug.utils import secure_filename
from typing import List, Optional

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def allowed_file(filename: str, allowed_extensions: List[str]) -> bool:
    """
    Check if the file extension is allowed
    
    Args:
        filename: Name of the file
        allowed_extensions: List of allowed file extensions
        
    Returns:
        True if file extension is allowed, False otherwise
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder: str, allowed_extensions: List[str]) -> Optional[str]:
    """
    Save an uploaded file to the specified folder with optimization
    
    Args:
        file: The uploaded file object
        upload_folder: Path to the folder where the file will be saved
        allowed_extensions: List of allowed file extensions
        
    Returns:
        The path to the saved file or None if an error occurred
    """
    if file and allowed_file(file.filename, allowed_extensions):
        try:
            # Ensure the upload folder exists
            os.makedirs(upload_folder, exist_ok=True)
            
            # Secure the filename
            original_filename = secure_filename(file.filename)
            filename = f"{os.urandom(8).hex()}_{original_filename}"
            
            # Generate the file path
            filepath = os.path.join(upload_folder, filename)
            
            # Save the file with chunk processing for large files
            chunk_size = 8192  # 8KB chunks
            with open(filepath, 'wb') as f:
                while True:
                    chunk = file.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
            
            logger.debug(f"File saved: {filepath}")
            
            # Implement basic file validation
            if os.path.getsize(filepath) < 10:  # Minimum reasonable size
                cleanup_file(filepath)
                logger.error(f"File too small: {filepath}")
                return None
                
            return filepath
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return None
    else:
        logger.warning(f"Invalid file: {file.filename if file else 'None'}")
        return None

def cleanup_file(filepath: str) -> bool:
    """
    Delete a file from the filesystem
    
    Args:
        filepath: Path to the file to delete
        
    Returns:
        True if the file was deleted successfully, False otherwise
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.debug(f"File deleted: {filepath}")
            return True
        else:
            logger.warning(f"File not found: {filepath}")
            return False
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return False
