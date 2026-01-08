"""
Telegram command bot for receiving commands from Telegram
Uses python-telegram-bot v21+ with polling
"""

import os
import time
from typing import Dict, Any, Optional, Callable, Tuple
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from notification.bot_state import BotState

load_dotenv()


def _admin_only(update: Update) -> bool:
    """
    Check if chat is allowed (private, group, supergroup) and user is admin
    
    Allows:
    - Private chats (if chat_id or user_id matches admin)
    - Group/Supergroup chats (if group chat_id matches admin)
    
    Supports multiple chat IDs separated by comma:
    TG_ADMIN_CHAT_ID=123456789,-1001234567890
    """
    chat_type = update.effective_chat.type
    # Only allow private, group, and supergroup
    if chat_type not in ("private", "group", "supergroup"):
        return False
    
    admin_id_str = os.getenv("TG_ADMIN_CHAT_ID", "").strip()
    if not admin_id_str:
        # If not set, allow all (not recommended for production)
        return True
    
    # Support multiple chat IDs (comma-separated)
    admin_ids = [id_str.strip() for id_str in admin_id_str.split(",") if id_str.strip()]
    
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id) if update.effective_user else None
    
    # Check if chat_id matches any admin ID
    if chat_id in admin_ids:
        return True
    
    # For private chats, also check user_id
    if chat_type == "private" and user_id and user_id in admin_ids:
        return True
    
    return False


def _fmt_status(s: Dict[str, Any], filter_magic: Optional[int] = None) -> str:
    """Format status message with MT5 account and positions"""
    lines = [
        "📌 <b>STATUS (MT5 LIVE)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Symbol: {s['symbol']} | TF: {s['timeframe']} | Session: {s['session']}",
        f"⏸️ Paused: {'Yes' if s['paused'] else 'No'} | "
        f"🚫 DayBlocked: {'Yes' if s['day_blocked'] else 'No'} | "
        f"📉 ConsecLoss: {s['consec_loss']}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    
    # Account info
    acc = s.get("account", {})
    if acc.get("ok"):
        lines += [
            f"<b>💼 ACCOUNT</b>",
            f"Login: {acc.get('login')} | {acc.get('server')}",
            f"Currency: {acc.get('currency')}",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💵 Balance: <b>{acc.get('balance', 0):.2f}$</b>",
            f"📊 Equity: <b>{acc.get('equity', 0):.2f}$</b>",
            f"💰 Margin: {acc.get('margin', 0):.2f}$ | Free: {acc.get('margin_free', 0):.2f}$",
        ]
        if acc.get('margin_level') is not None:
            lines.append(f"📈 Margin Level: {acc.get('margin_level', 0):.2f}%")
    elif acc:
        lines.append(f"⚠️ Account ERROR: {acc.get('error', 'unknown')}")
    
    # Positions
    pos = s.get("mt5_positions", [])
    
    # Check for errors first
    pos_errors = [p for p in pos if "_error" in p]
    pos_valid = [p for p in pos if "_error" not in p]
    
    # Filter by magic if specified (only valid positions)
    if filter_magic is not None:
        pos_valid = [p for p in pos_valid if p.get('magic') == filter_magic]
    
    # Display errors if any
    if pos_errors:
        for err_dict in pos_errors:
            lines.append(f"\n⚠️ <b>MT5 ERROR:</b> {err_dict.get('_error', 'Unknown error')}")
    
    if not pos_valid:
        lines.append(f"\n<b>📦 POSITIONS</b>\nOpen positions: <b>NONE</b>")
    else:
        lines.append(f"\n<b>📦 POSITIONS ({len(pos_valid)})</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        # Show max 10 positions
        for i, p in enumerate(pos_valid[:10], 1):
            pnl_emoji = "🟢" if p['profit'] >= 0 else "🔴"
            lines.append(
                f"<b>{i}. #{p['ticket']}</b> {p['symbol']} {p['direction']}\n"
                f"   Lot: {p['lots']:.2f} | Entry: {p['price_open']:.2f}\n"
                f"   SL: {p['sl']:.2f} | TP: {p['tp']:.2f}\n"
                f"   {pnl_emoji} PnL: {p['profit']:+.2f}$ | Time: {p['time_open']}"
            )
            if i < len(pos_valid[:10]):
                lines.append("")
        if len(pos_valid) > 10:
            lines.append(f"\n... and {len(pos_valid) - 10} more")
    
    # Error if any
    error_str = s.get('last_error')
    if error_str:
        lines.append(f"\nLastError: {error_str}")
    
    return "\n".join(lines)


class TelegramCommandBot:
    """Telegram command bot handler"""
    
    def __init__(self, state: BotState, on_close_all: Optional[Callable[[], Tuple[bool, str]]] = None):
        self.state = state
        self.on_close_all = on_close_all
        self._closeall_nonce: Optional[str] = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not _admin_only(update):
            await update.message.reply_text("Access denied.")
            return
        await update.message.reply_text(
            "Hello! Available commands:\n"
            "/status - Bot status\n"
            "/pause - Pause bot (no new entries)\n"
            "/resume - Resume bot\n"
            "/positions - Open positions\n"
            "/lasttrade - Last trade details\n"
            "/today - Today's stats\n"
            "/profit - Profit stats (WTD/MTD/YTD)\n"
            "/closeall - Close all positions (2-step confirm)\n"
            "/stats - Performance stats\n"
            "/chatid - Get chat ID (for setup)"
        )
    
    async def chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /chatid command - debug chat ID"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Log to console
        print("=" * 60)
        print("📱 TELEGRAM CHAT INFO")
        print("=" * 60)
        print(f"Chat ID: {chat.id}")
        print(f"Chat Type: {chat.type}")
        if chat.title:
            print(f"Chat Title: {chat.title}")
        if user:
            print(f"User ID: {user.id}")
            print(f"Username: @{user.username}" if user.username else "Username: N/A")
            print(f"Name: {user.first_name} {user.last_name or ''}")
        print("=" * 60)
        print(f"\n✅ Copy this to .env:")
        print(f"TG_ADMIN_CHAT_ID={chat.id}")
        print("=" * 60)
        
        # Reply to user
        msg = (
            f"📱 <b>CHAT INFO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Chat ID: <code>{chat.id}</code>\n"
            f"Chat Type: {chat.type}\n"
        )
        if chat.title:
            msg += f"Chat Title: {chat.title}\n"
        if user:
            msg += f"\n👤 User ID: <code>{user.id}</code>\n"
            if user.username:
                msg += f"Username: @{user.username}\n"
            msg += f"Name: {user.first_name} {user.last_name or ''}\n"
        msg += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\n✅ Copy to .env:\n"
            f"<code>TG_ADMIN_CHAT_ID={chat.id}</code>"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
    
    async def data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /data command - show current data status from MT5"""
        if not _admin_only(update):
            return
        snap = self.state.get_snapshot()
        
        # Get latest data info from bot state
        from datetime import datetime
        now = datetime.now()
        
        msg_lines = [
            f"📊 <b>DATA STATUS</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"📅 Session: <b>{snap.get('session', 'N/A')}</b>",
            f"💰 Balance: <b>{snap.get('balance', 0):.2f}$</b>",
            f"📦 Positions: <b>{len(snap.get('open_trades', []))}</b>",
        ]
        
        # MT5 account info
        acc = snap.get("account", {})
        if acc.get("ok"):
            msg_lines.extend([
                f"\n<b>MT5 ACCOUNT:</b>",
                f"✅ Connected",
                f"Login: {acc.get('login', 'N/A')}",
                f"Server: {acc.get('server', 'N/A')}",
                f"Balance: {acc.get('balance', 0):.2f} {acc.get('currency', 'USD')}",
                f"Equity: {acc.get('equity', 0):.2f}",
            ])
        else:
            msg_lines.append(f"\n⚠️ MT5 Account: {acc.get('error', 'Not connected')}")
        
        # MT5 positions
        mt5_pos = snap.get("mt5_positions", [])
        if mt5_pos:
            pos_valid = [p for p in mt5_pos if "_error" not in p]
            msg_lines.append(f"\n<b>MT5 POSITIONS:</b> {len(pos_valid)}")
            if pos_valid:
                for p in pos_valid[:5]:  # Show max 5
                    msg_lines.append(
                        f"  #{p['ticket']} {p['symbol']} {p['direction']} "
                        f"{p['lots']:.2f} lot @ {p['price_open']:.2f}"
                    )
        else:
            msg_lines.append(f"\n📦 MT5 Positions: None")
        
        msg_lines.append(f"\n━━━━━━━━━━━━━━━━━━━━")
        msg_lines.append(f"💡 Bot is fetching data from MT5 every 10-60s")
        msg_lines.append(f"💡 Check logs for latest candle timestamp")
        
        await update.message.reply_html("\n".join(msg_lines))
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not _admin_only(update):
            return
        
        # Check for filter argument: /status all or /status bot
        filter_magic = None
        if context.args:
            arg = context.args[0].strip().lower()
            if arg == "bot":
                # Filter by bot magic number (234000 from MT5Executor)
                filter_magic = 234000
            # "all" means no filter (show all positions)
        
        snap = self.state.get_snapshot()
        await update.message.reply_text(_fmt_status(snap, filter_magic=filter_magic), parse_mode="HTML")
    
    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command"""
        if not _admin_only(update):
            return
        self.state.set(paused=True)
        await update.message.reply_text("✅ Bot <b>PAUSED</b>: Will NOT open new positions.", parse_mode="HTML")
    
    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not _admin_only(update):
            return
        self.state.set(paused=False)
        await update.message.reply_text("✅ Bot <b>RESUMED</b>: Can open new positions.", parse_mode="HTML")
    
    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        if not _admin_only(update):
            return
        snap = self.state.get_snapshot()
        # Use open_trades if available, fallback to positions for backward compatibility
        pos = snap.get("open_trades", snap.get("positions", []))
        if not pos:
            await update.message.reply_text("No open positions.")
            return
        
        lines = ["<b>OPEN POSITIONS:</b>"]
        for i, p in enumerate(pos, 1):
            direction = p.get('direction', p.get('side', 'N/A'))
            setup = p.get('setup', '?')
            lot = p.get('lot_open', p.get('lot', 0))
            entry = p.get('entry', p.get('entry_price', 0))
            sl = p.get('sl', 0)
            tp1 = p.get('tp1', 0)
            tp2 = p.get('tp2', 0)
            lines.append(
                f"{i}. {direction} [{setup}]\n"
                f"   Lot: {lot:.2f} | Entry: {entry:.2f}\n"
                f"   SL: {sl:.2f} | TP1: {tp1:.2f} | TP2: {tp2:.2f}"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")
    
    async def lasttrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /lasttrade command"""
        if not _admin_only(update):
            return
        snap = self.state.get_snapshot()
        lt = snap["last_trade"]
        if not lt:
            await update.message.reply_text("No last trade.")
            return
        
        lines = ["<b>LAST TRADE:</b>"]
        for k, v in lt.items():
            lines.append(f"{k}: {v}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    
    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command"""
        if not _admin_only(update):
            return
        snap = self.state.get_snapshot()
        winrate = (snap['win_today'] / snap['trades_today'] * 100) if snap['trades_today'] > 0 else 0.0
        await update.message.reply_text(
            f"<b>TODAY'S STATS:</b>\n"
            f"PnL: ${snap['pnl_today']:.2f}\n"
            f"Trades: {snap['trades_today']}\n"
            f"Wins: {snap['win_today']} | Losses: {snap['loss_today']}\n"
            f"Winrate: {winrate:.1f}%",
            parse_mode="HTML"
        )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command (alias for /today)"""
        await self.today(update, context)
    
    async def profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /profit command - show profit stats from MT5 history deals"""
        if not _admin_only(update):
            return
        snap = self.state.get_snapshot()
        profit_data = snap.get("mt5_profit", {})
        
        if not profit_data.get("ok"):
            await update.message.reply_text(
                "⚠️ <b>PROFIT DATA UNAVAILABLE</b>\n"
                f"Error: {profit_data.get('error', 'No data cached yet')}\n"
                f"Please wait for next update (60s interval).",
                parse_mode="HTML"
            )
            return
        
        buckets = profit_data.get("buckets", {})
        asof = profit_data.get("asof", "N/A")
        
        # Get account balance for percentage calculation
        acc = snap.get("account", {})
        balance = acc.get("balance", 1000.0)  # Fallback to 1000 if not available
        
        def fmt_net(net: float) -> str:
            """Format net profit with color emoji"""
            if net > 0:
                return f"🟢 {net:+.2f}$"
            elif net < 0:
                return f"🔴 {net:+.2f}$"
            else:
                return f"⚪ {net:.2f}$"
        
        def fmt_bucket(bucket: Dict) -> str:
            """Format a single bucket"""
            if not bucket.get("ok"):
                return f"❌ Error: {bucket.get('error', 'Unknown')}"
            net = bucket.get("net", 0.0)
            return fmt_net(net)
        
        # Format as clean table
        msg = (
            f"💰 <b>PROFIT REPORT (MT5 HISTORY)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Balance: <b>{balance:.2f}$</b>\n"
            f"🕐 Updated: {asof}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"<b>📅 DAILY</b>\n"
            f"  Today:     {fmt_bucket(buckets.get('today', {}))}\n"
            f"  Yesterday: {fmt_bucket(buckets.get('yesterday', {}))}\n"
            f"\n"
            f"<b>📅 WEEKLY</b>\n"
            f"  This Week: {fmt_bucket(buckets.get('this_week', {}))}\n"
            f"  Last Week: {fmt_bucket(buckets.get('last_week', {}))}\n"
            f"\n"
            f"<b>📅 MONTHLY</b>\n"
            f"  This Month: {fmt_bucket(buckets.get('this_month', {}))}\n"
            f"  Last Month: {fmt_bucket(buckets.get('last_month', {}))}\n"
            f"\n"
            f"<b>📅 YEARLY</b>\n"
            f"  This Year: {fmt_bucket(buckets.get('this_year', {}))}\n"
            f"  Last Year: {fmt_bucket(buckets.get('last_year', {}))}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"<i>Note: Includes profit + swap + commission from all deals (bot + manual)</i>"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
    
    async def closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command with 2-step confirmation"""
        if not _admin_only(update):
            return
        
        # Step 1: Request confirmation
        if not context.args:
            now = int(time.time())
            self._closeall_nonce = str(now)[-4:]
            await update.message.reply_text(
                f"⚠️ <b>CONFIRM CLOSE ALL POSITIONS</b>\n\n"
                f"Send again:\n"
                f"<code>/closeall {self._closeall_nonce}</code>",
                parse_mode="HTML"
            )
            return
        
        # Step 2: Verify nonce
        nonce = context.args[0].strip()
        if nonce != self._closeall_nonce:
            await update.message.reply_text(
                "❌ Wrong confirmation code. Try /closeall again.",
                parse_mode="HTML"
            )
            return
        
        # Execute close all
        self._closeall_nonce = None
        if self.on_close_all:
            try:
                ok, msg = self.on_close_all()
                emoji = "✅" if ok else "❌"
                await update.message.reply_text(
                    f"{emoji} <b>Close All:</b> {msg}",
                    parse_mode="HTML"
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error: {str(e)}",
                    parse_mode="HTML"
                )
        else:
            await update.message.reply_text(
                "❌ Close all callback not configured.",
                parse_mode="HTML"
            )


def run_telegram_command_bot(state: BotState, on_close_all: Optional[Callable[[], Tuple[bool, str]]] = None):
    """
    Run Telegram command bot in polling mode.
    This function blocks, so should be run in a separate thread.
    Creates a new event loop for the thread.
    """
    import asyncio
    
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TG_BOT_TOKEN in .env")
    
    bot = TelegramCommandBot(state=state, on_close_all=on_close_all)
    app = Application.builder().token(token).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("pause", bot.pause))
    app.add_handler(CommandHandler("resume", bot.resume))
    app.add_handler(CommandHandler("positions", bot.positions))
    app.add_handler(CommandHandler("lasttrade", bot.lasttrade))
    app.add_handler(CommandHandler("today", bot.today))
    app.add_handler(CommandHandler("profit", bot.profit))
    app.add_handler(CommandHandler("stats", bot.stats))
    app.add_handler(CommandHandler("closeall", bot.closeall))
    app.add_handler(CommandHandler("chatid", bot.chatid))
    app.add_handler(CommandHandler("data", bot.data))
    
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run polling
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        loop.close()

