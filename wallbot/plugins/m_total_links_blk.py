import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired

mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["management_bot"]
settings_col = db["total_links_block"]
warns_col = db["user_warns"]


# ------------------- HELPERS -------------------


#onlyfor admin
async def is_admin_with_permission(client: Client, chat_id: int, user_id: int, permission: str):
    """Check if a user is an admin with a specific permission."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            if permission == 'can_restrict_members':
                return member.privileges and member.privileges.can_restrict_members
        return False
    except UserNotParticipant:
        return False

async def get_settings(chat_id: int) -> dict:
    settings = await settings_col.find_one({"chat_id": chat_id})
    if not settings:
        settings = {"chat_id": chat_id, "enabled": False, "punishment": "warn"}
        await settings_col.insert_one(settings)
    return settings

async def update_settings(chat_id: int, data: dict):
    await settings_col.update_one({"chat_id": chat_id}, {"$set": data}, upsert=True)

async def apply_punishment(message: Message, punishment: str):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if punishment == "warn":
        user_warns = await warns_col.find_one({"chat_id": chat_id, "user_id": user_id}) or {"warns": 0}
        warns = user_warns.get("warns", 0) + 1
        await warns_col.update_one({"chat_id": chat_id, "user_id": user_id}, {"$set": {"warns": warns}}, upsert=True)
        await message.reply_text(f"⚠️ {message.from_user.mention} warned! Total warns: {warns}")

    elif punishment == "kick":
        try:
            await app.kick_chat_member(chat_id, user_id)
            await asyncio.sleep(1)
            await app.unban_chat_member(chat_id, user_id)
            await message.reply_text(f"👢 {message.from_user.mention} was kicked for sending a link.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to kick: {e}")

    elif punishment == "ban":
        try:
            await app.kick_chat_member(chat_id, user_id)
            await message.reply_text(f"🚫 {message.from_user.mention} was banned for sending a link.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to ban: {e}")

    elif punishment == "mute":
        try:
            await app.restrict_chat_member(chat_id, user_id, permissions={})
            await message.reply_text(f"🔇 {message.from_user.mention} was muted for sending a link.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to mute: {e}")

# ------------------- COMMAND HANDLER -------------------

@app.on_message(filters.command("total_links_block") & filters.group)
async def total_links_block_cmd(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
      
    settings = await get_settings(message.chat.id)
    status = "✅ Enabled" if settings["enabled"] else "❌ Disabled"
    punishment = settings["punishment"].capitalize()

    buttons = [
        [InlineKeyboardButton(f"Status: {status}", callback_data=f"tlb_toggle_{int(not settings['enabled'])}")],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data="tlb_set_warn"),
            InlineKeyboardButton("👢 Kick", callback_data="tlb_set_kick"),
        ],
        [
            InlineKeyboardButton("🚫 Ban", callback_data="tlb_set_ban"),
            InlineKeyboardButton("🔇 Mute", callback_data="tlb_set_mute"),
        ]
    ]

    await message.reply_text(
        f"🔧 **Total Links Block Settings**\n\nStatus: {status}\nPunishment: {punishment}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"tlb_"))
async def callback_handler(client, callback_query):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        return await callback_query.answer("❌ Only admins can change this.", show_alert=True)

    data = callback_query.data

    if data.startswith("tlb_toggle_"):
        enabled = bool(int(data.split("_")[2]))
        await update_settings(chat_id, {"enabled": enabled})
        await callback_query.answer("✅ Updated!")
        await total_links_block_cmd(client, callback_query.message)

    elif data.startswith("tlb_set_"):
        punishment = data.split("_")[2]
        await update_settings(chat_id, {"punishment": punishment})
        await callback_query.answer(f"✅ Punishment set to {punishment.capitalize()}")
        await total_links_block_cmd(client, callback_query.message)

# ------------------- LINK DETECTION -------------------

LINK_REGEX = re.compile(r"(https?://\S+|t\.me/\S+|@\w+)", re.IGNORECASE)

@app.on_message(filters.group, group=6)
async def detect_links(client, message: Message):
    if not message.from_user or message.sender_chat:
        return

    settings = await get_settings(message.chat.id)
    if not settings["enabled"]:
        return

    text = message.text or message.caption or ""
    if LINK_REGEX.search(text):
        await apply_punishment(message, settings["punishment"])
        try:
            await message.delete()
        except:
            pass

