import re
import time
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from wallbot import wbot as app

from wallbot.database.afk_db import add_afk, cleanmode_off, cleanmode_on, is_afk, remove_afk
from wallbot.utils.human_read import get_readable_time2
from wallbot.utils.clea_md import put_cleanmode


#[<code>{}</code>]
# Handle set AFK Command
@app.on_message(filters.command("afk"))
async def active_afk(_, ctx):
    if ctx.sender_chat:
        return await ctx.reply_text("This feature not supported for channel.", del_in=6)
    user_id = ctx.from_user.id
    verifier, reasondb = await is_afk(user_id)
    if verifier:
        await remove_afk(user_id)
        try:
            afktype = reasondb["type"]
            timeafk = reasondb["time"]
            data = reasondb["data"]
            reasonafk = reasondb["reason"]
            seenago = get_readable_time2((int(time.time() - timeafk)))
            if afktype == "animation":
                send = (
                    await ctx.reply_animation(
                        data,
                        caption="**{}** is back online and was away for {}\n\n".format(
                            ctx.from_user.mention, ctx.from_user.id, seenago
                        ),
                    )
                    if str(reasonafk) == "None"
                    else await ctx.reply_animation(
                        data,
                        caption="**{}** is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                            ctx.from_user.mention,
                            ctx.from_user.id,
                            seenago,
                            reasonafk,
                        ),
                    )
                )
            elif afktype == "photo":
                send = (
                    await ctx.reply_photo(
                        photo=f"downloads/{user_id}.jpg",
                        caption="**{}** is back online and was away for {}\n\n".format(
                            ctx.from_user.mention, ctx.from_user.id, seenago
                        ),
                    )
                    if str(reasonafk) == "None"
                    else await ctx.reply_photo(
                        photo=f"downloads/{user_id}.jpg",
                        caption="**{}** is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                            ctx.from_user.first_name, ctx.from_user.id, seenago, reasonafk
                        ),
                    )
                )
            elif afktype == "text":
                send = await ctx.reply_text(
                    "**{}** is back online and was away for {}\n\n".format(
                        ctx.from_user.mention, ctx.from_user.id, seenago
                    ),
                    disable_web_page_preview=True,
                )
            elif afktype == "text_reason":
                send = await ctx.reply_text(
                    "**{}** is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                        ctx.from_user.mention,
                        ctx.from_user.id,
                        seenago,
                        reasonafk,
                    ),
                    disable_web_page_preview=True,
                )
        except Exception:
            send = await ctx.reply_text(
                "**{}** is back online".format(
                    ctx.from_user.first_name, ctx.from_user.id
                ),
                disable_web_page_preview=True,
            )
        await put_cleanmode(ctx.chat.id, send.id)
        return
    if len(ctx.command) == 1 and not ctx.reply_to_message:
        details = {
            "type": "text",
            "time": time.time(),
            "data": None,
            "reason": None,
        }
    elif len(ctx.command) > 1 and not ctx.reply_to_message:
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        details = {
            "type": "text_reason",
            "time": time.time(),
            "data": None,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.animation:
        _data = ctx.reply_to_message.animation.file_id
        details = {
            "type": "animation",
            "time": time.time(),
            "data": _data,
            "reason": None,
        }
    elif len(ctx.command) > 1 and ctx.reply_to_message.animation:
        _data = ctx.reply_to_message.animation.file_id
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        details = {
            "type": "animation",
            "time": time.time(),
            "data": _data,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.photo:
        await app.download_media(ctx.reply_to_message, file_name=f"{user_id}.jpg")
        details = {
            "type": "photo",
            "time": time.time(),
            "data": None,
            "reason": None,
        }
    elif len(ctx.command) > 1 and ctx.reply_to_message.photo:
        await app.download_media(ctx.reply_to_message, file_name=f"{user_id}.jpg")
        _reason = ctx.text.split(None, 1)[1].strip()
        details = {
            "type": "photo",
            "time": time.time(),
            "data": None,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.sticker:
        if ctx.reply_to_message.sticker.is_animated:
            details = {
                "type": "text",
                "time": time.time(),
                "data": None,
                "reason": None,
            }
        else:
            await app.download_media(ctx.reply_to_message, file_name=f"{user_id}.jpg")
            details = {
                "type": "photo",
                "time": time.time(),
                "data": None,
                "reason": None,
            }
    elif len(ctx.command) > 1 and ctx.reply_to_message.sticker:
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        if ctx.reply_to_message.sticker.is_animated:
            details = {
                "type": "text_reason",
                "time": time.time(),
                "data": None,
                "reason": _reason,
            }
        else:
            await app.download_media(ctx.reply_to_message, file_name=f"{user_id}.jpg")
            details = {
                "type": "photo",
                "time": time.time(),
                "data": None,
                "reason": _reason,
            }
    else:
        details = {
            "type": "text",
            "time": time.time(),
            "data": None,
            "reason": None,
        }

    await add_afk(user_id, details)
    send = await ctx.reply_text(
        "{} [<code>{}</code>] is now AFK!.".format(ctx.from_user.mention, ctx.from_user.id)
    )
    await put_cleanmode(ctx.chat.id, send.id)


@app.on_message(filters.command("afkdel"))
async def afk_state(_, ctx):
    if not ctx.from_user:
        return
    if len(ctx.command) == 1:
        return await ctx.reply_text(
            "**Usage:**\n/{} [ENABLE|DISABLE] to enable or disable auto delete message.".format(ctx.command[0]), del_in=6
        )
    chat_id = ctx.chat.id
    state = ctx.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await cleanmode_on(chat_id)
        await ctx.reply_text("Enabled auto delete AFK message in this chat.")
    elif state == "disable":
        await cleanmode_off(chat_id)
        await ctx.reply_text("Disabled auto delete AFK message.")
    else:
        await ctx.reply_text("**Usage:**\n/{} [ENABLE|DISABLE] to enable or disable auto delete message.".format(cmd=ctx.command[0]), del_in=6)


# Detect user that AFK based on Yukki Repo
@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot,
    group=1,
)
async def afk_watcher_func(self: Client, ctx):
    if ctx.sender_chat:
        return
    userid = ctx.from_user.id
    user_name = ctx.from_user.mention
    if ctx.entities:
        possible = ["/afk", f"/afk@{self.me.username}", "!afk"]
        message_text = ctx.text or ctx.caption
        for entity in ctx.entities:
            try:
                if (
                    entity.type == enums.MessageEntityType.BOT_COMMAND
                    and (message_text[0 : 0 + entity.length]).lower() in possible
                ):
                    return
            except UnicodeDecodeError:  # Some weird character make error
                return

    msg = ""
    replied_user_id = 0

    # Self AFK
    verifier, reasondb = await is_afk(userid)
    if verifier:
        await remove_afk(userid)
        try:
            afktype = reasondb["type"]
            timeafk = reasondb["time"]
            data = reasondb["data"]
            reasonafk = reasondb["reason"]
            seenago = get_readable_time2((int(time.time() - timeafk)))
            if afktype == "text":
                msg += "**{}** [<code>{}</code>] is back online and was away for {}\n\n".format(
                    user_name, userid, seenago
                )
            if afktype == "text_reason":
                msg += "**{}** [<code>{}</code>] is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                    user_name, userid, seenago, reasonafk
                )
            if afktype == "animation":
                if str(reasonafk) == "None":
                    send = await ctx.reply_animation(
                        data,
                        caption="**{}** [<code>{}</code>] is back online and was away for {}\n\n".format(
                            user_name, userid, seenago
                        ),
                    )
                else:
                    send = await ctx.reply_animation(
                        data,
                        caption="**{}** [<code>{}</code>] is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                            user_name, userid, seenago, reasonafk
                        ),
                    )
            if afktype == "photo":
                if str(reasonafk) == "None":
                    send = await ctx.reply_photo(
                        photo=f"downloads/{userid}.jpg",
                        caption="**{}** [<code>{}</code>] is back online and was away for {}\n\n".format(
                            user_name, userid, seenago
                        ),
                    )
                else:
                    send = await ctx.reply_photo(
                        photo=f"downloads/{userid}.jpg",
                        caption="**{}** [<code>{}</code>] is back online and was away for {}\n\n**Reason:** `{}`\n\n".format(
                            user_name, userid, seenago, reasonafk
                        ),
                    )
        except:
            msg += "**{usr}** [<code>{id}</code>] is back online".format(user_name, userid)

    # Replied to a User which is AFK
    if ctx.reply_to_message:
        try:
            replied_first_name = ctx.reply_to_message.from_user.mention
            replied_user_id = ctx.reply_to_message.from_user.id
            verifier, reasondb = await is_afk(replied_user_id)
            if verifier:
                try:
                    afktype = reasondb["type"]
                    timeafk = reasondb["time"]
                    data = reasondb["data"]
                    reasonafk = reasondb["reason"]
                    seenago = get_readable_time2((int(time.time() - timeafk)))
                    if afktype == "text":
                        msg += strings("is_afk_msg_no_r").format(
                            replied_first_name, replied_user_id, seenago
                        )
                    if afktype == "text_reason":
                        msg += "**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                            replied_first_name,
                            replied_user_id,
                            seenago,
                            reasonafk,
                        )
                    if afktype == "animation":
                        if str(reasonafk) == "None":
                            send = await ctx.reply_animation(
                                data,
                                caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                    replied_first_name,
                                    replied_user_id,
                                    seenago,
                                ),
                            )
                        else:
                            send = await ctx.reply_animation(
                                data,
                                caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                    replied_first_name,
                                    replied_user_id,
                                    seenago,
                                    reasonafk,
                                ),
                            )
                    if afktype == "photo":
                        if str(reasonafk) == "None":
                            send = await ctx.reply_photo(
                                photo=f"downloads/{replied_user_id}.jpg",
                                caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                    replied_first_name,
                                    replied_user_id,
                                    seenago,
                                ),
                            )
                        else:
                            send = await ctx.reply_photo(
                                photo=f"downloads/{replied_user_id}.jpg",
                                caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                    replied_first_name,
                                    replied_user_id,
                                    seenago,
                                    reasonafk,
                                ),
                            )
                except Exception:
                    msg += "{} [<code>{}</code>] is AFK!.".format(
                        replied_first_name, replied_user_id
                    )
        except:
            pass

    # If username or mentioned user is AFK
    if ctx.entities:
        entity = ctx.entities
        j = 0
        for _ in range(len(entity)):
            if (entity[j].type) == enums.MessageEntityType.MENTION:
                found = re.findall("@([_0-9a-zA-Z]+)", ctx.text)
                try:
                    get_user = found[j]
                    user = await app.get_users(get_user)
                    if user.id == replied_user_id:
                        j += 1
                        continue
                except:
                    j += 1
                    continue
                verifier, reasondb = await is_afk(user.id)
                if verifier:
                    try:
                        afktype = reasondb["type"]
                        timeafk = reasondb["time"]
                        data = reasondb["data"]
                        reasonafk = reasondb["reason"]
                        seenago = get_readable_time2((int(time.time() - timeafk)))
                        if afktype == "text":
                            msg += "**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                user.first_name[:25], user.id, seenago
                            )
                        if afktype == "text_reason":
                            msg += "**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                user.first_name[:25],
                                user.id,
                                seenago,
                                reasonafk,
                            )
                        if afktype == "animation":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_animation(
                                    data,
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                        user.first_name[:25], user.id, seenago
                                    ),
                                )
                            else:
                                send = await ctx.reply_animation(
                                    data,
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                        user.first_name[:25],
                                        user.id,
                                        seenago,
                                        reasonafk,
                                    ),
                                )
                        if afktype == "photo":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user.id}.jpg",
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                        user.first_name[:25], user.id, seenago
                                    ),
                                )
                            else:
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user.id}.jpg",
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                        user.first_name[:25],
                                        user.id,
                                        seenago,
                                        reasonafk,
                                    ),
                                )
                    except:
                        msg += "{} [<code>{}</code>] is AFK!.".format(
                            user.first_name[:25], user.id
                        )
            elif (entity[j].type) == enums.MessageEntityType.TEXT_MENTION:
                try:
                    user_id = entity[j].user.id
                    if user_id == replied_user_id:
                        j += 1
                        continue
                    first_name = entity[j].user.first_name
                except:
                    j += 1
                    continue
                verifier, reasondb = await is_afk(user_id)
                if verifier:
                    try:
                        afktype = reasondb["type"]
                        timeafk = reasondb["time"]
                        data = reasondb["data"]
                        reasonafk = reasondb["reason"]
                        seenago = get_readable_time2((int(time.time() - timeafk)))
                        if afktype == "text":
                            msg += "**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                first_name[:25], user_id, seenago
                            )
                        if afktype == "text_reason":
                            msg += "**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                first_name[:25],
                                user_id,
                                seenago,
                                reasonafk,
                            )
                        if afktype == "animation":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_animation(
                                    data,
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                        first_name[:25], user_id, seenago
                                    ),
                                )
                            else:
                                send = await ctx.reply_animation(
                                    data,
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                        first_name[:25],
                                        user_id,
                                        seenago,
                                        reasonafk,
                                    ),
                                )
                        if afktype == "photo":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user_id}.jpg",
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n".format(
                                        first_name[:25], user_id, seenago
                                    ),
                                )
                            else:
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user_id}.jpg",
                                    caption="**{}** [<code>{}</code>] is AFK since {} ago.\n\n**Reason:** {}\n\n".format(
                                        first_name[:25],
                                        user_id,
                                        seenago,
                                        reasonafk,
                                    ),
                                )
                    except:
                        msg += "{} [<code>{}</code>] is AFK!.".format(first_name[:25], user_id)
            j += 1
    if msg != "":
        try:
            send = await ctx.reply_text(msg, disable_web_page_preview=True)
        except:
            pass
    try:
        await put_cleanmode(ctx.chat.id, send.id)
    except:
        pass
