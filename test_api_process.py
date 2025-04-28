#!/usr/bin/env python
"""
Test script for the /api/process endpoint
"""
import os
import sys
import requests
import json

def test_api_process(file_path, api_url='http://0.0.0.0:5000/api/process'):
    """
    Test the /api/process endpoint by uploading a document
    
    Args:
        file_path: Path to the document to upload
        api_url: URL of the API endpoint
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        sys.exit(1)
    
    # Get file extension
    file_extension = file_path.split('.')[-1].lower()
    
    # Check if the file type is supported
    if file_extension not in ['pdf', 'doc', 'docx', 'pptx', 'txt']:
        print(f"Error: Unsupported file type: {file_extension}")
        print("Supported types: pdf, doc, docx, pptx, txt")
        sys.exit(1)
    
    print(f"Testing /api/process endpoint with file: {file_path}")
    
    # Create a multipart form request
    with open(file_path, 'rb') as file:
        files = {'document': file}
        data = {'audience': 'general'}
        
        try:
            print("Sending request...")
            response = requests.post(api_url, files=files, data=data)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print("Success! Document processed successfully.")
                print(f"Document ID: {result.get('document_id')}")
                
                # Print a preview of the text content
                if 'text_preview' in result:
                    print("\nText Preview:")
                    print(result['text_preview'])
                
                # Print the case study sections
                if 'case_study' in result:
                    print("\nCase Study:")
                    case_study = result['case_study']
                    print(f"Title: {case_study.get('title')}")
                    print(f"Challenge: {case_study.get('challenge')[:100]}...")
                    print(f"Approach: {case_study.get('approach')[:100]}...")
                    print(f"Solution: {case_study.get('solution')[:100]}...")
                    print(f"Outcomes: {case_study.get('outcomes')[:100]}...")
            else:
                print("Error processing document")
                print(response.text)
        except Exception as e:
            print(f"Error making API request: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_api_process.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    test_api_process(file_path)