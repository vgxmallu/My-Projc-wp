import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio
from config import DB_URL
from wallbot import wbot as app


# ─── INIT ─────────────────────────────
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo_client["link_guardian_db"]
settings_col = db["settings"]

# ─── HELPERS ──────────────────────────
async def get_settings(chat_id: int):
    settings = await settings_col.find_one({"chat_id": chat_id})
    if not settings:
        settings = {"chat_id": chat_id, "enabled": False, "punishment": "warn"}
        await settings_col.insert_one(settings)
    return settings

async def update_settings(chat_id: int, data: dict):
    await settings_col.update_one({"chat_id": chat_id}, {"$set": data}, upsert=True)

# ─── LINK FILTER (Regex) ──────────────
@app.on_message(
    filters.group 
    & filters.regex(r"(t\.me/|telegram\.me/|@[\w\d_]{3,32})") 
    & ~filters.bot
)
async def link_detector(client, message):
    settings = await get_settings(message.chat.id)
    if not settings["enabled"]:
        return

    punishment = settings["punishment"]

    if punishment == "warn":
        await message.reply_text(f"⚠️ {message.from_user.mention}, Telegram links are not allowed!")
    elif punishment == "kick":
        try:
            await message.chat.kick_member(message.from_user.id)
            await message.reply_text(f"👢 {message.from_user.mention} was kicked for sending Telegram links!")
        except Exception as e:
            await message.reply_text(f"❌ Failed to kick: {e}")
    elif punishment == "ban":
        try:
            await message.chat.ban_member(message.from_user.id)
            await message.reply_text(f"🔨 {message.from_user.mention} was banned for sending Telegram links!")
        except Exception as e:
            await message.reply_text(f"❌ Failed to ban: {e}")

# ─── COMMAND: SETTINGS ─────────────────
@app.on_message(filters.command("linkfilter") & filters.group)
async def link_shettings(client, message):
    settings = await get_settings(message.chat.id)

    buttons = [
        [
            InlineKeyboardButton(
                f"Module: {'✅ ON' if settings['enabled'] else '❌ OFF'}",
                callback_data=f"toggle_{message.chat.id}"
            )
        ],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data=f"set_warn_{message.chat.id}"),
            InlineKeyboardButton("👢 Kick", callback_data=f"set_kick_{message.chat.id}"),
            InlineKeyboardButton("🔨 Ban", callback_data=f"set_ban_{message.chat.id}")
        ]
    ]

    await message.reply_text(
        "⚙️ **Link Filter Settings**\n\n"
        f"Status: {'✅ Enabled' if settings['enabled'] else '❌ Disabled'}\n"
        f"Punishment: **{settings['punishment'].capitalize()}**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ─── CALLBACK HANDLER ──────────────────
@app.on_callback_query(filters.regex(r"^(toggle|set_warn|set_kick|set_ban)"))
async def cb_handler(client, query):
    data = query.data.split("_")
    action = data[0]
    chat_id = int(data[-1])

    if action == "toggle":
        settings = await get_settings(chat_id)
        new_status = not settings["enabled"]
        await update_settings(chat_id, {"enabled": new_status})
        await query.answer(f"Module {'Enabled ✅' if new_status else 'Disabled ❌'}")
    elif action.startswith("set_"):
        punishment = action.split("set_")[1]
        await update_settings(chat_id, {"punishment": punishment})
        await query.answer(f"Punishment set to {punishment.capitalize()} ✅")

    # Refresh settings menu
    new_settings = await get_settings(chat_id)
    buttons = [
        [
            InlineKeyboardButton(
                f"Module: {'✅ ON' if new_settings['enabled'] else '❌ OFF'}",
                callback_data=f"toggle_{chat_id}"
            )
        ],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data=f"set_warn_{chat_id}"),
            InlineKeyboardButton("👢 Kick", callback_data=f"set_kick_{chat_id}"),
            InlineKeyboardButton("🔨 Ban", callback_data=f"set_ban_{chat_id}")
        ]
    ]
    await query.edit_message_text(
        "⚙️ **Link Filter Settings**\n\n"
        f"Status: {'✅ Enabled' if new_settings['enabled'] else '❌ Disabled'}\n"
        f"Punishment: **{new_settings['punishment'].capitalize()}**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
