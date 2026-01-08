from __future__ import annotations
import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram notifier for sending trading notifications"""
    
    def __init__(self):
        self.enabled = os.getenv("TG_ENABLED", "true").lower() == "true"
        self.token = os.getenv("TG_BOT_TOKEN", "").strip()
        chat_id_str = os.getenv("TG_ADMIN_CHAT_ID", "").strip()
        # Support multiple chat IDs (comma-separated)
        self.chat_ids = [cid.strip() for cid in chat_id_str.split(",") if cid.strip()] if chat_id_str else []
        self.max_retries = 2
        self.retry_delay = 1.0  # seconds

    def send(self, text: str, silent_fail: bool = False):
        """
        Send raw text message to all configured chat IDs
        
        Args:
            text: Message text
            silent_fail: If True, suppress all exceptions (for shutdown scenarios)
        
        This method never raises exceptions - all errors are caught and logged.
        """
        try:
            if not self.enabled or not self.token or not self.chat_ids:
                return
            
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            
            # Send to all chat IDs
            for chat_id in self.chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                    "parse_mode": "HTML",
                }
                
                # Retry logic for network errors
                last_error = None
                for attempt in range(self.max_retries + 1):
                    try:
                        response = requests.post(url, json=payload, timeout=10)
                        response.raise_for_status()  # Raise exception for HTTP errors
                        break  # Success, exit retry loop
                    except (requests.exceptions.Timeout, 
                            requests.exceptions.ConnectionError,
                            requests.exceptions.ReadTimeout,
                            requests.exceptions.RequestException) as e:
                        last_error = e
                        if attempt < self.max_retries:
                            time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                        else:
                            # Final attempt failed
                            if not silent_fail:
                                # Log error but don't crash
                                logger.warning(f"Failed to send Telegram message after {self.max_retries + 1} attempts: {e}")
                            # Continue to next chat_id if one fails
                    except Exception as e:
                        # Other unexpected errors (should not happen, but catch all)
                        if not silent_fail:
                            logger.warning(f"Unexpected error sending Telegram message: {e}")
                        break  # Don't retry for unexpected errors
        except Exception as e:
            # Ultimate safety net - catch any unexpected errors in the method itself
            if not silent_fail:
                logger.error(f"Critical error in TelegramNotifier.send(): {e}", exc_info=True)

    # ========== Notification Templates ==========
    
    def notify_start(self, app: str, symbol: str, tf: str, tz: str, sessions: str, cfg_summary: str):
        """Notify bot started"""
        self.send(
            f"✅ <b>BOT STARTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{app}</b>\n"
            f"Symbol: {symbol} | TF: {tf}\n"
            f"TZ: {tz}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Sessions: {sessions}\n"
            f"⚙️ {cfg_summary}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def notify_open(self, d: dict):
        """
        Notify trade opened
        d: {direction, setup, session, entry, sl, tp1, tp2, lot, reason}
        """
        direction_emoji = "🔼" if d['direction'] == "BUY" else "🔽"
        self.send(
            f"{direction_emoji} <b>OPEN {d['direction']}</b> [{d.get('setup', '?')}]\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Session: {d.get('session', '?')}\n"
            f"💰 Entry: <b>{d['entry']:.2f}</b>\n"
            f"🛡️ SL: {d['sl']:.2f}\n"
            f"🎯 TP1: {d.get('tp1', 0):.2f} | TP2: {d.get('tp2', 0):.2f}\n"
            f"📦 Lot: <b>{d.get('lot', 0):.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 {d.get('reason', '-')}"
        )

    def notify_tp1(self, d: dict):
        """
        Notify TP1 hit (partial close)
        d: {direction, setup, tp1, closed_lot, runner_lot, new_sl, pnl_part}
        """
        self.send(
            f"✅ <b>TP1 HIT</b> [{d.get('setup', '?')}] {d['direction']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 TP1: <b>{d['tp1']:.2f}</b>\n"
            f"💰 Closed: {d['closed_lot']:.2f} lot\n"
            f"📦 Runner: {d['runner_lot']:.2f} lot\n"
            f"🛡️ SL → BE+: <b>{d['new_sl']:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 PnL (partial): <b>{d['pnl_part']:+.2f}$</b>"
        )

    def notify_close(self, d: dict):
        """
        Notify trade closed
        d: {direction, setup, reason, exit_price, pnl, balance, consec_loss}
        """
        pnl = d['pnl']
        reason = d.get('reason', '')
        
        # Format message theo yêu cầu
        if pnl > 0:
            # Chốt lời
            msg = f"🎯 <b>PhenCha đã đớp được {pnl:+.2f}$</b>\n"
        elif pnl < 0:
            # Dính SL
            msg = f"🛑 <b>PhenCha đã làm rớt {pnl:+.2f}$</b>\n"
        else:
            # Break even
            msg = f"⚪ <b>PhenCha break even (0.00$)</b>\n"
        
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 {d['direction']} [{d.get('setup', '?')}] | {reason}\n"
        msg += f"💰 Exit: <b>{d['exit_price']:.2f}</b>\n"
        msg += f"💵 Balance: <b>{d['balance']:.2f}$</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 ConsecLoss: {d.get('consec_loss', 0)}"
        
        self.send(msg)

    def notify_stop_day(self, consec_loss: int):
        """Notify stop day (consecutive loss block)"""
        self.send(
            f"🛑 <b>STOP DAY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Consecutive losses: <b>{consec_loss}</b>\n"
            f"🚫 Bot blocked until next day"
        )

    def notify_error(self, err: str):
        """Notify error"""
        self.send(
            f"🚨 <b>ERROR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ {err}"
        )

    def notify_session_start(self, session: str, time_str: str):
        """
        Notify session started
        session: "ASIA", "LONDON", "US"
        time_str: formatted time string
        """
        session_emoji = {
            "ASIA": "🌏",
            "LONDON": "🇬🇧",
            "US": "🇺🇸",
        }.get(session, "⏰")
        
        session_name = {
            "ASIA": "ASIA SESSION",
            "LONDON": "LONDON SESSION",
            "US": "US SESSION",
        }.get(session, session)
        
        self.send(
            f"{session_emoji} <b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"{session_emoji} <b>{session_name} OPENED</b>\n"
            f"{session_emoji} <b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"🕐 {time_str}\n"
            f"✅ Bot ready to trade"
        )

