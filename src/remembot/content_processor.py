"""
Content processor for RememBot.
Handles URL fetching, image processing, and document parsing.
"""

import asyncio
import logging
import tempfile
import os
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import aiohttp
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from docx import Document
import pypdf
from pypdf import PdfReader
import openpyxl

logger = logging.getLogger(__name__)


class ContentProcessor:
    """Processes different types of content for storage."""
    
    def __init__(self):
        """Initialize content processor."""
        self.session = None
    
    async def _get_session(self):
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def process_text(self, text: str) -> Dict[str, Any]:
        """Process text content, detecting URLs and extracting content."""
        # Check if text contains URLs
        words = text.split()
        urls = [word for word in words if self._is_url(word)]
        
        if urls:
            # Process as URL
            return await self._process_url(urls[0], text)
        else:
            # Process as plain text
            return {
                'content_type': 'text',
                'extracted_info': text,
                'metadata': {
                    'word_count': len(words),
                    'character_count': len(text),
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
            }
    
    def _is_url(self, text: str) -> bool:
        """Check if text is a URL."""
        try:
            result = urlparse(text)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    async def _process_url(self, url: str, original_text: str) -> Dict[str, Any]:
        """Extract content from URL."""
        try:
            session = await self._get_session()
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract title
                    title = soup.find('title')
                    title_text = title.get_text().strip() if title else "No title"
                    
                    # Extract main content (simple approach)
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text()
                    
                    # Clean up text
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    clean_text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    # Limit text length
                    if len(clean_text) > 5000:
                        clean_text = clean_text[:5000] + "..."
                    
                    return {
                        'content_type': 'url',
                        'extracted_info': f"Title: {title_text}\n\nContent: {clean_text}",
                        'metadata': {
                            'url': url,
                            'title': title_text,
                            'status_code': response.status,
                            'content_length': len(clean_text),
                            'processed_at': datetime.now(timezone.utc).isoformat()
                        }
                    }
                else:
                    logger.warning(f"Failed to fetch URL {url}: HTTP {response.status}")
                    return {
                        'content_type': 'url',
                        'extracted_info': f"Failed to fetch URL: {url} (HTTP {response.status})",
                        'metadata': {
                            'url': url,
                            'status_code': response.status,
                            'error': f"HTTP {response.status}",
                            'processed_at': datetime.now(timezone.utc).isoformat()
                        }
                    }
        
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            return {
                'content_type': 'url',
                'extracted_info': f"Error processing URL: {url} - {str(e)}",
                'metadata': {
                    'url': url,
                    'error': str(e),
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
            }
    
    async def process_image(self, file) -> Dict[str, Any]:
        """Process image file with OCR."""
        try:
            # Download file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                await file.download_to_drive(tmp_file.name)
                
                # Open image with PIL
                image = Image.open(tmp_file.name)
                
                # Perform OCR
                ocr_text = pytesseract.image_to_string(image)
                
                # Get image metadata
                width, height = image.size
                format_info = image.format
                
                # Clean up temporary file
                os.unlink(tmp_file.name)
                
                return {
                    'content_type': 'image',
                    'extracted_info': f"OCR Text: {ocr_text.strip()}",
                    'metadata': {
                        'width': width,
                        'height': height,
                        'format': format_info,
                        'file_size': file.file_size,
                        'has_text': bool(ocr_text.strip()),
                        'processed_at': datetime.now(timezone.utc).isoformat()
                    }
                }
        
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return {
                'content_type': 'image',
                'extracted_info': f"Error processing image: {str(e)}",
                'metadata': {
                    'error': str(e),
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
            }
    
    async def process_document(self, file, filename: str) -> Dict[str, Any]:
        """Process document file (PDF, Word, Excel)."""
        try:
            file_ext = Path(filename).suffix.lower()
            
            # Download file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                await file.download_to_drive(tmp_file.name)
                
                if file_ext == '.pdf':
                    content = self._extract_pdf_text(tmp_file.name)
                elif file_ext in ['.docx', '.doc']:
                    content = self._extract_word_text(tmp_file.name)
                elif file_ext in ['.xlsx', '.xls']:
                    content = self._extract_excel_text(tmp_file.name)
                else:
                    content = f"Unsupported file type: {file_ext}"
                
                # Clean up temporary file
                os.unlink(tmp_file.name)
                
                return {
                    'content_type': 'document',
                    'extracted_info': content,
                    'metadata': {
                        'filename': filename,
                        'file_extension': file_ext,
                        'file_size': file.file_size,
                        'content_length': len(content),
                        'processed_at': datetime.now(timezone.utc).isoformat()
                    }
                }
        
        except Exception as e:
            logger.error(f"Error processing document {filename}: {e}")
            return {
                'content_type': 'document',
                'extracted_info': f"Error processing document: {str(e)}",
                'metadata': {
                    'filename': filename,
                    'error': str(e),
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
            }
    
    def _extract_pdf_text(self, file_path: str) -> str:
        """Extract text from PDF file."""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return f"Error extracting PDF text: {str(e)}"
    
    def _extract_word_text(self, file_path: str) -> str:
        """Extract text from Word document."""
        try:
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting Word text: {e}")
            return f"Error extracting Word text: {str(e)}"
    
    def _extract_excel_text(self, file_path: str) -> str:
        """Extract text from Excel file."""
        try:
            workbook = openpyxl.load_workbook(file_path, data_only=True)
            text = ""
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                text += f"Sheet: {sheet_name}\n"
                for row in sheet.iter_rows(values_only=True):
                    row_text = "\t".join([str(cell) if cell is not None else "" for cell in row])
                    if row_text.strip():
                        text += row_text + "\n"
                text += "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting Excel text: {e}")
            return f"Error extracting Excel text: {str(e)}"
    
    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()