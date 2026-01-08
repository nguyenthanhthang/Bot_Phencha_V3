"""
Telegram client for sending notifications (one-way: bot -> Telegram)
Async-safe, can be called from sync code
"""

import os
import asyncio
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TelegramConfig:
    """Telegram configuration"""
    enabled: bool
    token: str
    chat_id: str


def load_telegram_config() -> TelegramConfig:
    """Load Telegram config from environment"""
    enabled = os.getenv("TG_ENABLED", "true").lower() == "true"
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id_str = os.getenv("TG_ADMIN_CHAT_ID", "").strip()
    # For backward compatibility, use first chat_id if multiple provided
    # Note: TelegramClient is legacy, TelegramNotifier handles multiple chat IDs
    chat_id = chat_id_str.split(",")[0].strip() if chat_id_str else ""
    return TelegramConfig(enabled=enabled, token=token, chat_id=chat_id)


class TelegramClient:
    """
    Send messages to Telegram (one-way communication).
    Uses HTTP API, independent of PTB polling loop.
    Async-safe, can be called from sync code.
    """
    
    def __init__(self, cfg: TelegramConfig):
        self.cfg = cfg
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def _send_async(self, text: str) -> bool:
        """Internal async send method"""
        if not self.cfg.enabled:
            return False
        if not self.cfg.token or not self.cfg.chat_id:
            return False
        
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.cfg.token}/sendMessage"
            payload = {
                "chat_id": self.cfg.chat_id,
                "text": text,
                "disable_web_page_preview": True,
                "parse_mode": "HTML",
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    return False
        except Exception:
            # Silently ignore errors (or log to your logger)
            return False
    
    def send(self, text: str) -> None:
        """
        Fire-and-forget send message.
        Can be called from sync code (trading loop).
        """
        if not self.cfg.enabled or not text:
            return
        
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
            # If loop exists, schedule task
            loop.create_task(self._send_async(text))
        except RuntimeError:
            # No running loop, create new one
            try:
                asyncio.run(self._send_async(text))
            except Exception:
                # Ignore errors silently
                pass
