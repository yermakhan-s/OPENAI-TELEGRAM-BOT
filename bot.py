import os
import json
import logging
import re
import openai
from telegram import Update, ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction 
import html
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve tokens and keys from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ORGANIZATION = os.getenv("OPENAI_ORGANIZATION")  # Optional

# Retrieve allowed user IDs (comma-separated list)
allowed_users_env = os.getenv("ALLOWED_USER_IDS", "")
if allowed_users_env:
    try:
        ALLOWED_USER_IDS = [int(uid.strip()) for uid in allowed_users_env.split(",")]
    except ValueError:
        ALLOWED_USER_IDS = []
        print("Error: ALLOWED_USER_IDS must be a comma-separated list of numbers.")
else:
    ALLOWED_USER_IDS = []

# Configure OpenAI API
openai.api_key = OPENAI_API_KEY
if OPENAI_ORGANIZATION:
    openai.organization = OPENAI_ORGANIZATION

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# File to store selected models persistently
USER_MODELS_FILE = "user_models.json"

def load_selected_models():
    """Load persisted selected models from file."""
    if os.path.exists(USER_MODELS_FILE):
        try:
            with open(USER_MODELS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user models file: {e}")
            return {}
    else:
        return {}

def save_selected_models(models):
    """Persist the selected models to file."""
    try:
        with open(USER_MODELS_FILE, "w") as f:
            json.dump(models, f)
    except Exception as e:
        logger.error(f"Error saving user models file: {e}")

# Load the persisted models into selected_models dict
selected_models = load_selected_models()

def is_user_allowed(update: Update) -> bool:
    """Return True if the user is allowed to use the bot."""
    user_id = update.effective_user.id
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        return False
    return True

def format_reply(reply: str) -> str:
    """
    Format the reply so that text inside triple backticks is wrapped in <pre><code> tags,
    and other text is HTML-escaped.
    Removes a language specification (e.g. "python") from the top of code blocks if present.
    """
    parts = re.split(r"```", reply)
    formatted_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Non-code parts: HTML-escape
            formatted_parts.append(html.escape(part))
        else:
            # Code parts: remove a potential language spec from the first line
            lines = part.splitlines()
            if lines and re.match(r"^[a-zA-Z0-9]+$", lines[0].strip()):
                code = "\n".join(lines[1:])
            else:
                code = part
            formatted_parts.append(f"<pre><code>{html.escape(code)}</code></pre>")
    return "".join(formatted_parts)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message and set the default model for the user if not set."""
    if not is_user_allowed(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    user = update.effective_user
    user_id = user.id
    if str(user_id) not in selected_models:
        selected_models[str(user_id)] = "gpt-3.5-turbo"
        save_selected_models(selected_models)
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm an OpenAI-powered bot. "
        "Send me a message or a text file and I'll reply. "
        "You can change the model using <code>/setmodel</code> and check your model with <code>/whichmodel</code>.",
        reply_markup=ForceReply(selective=True),
    )

async def setmodel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch available models from OpenAI and display an inline keyboard for selection."""
    if not is_user_allowed(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    try:
        models_response = openai.Model.list()
        available_models = [
            model["id"] for model in models_response["data"] if model["id"].startswith("gpt-")
        ]
        if not available_models:
            raise Exception("No GPT models found.")
    except Exception as e:
        logger.error(f"Error fetching models from OpenAI: {e}")
        await update.message.reply_text("Failed to retrieve available models. Please try again later.")
        return

    keyboard = [
        [InlineKeyboardButton(model, callback_data=f"setmodel|{model}")]
        for model in available_models
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select a model:", reply_markup=reply_markup)

async def set_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the callback query when a user selects a model."""
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    if len(data) == 2 and data[0] == "setmodel":
        chosen_model = data[1]
        user_id = update.effective_user.id
        selected_models[str(user_id)] = chosen_model
        save_selected_models(selected_models)
        await query.edit_message_text(text=f"Model has been changed to {chosen_model}")
    else:
        await query.edit_message_text(text="Invalid selection.")

async def whichmodel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell the user which model is currently set."""
    if not is_user_allowed(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    user_id = update.effective_user.id
    model = selected_models.get(str(user_id), "gpt-3.5-turbo")
    await update.message.reply_text(f"Your current model is: {model}")

async def process_text_input(user_id: int, text: str) -> str:
    """Send a single prompt to OpenAI using a fresh system prompt and the user's input."""
    model = selected_models.get(str(user_id), "gpt-3.5-turbo")
    logger.info(f"User {user_id} using model: {model}")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": text},
    ]
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
        )
        bot_reply = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error from OpenAI: {e}")
        bot_reply = "Sorry, I encountered an error processing your request."
    return bot_reply

# Global variables for debouncing
pending_texts = {}  # key: user_id, value: {"text": accumulated_text, "chat_id": chat_id}
pending_jobs = {}   # key: user_id, value: scheduled job
WAIT_TIME = 2       # seconds to wait for additional parts

async def process_accumulated_text(context: ContextTypes.DEFAULT_TYPE):
    """Process the accumulated text for a user after the waiting period."""
    job_data = context.job.data
    user_id = job_data["user_id"]
    chat_id = job_data["chat_id"]
    entry = pending_texts.pop(user_id, None)
    if not entry:
        return
    text_to_process = entry["text"]
    reply = await process_text_input(user_id, text_to_process)
    safe_reply = format_reply(reply)
    await context.bot.send_message(chat_id=chat_id, text=safe_reply, parse_mode="HTML")
    pending_jobs.pop(user_id, None)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Accumulate incoming text messages and process them as one prompt."""
    if not is_user_allowed(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    new_text = update.message.text

    # Accumulate text parts from the same user
    if user_id in pending_texts:
        pending_texts[user_id]["text"] += "\n" + new_text
    else:
        pending_texts[user_id] = {"text": new_text, "chat_id": chat_id}

    # Cancel any previously scheduled job for this user
    if user_id in pending_jobs:
        pending_jobs[user_id].schedule_removal()

    # Schedule a new job to process the accumulated text after WAIT_TIME seconds
    job_data = {"user_id": user_id, "chat_id": chat_id}
    pending_jobs[user_id] = context.job_queue.run_once(process_accumulated_text, WAIT_TIME, data=job_data)

    # Optionally, send a typing action
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle documents (assumed to be text files) as independent prompts."""
    if not is_user_allowed(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    user_id = update.effective_user.id
    document = update.message.document
    file_path = os.path.join("/tmp", document.file_name)
    try:
        file = await document.get_file()
        await file.download_to_drive(file_path)
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        await update.message.reply_text("Failed to download the file.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            file_text = f.read()
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        await update.message.reply_text("Failed to read the file as text.")
        return

    reply = await process_text_input(user_id, file_text)
    safe_reply = format_reply(reply)
    await update.message.reply_text(safe_reply, parse_mode="HTML")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler to log exceptions."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and hasattr(update, "message") and update.message:
        try:
            await update.message.reply_text("An unexpected error occurred. Please try again later.")
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

def main() -> None:
    """Run the Telegram bot with error handling and crash resilience."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setmodel", setmodel))
    application.add_handler(CommandHandler("whichmodel", whichmodel))
    application.add_handler(CallbackQueryHandler(set_model_callback, pattern=r"^setmodel\|"))
    
    # Message handlers for text messages and documents
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Global error handler to catch all errors
    application.add_error_handler(error_handler)

    application.run_polling()
    
if __name__ == "__main__":
    main()
