from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import random
import Script
import html

@Client.on_message(filters.command('runs') & filters.incoming)
async def runs(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.RUN_STRINGS),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command('roll') & filters.incoming)
async def roll(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(range(1, 7)),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command('toss') & filters.incoming)
async def toss(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.TOSS),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    
@Client.on_message(filters.command('throw') & filters.incoming)
async def throw(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.THROW),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    
@Client.on_message(filters.command('hit') & filters.incoming)
async def hit(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.HIT),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command('abuse') & filters.incoming)
async def abuse(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.ABUSE_STRINGS),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command('shrug') & filters.incoming)
async def shrug(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=r"¯\_(ツ)_/¯",
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command('pings') & filters.incoming)
async def pings(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.PING_STRING),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    
@Client.on_message(filters.command('items') & filters.incoming)
async def items(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.ITEMS),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command('bluetext') & filters.incoming)
async def bluetext(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text="/BLUE /TEXT\n/MUST /CLICK\n/I /AM /A /STUPID /ANIMAL /THAT /IS /ATTRACTED /TO /COLORS",
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command('rlg') & filters.incoming)
async def rlg(bot, update):
    eyes = random.choice(Script.EYES)
    mouth = random.choice(Script.MOUTHS)
    ears = random.choice(Script.EARS)

    if len(eyes) == 2:
        repl = ears[0] + eyes[0] + mouth[0] + eyes[1] + ears[1]
    else:
        repl = ears[0] + eyes[0] + mouth[0] + eyes[0] + ears[1]
    await bot.send_message(
        chat_id=update.chat.id,
        text=repl,
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command('decide') & filters.incoming)
async def decide(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.DECIDE),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command('table') & filters.incoming)
async def table(bot, update):
    await bot.send_message(
        chat_id=update.chat.id,
        text=random.choice(Script.TABLE),
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
