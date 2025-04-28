# AI Document Case Study Generator

A Flask-powered AI case study generation platform that enables robust document processing and professional report generation with enhanced error handling and file upload capabilities.

## Features

- **Document Processing**: Process PDF, DOCX, and PPTX documents to extract text and images
- **AI Case Study Generation**: Use OpenAI to generate professional case studies from the extracted content
- **Interactive Editor**: Edit generated case studies with a rich text editor
- **Fallback Mechanism**: Local processing when the Render API is unavailable
- **Database Integration**: PostgreSQL database for storing documents, case studies, and images
- **Error Handling**: Comprehensive error handling for document processing

## Architecture

The application follows a hybrid processing model:
1. Documents are initially uploaded to the Replit server for validation
2. Documents are typically sent to the Render API for intensive processing
3. If the Render API is unavailable, documents are processed locally
4. AI-generated case studies are presented to the user in an interactive editor

## Setup

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   - `DATABASE_URL`: PostgreSQL database URL
   - `OPENAI_API_KEY`: OpenAI API key for AI generation

3. Run the application:
   ```
   gunicorn --bind 0.0.0.0:5000 main:app
   ```

## Development

The project structure follows a modular approach:
- `app.py`: Main Flask application with routes and error handlers
- `models.py`: Database models for documents, case studies, and images
- `processors/`: Document processing modules
- `ai/`: AI generation modules
- `utils/`: Utility functions
- `templates/`: HTML templates
- `static/`: Static files (CSS, JS, etc.)

## License

[MIT License](LICENSE)