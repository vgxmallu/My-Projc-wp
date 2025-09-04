import os
import asyncio
import pyrogram
from pyrogram import Client, filters
from wallbot import wbot as app

bullets = {
    "bullet1": ">",
    "bullet2": "•",
    "bullet3": "⋟",
    "bullet4": "◈",
    "bullet5": "┏",
    "bullet6": "┣",
    "bullet7": "┗",
}

b1 = bullets["bullet4"]
b2 = bullets["bullet2"]
b3 = bullets["bullet3"]
b4 = bullets["bullet4"]
b5 = bullets["bullet5"]
b6 = bullets["bullet6"]
b7 = bullets["bullet7"]

dc_id = {
    1: "Miami FL, USA",
    2: "Amsterdam, NL",
    3: "Miami FL, USA",
    4: "Amsterdam, NL",
    5: "Singapore, SG",
}


@Client.on_message(filters.command(["info", "whois"]))
async def whois(bot, message):
    global chat
    msg = await message.reply_text("`Processing...`")
    if message.reply_to_message:
        user = message.reply_to_message.from_user.id
    elif len(message.text.split(" ", 1)) == 1 and not message.reply_to_message:
        user = message.from_user.id
        chat = message.chat.id
        t = "Chat id: {}".format(chat)

    elif len(message.text.split(" ", 1)) == 2 and not message.reply_to_message:
        user = message.text.split(" ", 1)[1]
    else:
        return await msg.edit("`Give a username or reply to a user..`")
    try:
        ui = await bot.get_users(user)
    except Exception as e:
        return await msg.edit("`Failed to get user`")
    xio = f"{ui.dc_id} | {dc_id[ui.dc_id]}" if ui.dc_id else "Unknown"
    ui_text = [
        f"  {b3} <b>User-info of <i>{ui.mention}</i> :</b>\n\n",
        f"  {b1} <b>Firstname : <i>{ui.first_name}</i></b>\n",
        f"  {b1} <b>Lastname : <i>{ui.last_name}</i></b>\n" if ui.last_name else "",
        (f"  {b1} <b>Username :</b> <code>@{ui.username}</code>\n" if ui.username else ""),
        f"  {b1} <b>User ID :</b> <code>{ui.id}</code>\n",
        f"  {b2} <b>User DCID : <i>{xio}</i></b>\n",
        f"  {b2} <b>Premium User : <i>{ui.is_premium}</i></b>\n"
        f"  {b2} <b>Status : <i>{ui.status}</i></b>\n",
        f"  {b2} <b>Is Bot : <i>{'Yes' if ui.is_bot else 'No'}</i></b>\n",
        f"  {b2} <b>Is Scam : <i>{'Yes' if ui.is_scam else 'No'}</i></b>\n",
        f"  {b2} <b>Is Mutual : <i>{'Yes' if ui.is_mutual_contact else 'No'}</i></b>\n",
        f"  {b2} <b>Is Verified : <i>{'Yes' if ui.is_verified else 'No'}</i></b> \n",
        f"  {b2} <b>This Chat ID : <i>{message.chat.id}</i></b>\n",
    ]
    pic = ui.photo.big_file_id if ui.photo else None
    if pic is not None:
        await msg.delete()
        photo = await bot.download_media(pic)
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo,
            caption="".join(ui_text),
            reply_to_message_id=message.id,
        )
        if os.path.exists(photo):
            os.remove(photo)
    else:
        await msg.edit("".join(ui_text))

@Client.on_message(filters.command(["chatinfo", "cinfo"]))
async def chat_info(c, m):
    # Check if the command has an argument (chat ID)
    if len(m.command) > 1:
        chat_id = m.command[1]
    else:
        chat_id = m.chat.id
    s = await m.reply_text("`Processing...`")
    try:
        cht = await c.get_chat(chat_id)
        msg = f"**❖ Chat Info** \n\n"
        msg += f"**⦾ Chat Title :** `{cht.title}` \n"
        msg += f"**⦾ Chat-ID :** `{cht.id}` \n"
        msg += f"**⦾ Verified :** `{cht.is_verified}` \n"
        msg += f"**⦾ Is Scam :** `{cht.is_scam}` \n"
        if cht.dc_id:
            msg += f"**⦾ Chat DC :** `{cht.dc_id}` \n"
        if cht.username:
            msg += f"**⦾ Chat Username :** `{cht.username}` \n"
        if cht.description:
            msg += f"**â¦¾ Chat Description :** `{cht.description}` \n"
        msg += f"**⦾ Chat Members Count :** `{cht.members_count}` \n"
        if cht.photo:
            kek = await c.download_media(cht.photo.big_file_id)
            await c.send_photo(m.chat.id, photo=kek, caption=msg)
            await s.delete()
            os.remove(kek)
        else:
            await s.edit(msg)
    except Exception as e:
        await s.edit(f"**An error occurred:** `{str(e)}`")


# Define handlers for different types of messages
@app.on_message(filters.video)
async def handle_video(bot, message):
    # Handle video message
    await message.reply_text(f"Video file ID: {message.video.file_id}")

#@app.on_message(filters.sticker)
async def handle_sticker(bot, message):
    # Handle sticker message
    await message.reply_text(f"Sticker file ID: {message.sticker.file_id}")

#@app.on_message(filters.photo)
async def handle_photo(bot, message):
    # Handle photo message
    await message.reply_text(f"Photo file ID: {message.photo.file_id}")

@app.on_message(filters.document)
async def handle_document(bot, message):
    # Handle document message
    await message.reply_text(f"Document file ID: {message.document.file_id}")

# Define handlers for voice and audio messages
@app.on_message(filters.voice)
async def handle_voice(bot, message):
    # Handle voice message
    await message.reply_text(f"Voice file ID: {message.voice.file_id}")

@app.on_message(filters.audio)
async def handle_audio(bot, message):
    # Handle audio message
    await message.reply_text(f"Audio file ID: {message.audio.file_id}")
    
