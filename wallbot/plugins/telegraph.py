import os, asyncio
from typing import Optional
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from telegraph import upload_file

from wallbot import wbot as app

import time
import string
import random
import requests
import traceback

import datetime
import aiofiles
import logging
from random import choice
#---------------FUNCTION---------------#



# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Function to upload a file to Catbox
def upload_file(file_path):
    url = "https://catbox.moe/user/api.php"
    data = {"reqtype": "fileupload", "json": "true"}

    try:
        with open(file_path, "rb") as file:
            files = {"fileToUpload": file}
            response = requests.post(url, data=data, files=files)

        logger.info(f"Response from Catbox: {response.status_code} - {response.text}")

        if response.status_code == 200:
            # Catbox returns a plain URL, not JSON
            if response.text.startswith("https://files.catbox.moe/"):
                return True, response.text.strip()
            else:
                return False, f"Unexpected response from Catbox: {response.text}"
        else:
            logger.error(f"Error from Catbox: {response.status_code} - {response.text}")
            return False, f"Error: {response.status_code} - {response.text}"

    except Exception as e:
        logger.error(f"Exception occurred: {str(e)}")
        return False, f"Exception occurred: {str(e)}"

# Handler for incoming photo messages
@app.on_message(filters.private & filters.command(["telegraph", "tp"]))
async def photo_handler(_, message: Message):
    """Handles incoming photo messages by uploading to Catbox.moe."""
    media = message.reply_to_message
 
    file_size = media.photo.file_size if media.photo else 0

    # Check if file is larger than 200MB
    if file_size > 200 * 1024 * 1024:
        return await message.reply_text("Pʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴘʜᴏᴛᴏ ᴜɴᴅᴇʀ 200MB.")

    try:
        # Initial response message
        text = await message.reply("Processing...")

        # Download the file
        local_path = await media.download()
        if not local_path or not os.path.exists(local_path): 
            await text.edit_text("Failed to download the file. Please try again.")
            return

        # Inform the user that upload is in progress
        await text.edit_text("Uploading...")
        # Upload the file to Catbox
        success, upload_url_or_error = upload_file(local_path)
        
        if success:
            # Prepare the message text with the upload URL
            final_text = f"[your link is ready.]({upload_url_or_error})"

            # Inline buttons with the response link
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(text="X-BOTS-X", url="https://t.me/xbots_x"),
                    ]
                ]
                                                                   )
            # Send final message with the URL and buttons
            await text.edit_text(
                text=final_text,
                disable_web_page_preview=True,
                reply_markup=reply_markup
            )
        else:
            # In case of failure, show the error
            await text.edit_text(f"❍ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴜᴘʟᴏᴀᴅɪɴɢ. {upload_url_or_error}")

    except Exception as e:
        logger.error(f"Error during file upload: {str(e)}")
        await text.edit_text("File upload failed.")

    finally:
        # Ensure that the local file is always removed
        if os.path.exists(local_path):
            os.remove(local_path)
