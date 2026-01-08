from __future__ import annotations

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Try to use ConcurrentRotatingFileHandler for better Windows support
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    HAS_CONCURRENT_HANDLER = True
except ImportError:
    HAS_CONCURRENT_HANDLER = False
    ConcurrentRotatingFileHandler = None


class SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that gracefully handles rotation errors (file locked)"""
    
    def emit(self, record):
        """Override emit to catch rotation errors during logging"""
        try:
            super().emit(record)
        except (PermissionError, OSError):
            # If rotation fails, try to log without rotation
            # Fallback: just write to console to avoid recursion
            self.handleError(record)
    
    def doRollover(self):
        """Override to handle PermissionError gracefully"""
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # File is locked (another process using it) - skip rotation silently
            # Don't print here to avoid recursion - just skip rotation
            pass


def setup_logger(
    name: str = "BOT_XAUUSD",
    log_dir: str = "logs",
    level: str = "INFO",
    use_timestamp_log: bool = False,
) -> logging.Logger:
    """
    Console + rotating file logger.
    Creates logs/app.log (rotates by size) or logs/app_YYYYMMDD_HHMMSS.log (timestamp-based).
    
    Args:
        name: Logger name
        log_dir: Directory for log files
        level: Logging level
        use_timestamp_log: If True, use timestamp-based log file (no rotation needed, avoids WinError 32)
    
    Uses SafeRotatingFileHandler or ConcurrentRotatingFileHandler to handle file lock errors gracefully.
    """
    logger = logging.getLogger(name)

    # Clear existing handlers to ensure we use the new handler
    # This prevents using old handlers that don't handle file lock errors
    if logger.handlers:
        # Remove old file handlers (they might be the problematic RotatingFileHandler)
        for handler in logger.handlers[:]:
            if isinstance(handler, (RotatingFileHandler, logging.FileHandler)):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except:
                    pass

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Option 1: Use timestamp-based log file (no rotation, avoids WinError 32)
    if use_timestamp_log:
        log_path = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
    else:
        # Option 2: Use rotating handler with better Windows support
        log_path = os.path.join(log_dir, "app.log")
        
        # Prefer ConcurrentRotatingFileHandler if available (better for Windows)
        if HAS_CONCURRENT_HANDLER:
            fh = ConcurrentRotatingFileHandler(
                log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
            )
        else:
            # Fallback to SafeRotatingFileHandler
            fh = SafeRotatingFileHandler(
                log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
            )

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
