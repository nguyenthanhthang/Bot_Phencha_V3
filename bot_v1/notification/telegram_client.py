"""
Telegram Client Module
Handles Telegram bot communication
"""

import requests
from typing import Optional, Dict
import json


class TelegramClient:
    """Telegram bot client"""
    
    def __init__(self, token: str, chat_id: str):
        """
        Initialize Telegram client
        
        Args:
            token: Bot token from @BotFather
            chat_id: Chat ID to send messages to
        """
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send text message
        
        Args:
            text: Message text
            parse_mode: Parse mode (HTML, Markdown, etc.)
            
        Returns:
            True if successful
        """
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return False
    
    def send_photo(self, photo_path: str, caption: Optional[str] = None) -> bool:
        """
        Send photo
        
        Args:
            photo_path: Path to photo file
            caption: Photo caption
            
        Returns:
            True if successful
        """
        url = f"{self.base_url}/sendPhoto"
        
        try:
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {"chat_id": self.chat_id}
                if caption:
                    data["caption"] = caption
                
                response = requests.post(url, files=files, data=data, timeout=10)
                return response.status_code == 200
        except Exception as e:
            print(f"Error sending Telegram photo: {e}")
            return False
    
    def send_document(self, document_path: str, caption: Optional[str] = None) -> bool:
        """
        Send document
        
        Args:
            document_path: Path to document file
            caption: Document caption
            
        Returns:
            True if successful
        """
        url = f"{self.base_url}/sendDocument"
        
        try:
            with open(document_path, 'rb') as doc:
                files = {'document': doc}
                data = {"chat_id": self.chat_id}
                if caption:
                    data["caption"] = caption
                
                response = requests.post(url, files=files, data=data, timeout=10)
                return response.status_code == 200
        except Exception as e:
            print(f"Error sending Telegram document: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test Telegram connection"""
        return self.send_message("🤖 Bot connection test successful!")


