import asyncio
import re
import os
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message, ChatPermissions
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import timedelta
from config import DB_URL
from wallbot import wbot as app

MUTE_DURATION_MINUTES = 30 # Default duration for mute punishment

# --- MONGO DB SETUP ---
# Initialize Motor client for async MongoDB operations
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client.tlantispam_link_bot_db
settings_collection = db.link_settings  # Collection for group configurations
warnings_collection = db.link_warnings    # Collection for user warnings
    


# --- UTILITY FUNCTIONS FOR DATABASE (SETTINGS) ---

async def get_group_settings(chat_id):
    """Fetches group settings, defaulting to disabled link block and standard punishments."""
    default_settings = {
        "_id": chat_id,
        "link_block_enabled": False,
        # Punishment map: {warn_count: punishment_type (warn, mute, kick, ban)}
        "punishments": {
            1: "warn",
            3: "mute",
            5: "kick",
            7: "ban"
        }
    }
    settings = await settings_collection.find_one({"_id": chat_id})
    if settings:
        default_settings.update(settings)
    return default_settings

async def save_group_settings(chat_id: int, key: str, value):
    """Saves a specific key-value setting for a group."""
    await settings_collection.update_one(
        {"_id": chat_id},
        {"$set": {key: value}},
        upsert=True
    )

# --- UTILITY FUNCTIONS FOR DATABASE (WARNINGS) ---

async def get_warnings(chat_id: int, user_id: int) -> int:
    """Gets the current warning count for a user in a specific chat."""
    warning_doc = await warnings_collection.find_one({
        "chat_id": chat_id,
        "user_id": user_id
    })
    return warning_doc.get("count", 0) if warning_doc else 0

async def add_warning(chat_id: int, user_id: int) -> int:
    """Increments a user's warning count and returns the new count."""
    result = await warnings_collection.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True
    )
    return result["count"]

async def reset_warnings(chat_id: int, user_id: int):
    """Resets a user's warning count to zero."""
    await warnings_collection.delete_one({
        "chat_id": chat_id,
        "user_id": user_id
    })
    print(f"Warnings reset for user {user_id} in chat {chat_id}")

# Helper function to find the next punishment level
def next_punishment_level(punishments: dict, current_warnings: int) -> int:
    """Finds the next warning count that triggers a punishment."""
    punishment_counts = [int(k) for k in punishments.keys()]
    punishment_counts.sort()
    for count in punishment_counts:
        if count > current_warnings:
            return count
    return max(punishment_counts) if punishment_counts else 1


# --- CUSTOM DECORATOR FOR ADMIN CHECK ---

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
# --- COMMAND HANDLERS (ADMIN ONLY) ---

@app.on_message(filters.command("linkblock") & filters.group)
async def toggle_link_block(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    """Enables or disables the total link block module."""
    if len(message.command) != 2:
        return await message.reply("Usage: `/linkblock [enable|disable]`")

    action = message.command[1].lower()
    chat_id = message.chat.id

    if action == "enable":
        await save_group_settings(chat_id, "link_block_enabled", True)
        await message.reply("✅ **Total Link Block ENABLED.** All forms of links will now be deleted and users penalized.")
    elif action == "disable":
        await save_group_settings(chat_id, "link_block_enabled", False)
        await message.reply("❌ **Total Link Block DISABLED.**")
    else:
        await message.reply("Invalid action. Use `enable` or `disable`.")

@app.on_message(filters.command("setlinkpunishment") & filters.group)
async def set_punishment(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    """Sets a custom punishment for a specific warning count."""
    if len(message.command) != 3:
        return await message.reply("Usage: `/setlinkpunishment [warns] [punishment]`\n\n**Punishments:** `warn`, `mute`, `kick`, `ban`\n**Example:** `/setlinkpunishment 4 mute` (Mutes user on 4th warning)")

    try:
        warn_count = int(message.command[1])
        punishment = message.command[2].lower()
    except ValueError:
        return await message.reply("Invalid warning count. It must be a number.")

    if punishment not in ["warn", "mute", "kick", "ban"]:
        return await message.reply("Invalid punishment type. Choose from `warn`, `mute`, `kick`, or `ban`.")

    chat_id = message.chat.id
    settings = await get_group_settings(chat_id)
    settings["punishments"][str(warn_count)] = punishment

    await save_group_settings(chat_id, "punishments", settings["punishments"])
    await message.reply(f"🔧 **Punishment Updated:** A user will now be **{punishment.upper()}** after **{warn_count}** warnings for sending links.")

@app.on_message(filters.command("getlinkpunishments") & filters.group)
async def get_punishments(client, message: Message):
    """Displays the current link block configuration."""
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    settings = await get_group_settings(chat_id)

    status = "✅ ENABLED" if settings["link_block_enabled"] else "❌ DISABLED"
    punishments = settings["punishments"]

    response = f"**Current Total Link Block Settings for {message.chat.title}**\n"
    response += f"**Status:** {status}\n\n"
    response += "**Punishment Thresholds:**\n"

    # Sort punishments by warning count for clean display
    sorted_punishments = sorted(punishments.items(), key=lambda item: int(item[0]))

    for count, action in sorted_punishments:
        if action == "warn":
            response += f"  - On **{count}** warnings: ⚠️ WARN\n"
        elif action == "mute":
            response += f"  - On **{count}** warnings: 🔇 MUTE for {MUTE_DURATION_MINUTES} minutes\n"
        elif action == "kick":
            response += f"  - On **{count}** warnings: 👢 KICK\n"
        elif action == "ban":
            response += f"  - On **{count}** warnings: 🚫 BAN\n"

    await message.reply(response)

# --- CORE ANTISPAM LOGIC (MESSAGE HANDLER) ---

# Comprehensive Regex to detect various link patterns:
# 1. http(s)://...
# 2. common domain formats (domain.tld)
# 3. t.me/ or t.me/... (Telegram links)
# 4. telegraph.ph/...
# 5. [Text](http...) markdown links
LINK_REGEX = re.compile(
    r'(https?|ftp):\/\/[^\s\/$.?#].[^\s]*|' # Full URLs
    r'([a-zA-Z0-9-]+\.([a-zA-Z]{2,})(\/\S*)?)\b|' # Domain names
    r'(t\.me|telegra\.ph)\/[^\s]+', # Telegram specific links
    re.IGNORECASE
)

@app.on_message(filters.group & filters.incoming)
async def check_total_link_spam(client, message: Message):
    """Handles messages and applies link blocking logic if enabled."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    # 1. Skip if the sender is an admin or the chat creator
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except Exception:
        pass

    # 2. Load group settings and check if the module is enabled
    settings = await get_group_settings(chat_id)
    if not settings["link_block_enabled"]:
        return

    # 3. Check for links in the message text
    match = LINK_REGEX.search(text)

    # Also check for links embedded in media captions, documents, etc.
    if not match and message.entities:
        for entity in message.entities:
            # Check for URL entity type (which Pyrogram detects for links)
            if entity.type.name in ["URL", "TEXT_LINK"]:
                match = True
                break

    if not match:
        return

    # 4. Execute Punishment Cycle
    try:
        # Delete the spam message immediately
        await message.delete()
    except Exception as e:
        print(f"Failed to delete link message from {user_id}: {e}")

    current_warnings = await get_warnings(chat_id, user_id)
    new_warnings = await add_warning(chat_id, user_id)

    # Find the punishment defined for the new warning count
    punishments = settings["punishments"]
    action_to_take = punishments.get(str(new_warnings), "warn") # Default to warn

    user_mention = message.from_user.mention
    punishment_message = (
        f"**🔗 Link Spam Detected!**\n\n"
        f"**User:** {user_mention}\n"
        f"**Reason:** Sending unapproved links.\n"
        f"**Warnings:** {new_warnings}"
    )

    # 5. Apply the determined action
    try:
        if action_to_take == "warn":
            next_level = next_punishment_level(punishments, new_warnings)
            await client.send_message(
                chat_id,
                f"{punishment_message}\n**Action:** ⚠️ **WARNED**\n_Next action ({punishments.get(str(next_level), 'N/A').upper()}) at warning count {next_level}._"
            )

        elif action_to_take == "mute":
            # Restrict permissions for the defined duration
            mute_until = int((message.date + timedelta(minutes=MUTE_DURATION_MINUTES)).timestamp())
            await client.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(), # Empty permissions means user can't send anything
                until_date=mute_until
            )
            await client.send_message(
                chat_id,
                f"{punishment_message}\n**Action:** 🔇 **MUTED** for **{MUTE_DURATION_MINUTES} minutes**."
            )

        elif action_to_take == "kick":
            await client.ban_chat_member(chat_id, user_id)
            await client.unban_chat_member(chat_id, user_id) # Unban immediately to allow rejoining
            await reset_warnings(chat_id, user_id)
            await client.send_message(
                chat_id,
                f"{punishment_message}\n**Action:** 👢 **KICKED**\n_All warnings have been reset._"
            )

        elif action_to_take == "ban":
            await client.ban_chat_member(chat_id, user_id)
            await reset_warnings(chat_id, user_id)
            await client.send_message(
                chat_id,
                f"{punishment_message}\n**Action:** 🚫 **PERMANENTLY BANNED**\n_All warnings have been reset._"
            )

    except Exception as e:
        print(f"Failed to apply punishment to user {user_id}: {e}")
        await client.send_message(
            chat_id,
            f"⚠️ **Error:** Failed to execute punishment ({action_to_take}) for {user_mention}. Bot needs 'Restrict Members' or 'Ban Members' permission."
        )

