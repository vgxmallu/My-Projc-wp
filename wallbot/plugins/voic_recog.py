import os
import re
import aiohttp
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

mongo = AsyncIOMotorClient(DB_URL)
db = mongo.voice_filter_bot

# =============== HELPER FUNCTIONS ===============
async def is_admin_or_creator(client: Client, chat_id: int, user_id: int) -> bool:
    """Checks if a user is an admin or creator in the chat."""
    try:
        member: ChatMember = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False # Failsafe
        
async def get_settings(chat_id: int):
    data = await db.settings.find_one({"chat_id": chat_id})
    if not data:
        data = {"chat_id": chat_id, "enabled": True}
        await db.settings.insert_one(data)
    return data

async def set_enabled(chat_id: int, state: bool):
    await db.settings.update_one({"chat_id": chat_id}, {"$set": {"enabled": state}}, upsert=True)

async def get_banned_words():
    doc = await db.banned_words.find_one({"_id": "words"})
    if not doc:
        words = ["badword1", "badword2", "offensive"]
        await db.banned_words.insert_one({"_id": "words", "words": words})
        return words
    return doc["words"]

async def transcribe_voice(file_path: str) -> str:
    """Transcribe audio using a free Whisper model on HuggingFace"""
    url = "https://api-inference.huggingface.co/models/openai/whisper-tiny"
    headers = {"Authorization": f"Bearer {os.getenv('HF_API', '')}"}
    with open(file_path, "rb") as f:
        data = f.read()

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=data) as resp:
            result = await resp.json()
            text = result.get("text", "")
            return text.strip()

async def contains_profanity(text: str) -> bool:
    words = await get_banned_words()
    pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))

# =============== ADMIN COMMANDS ===============

@app.on_message(filters.command("voicefilter") & filters.group)
async def voicefilter_settings(_, message: Message):
    chat_id = message.chat.id
    
    settings = await get_settings(chat_id)
    status = "🟢 Enabled" if settings["enabled"] else "🔴 Disabled"

    btns = [
        [
            InlineKeyboardButton("✅ Enable", callback_data=f"vf_enable_{chat_id}"),
            InlineKeyboardButton("🚫 Disable", callback_data=f"vf_disable_{chat_id}")
        ]
    ]

    await message.reply_text(
        f"🎙 **Voice Profanity Filter Settings**\n\n"
        f"Current status: {status}\n\n"
        f"Toggle below to enable or disable.",
        reply_markup=InlineKeyboardMarkup(btns)
    )

@app.on_callback_query(filters.regex(r"^vf_(enable|disable)_(\d+)$"))
async def toggle_voicefilter(_, query):
    action, chat_id = query.data.split("_")[1:]
    chat_id = int(chat_id)

    member = await app.get_chat_member(chat_id, query.from_user.id)
    if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
        return await query.answer("Only admins can do this.", show_alert=True)

    if action == "enable":
        await set_enabled(chat_id, True)
        await query.edit_message_text("✅ Voice filter enabled.")
    else:
        await set_enabled(chat_id, False)
        await query.edit_message_text("🚫 Voice filter disabled.")

# =============== VOICE HANDLER ===============

@app.on_message(filters.voice & filters.group)
async def handle_voice(_, message: Message):
    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    if not settings["enabled"]:
        return

    user = message.from_user
    file = await app.download_media(message.voice.file_id)

    try:
        text = await transcribe_voice(file)
        if not text:
            return await message.reply("⚠️ Couldn’t transcribe that voice note.")

        if await contains_profanity(text):
            await message.delete()
            await message.reply(f"🚫 {user.mention}, your voice message contained banned words!")
        else:
            await message.reply(f"🗣 Transcription:\n`{text}`")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    finally:
        os.remove(file)
