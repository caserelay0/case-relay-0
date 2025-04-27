from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
import datetime
import json

# Import db from app.py
from app import db


class Document(db.Model):
    """Document model for storing uploaded document information"""
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf, docx, pptx
    file_size = Column(Integer, nullable=False)
    upload_date = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Extracted data stored as JSON - Using Text column with manual JSON serialization for compatibility
    _extracted_data = Column("extracted_data", Text, nullable=True)
    
    # Relationships
    case_studies = relationship("CaseStudy", back_populates="document", cascade="all, delete-orphan")
    
    @property
    def extracted_data(self):
        """Get the extracted data as a Python dictionary"""
        if self._extracted_data:
            try:
                return json.loads(self._extracted_data)
            except Exception:
                return {}
        return {}
    
    @extracted_data.setter
    def extracted_data(self, value):
        """Set the extracted data, converting from Python dictionary to JSON string"""
        if value is None:
            self._extracted_data = None
        else:
            self._extracted_data = json.dumps(value)
    
    def __repr__(self):
        return f"<Document {self.id}: {self.original_filename}>"


class CaseStudy(db.Model):
    """Case Study model for storing generated case studies"""
    __tablename__ = 'case_studies'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    title = Column(String(255), nullable=False)
    audience = Column(String(50), default='general')
    creation_date = Column(DateTime, default=datetime.datetime.utcnow)
    last_modified = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Case study content sections
    challenge = Column(Text, nullable=True)
    approach = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    outcomes = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    
    # Additional data stored as JSON - Using Text column with manual JSON serialization for compatibility
    _additional_data = Column("additional_data", Text, nullable=True)
    
    # HTML content (for storing edited/modified content)
    html_content = Column(Text, nullable=True)
    
    # Relationship
    document = relationship("Document", back_populates="case_studies")
    
    @property
    def additional_data(self):
        """Get the additional data as a Python dictionary"""
        if self._additional_data:
            try:
                return json.loads(self._additional_data)
            except Exception:
                return {}
        return {}
    
    @additional_data.setter
    def additional_data(self, value):
        """Set the additional data, converting from Python dictionary to JSON string"""
        if value is None:
            self._additional_data = None
        else:
            self._additional_data = json.dumps(value)
    
    def __repr__(self):
        return f"<CaseStudy {self.id}: {self.title}>"


class Image(db.Model):
    """Image model for storing extracted images from documents"""
    __tablename__ = 'images'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    image_id = Column(String(50), nullable=False)  # A unique ID for the image within the document
    caption = Column(String(255), nullable=True)
    image_type = Column(String(10), nullable=False)  # jpeg, png, etc.
    image_data = Column(Text, nullable=False)  # Base64 encoded image data
    selected = Column(Boolean, default=False)  # Whether the image is selected for inclusion in the case study
    
    # Relationship
    document = relationship("Document")
    
    def __repr__(self):
        return f"<Image {self.id}: {self.image_id}>"