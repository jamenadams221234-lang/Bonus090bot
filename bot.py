import os
import logging
import tempfile
import asyncio
from io import BytesIO

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from gtts import gTTS
import language_tool_python

# ---------- Config ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- LanguageTool (lazy init) ----------
_tool = None

def get_tool():
    global _tool
    if _tool is None:
        logger.info("Initializing LanguageTool...")
        _tool = language_tool_python.LanguageTool("en-US")
        logger.info("LanguageTool ready.")
    return _tool


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *AI Grammar Corrector + 🔊 Text-to-Speech*\n\n"
        "✍️ *Fix your grammar* — send any English text\n"
        "🗣 *Convert text to speech* — use /tts <text>\n\n"
        "⚡️ Fast, simple & easy to use\n\n"
        "Send me a message to get started!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *How to use:*\n\n"
        "• Send any text → I'll correct the grammar\n"
        "• `/tts <text>` → I'll send back a voice message\n"
        "• `/voice` → reply to any message with `/voice` to hear it\n"
        "• `/start` → show the welcome message\n"
        "• `/help` → show this help"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def correct_grammar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if not user_text or not user_text.strip():
        await update.message.reply_text("⚠️ Please send some text to correct.")
        return

    msg = await update.message.reply_text("✍️ Checking grammar...")

    try:
        tool = await asyncio.to_thread(get_tool)
        matches = await asyncio.to_thread(tool.check, user_text)
        corrected = language_tool_python.utils.correct(user_text, matches)

        if corrected.strip() == user_text.strip():
            await msg.edit_text(
                f"✅ *No issues found!*\n\n_{user_text}_",
                parse_mode="Markdown",
            )
            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔊 Hear it", callback_data="tts_corrected"),
                ]
            ]
        )
        # store corrected text in user_data for TTS callback
        context.user_data["last_corrected"] = corrected

        # Escape for Markdown safely
        safe_original = user_text.replace("*", "").replace("_", "")
        safe_corrected = corrected.replace("*", "").replace("_", "")

        response = (
            f"📝 *Original:*\n{safe_original}\n\n"
            f"✅ *Corrected:*\n{safe_corrected}"
        )
        await msg.edit_text(response, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        logger.exception("Grammar correction failed")
        await msg.edit_text(f"❌ Error while correcting: {e}")


async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🗣 Usage: `/tts <text to speak>`", parse_mode="Markdown"
        )
        return
    text = " ".join(context.args)
    await send_tts(update, text)


async def voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reply to a message and use /voice to read that message aloud
    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text(
            "↩️ Reply to a text message with `/voice` to hear it."
        )
        return
    text = update.message.reply_to_message.text
    await send_tts(update, text)


async def send_tts(update: Update, text: str):
    msg = await update.message.reply_text("🔊 Generating audio...")
    try:
        def _make_tts():
            buf = BytesIO()
            gTTS(text=text, lang="en").write_to_fp(buf)
            buf.seek(0)
            buf.name = "speech.mp3"
            return buf

        audio = await asyncio.to_thread(_make_tts)
        await update.message.reply_voice(voice=audio)
        await msg.delete()
    except Exception as e:
        logger.exception("TTS failed")
        await msg.edit_text(f"❌ TTS error: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tts_corrected":
        corrected = context.user_data.get("last_corrected")
        if not corrected:
            await query.message.reply_text("⚠️ No corrected text available.")
            return
        try:
            def _make_tts():
                buf = BytesIO()
                gTTS(text=corrected, lang="en").write_to_fp(buf)
                buf.seek(0)
                buf.name = "corrected.mp3"
                return buf

            audio = await asyncio.to_thread(_make_tts)
            await query.message.reply_voice(voice=audio)
        except Exception as e:
            logger.exception("Callback TTS failed")
            await query.message.reply_text(f"❌ TTS error: {e}")


# ---------- Main ----------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("tts", tts_command))
    app.add_handler(CommandHandler("voice", voice_reply))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, correct_grammar))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
