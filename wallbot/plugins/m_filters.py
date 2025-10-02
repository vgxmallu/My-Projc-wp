import os
import re
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember
from pyrogram.enums import ChatMemberStatus
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

# --- Database Setup ---
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client.filters_bot_db
filters_collection = db.filters
    

# --- Utility Functions ---

async def is_admin_or_creator(client: Client, chat_id: int, user_id: int) -> bool:
    """Checks if a user is an admin or creator in the chat."""
    if user_id == client.me.id: 
        return True
    try:
        member: ChatMember = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False 

async def get_chat_filters(chat_id: int) -> dict:
    """Retrieves all active filters for a given chat from MongoDB."""
    # The 'filters' field stores a dictionary of {trigger: reply}
    settings = await filters_collection.find_one({"_id": chat_id})
    return settings.get("filters", {}) if settings else {}


@app.on_message(filters.command("filter") & filters.group)
async def add_filter(client: Client, message: Message):
    """
    /filter <trigger> <reply>
    Adds a new chat filter. Use quotes for multi-word triggers.
    """
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    # Extract the text after the command
    full_text = (message.text or message.caption).split(maxsplit=1)[-1]
    
    # Regex to extract: 1. Quoted Trigger OR 2. Single-Word Trigger, followed by 3. Reply
    match = re.match(r'^(?:"(.+?)"|(\S+))\s+(.+)$', full_text.split(maxsplit=1)[-1].strip())

    if not match:
        return await message.reply(
            "📝 **Usage:** `/filter <trigger> <reply>`\n"
            "Use quotes for multi-word triggers, e.g., `/filter \"hi bot\" Hello there!`"
        )
    
    # The trigger is captured in group 1 (if quoted) or group 2 (if single word)
    trigger = (match.group(1) or match.group(2)).lower().strip()
    reply = match.group(3).strip()

    if not trigger or not reply:
        return await message.reply("❌ Both a trigger and a reply sentence are required.")
    
    # We use $set with dot notation to set a key in the nested 'filters' map
    await filters_collection.update_one(
        {"_id": message.chat.id},
        {"$set": {f"filters.{trigger}": reply}}, 
        upsert=True # Creates the document if it doesn't exist
    )
    
    await message.reply(f"✅ Filter **`{trigger}`** added/updated successfully.")


@app.on_message(filters.command("filters") & filters.group)
async def list_filters(client: Client, message: Message):
    """/filters: List all chat filters."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    filters_data = await get_chat_filters(message.chat.id)
    
    if not filters_data:
        return await message.reply("✅ No filters are currently set in this chat.")

    filters_text = "📝 **Current Chat Filters:**\n\n"
    
    for trigger, reply in sorted(filters_data.items()):
        # Truncate reply for a cleaner list view
        truncated_reply = reply[:50] + "..." if len(reply) > 50 else reply
        filters_text += f"➡️ **`{trigger}`**\n    `{truncated_reply}`\n"

    await message.reply(filters_text)


@app.on_message(filters.command("stop") & filters.group)
async def remove_filter(client: Client, message: Message):
    """/stop <trigger>: Stop the bot from replying to a trigger."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    full_text = (message.text or message.caption).split(maxsplit=1)[-1]
    
    # Regex to extract the trigger
    match = re.match(r'^(?:"(.+?)"|(\S+))$', full_text.split(maxsplit=1)[-1].strip())
    
    if not match:
        return await message.reply("📝 **Usage:** `/stop <trigger>`")
        
    trigger = (match.group(1) or match.group(2)).lower().strip()

    filters_data = await get_chat_filters(message.chat.id)
    if trigger not in filters_data:
        return await message.reply(f"❌ Filter **`{trigger}`** not found.")

    # Remove the filter using $unset on the nested map
    await filters_collection.update_one(
        {"_id": message.chat.id},
        {"$unset": {f"filters.{trigger}": ""}}
    )
    
    await message.reply(f"✅ Filter **`{trigger}`** has been stopped.")


@app.on_message(filters.command("stopall") & filters.group)
async def stop_all_filters(client: Client, message: Message):
    """/stopall: Stop ALL filters in the current chat - chat creator only."""
    try:
        member: ChatMember = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status != ChatMemberStatus.OWNER:
            return await message.reply("❌ **Access Denied.** This command is for the **chat creator** only.")
    except Exception:
        return await message.reply("❌ Could not determine your status in the chat.")

    # Overwrite the 'filters' field with an empty map to clear all
    await filters_collection.update_one(
        {"_id": message.chat.id},
        {"$set": {"filters": {}}}
    )
    
    await message.reply("⚠️ **All filters have been STOPPED** for this chat! This cannot be undone.")

# ----------------------------------------------------
# --- Core Message Handler ---
# ----------------------------------------------------

@app.on_message(filters.group)
async def filter_checker(client: Client, message: Message):
    """Checks for filter triggers in every non-edited message."""
    message_content = message.text or message.caption
    
    # Ignore if no content, or if the user is a bot
    if not message_content or message.from_user.is_bot:
        return

    # Admins' messages are ignored to prevent accidental bot-on-bot replies
    if await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return

    filters_data = await get_chat_filters(message.chat.id)
    if not filters_data:
        return

    message_text_lower = message_content.lower()
    
    # Check for trigger matches
    for trigger, reply in filters_data.items():
        # Case-insensitive check if the trigger is anywhere in the message
        if trigger in message_text_lower:
            # Reply to the user's message and stop processing
            return await message.reply(reply, quote=True)

