import os

# Application settings
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')

# Database settings
DATABASE_URL = os.environ.get('DATABASE_URL')

# File upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'pptx', 'txt'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB per file
MAX_TOTAL_SIZE = 200 * 1024 * 1024  # 200MB total across all files

# Processing timeout
PROCESSING_TIMEOUT = 300  # 5 minute timeout for document processing

# Remote API configuration
# URL of the Render API for document processing and case study generation
RENDER_API_URL = os.environ.get('RENDER_API_URL', 'https://case-relay-mvp.onrender.com')

# API key for authentication with the Render API (if required)
RENDER_API_KEY = os.environ.get('RENDER_API_KEY')

# API request timeouts (in seconds)
API_TIMEOUT_SHORT = 30    # For simple API calls (improve text, status checks)
API_TIMEOUT_MEDIUM = 120  # For document uploads and initial processing
API_TIMEOUT_LONG = 300    # For case study generation and regeneration

# OpenAI settings (for local fallback if needed)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')  # Use the latest model