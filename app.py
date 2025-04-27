import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import json
import uuid
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Import utility functions
from utils.file_utils import allowed_file, save_uploaded_file, cleanup_file

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize SQLAlchemy with a custom base
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# App configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Apply ProxyFix middleware for proper URL generation behind proxies
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Database configuration
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Create a default SQLite database if no database URL is provided
    logger.warning("No DATABASE_URL environment variable found, using SQLite")
    database_url = "sqlite:///app.db"
    
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 600,
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
    "connect_args": {
        "connect_timeout": 120,
        "options": "-c statement_timeout=1200000"  # 20 minutes in milliseconds
    }
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Maximum file size for uploads - increased to handle larger presentations
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB per file
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'pptx', 'txt'}
app.config['MAX_TOTAL_SIZE'] = 200 * 1024 * 1024  # 200MB total across all files
app.config['TIMEOUT'] = 300  # 5 minute timeout for document processing

# Ensure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Import modules after app initialization
from processors.document_processor import process_document
from ai.generator import generate_case_study, improve_text
from storage.document_storage import DocumentStorage
from utils.file_utils import allowed_file, save_uploaded_file, cleanup_file

# Initialize document storage
document_storage = DocumentStorage()

# Import models and ensure database schema is created
with app.app_context():
    import models
    # Drop and recreate all tables
    db.drop_all()
    db.create_all()
    logger.info("Database schema recreated")

# Using allowed_file from utils.file_utils

# Custom middleware to catch connection reset errors
class ConnectionResetMiddleware:
    """Middleware to catch connection reset errors that bypass regular error handlers"""
    
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except Exception as e:
            error_str = str(e).lower()
            if 'connection reset' in error_str or 'broken pipe' in error_str or 'connection closed' in error_str:
                # Log the connection reset error
                logger.error(f"Connection reset caught in middleware: {str(e)}")
                
                # Create a response manually
                start_response('500 Internal Server Error', [('Content-Type', 'text/html')])
                error_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Connection Reset</title>
                    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.0/dist/css/bootstrap.min.css">
                    <style>
                        body { padding-top: 2rem; }
                        .error-container { max-width: 800px; margin: 0 auto; }
                        .error-icon { font-size: 4rem; color: #dee2e6; margin-bottom: 1rem; }
                    </style>
                </head>
                <body>
                    <div class="container error-container text-center">
                        <div class="error-icon">⚠️</div>
                        <h1>Connection Reset</h1>
                        <p class="lead">The connection was reset while processing your request.</p>
                        <div class="alert alert-warning">
                            <p>This typically happens when working with large files or complex documents.</p>
                        </div>
                        <div class="card mt-4">
                            <div class="card-header">Troubleshooting Tips</div>
                            <div class="card-body">
                                <ul class="list-group list-group-flush text-left">
                                    <li class="list-group-item">Try using files under 50MB each for better reliability</li>
                                    <li class="list-group-item">Reduce the total size of all files to under 100MB if possible</li>
                                    <li class="list-group-item">Split very large documents into multiple smaller ones</li>
                                    <li class="list-group-item">Remove unnecessary high-resolution images or complex formatting</li>
                                    <li class="list-group-item">Try a different file format (e.g., convert DOCX to PDF)</li>
                                </ul>
                            </div>
                        </div>
                        <div class="mt-4">
                            <a href="/" class="btn btn-primary">Try Again</a>
                        </div>
                    </div>
                </body>
                </html>
                """
                return [error_html.encode('utf-8')]
            else:
                # Re-raise other exceptions
                raise

# Apply the middleware
app.wsgi_app = ConnectionResetMiddleware(app.wsgi_app)

@app.route('/')
def index():
    """Home page with file upload form"""
    # Reset error status if any
    if 'processing_error' in session:
        del session['processing_error']
    
    return render_template('index.html', 
                         max_file_size=app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
                         max_total_size=app.config['MAX_TOTAL_SIZE'] / (1024 * 1024))

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle multiple document uploads and processing"""
    # Set up more detailed logging for debugging
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    
    # Debug: Log all form keys and request information
    logger.debug(f"Form keys: {list(request.files.keys())}")
    logger.debug(f"Form data: {list(request.form.keys())}")
    logger.debug(f"Request method: {request.method}")
    logger.debug(f"Content type: {request.content_type}")
    
    # Log request files for debugging
    logger.debug(f"All request.files keys: {list(request.files.keys())}")
    for key in request.files.keys():
        logger.debug(f"Files for key '{key}': {[f.filename for f in request.files.getlist(key)]}")
    
    # Check if files were uploaded with any of the expected field names
    possible_keys = ['documents[]', 'documents', 'document', 'file', 'files', 'files[]']
    files = []
    
    # Try each possible key
    for key in possible_keys:
        if key in request.files:
            logger.debug(f"Found files with key: {key}")
            file_list = request.files.getlist(key)
            if file_list and any(f.filename for f in file_list):
                logger.debug(f"Using files from key: {key}")
                files.extend(file_list)
    
    # If no files found, check if there are any files in the request at all
    if not files:
        # Try getting all files from any key
        for key in request.files.keys():
            file_list = request.files.getlist(key)
            if file_list and any(f.filename for f in file_list):
                logger.debug(f"Using files from unexpected key: {key}")
                files.extend(file_list)
    
    # If still no files, return error
    if not files:
        flash('No files provided', 'danger')
        logger.error("No valid files found in request")
        return redirect(url_for('index'))
    
    # Check if at least one file was selected
    if not files or all(file.filename == '' for file in files):
        flash('No files selected', 'danger')
        return redirect(url_for('index'))
    
    # Check number of files
    if len(files) > 10:  # Setting a reasonable upper limit
        flash('Too many files. Please upload 10 or fewer files.', 'danger')
        return redirect(url_for('index'))
    
    # Calculate total size
    total_size = sum(len(file.read()) for file in files)
    # Reset file pointers after reading
    for file in files:
        file.seek(0)
    
    # Check total size against our new lower limit
    if total_size > app.config['MAX_TOTAL_SIZE']:
        max_mb = app.config['MAX_TOTAL_SIZE'] / (1024 * 1024)
        flash(f'Total file size exceeds {int(max_mb)}MB limit. Please reduce file sizes or submit fewer files.', 'danger')
        return redirect(url_for('index'))
    
    # Import models
    from models import Document, CaseStudy, Image
    
    try:
        # Log files information
        files_info = [f"{i+1}: {f.filename}" for i, f in enumerate(files)]
        logger.debug(f"Processing files: {files_info}")
        
        # Process primary document (first file)
        if not files:
            logger.error("Files list is empty after validation")
            flash('No valid files found to process', 'danger')
            return redirect(url_for('index'))
            
        primary_file = files[0]
        logger.debug(f"Primary file: {primary_file.filename}, content type: {primary_file.content_type}")
        
        # Check allowed extensions again
        if not allowed_file(primary_file.filename, app.config['ALLOWED_EXTENSIONS']):
            logger.error(f"Primary file has invalid extension: {primary_file.filename}")
            flash(f'Invalid file type. Allowed types: {", ".join(app.config["ALLOWED_EXTENSIONS"])}', 'danger')
            return redirect(url_for('index'))
            
        primary_filepath = save_uploaded_file(primary_file, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS'])
        
        if not primary_filepath:
            flash(f'Invalid primary file type. Allowed types: {", ".join(app.config["ALLOWED_EXTENSIONS"])}', 'danger')
            return redirect(url_for('index'))
        
        # Get primary file information
        primary_filename = os.path.basename(primary_filepath)
        primary_original_filename = primary_file.filename
        primary_file_size = os.path.getsize(primary_filepath)
        primary_file_type = primary_original_filename.rsplit('.', 1)[1].lower()
        
        # Flag for extra-large files to use special handling
        is_large_file = primary_file_size > 50 * 1024 * 1024  # 50MB
        if is_large_file:
            logger.debug(f"Large file detected ({primary_file_size/1024/1024:.2f}MB). Using optimized processing.")
        
        # Process the primary document
        logger.debug(f"Processing primary document: {primary_filepath}")
        primary_document_data = process_document(primary_filepath)
        
        if not primary_document_data:
            flash('Failed to extract content from primary document', 'danger')
            cleanup_file(primary_filepath)
            return redirect(url_for('index'))
        
        # Optimize for large presentations by limiting text size
        if is_large_file and len(primary_document_data.get('text', '')) > 1000000:  # If text is over 1MB
            logger.debug(f"Truncating large text content from {len(primary_document_data['text'])} characters")
            # Keep the first 200KB and last 100KB of text
            text = primary_document_data['text']
            primary_document_data['text'] = text[:200000] + "\n\n[...content truncated...]\n\n" + text[-100000:]
            logger.debug(f"Text truncated to {len(primary_document_data['text'])} characters")
            
        # Create document record in DB for primary document
        primary_document = Document(
            filename=primary_filename,
            original_filename=primary_original_filename,
            file_type=primary_file_type,
            file_size=primary_file_size,
            extracted_data=primary_document_data
        )
        
        # Use a smaller transaction with immediate commit for large files
        if is_large_file:
            logger.debug("Using optimized database transaction for large file")
            db.session.add(primary_document)
            db.session.commit()  # Commit immediately 
            document_id = primary_document.id
            logger.debug(f"Document record created with ID: {document_id}")
        else:
            db.session.add(primary_document)
            db.session.flush()  # Get the ID for the document
        
        # Save images from primary document to database
        for img_data in primary_document_data.get('images', []):
            image = Image(
                document_id=primary_document.id,
                image_id=img_data['id'],
                caption=img_data['caption'],
                image_type=img_data['type'],
                image_data=img_data['data'],
                selected=False
            )
            db.session.add(image)
        
        # Process additional documents (if any) and merge data
        supplementary_text = ""
        supplementary_images = []
        
        supplementary_file_count = len(files[1:])
        if supplementary_file_count > 0:
            logger.debug(f"Processing {supplementary_file_count} supplementary documents")
        
        for i, file in enumerate(files[1:], 1):
            try:
                if not file or not file.filename:
                    logger.warning(f"Supplementary file {i} is missing or has no filename, skipping")
                    continue
                    
                logger.debug(f"Processing supplementary file {i}: {file.filename}")
                
                # Validate file type
                if not allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
                    logger.warning(f"Skipping supplementary file with invalid extension: {file.filename}")
                    continue
                
                # Save file for processing
                filepath = save_uploaded_file(file, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS'])
                
                if not filepath:
                    logger.warning(f"Failed to save supplementary file {i}: {file.filename}")
                    continue
                
                try:
                    # Process the supplementary document
                    logger.debug(f"Processing supplementary document {i}: {filepath}")
                    supplementary_data = process_document(filepath)
                    
                    if supplementary_data:
                        # Add text with document separator
                        if supplementary_data.get('text'):
                            supplementary_text += f"\n\n--- Document {i+1}: {file.filename} ---\n\n"
                            supplementary_text += supplementary_data['text']
                            logger.debug(f"Added text from supplementary document {i} ({len(supplementary_data['text'])} chars)")
                        
                        # Add images
                        image_count = 0
                        for img_data in supplementary_data.get('images', []):
                            try:
                                # Create a new ID to avoid collision
                                img_data['id'] = f"supp_{i}_{img_data['id']}"
                                supplementary_images.append(img_data)
                                
                                # Save supplementary images to database
                                image = Image(
                                    document_id=primary_document.id,  # Associate with primary document
                                    image_id=img_data['id'],
                                    caption=img_data['caption'],
                                    image_type=img_data['type'],
                                    image_data=img_data['data'],
                                    selected=False
                                )
                                db.session.add(image)
                                image_count += 1
                            except Exception as img_err:
                                logger.error(f"Error adding supplementary image: {str(img_err)}")
                        
                        logger.debug(f"Added {image_count} images from supplementary document {i}")
                    else:
                        logger.warning(f"No data extracted from supplementary document {i}")
                    
                except Exception as e:
                    logger.error(f"Error processing supplementary file {i}: {str(e)}")
                
                # Cleanup supplementary file after processing
                cleanup_file(filepath)
            
            except Exception as file_error:
                logger.error(f"Unexpected error with supplementary file {i}: {str(file_error)}")
                # Continue with other files
        
        # Enrich primary document data with supplementary content
        if supplementary_text:
            primary_document_data['text'] += supplementary_text
            primary_document.extracted_data = primary_document_data
        
        # Generate case study using combined data
        logger.debug("Generating case study from combined documents")
        case_study_data = generate_case_study(primary_document_data)
        
        if not case_study_data:
            flash('Failed to generate case study', 'danger')
            cleanup_file(primary_filepath)
            return redirect(url_for('index'))
        
        # Create case study record in DB
        case_study = CaseStudy(
            document_id=primary_document.id,
            title=case_study_data['title'],
            challenge=case_study_data['challenge'],
            approach=case_study_data['approach'],
            solution=case_study_data['solution'],
            outcomes=case_study_data['outcomes'],
            summary=case_study_data.get('summary', ''),
            additional_data={
                'key_points': case_study_data.get('key_points', []),
                'images': [img['id'] for img in case_study_data.get('images', [])]
            }
        )
        db.session.add(case_study)
        
        # Commit changes to DB
        db.session.commit()
        
        # Store document ID in session for access later
        session['document_id'] = primary_document.id
        session['case_study_id'] = case_study.id
        
        # Cleanup the primary file after processing
        cleanup_file(primary_filepath)
        
        # Redirect to editor page
        return redirect(url_for('editor'))
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        logger.error(f"Error processing documents: {error_msg}")
        
        # Provide more user-friendly error messages based on error type
        if "Permission" in error_msg or "denied" in error_msg:
            user_msg = "File access error: The system couldn't access one of your files. Please try uploading again with different files."
        elif "PDF" in error_msg or "pdf" in error_msg:
            user_msg = "PDF processing error: One of your PDF files couldn't be processed. This could be due to file corruption, password protection, or an unsupported PDF format. Try with a different PDF file."
        elif "Image" in error_msg or "image" in error_msg or "JPEG" in error_msg or "PNG" in error_msg:
            user_msg = "Image processing error: There was a problem extracting or processing images in your documents. Try with files containing smaller or fewer images."
        elif "Memory" in error_msg or "memory" in error_msg:
            user_msg = "Memory limit exceeded: The files you uploaded are too large or complex for processing. Try with smaller files or fewer documents."
        elif "SSL connection has been closed" in error_msg or "connection has been closed" in error_msg:
            user_msg = "Database connection error: Your file might be too large or contain too many images for processing. Try with a smaller file (under 50MB) or a file with fewer embedded images."
        elif "Timeout" in error_msg or "time" in error_msg or "timed out" in error_msg:
            user_msg = "Processing timeout: Your documents took too long to process. Try with smaller or less complex files."
        elif "statement timeout" in error_msg:
            user_msg = "Database timeout: Your file contains too much data to process efficiently. Try with a smaller file or one with fewer slides/pages."
        elif "DOCX" in error_msg or "docx" in error_msg:
            user_msg = "Word document error: One of your DOCX files couldn't be processed. It may be corrupted or in an unsupported format."
        elif "PPTX" in error_msg or "pptx" in error_msg:
            user_msg = "PowerPoint error: One of your presentation files couldn't be processed. It may be corrupted or in an unsupported format."
        else:
            user_msg = f"An error occurred while processing your documents. Please try again with different files. Technical details: {error_msg}"
        
        flash(user_msg, 'danger')
        return redirect(url_for('index'))

@app.route('/editor')
def editor():
    """Display the editor page with the generated case study"""
    # Check if document ID exists in session
    if 'document_id' not in session or 'case_study_id' not in session:
        flash('No case study found. Please upload a document first.', 'danger')
        return redirect(url_for('index'))
    
    document_id = session['document_id']
    case_study_id = session['case_study_id']
    
    # Import models
    from models import Document, CaseStudy, Image
    
    try:
        # Retrieve document and case study from database
        document = Document.query.get(document_id)
        case_study = CaseStudy.query.get(case_study_id)
        images = Image.query.filter_by(document_id=document_id).all()
        
        if not document or not case_study:
            flash('Failed to load case study data. Please try again.', 'danger')
            return redirect(url_for('index'))
        
        # Prepare data for the template
        document_data = {
            'text': document.extracted_data.get('text', ''),
            'images': [
                {
                    'id': img.image_id,
                    'caption': img.caption,
                    'type': img.image_type,
                    'data': img.image_data,
                    'selected': img.selected
                } 
                for img in images
            ]
        }
        
        # Format case study data for the template
        case_study_data = {
            'title': case_study.title,
            'challenge': case_study.challenge,
            'approach': case_study.approach,
            'solution': case_study.solution,
            'outcomes': case_study.outcomes,
            'summary': case_study.summary,
            'key_points': case_study.additional_data.get('key_points', []),
            'images': document_data['images']  # Using the images from the document
        }
        
        return render_template('editor.html',
                              case_study=case_study_data,
                              document_data=document_data)
    
    except Exception as e:
        logger.error(f"Error retrieving case study data: {str(e)}")
        flash(f'Error retrieving case study data: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/api/improve-text', methods=['POST'])
def api_improve_text():
    """API endpoint to improve selected text"""
    data = request.json
    text = data.get('text')
    improvement_type = data.get('type', 'improve')  # improve, simplify, extend
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    try:
        logger.debug(f"Improving text with type: {improvement_type}")
        improved_text = improve_text(text, improvement_type)
        return jsonify({'improved_text': improved_text})
    except Exception as e:
        logger.error(f"Error improving text: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/regenerate', methods=['POST'])
def api_regenerate():
    """API endpoint to regenerate case study with different audience"""
    if 'document_id' not in session or 'case_study_id' not in session:
        return jsonify({'error': 'No document ID or case study ID found'}), 400
    
    document_id = session['document_id']
    case_study_id = session['case_study_id']
    data = request.json
    audience = data.get('audience', 'general')
    
    try:
        # Import models
        from models import Document, CaseStudy, Image
        
        # Get document data from database
        document = Document.query.get(document_id)
        case_study = CaseStudy.query.get(case_study_id)
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
            
        document_data = document.extracted_data
            
        # Generate new case study with specified audience
        logger.debug(f"Regenerating case study with audience: {audience}")
        case_study_data = generate_case_study(document_data, audience=audience)
        
        if not case_study_data:
            return jsonify({'error': 'Failed to generate case study'}), 500
        
        # Create a new case study or update existing one
        if case_study:
            # Update existing case study
            case_study.title = case_study_data['title']
            case_study.audience = audience
            case_study.challenge = case_study_data['challenge']
            case_study.approach = case_study_data['approach']
            case_study.solution = case_study_data['solution']
            case_study.outcomes = case_study_data['outcomes']
            case_study.summary = case_study_data.get('summary', '')
            case_study.additional_data = {
                'key_points': case_study_data.get('key_points', []),
                'images': [img['id'] for img in case_study_data.get('images', [])]
            }
        else:
            # Create a new case study
            case_study = CaseStudy(
                document_id=document_id,
                title=case_study_data['title'],
                audience=audience,
                challenge=case_study_data['challenge'],
                approach=case_study_data['approach'],
                solution=case_study_data['solution'],
                outcomes=case_study_data['outcomes'],
                summary=case_study_data.get('summary', ''),
                additional_data={
                    'key_points': case_study_data.get('key_points', []),
                    'images': [img['id'] for img in case_study_data.get('images', [])]
                }
            )
            db.session.add(case_study)
        
        # Commit changes to DB
        db.session.commit()
        
        # Update session
        session['case_study_id'] = case_study.id
        
        # Prepare images for response
        images = Image.query.filter_by(document_id=document_id).all()
        image_list = [
            {
                'id': img.image_id,
                'caption': img.caption,
                'type': img.image_type,
                'data': img.image_data,
                'selected': img.selected
            } 
            for img in images
        ]
        
        # Add images to the case study data for the response
        case_study_data['images'] = image_list
        
        return jsonify({'case_study': case_study_data})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error regenerating case study: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    flash('File too large. Maximum size is 16MB per file and 64MB total. Please reduce your file size or use document compression tools before uploading.', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(408)
def request_timeout(e):
    """Handle request timeout errors"""
    logger.error(f"Request timeout: {str(e)}")
    return render_template('error.html',
                          error="Request Timeout",
                          details="The server timed out while processing your request. This usually happens with very large or complex documents. Try with smaller files or fewer files at once.",
                          technical_details="The connection timed out while processing your request."), 408

# Define a custom connection reset error handler
class ConnectionResetError(Exception):
    """Custom exception for connection reset errors"""
    pass

@app.errorhandler(ConnectionResetError)
def handle_connection_reset(e):
    """Handle connection reset errors"""
    logger.error(f"Connection reset: {str(e)}")
    return render_template('error.html',
                          error="Connection Reset",
                          details="The connection was interrupted while processing your files. This typically happens with very large files or when the server is under heavy load. Try with smaller files or fewer files.",
                          technical_details=str(e)), 500

@app.errorhandler(500)
def server_error(e):
    """Handle server errors"""
    logger.error(f"Server error: {str(e)}")
    error_msg = str(e)
    
    # Check for connection reset errors
    if "connection reset" in error_msg.lower() or "broken pipe" in error_msg.lower():
        # Handle as a connection reset error
        return handle_connection_reset(ConnectionResetError(error_msg))
    
    # Provide a more user-friendly explanation
    user_friendly_error = "An unexpected server error occurred."
    
    # Provide specific details based on the type of error
    details = "We encountered a problem while processing your request."
    
    if "database" in error_msg.lower() or "sql" in error_msg.lower():
        details = "There was a problem with our database. Your work may not have been saved. Please try again later."
    elif "memory" in error_msg.lower():
        details = "The server ran out of memory while processing your files. Try using smaller files or fewer files at once."
    elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
        details = "The operation took too long to complete. This usually happens with very large or complex documents. Try with smaller files or fewer files."
    elif "openai" in error_msg.lower() or "api key" in error_msg.lower():
        details = "There was an issue connecting to our AI service. This might be temporary - please try again later."
    elif "connection" in error_msg.lower() or "reset" in error_msg.lower():
        details = "The connection was interrupted while processing your files. This typically happens with very large files or when the server is under heavy load."
    elif "pdf" in error_msg.lower():
        details = "We encountered a problem with your PDF file. It might be corrupted, password-protected, or in an unsupported format."
    elif "docx" in error_msg.lower() or "word" in error_msg.lower():
        details = "We encountered a problem with your Word document. It might be corrupted or in an unsupported format."
    elif "pptx" in error_msg.lower() or "powerpoint" in error_msg.lower():
        details = "We encountered a problem with your PowerPoint presentation. It might be corrupted or in an unsupported format."
    elif "image" in error_msg.lower() or "png" in error_msg.lower() or "jpg" in error_msg.lower():
        details = "We had trouble processing images in your document. They might be corrupted or in an unsupported format."
    
    # Include the technical error for debugging
    technical_details = f"{error_msg}" if app.debug else ""
    
    return render_template('error.html', 
                          error=user_friendly_error,
                          details=details,
                          technical_details=technical_details), 500

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return render_template('error.html', 
                          error="Page not found",
                          details="The page you're looking for doesn't exist. Please check the URL or return to the home page.",
                          technical_details=f"Requested URL: {request.path}"), 404

@app.route('/api/save-content', methods=['POST'])
def save_content():
    """API endpoint to save edited content"""
    if 'case_study_id' not in session:
        return jsonify({'error': 'No case study found'}), 400
    
    case_study_id = session['case_study_id']
    data = request.json
    html_content = data.get('content')
    
    if not html_content:
        return jsonify({'error': 'No content provided'}), 400
    
    try:
        # Import models
        from models import CaseStudy
        
        # Get case study from database
        case_study = CaseStudy.query.get(case_study_id)
        
        if not case_study:
            return jsonify({'error': 'Case study not found'}), 404
        
        # Update the HTML content
        case_study.html_content = html_content
        
        # Save to database
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Content saved successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving content: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
