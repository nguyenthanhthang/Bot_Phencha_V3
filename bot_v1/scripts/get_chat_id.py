import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - log chat_id to console and reply"""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "N/A"
    first_name = update.effective_user.first_name or "N/A"
    
    # Print to console (chuẩn nhất)
    print("=" * 60)
    print("📱 TELEGRAM UPDATE RECEIVED")
    print("=" * 60)
    print(f"Chat ID: {chat_id}")
    print(f"Username: @{username}")
    print(f"Name: {first_name}")
    print(f"Chat Type: {update.effective_chat.type}")
    print("=" * 60)
    print(f"\n✅ Copy this to .env:")
    print(f"TG_ADMIN_CHAT_ID={chat_id}")
    print("=" * 60)
    
    # Optional: Print raw update for debugging
    # print("\nRAW UPDATE:")
    # print(update.to_dict())
    
    # Reply to user
    await update.message.reply_text(
        f"✅ Your chat_id = <code>{chat_id}</code>\n\n"
        f"Copy this to .env:\n"
        f"<code>TG_ADMIN_CHAT_ID={chat_id}</code>",
        parse_mode="HTML"
    )


def main():
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    if not token:
        print("❌ ERROR: TG_BOT_TOKEN not found in .env")
        print("Please add TG_BOT_TOKEN=your_token to .env file")
        return
    
    print("🤖 Starting Telegram bot to get chat_id...")
    print("📨 Send /start to your bot and check console output")
    print("-" * 60)
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
