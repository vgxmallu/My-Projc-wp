from pyrogram import enums, filters
from pyrogram.errors import UserIsBlocked, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from wallbot import wbot as app


@app.on_message(filters.command(["copy"]))
async def copymsg(_, message):
    if len(message.command) == 1:
        if not message.reply_to_message:
            return await message.reply("Please reply to the message you want to copy.")
        try:
            await message.reply_to_message.copy(
                message.from_user.id,
                caption_entities=message.reply_to_message.entities,
                reply_markup=message.reply_to_message.reply_markup,
            )
            return await message.reply_text("Message sent successfully..")
        except UserIsBlocked:
            return await message.reply(
                "Silahkan PM Saya untuk mengcopy pesan ke chat pribadi..",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="💬 Chat",
                                url=f"https://t.me/GojoSatoru_Xbot",
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            return await message.reply(f"ERROR: {str(e)}")
    elif message.reply_to_message:
        try:
            idtujuan = message.command[1]
            userstat = await app.get_chat_member(-1001686184174, message.from_user.id)
            if (
                userstat.status
                not in [
                    enums.ChatMemberStatus.ADMINISTRATOR,
                    enums.ChatMemberStatus.OWNER,
                ]
                and message.from_user.id != 2024984460
            ):
                return await message.reply_text("😌")
            await message.reply_to_message.copy(
                idtujuan,
                caption_entities=message.reply_to_message.entities,
                reply_markup=message.reply_to_message.reply_markup,
            )
            return await message.reply_text("Message sent successfully.")
        except UserNotParticipant:
            return await message.reply("This command is only for my owner.")
        except Exception as e:
            return await message.reply(f"ERROR: {e}")
    else:
        await message.reply("Please reply to the message you want to forward.")


@app.on_message(filters.command(["forward"]))
async def forwardmsg(_, message):
    if len(message.command) == 1:
        if not message.reply_to_message:
            return await message.reply("Please reply to the message you want to copy.")
        try:
            await message.reply_to_message.forward(message.from_user.id)
            return await message.reply_text("Message sent successfully.")
        except UserIsBlocked:
            return await message.reply(
                "Please PM me to forward the message to private chat.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="💬 Chat",
                                url=f"https://t.me/GojoSatoru_Xbot",
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            return await message.reply(f"ERROR: {str(e)}")
    elif message.reply_to_message:
        try:
            idtujuan = message.command[1]
            userstat = await app.get_chat_member(-1001686184174, message.from_user.id)
            if (
                userstat.status
                not in [
                    enums.ChatMemberStatus.ADMINISTRATOR,
                    enums.ChatMemberStatus.OWNER,
                ]
                and message.from_user.id != 2024984460
            ):
                return await message.reply_text("😴")
            await message.reply_to_message.forward(idtujuan)
            return await message.reply_text("Message sent successfully.")
        except UserNotParticipant:
            return await message.reply("This command is only for my owner.")
        except Exception as e:
            return await message.reply(f"ERROR: {e}")
    else:
        await message.reply("Please reply to the message you want to forward.")
