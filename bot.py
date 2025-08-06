import os
import shutil
import logging
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

from mp_fetch_data import fetch_emm11_data as fetch_mp_data
from up_fetch_data import fetch_emm11_data as fetch_up_data
from login_to_website import login_to_website
from pdf_gen import pdf_gen  

BOT_TOKEN = "7991394639:AAEfQ8QfM7bGWt4YClLn-NXCWa2r13_creY"

logging.basicConfig(level=logging.INFO)

SELECT_STATE, ASK_START, ASK_END, ASK_DISTRICT = range(4)

user_sessions = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("MP", callback_data="state_mp")],
        [InlineKeyboardButton("UP", callback_data="state_up")],
    ]
    await update.message.reply_text("Please select a state:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_STATE

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["start"] = int(update.message.text)
        await update.message.reply_text("Got it. Now enter the end number:")
        return ASK_END
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_START

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["end"] = int(update.message.text)
        await update.message.reply_text("Now, please enter the district name:")
        return ASK_DISTRICT
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_END

async def ask_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    district = update.message.text
    user_id = update.effective_user.id
    state = context.user_data.get("state")
    start = context.user_data["start"]
    end = context.user_data["end"]

    await update.message.reply_text(f"Fetching data for {state}, district: {district}...")

    user_sessions[user_id] = {"start": start, "end": end, "district": district, "data": []}

    async def send_entry(entry):
        msg = (
            f"{entry['eMM11_num']}\n"
            f"{entry['destination_district']}\n"
            f"{entry['destination_address']}\n"
            f"{entry['quantity_to_transport']}\n"
            f"{entry['generated_on']}"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        user_sessions[user_id]["data"].append(entry)

    if state == "MP":
        await fetch_mp_data(start, end, district, data_callback=send_entry)
    elif state == "UP":
        await fetch_up_data(start, end, district, data_callback=send_entry)
    else:
        await update.message.reply_text("❌ Unknown state selected.")
        return ConversationHandler.END

    if user_sessions[user_id]["data"]:
        keyboard = [[InlineKeyboardButton("Start Again", callback_data="start_again")]]
        if state == "UP":
            keyboard.append([InlineKeyboardButton("Login & Process", callback_data="login_process")])
        keyboard.append([InlineKeyboardButton("Exit", callback_data="exit_process")])

        await update.message.reply_text("✅ Data fetched. What would you like to do next?", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ No data found.")

    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data in ["state_mp", "state_up"]:
        state = query.data.split("_")[1].upper()
        context.user_data["state"] = state
        await query.edit_message_text(f"You selected {state}. Please enter the start number:")
        return ASK_START

    if user_id not in user_sessions:
        await query.edit_message_text("⚠️ Session expired. Please type /start to begin again.")
        return

    session = user_sessions[user_id]
    state = context.user_data.get("state", "")

    if query.data == "login_process":
        await query.edit_message_text("🔐 Logging in and processing...")

        async def log_callback(msg):
            await context.bot.send_message(chat_id=query.message.chat.id, text=msg)

        await login_to_website(session["data"], log_callback=log_callback)

        context.user_data["tp_num_list"] = [entry["eMM11_num"] for entry in session["data"]]

        keyboard = [
            [InlineKeyboardButton("📄 Generate PDF", callback_data="generate_pdf")],
            [InlineKeyboardButton("❌ Exit", callback_data="exit_process")],
        ]
        await context.bot.send_message(chat_id=query.message.chat.id, text="✅ Click below to generate PDF.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data == "generate_pdf":
        tp_num_list = context.user_data.get("tp_num_list", [])
        if not tp_num_list:
            await query.edit_message_text("⚠️ No TP numbers found.")
            return

        async def log_callback(msg):
            await context.bot.send_message(chat_id=query.message.chat.id, text=msg)

        await pdf_gen(tp_num_list, log_callback=log_callback)

        keyboard = [[InlineKeyboardButton(f"📄 {tp}.pdf", callback_data=f"pdf_{tp}")] for tp in tp_num_list]
        keyboard.append([InlineKeyboardButton("❌ Exit", callback_data="exit_process")])
        await context.bot.send_message(chat_id=query.message.chat.id, text="✅ Click a button below to download:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data.startswith("pdf_"):
        tp_num = query.data.replace("pdf_", "")
        path = os.path.join("pdf", f"{tp_num}.pdf")
        if os.path.exists(path):
            with open(path, "rb") as f:
                await context.bot.send_document(chat_id=query.message.chat.id, document=f, filename=f"{tp_num}.pdf", caption=f"📎 PDF for TP {tp_num}")
        else:
            await context.bot.send_message(chat_id=query.message.chat.id, text="❌ PDF not found.")
        return

    if query.data == "start_again":
        user_sessions.pop(user_id, None)
        await query.edit_message_text("🔁 Restarting...\nType /start")
        return

    if query.data == "exit_process":
        user_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Exiting process.")
        return

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Operation cancelled.")
    return ConversationHandler.END

# ------------------------- MAIN ------------------------- #

def cleanup():
    try:
        shutil.rmtree("pdf")
    except FileNotFoundError:
        pass

def main():
    cleanup()
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_STATE: [CallbackQueryHandler(button_handler)],
            ASK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
            ASK_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_district)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
