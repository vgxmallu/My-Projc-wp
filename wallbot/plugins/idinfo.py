import os
from pyrogram.types import Message
from pyrogram import Client, filters
from pyrogram.errors import UsernameInvalid, UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton






# User info

@Client.on_message(filters.private & filters.command("uinfo"))
async def uinfo(bot, hydrix):
    text = f"""
╭─────[ɪɴғᴏ]─────〄
├⍟ **Fɪʀsᴛ ɴᴀᴍᴇ** : {hydrix.from_user.first_name}
├⍟ **Lᴀsᴛ ɴᴀᴍᴇ** : {hydrix.from_user.last_name}
├⍟ **Usᴇʀɴᴀᴍᴇ** : @{hydrix.from_user.username}
├⍟ **Usᴇʀ ɪᴅ** : `{hydrix.from_user.id}`
├⍟ **Mᴇɴᴛɪᴏɴ** : {hydrix.from_user.mention}
├⍟ **Dᴀᴛᴀᴄᴇɴᴛᴇʀ** : {hydrix.from_user.dc_id}
╰───────────〄
"""
    await hydrix.reply_text(text=text)

# Group info



# id finder

@Client.on_message(filters.private & filters.forwarded)
async def forwarded(_, msg):
    if msg.forward_from:
        text = "Forwarded! \n\n"
        if msg.forward_from.is_bot:
            text += "**ʙᴏᴛ**"
        else:
            text += "**User**"
        text += f'\n{msg.forward_from.first_name} \n'
        if msg.forward_from.username:
            text += f'@{msg.forward_from.username} \nID : `{msg.forward_from.id}`'
        else:
            text += f'ID : `{msg.forward_from.id}`'
        await msg.reply(text, quote=True)
    else:
        hidden = msg.forward_sender_name
        if hidden:
            await msg.reply(
                f"Forward detected but, {hidden} Has enabled forward privacy, so i cant get there id.",
                quote=True,
            )
        else:
            text = f"Forward Detection. \n\n"
            if msg.forward_from_chat.type == "Channel":
                text += "**Channel**"
            if msg.forward_from_chat.type == "supergroup":
                text += "**Group**"
            text += f'\n{msg.forward_from_chat.title} \n'
            if msg.forward_from_chat.username:
                text += f'@{msg.forward_from_chat.username} \n'
                text += f'ɪᴅ : `{msg.forward_from_chat.id}`'
            else:
                text += f'ɪᴅ : `{msg.forward_from_chat.id}`'
            await msg.reply(text, quote=True)
# private id

@Client.on_message(filters.command("id"))
async def id_(bot: Client, msg: Message):
	if not msg.chat.type == "private":
		main = f"This {msg.chat.type}'s ɪᴅ is `{msg.chat.id}`"
		if msg.reply_to_message:
			if msg.reply_to_message.from_user:
				main = f"{msg.reply_to_message.from_user.first_name} your ɪᴅ is `{msg.reply_to_message.from_user.id}`"
				if msg.reply_to_message.sticker:
					main += f"\n\nYour Requested Sticker ID is `{msg.reply_to_message.sticker.file_id}`"

		await msg.reply(main)
	else:
		if len(msg.command) == 1:
			await msg.reply(f"Your id is `{msg.from_user.id}`", quote=True)
		if len(msg.command) == 2:
			try:
				uname = msg.command[1]
				if uname.startswith("@"):
					uname = uname[1:]
				try:
					user = await bot.get_users(uname)
					name = user.mention
					if len(user.first_name) <= 20:
						pass
					elif user.is_bot:
						name = "This Bot"
					else:
						name = "This User"
				except IndexError:
					user = await bot.get_chat(uname)
					name = '@'+user.username if user.username else user.title
				id = user.id
				await msg.reply(f"{name}'s ɪᴅ ɪs `{id}`", quote=True)
			except UsernameInvalid:
				await msg.reply("Invalid Username.", quote=True)
			except UsernameNotOccupied:
				await msg.reply("this username is not occupied by anyone.", quote=True)


# Dc finder

@Client.on_message(filters.private & filters.command(["dc"]))
async def dc(bot, update):
    text = START_TEXT.format(update.from_user.dc_id)
    reply_markup = START_BUTTON
    await update.reply_text(
        text=text,
        disable_web_page_preview=True,
        quote=True
    )

START_TEXT = "Your  Data center [DC] is `{}`"
