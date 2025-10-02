import os
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember
from pyrogram.enums import ChatMemberStatus
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app


# --- Database Setup ---

mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client.clean_service_db
cleanup_collection = db.cleanup_settings
    

# --- Service Message Definitions ---
# Map of user-facing types to functions that check the message object
SERVICE_MESSAGES_MAP = {
    # Function returns True if the message object matches the category
    "join": lambda m: bool(m.new_chat_members),
    "leave": lambda m: bool(m.left_chat_member),
    "photo": lambda m: bool(m.new_chat_photo or m.delete_chat_photo),
    "pin": lambda m: bool(m.pinned_message),
    "title": lambda m: bool(m.chat_title),
    "videochat": lambda m: bool(
        m.video_chat_started or 
        m.video_chat_ended or 
        m.video_chat_scheduled or
        m.video_chat_members_invited
    ),
    "other": lambda m: (
        bool(m.message_auto_delete_timer_changed or 
             m.proximity_alert_triggered or 
             m.web_app_data or 
             m.successful_payment or 
             m.chat_background_set or 
             m.boost_added)
    )
}

ALL_TYPES = list(SERVICE_MESSAGES_MAP.keys())

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

async def get_cleanup_settings(chat_id: int) -> list:
    """Retrieves the list of service types to delete for a chat."""
    settings = await cleanup_collection.find_one({"_id": chat_id})
    # Returns the list of categories currently set for deletion, defaults to empty list
    return settings.get("delete_types", []) if settings else []

async def update_cleanup_settings(chat_id: int, action: str, types: list):
    """
    Updates the MongoDB setting for which service messages to delete.
    action: "$addToSet" (to start deleting) or "$pull" (to stop deleting)
    """
    await cleanup_collection.update_one(
        {"_id": chat_id},
        {action: {"delete_types": {"$each": types}}}, # Add or remove the list of types
        upsert=True
    )


# ----------------------------------------------------
# --- Clean Service Admin Commands (Group Admins Only) ---
# ----------------------------------------------------

def parse_types(text: str) -> list:
    """Parses command argument text into a list of valid service types."""
    # Split by comma or space, remove duplicates, filter against valid types
    types = set([t.strip().lower() for t in text.replace(',', ' ').split() if t.strip()])
    
    if "all" in types:
        return ALL_TYPES
        
    return [t for t in types if t in ALL_TYPES]

@app.on_message(filters.command("cleanservice") & filters.group)
async def handle_cleanservice(client: Client, message: Message):
    """/cleanservice <type/yes/no/on/off>: Select which service messages to delete."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "📝 **Usage:** `/cleanservice <type>` or `/cleanservice all`\n"
            "Use `/cleanservicetypes` to see all available categories."
        )

    arg = parts[1].strip().lower()
    
    if arg in ["yes", "on"]:
        types_to_add = ALL_TYPES
    elif arg in ["no", "off"]:
        # If 'no' or 'off', we pull ALL types from the list (same as keepservice all)
        await update_cleanup_settings(message.chat.id, "$pull", ALL_TYPES)
        return await message.reply("✅ **Clean Service is OFF.** All service messages will now be kept.")
    else:
        types_to_add = parse_types(arg)
        if not types_to_add:
            return await message.reply(
                "❌ Invalid type provided. Use `/cleanservicetypes` to see available categories."
            )

    await update_cleanup_settings(message.chat.id, "$addToSet", types_to_add)
    
    if types_to_add == ALL_TYPES:
        reply_msg = "**All** service messages will now be deleted."
    else:
        reply_msg = f"✅ The following service messages will now be deleted: **{', '.join(types_to_add)}**"

    await message.reply(reply_msg)


@app.on_message(filters.command(["keepservice", "nocleanservice"]) & filters.group)
async def handle_keepservice(client: Client, message: Message):
    """/keepservice <type> or /nocleanservice <type>: Stop deleting selected service messages."""
    if not await is_admin_or_creator(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ **Access Denied.** This command is for group admins only.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "📝 **Usage:** `/keepservice <type>` or `/keepservice all`\n"
            "Use `/cleanservicetypes` to see all available categories."
        )

    types_to_remove = parse_types(parts[1])
    
    if not types_to_remove:
        return await message.reply(
            "❌ Invalid type provided. Use `/cleanservicetypes` to see available categories."
        )

    # Use $pull to remove the types from the deletion list
    await update_cleanup_settings(message.chat.id, "$pull", types_to_remove)
    
    if types_to_remove == ALL_TYPES:
        reply_msg = "✅ **All** service messages will now be kept (stopped deletion)."
    else:
        reply_msg = f"✅ Deletion stopped for: **{', '.join(types_to_remove)}**"

    await message.reply(reply_msg)


@app.on_message(filters.command("cleanservicetypes") & filters.group)
async def list_service_types(client: Client, message: Message):
    """/cleanservicetypes: List all the available service messages."""
    
    current_settings = await get_cleanup_settings(message.chat.id)
    
    status_map = {}
    for t in ALL_TYPES:
        status_map[t] = "✅ Deleting" if t in current_settings else "❌ Keeping"

    response = (
        "📝 **Available Service Message Categories**\n"
        "Use `/cleanservice <type>` or `/keepservice <type>`.\n"
        "Current Status:\n\n"
        f"**`all`** (All types): {status_map['join']} join (New user joins)\n"
        f"**`all`** (All types): {status_map['leave']} leave (User leaves/removed)\n"
        f"**`all`** (All types): {status_map['pin']} pin (New message pinned)\n"
        f"**`all`** (All types): {status_map['title']} title (Chat/Topic title changed)\n"
        f"**`all`** (All types): {status_map['photo']} photo (Chat photo/background changed)\n"
        f"**`all`** (All types): {status_map['videochat']} videochat (Voice/Video chat actions)\n"
        f"**`all`** (All types): {status_map['other']} other (Payments, webapp, auto-delete changes, etc.)\n"
    )

    await message.reply(response)


# ----------------------------------------------------
# --- Core Service Message Handler ---
# ----------------------------------------------------

@app.on_message(filters.service & filters.group)
async def service_cleaner(client: Client, message: Message):
    """Main handler to check and delete service messages based on chat settings."""
    
    # Ignore messages from the bot itself or other service bots
    if message.from_user and message.from_user.is_bot:
        return

    chat_id = message.chat.id
    types_to_delete = await get_cleanup_settings(chat_id)
    
    if not types_to_delete:
        return # Nothing configured for deletion

    message_category = None
    
    # Check the incoming message against all configured service types
    for category, checker_func in SERVICE_MESSAGES_MAP.items():
        try:
            if checker_func(message):
                message_category = category
                break
        except Exception:
            # Safely skip any checks that might fail for unusual message structures
            continue

    # If the message category is one we are configured to delete
    if message_category and message_category in types_to_delete:
        try:
            await message.delete()
            print(f"Deleted service message of type '{message_category}' in chat {chat_id}")
        except Exception as e:
            # The bot likely lacks the 'Delete Messages' permission
            print(f"Failed to delete service message in chat {chat_id}: {e}")

