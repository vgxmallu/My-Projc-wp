import os
import asyncio
import pypandoc
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from wallbot import wbot as app
# ========== CONFIG ==========


# ========== HELPER FUNCTIONS ==========
async def convert_file(input_path: str, output_format: str) -> str:
    """Convert file to desired format."""
    base, _ = os.path.splitext(input_path)
    output_path = f"{base}_converted.{output_format}"
    try:
        pypandoc.convert_file(input_path, output_format, outputfile=output_path, extra_args=['--standalone'])
        return output_path
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return None


# ========== COMMAND HANDLERS ==========
#@app.on_message(filters.command("start"))
async def stdhart(_, message: Message):
    await message.reply_text(
        "👋 **Welcome to File Converter Bot!**\n\n"
        "Just send a file (PDF, DOCX, TXT, MD) and I’ll help you convert it.\n\n"
        "📂 *Steps:*\n"
        "1️⃣ Send me a file.\n"
        "2️⃣ Choose a format using buttons.\n"
        "3️⃣ I’ll send back your converted file!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Supported Formats", callback_data="help_formats")]
        ])
    )


#@app.on_callback_query(filters.regex("^help_formats$"))
async def help_forumats(_, query: CallbackQuery):
    await query.message.edit_text(
        "🧾 **Supported Formats:**\n"
        "- PDF (`.pdf`)\n"
        "- DOCX (`.docx`)\n"
        "- TXT (`.txt`)\n"
        "- Markdown (`.md`)\n\n"
        "Just send a file, and I’ll show conversion options automatically!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="back_home")]
        ])
    )


@app.on_callback_query(filters.regex("^back_home$"))
async def back_gdhome(_, query: CallbackQuery):
    await start(_, query.message)


# ========== DOCUMENT HANDLER ==========
@app.on_message(filters.document)
async def handle_document(_, message: Message):
    file_name = message.document.file_name
    file_ext = os.path.splitext(file_name)[-1].lower()

    # Supported file types
    supported = [".pdf", ".docx", ".txt", ".md"]
    if file_ext not in supported:
        await message.reply_text("⚠️ Unsupported file type! Only PDF, DOCX, TXT, and MD are supported.")
        return

    buttons = [
        [
            InlineKeyboardButton("📄 To PDF", callback_data=f"convert|pdf|{message.document.file_id}"),
            InlineKeyboardButton("📝 To DOCX", callback_data=f"convert|docx|{message.document.file_id}")
        ],
        [
            InlineKeyboardButton("📃 To TXT", callback_data=f"convert|plain|{message.document.file_id}"),
            InlineKeyboardButton("📔 To Markdown", callback_data=f"convert|markdown|{message.document.file_id}")
        ]
    ]

    await message.reply_text(
        f"📁 **File:** `{file_name}`\n\nSelect the format you want to convert it to 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ========== CALLBACK HANDLER ==========
@app.on_callback_query(filters.regex(r"^convert\|"))
async def convert_callback(_, query: CallbackQuery):
    data = query.data.split("|")
    output_format = data[1]
    file_id = data[2]

    # Download file
    msg = await query.message.reply_text("⏳ Downloading and converting file... please wait.")
    file_path = await app.download_media(file_id)

    output_path = await convert_file(file_path, output_format)

    if not output_path:
        await msg.edit_text("❌ Conversion failed. Try again later.")
        os.remove(file_path)
        return

    await msg.edit_text("✅ Conversion complete! Uploading file...")
    await app.send_document(query.message.chat.id, output_path, caption=f"Converted to `{output_format.upper()}` ✅")

    # Cleanup
    os.remove(file_path)
    os.remove(output_path)
    await msg.delete()

