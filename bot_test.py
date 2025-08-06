import os
import asyncio
import shutil
from pytz import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    JobQueue
)

from fetch_emm11_data import fetch_emm11_data
from login_to_website import login_to_website
from pdf_gen import pdf_gen  # Ensure this is async

BOT_TOKEN = '7933257148:AAHf7HUyBtjQbnzlUqJpGwz0S2yJfC33mqw'

ASK_START, ASK_END, ASK_DISTRICT = range(3)
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Please enter the start number:")
    return ASK_START

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['start'] = int(update.message.text)
        await update.message.reply_text("Got it. Now enter the end number:")
        return ASK_END
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_START

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['end'] = int(update.message.text)
        await update.message.reply_text("Now, please enter the district name:")
        return ASK_DISTRICT
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_END

async def ask_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    district = update.message.text
    start = context.user_data['start']
    end = context.user_data['end']
    user_id = update.effective_user.id

    await update.message.reply_text(f"Fetching data for district: {district}...")

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

    await fetch_emm11_data(start, end, district, data_callback=send_entry)

    if user_sessions[user_id]["data"]:
        keyboard = [
            [InlineKeyboardButton("Start Again", callback_data="start_again")],
            [InlineKeyboardButton("Login & Process", callback_data="login_process")],
            [InlineKeyboardButton("Exit", callback_data="exit_process")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Data fetched. What would you like to do next?", reply_markup=reply_markup)
    else:
        await update.message.reply_text("No data found.")

    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "generate_pdf":
        tp_num_list = context.user_data.get("tp_num_list", [])
        if not tp_num_list:
            await query.edit_message_text("⚠️ No TP numbers found. Please process again.")
            return

        async def generate_and_store():
            await pdf_gen(
                tp_num_list,
                log_callback=lambda msg: asyncio.create_task(
                    context.bot.send_message(chat_id=query.message.chat.id, text=msg)
                ),
                send_pdf_callback=None
            )

        await generate_and_store()

        keyboard = [[InlineKeyboardButton(f"📄 {tp_num}.pdf", callback_data=f"pdf_{tp_num}")] for tp_num in tp_num_list]
        keyboard.append([InlineKeyboardButton("❌ Exit", callback_data="exit_process")])

        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="✅ PDFs are ready. Click a button below to download:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif query.data.startswith("pdf_"):
        tp_num = query.data.replace("pdf_", "")
        pdf_path = os.path.join("pdf", f"{tp_num}.pdf")
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=query.message.chat.id,
                    document=f,
                    filename=f"{tp_num}.pdf",
                    caption=f"📎 Download PDF for TP {tp_num}"
                )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"❌ PDF for TP {tp_num} not found. Please regenerate."
            )
        return

    if user_id not in user_sessions:
        await query.edit_message_text("⚠️ Session expired. Please type /start to begin again.")
        return

    session = user_sessions[user_id]

    if query.data == "start_again":
        await query.edit_message_text("🔁 Restarting...")
        await context.bot.send_message(chat_id=query.message.chat.id, text="/start")
        user_sessions.pop(user_id, None)
        return

    elif query.data == "exit_process":
        await query.edit_message_text("❌ Exiting process. Session ended.")
        user_sessions.pop(user_id, None)
        return

    elif query.data == "login_process":
        await query.edit_message_text("Processing entries...")

        async def process_and_prompt():
            def log_callback(msg):
                asyncio.create_task(context.bot.send_message(chat_id=query.message.chat.id, text=msg))

            await login_to_website(session["data"], log_callback=log_callback)

            context.user_data["tp_num_list"] = [entry['eMM11_num'] for entry in session["data"]]
            keyboard = [
                [InlineKeyboardButton("📄 Generate PDF", callback_data="generate_pdf")],
                [InlineKeyboardButton("❌ Exit", callback_data="exit_process")],
            ]
            await context.bot.send_message(chat_id=query.message.chat.id, text="✅ Click below to generate PDF.",
                                           reply_markup=InlineKeyboardMarkup(keyboard))

        await process_and_prompt()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Operation cancelled.")
    return ConversationHandler.END

async def main():
    try:
        shutil.rmtree("pdf")
    except:
        pass

    job_queue = JobQueue(timezone=timezone('Asia/Kolkata'))  # Fix for timezone error

    app = ApplicationBuilder().token(BOT_TOKEN).job_queue(job_queue).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
            ASK_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_district)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
