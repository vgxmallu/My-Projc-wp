# Copyright @ISmartDevs
# Channel t.me/TheSmartDev
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from core import user_history
from config import COMMAND_PREFIXES
from utils import LOGGER
from datetime import datetime

# Helper function to store and check user data
async def store_and_check_user(client, message):
    user = message.from_user
    if not user:
        return
    
    user_id = user.id
    username = f"@{user.username}" if user.username else None
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Unknown"
    timestamp = datetime.utcnow()

    try:
        # Get current user data from MongoDB
        user_doc = user_history.find_one({"user_id": user_id})
        
        # Initialize new user document if none exists
        if not user_doc:
            user_history.insert_one({
                "user_id": user_id,
                "names": [{"name": full_name, "timestamp": timestamp}],
                "usernames": [{"username": username, "timestamp": timestamp}] if username else []
            })
            LOGGER.info(f"Stored new user {user_id} in user_history")
            return

        # Check for name change
        current_name = user_doc["names"][-1]["name"]
        if current_name != full_name:
            user_history.update_one(
                {"user_id": user_id},
                {"$push": {"names": {"name": full_name, "timestamp": timestamp}}}
            )
            await client.send_message(
                chat_id=message.chat.id,
                text=f"**User `{user_id}` changed Name from `{current_name}` to `{full_name}`**",
                parse_mode=ParseMode.MARKDOWN
            )
            LOGGER.info(f"Name change for user {user_id}: {current_name} -> {full_name}")

        # Check for username change
        current_username = user_doc["usernames"][-1]["username"] if user_doc["usernames"] else None
        if current_username != username:
            user_history.update_one(
                {"user_id": user_id},
                {"$push": {"usernames": {"username": username, "timestamp": timestamp}} if username else {}}
            )
            if current_username and username:
                await client.send_message(
                    chat_id=message.chat.id,
                    text=f"**User `{user_id}` changed username from `{current_username}` to `{username}`**",
                    parse_mode=ParseMode.MARKDOWN
                )
                LOGGER.info(f"Username change for user {user_id}: {current_username} -> {username}")
            elif username:
                LOGGER.info(f"Username set for user {user_id}: {username}")

    except Exception as e:
        LOGGER.error(f"Error processing user {user_id}: {e}")

# History command to show user name/username history
@Client.on_message(filters.command("history"))
async def history_cgommand(client, message):
    try:
        # Get user_id or username from command arguments or use sender's data
        args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        user_id = None
        username = None
        if args:
            if args.startswith("@"):
                username = args
            elif args.isdigit():
                user_id = int(args)
        
        # If no args, use the sender's user_id
        if not user_id and not username:
            user_id = message.from_user.id
        
        # Query by username if provided
        if username:
            user_doc = user_history.find_one({"usernames.username": username})
            if not user_doc:
                await client.send_message(
                    chat_id=message.chat.id,
                    text=f"No history found for username `{username}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            user_id = user_doc["user_id"]

        # Fetch user history
        user_doc = user_history.find_one({"user_id": user_id})
        if not user_doc:
            await client.send_message(
                chat_id=message.chat.id,
                text=f"No history found for user ID `{user_id}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Build history message
        names = user_doc.get("names", [])
        usernames = user_doc.get("usernames", [])
        
        names_text = "**Names**\n"
        for i, entry in enumerate(names, 1):
            timestamp = entry["timestamp"].strftime("[%d/%m/%y %H:%M:%S]")
            names_text += f"{i:02d}. `{timestamp}` {entry['name']}\n"
        
        usernames_text = "**Usernames**\n"
        for i, entry in enumerate(usernames, 1):
            timestamp = entry["timestamp"].strftime("[%d/%m/%y %H:%M:%S]")
            usernames_text += f"{i:02d}. `{timestamp}` {entry['username']}\n"
        
        history_message = (
            f"**History for [{user_id}](tg://user?id={user_id})**\n"
            f"{names_text}\n"
            f"{usernames_text}".rstrip()
        )
        
        await client.send_message(
            chat_id=message.chat.id,
            text=history_message,
            parse_mode=ParseMode.MARKDOWN
        )
        LOGGER.info(f"History requested for user {user_id} by {message.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Error in history command for user {user_id}: {e}")
        await client.send_message(
            chat_id=message.chat.id,
            text="Error retrieving history. Check logs for details.",
            parse_mode=ParseMode.MARKDOWN
        )
