import os
import json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Callback for displaying message as JSON
@Client.on_message(filters.command(["json", "js", "showjson"]))
async def jsonify(client, message):
    """
    Handle the /json, /js, or /showjson command to display the JSON representation of a message.
    If the message is too large, it will save it as a file and send it instead.
    """
    the_real_message = message.reply_to_message or message  # Check for a replied message, else use the current message

    # Inline keyboard for closing the message
    close_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="𝙲𝙻𝙾𝚂𝙴", callback_data="close_data")]]
    )

    try:
        # Format the message as JSON if possible, falling back to string representation
        formatted_message = json.dumps(the_real_message, default=str, indent=2, ensure_ascii=False)

        # Attempt to send the JSON representation of the message
        await message.reply_text(
            f"<code>{formatted_message}</code>", reply_markup=close_button, quote=True
        )
    except Exception as e:
        # Handle cases where the message is too large to send directly
        temp_filename = "message_data.json"
        try:
            with open(temp_filename, "w", encoding="utf8") as out_file:
                json.dump(the_real_message, out_file, default=str, indent=2, ensure_ascii=False)

            # Send the JSON as a document with an error caption
            await message.reply_document(
                document=temp_filename,
                caption=f"Error: {e}",
                disable_notification=True,
                quote=True,
                reply_markup=close_button
            )
        finally:
            # Ensure the temporary file is removed
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

# Add a callback handler for the close button
@Client.on_callback_query(filters.regex("^close_data$"))
async def close_callback(client, callback_query):
    """
    Handle the close button callback to delete the JSON message.
    """
    await callback_query.message.delete()
    await callback_query.answer("Closed", show_alert=False)
