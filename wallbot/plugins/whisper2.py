import os
import asyncio
import json
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from pyrogram.errors import (
    Unauthorized, UserNotParticipant, ChatWriteForbidden,
    FloodWait, PeerIdInvalid
)
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
from config import DB_URL
from wallbot import wbot as app
# Configuration
ADMIN_USER_IDS = [784589736]  # Replace with your admin user IDs
MAX_WHISPERS_PER_USER = 50  # Maximum whispers a user can have active
WHISPER_EXPIRY_DAYS = 30  # Days after which whispers are automatically deleted
COOLDOWN_SECONDS = 30  # Seconds between sending whispers

# Initialize MongoDB
MONGO_URI = os.environ.get("DB_URL")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.whisper_bot

# Collections
whispers_col = db.whispers
users_col = db.users
blocks_col = db.blocks
analytics_col = db.analytics
settings_col = db.settings

# Create indexes
whispers_col.create_index([("from_user_id", 1), ("created_at", 1)])
whispers_col.create_index([("to_user_id", 1), ("is_read", 1)])
whispers_col.create_index("expires_at", expireAfterSeconds=0)
users_col.create_index("user_id", unique=True)
blocks_col.create_index([("user_id", 1), ("blocked_user_id", 1)], unique=True)

# Initialize Pyrogram Client
app = Client(
    "advanced_whisper_bot",
    api_id=int(os.environ.get("API_ID")),
    api_hash=os.environ.get("API_HASH"),
    bot_token=os.environ.get("BOT_TOKEN")
)

# Encryption functions (simple XOR for demonstration)
def encrypt_message(message: str, key: str) -> str:
    """Encrypt message using simple XOR cipher"""
    key = hashlib.sha256(key.encode()).digest()
    encrypted = []
    for i, char in enumerate(message):
        encrypted_char = chr(ord(char) ^ key[i % len(key)])
        encrypted.append(encrypted_char)
    return base64.b64encode(''.join(encrypted).encode()).decode()

def decrypt_message(encrypted_message: str, key: str) -> str:
    """Decrypt message using simple XOR cipher"""
    key = hashlib.sha256(key.encode()).digest()
    encrypted = base64.b64decode(encrypted_message.encode()).decode()
    decrypted = []
    for i, char in enumerate(encrypted):
        decrypted_char = chr(ord(char) ^ key[i % len(key)])
        decrypted.append(decrypted_char)
    return ''.join(decrypted)

# Database operations
async def get_or_create_user(user_id: int, username: str = "", first_name: str = ""):
    """Get user from DB or create if not exists"""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.now(),
            "whisper_count": 0,
            "received_count": 0,
            "is_banned": False,
            "language": "en"
        }
        users_col.insert_one(user)
    return user

async def create_whisper(from_user_id: int, to_user_id: int, message: str, 
                        whisper_type: str = "normal", expires_in: int = None):
    """Create a new whisper"""
    # Check if user is blocked
    if blocks_col.find_one({"user_id": to_user_id, "blocked_user_id": from_user_id}):
        return False, "You are blocked by this user"
    
    # Check user's whisper limit
    user_whispers = whispers_col.count_documents({
        "from_user_id": from_user_id,
        "expires_at": {"$gt": datetime.now()}
    })
    
    if user_whispers >= MAX_WHISPERS_PER_USER:
        return False, f"You can only have {MAX_WHISPERS_PER_USER} active whispers at a time"
    
    # Set expiration
    expires_at = datetime.now() + timedelta(days=expires_in or WHISPER_EXPIRY_DAYS)
    
    # Encrypt message
    encryption_key = f"{from_user_id}_{to_user_id}_{datetime.now().timestamp()}"
    encrypted_message = encrypt_message(message, encryption_key)
    
    # Create whisper
    whisper = {
        "from_user_id": from_user_id,
        "to_user_id": to_user_id,
        "message": encrypted_message,
        "encryption_key": encryption_key,
        "type": whisper_type,
        "is_read": False,
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "read_at": None
    }
    
    result = whispers_col.insert_one(whisper)
    
    # Update user stats
    users_col.update_one(
        {"user_id": from_user_id},
        {"$inc": {"whisper_count": 1}}
    )
    
    # Record analytics
    analytics_col.insert_one({
        "event": "whisper_created",
        "whisper_id": result.inserted_id,
        "from_user_id": from_user_id,
        "to_user_id": to_user_id,
        "type": whisper_type,
        "timestamp": datetime.now()
    })
    
    return True, result.inserted_id

async def get_whisper(whisper_id: str, user_id: int):
    """Get a whisper by ID with permission check"""
    whisper = whispers_col.find_one({"_id": whisper_id})
    if not whisper:
        return None, "Whisper not found"
    
    if whisper["to_user_id"] != user_id and user_id not in ADMIN_USER_IDS:
        return None, "You don't have permission to view this whisper"
    
    return whisper, None

async def mark_whisper_read(whisper_id: str):
    """Mark a whisper as read"""
    result = whispers_col.update_one(
        {"_id": whisper_id},
        {"$set": {"is_read": True, "read_at": datetime.now()}}
    )
    
    if result.modified_count:
        whisper = whispers_col.find_one({"_id": whisper_id})
        users_col.update_one(
            {"user_id": whisper["to_user_id"]},
            {"$inc": {"received_count": 1}}
        )
        
        # Record analytics
        analytics_col.insert_one({
            "event": "whisper_read",
            "whisper_id": whisper_id,
            "timestamp": datetime.now()
        })
        
        return True
    return False

async def delete_whisper(whisper_id: str, user_id: int):
    """Delete a whisper"""
    whisper = whispers_col.find_one({"_id": whisper_id})
    if not whisper:
        return False, "Whisper not found"
    
    if whisper["from_user_id"] != user_id and user_id not in ADMIN_USER_IDS:
        return False, "You don't have permission to delete this whisper"
    
    result = whispers_col.delete_one({"_id": whisper_id})
    
    if result.deleted_count:
        # Record analytics
        analytics_col.insert_one({
            "event": "whisper_deleted",
            "whisper_id": whisper_id,
            "user_id": user_id,
            "timestamp": datetime.now()
        })
        return True, "Whisper deleted"
    
    return False, "Failed to delete whisper"

async def block_user(user_id: int, blocked_user_id: int):
    """Block a user"""
    try:
        blocks_col.insert_one({
            "user_id": user_id,
            "blocked_user_id": blocked_user_id,
            "blocked_at": datetime.now()
        })
        return True, "User blocked"
    except DuplicateKeyError:
        return False, "User already blocked"

async def unblock_user(user_id: int, blocked_user_id: int):
    """Unblock a user"""
    result = blocks_col.delete_one({
        "user_id": user_id,
        "blocked_user_id": blocked_user_id
    })
    
    if result.deleted_count:
        return True, "User unblocked"
    return False, "User was not blocked"

async def get_user_whispers(user_id: int, sent: bool = True):
    """Get all whispers sent or received by a user"""
    field = "from_user_id" if sent else "to_user_id"
    return list(whispers_col.find({
        field: user_id,
        "expires_at": {"$gt": datetime.now()}
    }).sort("created_at", DESCENDING))

async def get_user_stats(user_id: int):
    """Get user statistics"""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return None
    
    sent_count = whispers_col.count_documents({"from_user_id": user_id})
    received_count = whispers_col.count_documents({"to_user_id": user_id, "is_read": True})
    unread_count = whispers_col.count_documents({"to_user_id": user_id, "is_read": False})
    
    return {
        "user": user,
        "sent_count": sent_count,
        "received_count": received_count,
        "unread_count": unread_count,
        "blocked_count": blocks_col.count_documents({"user_id": user_id})
    }

# Cooldown system
user_cooldowns = {}

def check_cooldown(user_id: int):
    """Check if user is in cooldown"""
    now = datetime.now().timestamp()
    if user_id in user_cooldowns:
        if now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
            return False, COOLDOWN_SECONDS - (now - user_cooldowns[user_id])
    user_cooldowns[user_id] = now
    return True, 0

# Handlers
@app.on_message(filters.command("srt"))
async def start_coddmmand(client, message: Message):
    """Handle /start command"""
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    welcome_text = (
        "🔒 *Advanced Whisper Bot*\n\n"
        "Send encrypted whispers that only the recipient can read!\n\n"
        "**Available Commands:**\n"
        "/whisper - Send a whisper\n"
        "/mywhispers - View your whispers\n"
        "/block - Block a user\n"
        "/unblock - Unblock a user\n"
        "/stats - Your whisper statistics\n\n"
        "**Features:**\n"
        "• End-to-end encryption\n"
        "• Self-destructing messages\n"
        "• User blocking system\n"
        "• Message expiration\n"
        "• Read receipts\n\n"
        "Use /help for detailed instructions."
    )
    
    await message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Send Whisper", switch_inline_query_current_chat="whisper ")
        ]]),
        disable_web_page_preview=True
    )

@app.on_message(filters.command("whisper"))
async def whisper_command(client, message: Message):
    """Handle /whisper command"""
    # Check cooldown
    cooldown_ok, remaining = check_cooldown(message.from_user.id)
    if not cooldown_ok:
        await message.reply_text(
            f"⏰ Please wait {int(remaining)} seconds before sending another whisper."
        )
        return
    
    if len(message.command) < 3:
        await message.reply_text(
            "**💬 Send a Whisper**\n\n"
            "Usage: `/whisper @username your message`\n\n"
            "**Options:**\n"
            "Add `-once` at the end for a one-time whisper\n"
            "Add `-burn 5` for a whisper that expires in 5 minutes\n\n"
            "**Examples:**\n"
            "`/whisper @username Hello!` - Normal whisper\n"
            "`/whisper @username Secret -once` - One-time whisper\n"
            "`/whisper @username Quick message -burn 5` - Expires in 5 min"
        )
        return
    
    # Parse command
    args = message.text.split()
    target = args[1]
    message_text = " ".join(args[2:])
    
    # Check for flags
    whisper_type = "normal"
    expires_in = None
    
    if " -once" in message_text:
        whisper_type = "one_time"
        message_text = message_text.replace(" -once", "")
    elif " -burn" in message_text:
        parts = message_text.split(" -burn ")
        if len(parts) > 1:
            try:
                burn_time = int(parts[1].split()[0])
                expires_in = burn_time  # minutes
                message_text = parts[0]
                whisper_type = "burn"
            except (ValueError, IndexError):
                pass
    
    # Validate message
    if not message_text.strip():
        await message.reply_text("Please provide a message to send.")
        return
    
    # Get target user
    try:
        if target.startswith("@"):
            target_user = await client.get_users(target)
        else:
            target_user = await client.get_users(int(target))
    except (PeerIdInvalid, IndexError, ValueError):
        await message.reply_text("❌ Invalid username or ID!")
        return
    
    # Check if trying to send to self
    if target_user.id == message.from_user.id:
        await message.reply_text("You can't send a whisper to yourself!")
        return
    
    # Check if target user has blocked the sender
    if blocks_col.find_one({"user_id": target_user.id, "blocked_user_id": message.from_user.id}):
        await message.reply_text("You can't send a whisper to this user.")
        return
    
    # Create whisper
    success, result = await create_whisper(
        message.from_user.id,
        target_user.id,
        message_text,
        whisper_type,
        expires_in
    )
    
    if not success:
        await message.reply_text(f"❌ {result}")
        return
    
    # Send confirmation
    confirm_text = f"✅ Whisper sent to {target_user.mention}!"
    if whisper_type == "one_time":
        confirm_text += "\n\n⚠️ This whisper will be deleted after being read once."
    elif whisper_type == "burn":
        confirm_text += f"\n\n🔥 This whisper will expire in {expires_in} minutes."
    
    # Create keyboard with options
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 View Stats", callback_data="stats"),
        InlineKeyboardButton("🚫 Delete", callback_data=f"delete_{result}")
    ]])
    
    await message.reply_text(confirm_text, reply_markup=keyboard)
    
    # Notify recipient if they've started the bot
    try:
        recipient_msg = await client.send_message(
            target_user.id,
            f"🔒 You have a new whisper from {message.from_user.mention}!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📩 View Whisper", callback_data=f"view_{result}")
            ]])
        )
    except (Unauthorized, UserNotParticipant):
        # User hasn't started the bot or blocked it
        pass

@app.on_message(filters.command("mywhispers"))
async def my_whispers_command(client, message: Message):
    """Handle /mywhispers command"""
    user_id = message.from_user.id
    
    # Get sent and received whispers
    sent_whispers = await get_user_whispers(user_id, sent=True)
    received_whispers = await get_user_whispers(user_id, sent=False)
    
    if not sent_whispers and not received_whispers:
        await message.reply_text("You don't have any whispers yet.")
        return
    
    # Create response
    response = "📨 **Your Whispers**\n\n"
    
    if sent_whispers:
        response += "**Sent Whispers:**\n"
        for whisper in sent_whispers[:5]:  # Show only 5 most recent
            status = "📨" if not whisper["is_read"] else "✅"
            response += f"{status} To: {whisper['to_user_id']} - {whisper['created_at'].strftime('%Y-%m-%d')}\n"
    
    if received_whispers:
        response += "\n**Received Whispers:**\n"
        for whisper in received_whispers[:5]:  # Show only 5 most recent
            status = "📬" if not whisper["is_read"] else "📭"
            response += f"{status} From: {whisper['from_user_id']} - {whisper['created_at'].strftime('%Y-%m-%d')}\n"
    
    # Add view all button if there are more whispers
    buttons = []
    if len(sent_whispers) > 5 or len(received_whispers) > 5:
        buttons.append([InlineKeyboardButton("📋 View All", callback_data="view_all_whispers")])
    
    await message.reply_text(response, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("block"))
async def block_command(client, message: Message):
    """Handle /block command"""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/block @username`")
        return
    
    target = message.command[1]
    
    try:
        if target.startswith("@"):
            target_user = await client.get_users(target)
        else:
            target_user = await client.get_users(int(target))
    except (PeerIdInvalid, IndexError, ValueError):
        await message.reply_text("❌ Invalid username or ID!")
        return
    
    # Block user
    success, result = await block_user(message.from_user.id, target_user.id)
    await message.reply_text(result)

@app.on_message(filters.command("unblock"))
async def unblock_command(client, message: Message):
    """Handle /unblock command"""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/unblock @username`")
        return
    
    target = message.command[1]
    
    try:
        if target.startswith("@"):
            target_user = await client.get_users(target)
        else:
            target_user = await client.get_users(int(target))
    except (PeerIdInvalid, IndexError, ValueError):
        await message.reply_text("❌ Invalid username or ID!")
        return
    
    # Unblock user
    success, result = await unblock_user(message.from_user.id, target_user.id)
    await message.reply_text(result)

@app.on_message(filters.command("sta"))
async def stats_commssand(client, message: Message):
    """Handle /stats command"""
    stats = await get_user_stats(message.from_user.id)
    if not stats:
        await message.reply_text("No statistics available.")
        return
    
    response = (
        "📊 **Your Whisper Statistics**\n\n"
        f"• Sent: {stats['sent_count']}\n"
        f"• Received: {stats['received_count']}\n"
        f"• Unread: {stats['unread_count']}\n"
        f"• Blocked Users: {stats['blocked_count']}\n\n"
        f"**Account Created:** {stats['user']['created_at'].strftime('%Y-%m-%d')}"
    )
    
    await message.reply_text(response)

@app.on_callback_query(filters.regex("^view_"))
async def view_whisper_callback(client, callback_query: CallbackQuery):
    """Handle view whisper callback"""
    whisper_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    # Get whisper
    whisper, error = await get_whisper(whisper_id, user_id)
    if error:
        await callback_query.answer(error, show_alert=True)
        return
    
    # Decrypt message
    try:
        decrypted_message = decrypt_message(whisper["message"], whisper["encryption_key"])
    except:
        await callback_query.answer("Failed to decrypt message", show_alert=True)
        return
    
    # Mark as read if not already
    if not whisper["is_read"]:
        await mark_whisper_read(whisper_id)
    
    # Show message
    message_text = (
        f"📨 **Whisper from** <user>{whisper['from_user_id']}</user>\n\n"
        f"{decrypted_message}\n\n"
        f"**Sent:** {whisper['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
    )
    
    if whisper["type"] == "one_time":
        message_text += "⚠️ This message will self-destruct after being read\n"
    
    # Add reply button if not one-time
    buttons = []
    if whisper["type"] != "one_time":
        buttons.append([InlineKeyboardButton("📤 Reply", callback_data=f"reply_{whisper['from_user_id']}")])
    
    buttons.append([InlineKeyboardButton("🚫 Delete", callback_data=f"delete_{whisper_id}")])
    
    await callback_query.message.edit_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^delete_"))
async def delete_whisper_callback(client, callback_query: CallbackQuery):
    """Handle delete whisper callback"""
    whisper_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    success, result = await delete_whisper(whisper_id, user_id)
    if success:
        await callback_query.message.edit_text("🗑️ Whisper deleted")
    else:
        await callback_query.answer(result, show_alert=True)
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^reply_"))
async def reply_whisper_callback(client, callback_query: CallbackQuery):
    """Handle reply to whisper callback"""
    target_user_id = int(callback_query.data.split("_")[1])
    
    # Store reply state
    settings_col.update_one(
        {"user_id": callback_query.from_user.id},
        {"$set": {"replying_to": target_user_id}},
        upsert=True
    )
    
    await callback_query.message.edit_text(
        "💬 Please type your reply message:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_reply")
        ]])
    )
    await callback_query.answer()

@app.on_message(filters.private & ~filters.command)
async def handle_reply_message(client, message: Message):
    """Handle reply messages"""
    # Check if user is in reply mode
    reply_state = settings_col.find_one({"user_id": message.from_user.id, "replying_to": {"$exists": True}})
    if not reply_state:
        return
    
    target_user_id = reply_state["replying_to"]
    
    # Create whisper as reply
    success, result = await create_whisper(
        message.from_user.id,
        target_user_id,
        message.text,
        "normal"
    )
    
    if success:
        await message.reply_text("✅ Reply sent!")
        
        # Notify recipient
        try:
            await client.send_message(
                target_user_id,
                f"💬 You have a reply from {message.from_user.mention}!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📩 View Reply", callback_data=f"view_{result}")
                ]])
            )
        except (Unauthorized, UserNotParticipant):
            pass
    else:
        await message.reply_text(f"❌ Failed to send reply: {result}")
    
    # Clear reply state
    settings_col.update_one(
        {"user_id": message.from_user.id},
        {"$unset": {"replying_to": ""}}
    )

@app.on_callback_query(filters.regex("^cancel_reply$"))
async def cancel_reply_callback(client, callback_query: CallbackQuery):
    """Handle cancel reply callback"""
    settings_col.update_one(
        {"user_id": callback_query.from_user.id},
        {"$unset": {"replying_to": ""}}
    )
    
    await callback_query.message.edit_text("❌ Reply cancelled")
    await callback_query.answer()

# Admin commands
@app.on_message(filters.command("admin") & filters.user(ADMIN_USER_IDS))
async def admin_command(client, message: Message):
    """Handle /admin command"""
    # Get bot statistics
    total_users = users_col.count_documents({})
    total_whispers = whispers_col.count_documents({})
    active_whispers = whispers_col.count_documents({"expires_at": {"$gt": datetime.now()}})
    
    response = (
        "👑 **Admin Panel**\n\n"
        f"• Total Users: {total_users}\n"
        f"• Total Whispers: {total_whispers}\n"
        f"• Active Whispers: {active_whispers}\n\n"
        "**Admin Commands:**\n"
        "/admin_stats - Detailed statistics\n"
        "/admin_broadcast - Broadcast message to all users\n"
        "/admin_user - Get user information\n"
    )
    
    await message.reply_text(response)

@app.on_message(filters.command("admin_stats") & filters.user(ADMIN_USER_IDS))
async def admin_stats_command(client, message: Message):
    """Handle /admin_stats command"""
    # Get detailed statistics
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_users = users_col.count_documents({"created_at": {"$gte": today}})
    today_whispers = whispers_col.count_documents({"created_at": {"$gte": today}})
    
    # Get popular whisper types
    whisper_types = whispers_col.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}}}
    ])
    
    type_stats = "\n".join([f"• {t['_id']}: {t['count']}" for t in whisper_types])
    
    response = (
        "📈 **Admin Statistics**\n\n"
        f"• New Users Today: {today_users}\n"
        f"• Whispers Today: {today_whispers}\n\n"
        f"**Whisper Types:**\n{type_stats}"
    )
    
    await message.reply_text(response)

# Error handler
@app.on_error()
async def error_handler(client, update, error):
    """Handle errors"""
    if isinstance(error, FloodWait):
        await asyncio.sleep(error.value)
    else:
        print(f"Error: {error}")

