import os
import uuid
import base64
from typing import Optional, Dict, Any
from fastapi import UploadFile
from datetime import datetime

class FileHandler:
    """Utility class for handling file uploads"""
    
    def __init__(self, upload_dir: str = "uploads"):
        """Initialize with upload directory"""
        self.upload_dir = upload_dir
        self._ensure_upload_dir_exists()
    
    def _ensure_upload_dir_exists(self) -> None:
        """Ensure upload directory exists"""
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
    
    async def save_upload_file(self, file: UploadFile, session_id: str = None) -> Dict[str, Any]:
        """Save uploaded file to disk and return file info"""
        # Generate a unique file ID
        file_id = str(uuid.uuid4())
        
        # Create session directory if session_id is provided
        file_dir = self.upload_dir
        if session_id:
            file_dir = os.path.join(self.upload_dir, session_id)
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)
        
        # Get file extension
        _, ext = os.path.splitext(file.filename)
        
        # Create a unique filename
        unique_filename = f"{file_id}{ext}"
        file_path = os.path.join(file_dir, unique_filename)
        
        # Save the file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Calculate relative path for API access
        relative_path = os.path.join("/files", session_id, unique_filename) if session_id else os.path.join("/files", unique_filename)
        
        # Return file info
        return {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": file_path,
            "file_url": relative_path,
            "file_type": file.content_type,
            "file_size": os.path.getsize(file_path),
            "created_at": datetime.utcnow()
        }
    
    def save_base64_file(self, base64_content: str, filename: str, session_id: str = None) -> Dict[str, Any]:
        """Save a base64 encoded file to disk and return file info"""
        # Generate a unique file ID
        file_id = str(uuid.uuid4())
        
        # Create session directory if session_id is provided
        file_dir = self.upload_dir
        if session_id:
            file_dir = os.path.join(self.upload_dir, session_id)
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)
        
        # Get file extension
        _, ext = os.path.splitext(filename)
        
        # Create a unique filename
        unique_filename = f"{file_id}{ext}"
        file_path = os.path.join(file_dir, unique_filename)
        
        # Decode and save the file
        try:
            # Remove data URL prefix if present
            if "base64," in base64_content:
                base64_content = base64_content.split("base64,")[1]
            
            file_bytes = base64.b64decode(base64_content)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            # Guess content type based on extension
            content_type = self._guess_content_type(ext)
            
            # Calculate relative path for API access
            relative_path = os.path.join("/files", session_id, unique_filename) if session_id else os.path.join("/files", unique_filename)
            
            # Return file info
            return {
                "file_id": file_id,
                "filename": filename,
                "file_path": file_path,
                "file_url": relative_path,
                "file_type": content_type,
                "file_size": os.path.getsize(file_path),
                "created_at": datetime.utcnow()
            }
        except Exception as e:
            # Handle error
            print(f"Error saving base64 file: {e}")
            raise
    
    def _guess_content_type(self, extension: str) -> str:
        """Guess content type based on file extension"""
        ext = extension.lower()
        # Map common extensions to MIME types
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file by path"""
        try:
            # Make sure file exists
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False 