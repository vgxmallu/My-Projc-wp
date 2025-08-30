from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pyrogram.errors import Unauthorized
from wallbot import wbot as app

# Database to store whispers (in production, use a proper database)
whisper_db = {}

# Command handler for /whisper
@app.on_message(filters.command("whisper"))
async def whisper_command(client, message: Message):
    if len(message.command) < 3:
        await message.reply_text(
            "**💒 Whisper Usage:**\n\n"
            "`/whisper [USERNAME|ID] [TEXT]`\n\n"
            "**Example:**\n"
            "`/whisper @username I have a secret for you!`"
        )
        return
    
    try:
        # Extract target user and message
        target = message.command[1]
        whisper_text = " ".join(message.command[2:])
        
        # Try to resolve the target user
        try:
            if target.startswith("@"):
                target_user = await client.get_users(target)
            else:
                target_user = await client.get_users(int(target))
        except Exception:
            await message.reply_text("❌ Invalid username or ID!")
            return
        
        # Store the whisper in database
        key = f"{message.from_user.id}_{target_user.id}"
        whisper_db[key] = whisper_text
        
        # Create buttons
        whisper_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "💒 Show Whisper", 
                callback_data=f"whisper_{message.from_user.id}_{target_user.id}"
            )
        ]])
        
        one_time_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔩 One-Time Whisper", 
                callback_data=f"whisper_{message.from_user.id}_{target_user.id}_one"
            )
        ]])
        
        # Send confirmation to sender
        await message.reply_text(
            f"✅ Whisper prepared for {target_user.mention}!\n\n"
            "Choose the type of whisper:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "💒 Normal Whisper", 
                        callback_data=f"send_whisper_normal_{key}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔩 One-Time Whisper", 
                        callback_data=f"send_whisper_one_{key}"
                    )
                ]
            ])
        )
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

# Handler for sending the whisper
@app.on_callback_query(filters.regex("^send_whisper_"))
async def send_whisper(client, callback_query: CallbackQuery):
    data = callback_query.data
    key = data.split("_")[3]
    whisper_type = data.split("_")[2]  # normal or one
    
    if key not in whisper_db:
        await callback_query.answer("Whisper not found or expired!", show_alert=True)
        return
    
    from_user_id, to_user_id = key.split("_")
    from_user_id = int(from_user_id)
    to_user_id = int(to_user_id)
    
    try:
        # Get the target user
        target_user = await client.get_users(to_user_id)
        
        # Prepare the message with button
        if whisper_type == "normal":
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💒 Show Whisper", 
                    callback_data=f"whisper_{from_user_id}_{to_user_id}"
                )
            ]])
        else:
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔩 One-Time Whisper", 
                    callback_data=f"whisper_{from_user_id}_{to_user_id}_one"
                )
            ]])
        
        # Send the whisper to the target user
        await client.send_message(
            target_user.id,
            f"🔒 You have a whisper from {callback_query.from_user.mention}!",
            reply_markup=btn
        )
        
        # Confirm to the sender
        await callback_query.edit_message_text(
            f"✅ Whisper sent to {target_user.mention}!"
        )
        
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

# Handler for showing the whisper
@app.on_callback_query(filters.regex("^whisper_"))
async def show_whisper(client, callback_query: CallbackQuery):
    data = callback_query.data.split("_")
    from_user = int(data[1])
    to_user = int(data[2])
    user_id = callback_query.from_user.id
    
    # Check if one-time whisper
    is_one_time = len(data) > 3 and data[3] == "one"
    
    # Check permissions
    if user_id not in [from_user, to_user, 6691393517]:  # Replace 6691393517 with your admin ID
        try:
            await client.send_message(
                from_user, 
                f"{callback_query.from_user.mention} is trying to open your whisper."
            )
        except Unauthorized:
            pass
        
        await callback_query.answer("This whisper is not for you 🚧", show_alert=True)
        return
    
    # Get the whisper
    search_msg = f"{from_user}_{to_user}"
    if search_msg not in whisper_db:
        await callback_query.answer("🚫 Whisper not found or expired!", show_alert=True)
        return
    
    msg = whisper_db[search_msg]
    
    # Show the whisper
    await callback_query.answer(msg, show_alert=True)
    
    # If it's a one-time whisper and the target user is reading it, delete it
    if is_one_time and user_id == to_user:
        del whisper_db[search_msg]
        await callback_query.edit_message_text(
            "📬 Whisper has been read and deleted!\n\n"
            "It was a one-time whisper.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💒 Send a Whisper", 
                    callback_data="send_whisper_help"
                )
            ]])
        )
      
