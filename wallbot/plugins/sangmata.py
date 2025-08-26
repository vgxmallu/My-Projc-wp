
from pyrogram import filters
from pyrogram.types import Message

from wallbot.database.sangmata_db import (
    add_userdata,
    cek_userdata,
    get_userdata,
    is_sangmata_on,
    sangmata_off,
    sangmata_on,
)
from wallbot import wbot as app




# Check user that change first_name, last_name and usernaname
@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot,
    group=5,
)
async def cek_mataa(_, ctx):
    if ctx.sender_chat or not await is_sangmata_on(ctx.chat.id):
        return
    if not await cek_userdata(ctx.from_user.id):
        return await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    usernamebefore, first_name, lastname_before = await get_userdata(ctx.from_user.id)
    msg = ""
    if (
        usernamebefore != ctx.from_user.username
        or first_name != ctx.from_user.first_name
        or lastname_before != ctx.from_user.last_name
    ):
        msg += f"{ctx.from_user.mention} [<code>{ctx.from_user.id}</code>] Has "
    if usernamebefore != ctx.from_user.username:
        usernamebefore = f"@{usernamebefore}" if usernamebefore else "<code>No Username</code>",
        usernameafter = (
            f"@{ctx.from_user.username}"
            if ctx.from_user.username
            else "<code>No Username</code>",
        )
        msg += "Changed username from {} to {}.".format(usernamebefore, usernameafter)
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if first_name != ctx.from_user.first_name:
        msg += "Changed first name from {} to {}.".format(
            first_name, ctx.from_user.first_name
        )
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if lastname_before != ctx.from_user.last_name:
        lastname_before = lastname_before or "<code>No Last Name</code>"
        lastname_after = ctx.from_user.last_name or "<code>No Last Name</code>"
        msg += "Changed last name from {} to {}.".format(
            lastname_before, lastname_after
        )
        await add_userdata(
            ctx.from_user.id,
            ctx.from_user.username,
            ctx.from_user.first_name,
            ctx.from_user.last_name,
        )
    if msg != "":
        await ctx.reply_text(msg, quote=False)


@app.on_message(
    filters.group
    & filters.command("sangmata_set")
    & ~filters.bot
    & ~filters.via_bot
)
async def set_mataa(_, ctx):
    gg = await ctx.delete()
    if len(ctx.command) == 1:
        return await ctx.reply_text(
            "Use <code>/{} on</code>, to enable. If you want disable, you can use off parameter.".format(ctx.command[0])
        )
    if ctx.command[1] == "on":
        cekset = await is_sangmata_on(ctx.chat.id)
        if cekset:
            await ctx.reply_text("I am already enabled in your groups.")
        else:
            await sangmata_on(ctx.chat.id)
            await ctx.reply_text("I am enabled in your groups.")
    elif ctx.command[1] == "off":
        cekset = await is_sangmata_on(ctx.chat.id)
        if not cekset:
            await ctx.reply_text("I am already disabled in your groups.")
        else:
            await sangmata_off(ctx.chat.id)
            await ctx.reply_text("I am disabled in your group.")
    else:
        await ctx.reply_text("Unknown parameter, use only on/off parameter.")
