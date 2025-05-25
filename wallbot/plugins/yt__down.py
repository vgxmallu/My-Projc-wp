import re
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from wallbot.plugins.yt_utils import fetch_download_options, send_file_with_thumbnail

@Client.on_message(filters.private & filters.regex(r"https?://(www\.)?(youtube\.com|youtu\.be)/"))
async def youtube_download_handler(client: Client, message: Message):
    url = message.text.strip()
    msg = await message.reply("🔍 Fetching formats...")
    try:
        results = fetch_download_options(url)
        if not results:
            return await msg.edit("❌ No downloadable formats found.")

        buttons = [
            [InlineKeyboardButton(f"{fmt['size']} {fmt['format']}", callback_data=f"yt_{fmt['url']}|{fmt['size']}|{fmt['format']}|{fmt['ext']}")]
            for fmt in results
        ]
        await msg.edit("✅ Choose a format to download:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        await msg.edit(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex(r"^yt_"))
async def download_selected_format(client: Client, callback):
    await callback.answer()
    data = callback.data[3:]
    url, size, fmt, ext = data.split("|")
    filename = f"{size} {fmt} -@mnbots-.{ext}"
    await send_file_with_thumbnail(client, callback.message, url, filename)
