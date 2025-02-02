import asyncio
import random
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram import filters


from wallbot import wbot
from wallbot.images_db.walls import ANIM_PICS                      
from config import LOG_CHANNEL
from wallbot.untils import pyro_cooldown

MW = """
📣 **LOG ALERT** 🏞️🤖

📛**Triggered Command** : /start
👤**Name** : {}
👾**Username** : @{}
💾**DC** : {}
♐**ID** : `{}`
🤖**BOT** : @Wallpepers_xbot
"""
@wbot.on_message(filters.private & filters.command("start"))
async def wall_start(client, message):
    await client.send_message(LOG_CHANNEL, MW.format(message.from_user.mention, message.from_user.username, message.from_user.dc_id, message.from_user.id))
    
    g = await message.reply_photo(
        photo=random.choice(PICS),
        caption="Welcome to Wallpapers x bot ;)",
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Wallpapers 🏞️", "✖️Close×"
            ]], 
            resize_keyboard=True
        ) 
    )
    await asyncio.sleep(9)
    await k.delete()
    await asyncio.sleep(5)
    await g.delete()
    await message.delete()
    await message.reply_text("/help")
    return
