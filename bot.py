from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
)
import asyncio
from fetch_emm11_data import fetch_emm11_data
from login_to_website import login_to_website

BOT_TOKEN = '7933257148:AAHf7HUyBtjQbnzlUqJpGwz0S2yJfC33mqw'  # Replace with your bot token

# Conversation states
ASK_START, ASK_END, ASK_DISTRICT = range(3)
user_sessions = {}

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Welcome! Please enter the start number:")
    return ASK_START

def ask_start(update: Update, context: CallbackContext):
    context.user_data['start'] = int(update.message.text)
    update.message.reply_text("✅ Got it. Now enter the end number:")
    return ASK_END

def ask_end(update: Update, context: CallbackContext):
    context.user_data['end'] = int(update.message.text)
    update.message.reply_text("✅ Now, please enter the district name:")
    return ASK_DISTRICT

def ask_district(update: Update, context: CallbackContext):
    district = update.message.text
    start = context.user_data['start']
    end = context.user_data['end']
    user_id = update.effective_user.id

    update.message.reply_text(f"📡 Fetching data from {start} to {end} for district: {district}...")

    user_sessions[user_id] = {"start": start, "end": end, "district": district, "data": []}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def send_entry(entry):
        msg = (
            f"📄 eMM11: {entry['eMM11_num']}\n"
            f"📍 District: {entry['destination_district']}\n"
            f"🏠 Address: {entry['destination_address']}\n"
            f"🚚 Qty: {entry['quantity_to_transport']}\n"
            f"📆 Generated On: {entry['generated_on']}"
        )
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

        user_sessions[user_id]["data"].append(entry)

    results = []

    async def run_fetch():
        await fetch_emm11_data(start, end, district, data_callback=send_entry)

    loop.run_until_complete(run_fetch())

    if user_sessions[user_id]["data"]:
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
            [InlineKeyboardButton("🔐 Login & Process", callback_data="login_process")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("✅ Data fetched. What would you like to do next?", reply_markup=reply_markup)
    else:
        update.message.reply_text("⚠️ No data found.")

    return ConversationHandler.END

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if user_id not in user_sessions:
        query.edit_message_text("Session expired. Please restart with /start.")
        return

    session = user_sessions[user_id]

    if query.data == "refresh":
        query.edit_message_text("🔄 Refreshing data...")

        start = session["start"]
        end = session["end"]
        district = session["district"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def send_entry(entry):
            msg = (
                f"📄 eMM11: {entry['eMM11_num']}\n"
                f"📍 District: {entry['destination_district']}\n"
                f"🏠 Address: {entry['destination_address']}\n"
                f"🚚 Qty: {entry['quantity_to_transport']}\n"
                f"📆 Generated On: {entry['generated_on']}"
            )
            context.bot.send_message(chat_id=query.message.chat.id, text=msg)

        async def run_fetch():
            await fetch_emm11_data(start, end, district, data_callback=lambda entry: loop.call_soon_threadsafe(send_entry, entry))

        loop.run_until_complete(run_fetch())

    elif query.data == "login_process":
        query.edit_message_text("🔐 Logging in and processing entries...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def log_callback(msg):
            context.bot.send_message(chat_id=query.message.chat.id, text=msg)

        loop.run_until_complete(login_to_website(session["data"], log_callback=log_callback))

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_START: [MessageHandler(Filters.text & ~Filters.command, ask_start)],
            ASK_END: [MessageHandler(Filters.text & ~Filters.command, ask_end)],
            ASK_DISTRICT: [MessageHandler(Filters.text & ~Filters.command, ask_district)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
