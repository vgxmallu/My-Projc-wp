import os
import re
import logging
import time
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, ChatPermissions
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import DB_URL
from wallbot import wbot as app


mongo_client = MongoClient(DB_URL)
db = mongo_client.LinkManagerBot
settings_collection = db.group_settings
    


# A simple in-memory cache to track which admin is setting what.
# Format: {(chat_id, user_id): "action"} e.g., "awaiting_mute_duration"
admin_actions = {}

# --- Helper Functions ---

def get_default_settings():
    """Returns a dictionary with default settings for a group."""
    return {
        "enabled": False,
        "punishment_type": "warn",
        "mute_duration": 300,  # 5 minutes in seconds
        "warn_message": "❗️ **Warning:** Sending Telegram links is not allowed in this group."
    }

async def get_group_settings(chat_id: int):
    """
    Retrieves settings for a specific group from MongoDB.
    If no settings exist, it creates and returns the default settings.
    """
    settings = settings_collection.find_one({"_id": chat_id})
    if not settings:
        default_settings = get_default_settings()
        # The _id field must be added manually when using a default dict.
        default_settings["_id"] = chat_id
        settings_collection.insert_one(default_settings)
        return default_settings
    return settings

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

# --- Main Command Handler ---

@app.on_message(filters.command("bloklink") & filters.group)
async def bloklink_command(client: Client, message: Message):
    """Main command for admins to open the settings menu."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return

    settings = await get_group_settings(chat_id)
    await send_settings_menu(message, settings)


async def send_settings_menu(message_or_query, settings: dict):
    """Sends or edits the settings menu message."""
    status_text = "Enabled ✅" if settings['enabled'] else "Disabled ❌"
    punishment_text = settings['punishment_type'].capitalize()
    if settings['punishment_type'] == 'mute':
        duration = timedelta(seconds=settings['mute_duration'])
        punishment_text += f" ({str(duration)})"

    text = (
        "**🔗 Telegram Link Blocker Settings**\n\n"
        "Here you can configure the punishment for users who send Telegram links (`t.me/...`).\n\n"
        f"**Status:** `{status_text}`\n"
        f"**Current Punishment:** `{punishment_text}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Toggle ({'Disable' if settings['enabled'] else 'Enable'})", callback_data="toggle_status")
        ],
        [
            InlineKeyboardButton("🔧 Set Punishment", callback_data="set_punishment_menu")
        ],
        [
            InlineKeyboardButton("Close Menu", callback_data="close_menu")
        ]
    ])
    
    # Check if we should edit an existing message or send a new one.
    if isinstance(message_or_query, CallbackQuery):
        try:
            await message_or_query.message.edit_text(text, reply_markup=keyboard)
        except: # Message not modified, etc.
            pass
    else: # It's a Message object
        await message_or_query.reply_text(text, reply_markup=keyboard)

# --- Callback Query Handlers ---

@app.on_callback_query(filters.regex(r"^(toggle_status|set_punishment_menu|main_menu|close_menu)$"))
async def main_menu_hcallbacks(client: Client, query: CallbackQuery):
    """Handles callbacks from the main settings menu."""
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await query.answer("You are not authorized to do this.", show_alert=True)
        return

    action = query.data
    settings = await get_group_settings(chat_id)

    if action == "toggle_status":
        settings['enabled'] = not settings['enabled']
        settings_collection.update_one({"_id": chat_id}, {"$set": {"enabled": settings['enabled']}})
        await query.answer(f"Link Blocker {'Enabled' if settings['enabled'] else 'Disabled'}")
        await send_settings_menu(query, settings)

    elif action == "set_punishment_menu":
        await send_punishment_menu(query)

    elif action == "main_menu":
        await send_settings_menu(query, settings)

    elif action == "close_menu":
        await query.message.delete()


async def send_punishment_menu(query: CallbackQuery):
    """Displays the punishment selection menu."""
    text = "**🔧 Set Punishment Type**\n\nSelect the action to perform when a user sends a Telegram link."
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Warn", callback_data="set_punish_warn"),
            InlineKeyboardButton("🔇 Mute", callback_data="set_punish_mute")
        ],
        [
            InlineKeyboardButton("👢 Kick", callback_data="set_punish_kick"),
            InlineKeyboardButton("🚫 Ban", callback_data="set_punish_ban")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")
        ]
    ])
    await query.message.edit_text(text, reply_markup=keyboard)


@app.on_callback_query(filters.regex(r"^set_punish_"))
async def set_punishmehnt_callbacks(client: Client, query: CallbackQuery):
    """Handles punishment type selection."""
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await query.answer("You are not authorized to do this.", show_alert=True)
        return
    
    punishment_type = query.data.split("_")[-1]
    
    if punishment_type == "mute":
        admin_actions[(chat_id, user_id)] = "awaiting_mute_duration"
        await query.message.edit_text(
            "**⏳ Set Mute Duration**\n\nReply to this message with the mute duration in minutes (e.g., `5` for 5 minutes)."
        )
        return

    # For other punishments, update directly.
    settings_collection.update_one({"_id": chat_id}, {"$set": {"punishment_type": punishment_type}})
    await query.answer(f"Punishment set to: {punishment_type.capitalize()}")
    settings = await get_group_settings(chat_id)
    await send_settings_menu(query, settings)


# --- Message Handler for Admin Replies ---

@app.on_message(filters.group & filters.reply)
async def handle_admin_repjlies(client: Client, message: Message):
    """Handles admin replies for setting mute duration etc."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    action_key = (chat_id, user_id)
    
    if action_key in admin_actions and admin_actions[action_key] == "awaiting_mute_duration":
        # Check if the replied-to message is from our bot and has the correct prompt
        if not (message.reply_to_message and message.reply_to_message.from_user.is_self and "Set Mute Duration" in message.reply_to_message.text):
            return

        try:
            duration_minutes = int(message.text.strip())
            if duration_minutes <= 0:
                await message.reply_text("Please enter a positive number for the duration.")
                return
            
            duration_seconds = duration_minutes * 60
            settings_collection.update_one(
                {"_id": chat_id},
                {"$set": {"punishment_type": "mute", "mute_duration": duration_seconds}}
            )
            
            # Delete the original prompt message from the bot
            await message.reply_to_message.delete()
            
            # Delete the admin's reply message
            await message.delete()

            # Inform about the update and show a fresh menu
            settings = await get_group_settings(chat_id)
            # Use the admin's reply message as a reference to send the new menu.
            await send_settings_menu(message, settings)
            
            # Cleanup
            del admin_actions[action_key]

        except ValueError:
            await message.reply_text("Invalid input. Please reply with a number (e.g., `10`).")
        except Exception as e:
            LOGGER.error(f"Error handling admin reply: {e}")
            await message.reply_text("An error occurred. Please try again.")
            if action_key in admin_actions:
                del admin_actions[action_key]


# --- Link Detection and Punishment Handler ---

TELEGRAM_LINK_REGEX = re.compile(
    r'(https?|ftp):\/\/[^\s\/$.?#].[^\s]*|' # Full URLs
    r'([a-zA-Z0-9-]+\.([a-zA-Z]{2,})(\/\S*)?)\b|' # Domain names
    r'(@[a-zA-Z0-9_]|telegram\.me)'
    r'(t\.me|telegra\.ph)\/[^\s]+', # Telegram specific links
    re.IGNORECASE
)

@app.on_message(filters.regex(TELEGRAM_LINK_REGEX) & filters.group, group=2)
async def link_blocjker_handler(client: Client, message: Message):
    """This handler now only triggers for messages containing a Telegram link."""
    chat_id = message.chat.id
    # message.from_user can be None for anonymous admins or channel posts.
    if not message.from_user:
        return
        
    user_id = message.from_user.id
    
    settings = await get_group_settings(chat_id)

    # If module is disabled, do nothing.
    if not settings['enabled']:
        return

    # Check if user is an admin; admins are immune.
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return
    except UserNotParticipant:
        # User is not in the chat (e.g., linked channel), proceed to punish.
        pass
    except Exception as e:
        LOGGER.error(f"Could not get chat member {user_id} in {chat_id}: {e}")
        return # Avoid accidental punishment if Telegram API fails.

    # --- If we reach here, a non-admin sent a link and the module is on ---
    
    try:
        await message.delete()
    except Exception as e:
        LOGGER.warning(f"Could not delete message in {chat_id}: {e}")
    
    # Apply the configured punishment
    punishment = settings['punishment_type']
    
    try:
        if punishment == "warn":
            await client.send_message(chat_id, f"{message.from_user.mention} {settings['warn_message']}")
        
        elif punishment == "mute":
            # Pyrogram uses `datetime` objects for timed restrictions now.
            until_date = datetime.now() + timedelta(seconds=settings['mute_duration'])
            await client.restrict_chat_member(
                chat_id, user_id, 
                permissions=ChatPermissions(), 
                until_date=until_date
            )
            duration_str = str(timedelta(seconds=settings['mute_duration']))
            await client.send_message(chat_id, f"🔇 {message.from_user.mention} has been muted for {duration_str} for sending a link.")

        elif punishment == "kick":
            await client.ban_chat_member(chat_id, user_id)
            await client.unban_chat_member(chat_id, user_id) # Unban immediately to just kick
            await client.send_message(chat_id, f"👢 {message.from_user.mention} has been kicked for sending a link.")

        elif punishment == "ban":
            await client.ban_chat_member(chat_id, user_id)
            await client.send_message(chat_id, f"🚫 {message.from_user.mention} has been permanently banned for sending a link.")

    except ChatAdminRequired:
        LOGGER.error(f"Cannot apply punishment in {chat_id}. Bot is not an admin or lacks permissions.")
    except Exception as e:
        LOGGER.error(f"Failed to apply punishment in {chat_id} for user {user_id}: {e}")


