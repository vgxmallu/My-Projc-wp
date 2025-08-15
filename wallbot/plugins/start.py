from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from wallbot.database.db import add_user, get_user, add_group, get_group
from wallbot import wbot as word

START_TEXT = """**👋 Hey {user}!

 Hi! My name is {bot}I i have somany futurs!
**"""

@word.on_message(filters.command(["start", "help"]) & filters.private)
async def start(client: Client, message: Message):
    await message.reply_photo(
        photo="https://files.catbox.moe/wpxnj9.jpg",
        caption=START_TEXT.format(
            user=message.from_user.mention,
            bot=(await client.get_me()).first_name
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("My Channel", url="https://t.me/XBOTS_X"),
                ]
            ]
        )
    )

@word.on_message(filters.command("start") & filters.group)
async def start_group(client: Client, message: Message):
    
    await message.reply_photo(
        photo="https://files.catbox.moe/wpxnj9.jpg",
        caption=START_TEXT.format(
            user=message.from_user.mention,
            bot=(await client.get_me()).first_name
        )
    )
