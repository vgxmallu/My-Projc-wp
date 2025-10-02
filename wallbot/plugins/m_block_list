import os
import re
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions, ChatMember
from pyrogram.enums import ChatMemberStatus
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app


# --- Database Setup ---
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client.blocklist_bot_db
chats_collection = db.chats

# --- Constants ---
# Available blocklist actions
BLOCKLIST_MODES = {
    "nothing": "Take no action",
    "ban": "Banned permanently",
    "mute": "Muted indefinitely",
    "kick": "Kicked (can rejoin)",
    "warn": "Sent a warning message",
}
DEFAULT_REASON = "You used a blocked word or phrase in this chat."

# --- Utility Functions ---

async def is_admin_or_creator(client: Client, chat_id: int, user_id: int) -> bool:
    """Checks if a user is an admin or creator in the chat."""
    try:
        member: ChatMember = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False # Failsafe

async def get_chat_settings(chat_id: int) -> dict:
    """Retrieves chat settings from the database, or returns defaults."""
    default_settings = {
        "blocklist_triggers": [], # List of blocked strings
        "blocklist_mode": "nothing",
        "blocklist_delete": True, # Always delete the blocklisted message for simplicity
    }
    settings = await chats_collection.find_one({"_id": chat_id})
    if settings is None:
        await chats_collection.insert_one({"_id": chat_id, **default_settings})
        return default_settings
    
    # Ensure backward compatibility if the field is missing
    if "blocklist_delete" not in settings:
        settings["blocklist_delete"] = True
    
    return settings


@app.on_message(filters.command("addblocklist") & filters.group)
async def add_blocklist_trigger(client: Client, message: Message):
    """/addblocklist <trigger>: Add a blocklist trigger."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    full_text = message.text or message.caption
    if not full_text:
        return await message.reply("📝 **Usage:** The command must contain a trigger.")

    parts = full_text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "📝 **Usage:** `/addblocklist <blocklist trigger>`\n"
            "Use quotes for multi-word triggers, e.g., `/addblocklist \"stupid question\"`"
        )
    
    # A regex to extract a quoted phrase OR the next non-space word
    match = re.match(r'^(?:"(.+?)"|(\S+))$', parts[1].strip())
    
    if not match:
        return await message.reply("❌ Could not parse the trigger. Ensure you use quotes for multi-word phrases or just the word itself.")

    trigger = (match.group(1) or match.group(2)).lower()
    
    if not trigger:
        return await message.reply("❌ The blocklist trigger cannot be empty.")

    # Add to database using $addToSet to prevent duplicates
    await chats_collection.update_one(
        {"_id": message.chat.id},
        {"$addToSet": {"blocklist_triggers": trigger}},
        upsert=True
    )
    
    await message.reply(f"✅ Blocklist trigger **`{trigger}`** has been added.")


@app.on_message(filters.command("rmblocklist") & filters.group)
async def remove_blocklist_trigger(client: Client, message: Message):
    """/rmblocklist <trigger>: Remove a blocklist trigger."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    full_text = message.text or message.caption
    if not full_text:
        return await message.reply("📝 **Usage:** The command must contain a trigger.")
        
    parts = full_text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("📝 **Usage:** `/rmblocklist <blocklist trigger>`")
        
    # Get the trigger (handles quotes for multi-word triggers)
    match = re.match(r'"(.+?)"|(\S+)', parts[1].strip())
    if not match:
        return await message.reply("❌ Could not parse the trigger.")
        
    trigger = (match.group(1) or match.group(2)).lower()

    settings = await get_chat_settings(message.chat.id)
    if trigger not in settings.get("blocklist_triggers", []):
        return await message.reply(f"❌ Blocklist trigger **`{trigger}`** not found.")

    # Update database to pull (remove) the item from the array
    await chats_collection.update_one(
        {"_id": message.chat.id},
        {"$pull": {"blocklist_triggers": trigger}}
    )
    
    await message.reply(f"✅ Blocklist trigger **`{trigger}`** has been removed.")


@app.on_message(filters.command("unblocklistall") & filters.group)
async def unblocklist_all(client: Client, message: Message):
    """/unblocklistall: Remove all blocklist triggers - chat creator only."""
    try:
        member: ChatMember = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status != ChatMemberStatus.OWNER:
            return await message.reply("❌ **Access Denied.** This command is for the **chat creator** only.")
    except Exception:
        return await message.reply("❌ Could not determine your status in the chat.")

    await chats_collection.update_one(
        {"_id": message.chat.id},
        {"$set": {"blocklist_triggers": []}}
    )
    
    await message.reply("✅ All blocklist triggers have been removed!")


@app.on_message(filters.command("blocklist") & filters.group)
async def list_blocklists(client: Client, message: Message):
    """/blocklist: List all blocklisted items."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    settings = await get_chat_settings(message.chat.id)
    triggers = settings.get("blocklist_triggers", [])

    if not triggers:
        return await message.reply("✅ The blocklist is currently empty.")

    blocklist_text = "📝 **Current Blocklist Triggers:**\n"
    for i, trigger in enumerate(sorted(triggers), 1):
        blocklist_text += f"{i}. `{trigger}`\n"

    await message.reply(blocklist_text)


@app.on_message(filters.command("blocklistmode") & filters.group)
async def set_blocklist_mode(client: Client, message: Message):
    """/blocklistmode <mode>: Set the desired action."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    full_text = message.text or message.caption
    if not full_text:
        modes_list = ", ".join(BLOCKLIST_MODES.keys())
        return await message.reply(
            "📝 **Usage:** `/blocklistmode <mode>`\n"
            f"Available modes: `{modes_list}`"
        )

    text = full_text.split(maxsplit=1)
    if len(text) < 2:
        modes_list = ", ".join(BLOCKLIST_MODES.keys())
        return await message.reply(
            "📝 **Usage:** `/blocklistmode <mode>`\n"
            f"Available modes: `{modes_list}`"
        )

    mode = text[1].strip().lower()
    if mode not in BLOCKLIST_MODES:
        modes_list = ", ".join(BLOCKLIST_MODES.keys())
        return await message.reply(
            f"❌ Invalid mode. Available: `{modes_list}`"
        )
    
    await chats_collection.update_one(
        {"_id": message.chat.id},
        {"$set": {"blocklist_mode": mode}}
    )

    action_display = BLOCKLIST_MODES[mode]
    await message.reply(f"✅ Blocklist action set to **`{mode}`** ({action_display}).")

# ----------------------------------------------------
# --- Blocklist Message Handler ---
# ----------------------------------------------------

@app.on_message(filters.group)
async def blocklist_checker(client: Client, message: Message):
    """Checks incoming messages (text or caption) against the chat's blocklist."""
    
    # Get text from either message or caption
    message_content = message.text or message.caption
    if not message_content:
        return # Ignore messages without text/caption

    # Skip messages from admins or the bot itself
    if await is_admin_or_creator(client, message.chat.id, message.from_user.id) or message.from_user.is_bot:
        return

    settings = await get_chat_settings(message.chat.id)
    triggers = settings.get("blocklist_triggers", [])
    
    if not triggers:
        return

    # Check for trigger matches
    message_text_lower = message_content.lower()
    matched_trigger = None
    
    for trigger in triggers:
        # Check if the trigger is a substring of the message content.
        if trigger in message_text_lower:
            matched_trigger = trigger
            break
            
    if not matched_trigger:
        return # No match found

    # 1. Delete Message
    if settings.get("blocklist_delete", True): # Default to True
        try:
            await message.delete()
        except Exception:
            # Bot might not have permission to delete
            pass

    # 2. Determine and apply the action
    mode = settings["blocklist_mode"]
    reason = DEFAULT_REASON 
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        action_msg = f"⚠️ **Blocklist Triggered!**\nUser: {message.from_user.mention}\nTrigger: `{matched_trigger}`\nAction: **{BLOCKLIST_MODES[mode]}**\nReason: {reason}"
        
        # Action based on mode
        if mode == "ban":
            await client.ban_chat_member(chat_id, user_id)
        elif mode == "mute":
            # Mute indefinitely (until 2038)
            await client.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False, can_send_media_messages=False))
        elif mode == "kick":
            # Kick and then unban immediately so they can rejoin
            await client.ban_chat_member(chat_id, user_id)
            await client.unban_chat_member(chat_id, user_id)
        elif mode == "warn":
            # Action message is sent below
            pass
        else: # "nothing"
            return # Do nothing
            
        # Send the action message
        await client.send_message(chat_id, action_msg)
        
    except Exception as e:
        # Failsafe message if action couldn't be performed
        await client.send_message(
            chat_id, 
            f"❌ **Error applying blocklist action (`{mode}`).**\n"
            f"The bot might lack necessary permissions (e.g., Ban Users) to punish {message.from_user.mention}."
        )
