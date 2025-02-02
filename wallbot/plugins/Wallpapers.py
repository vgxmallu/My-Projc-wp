import asyncio
import random
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram import filters
from random import choice
import requests
from wallbot import wbot
from wallbot.images_db.walls import ANIM_PICS, ANIMALS_PICS, LOGO_PICS, CARS_PICS, DROWIG_PICS, FUNNY_PICS, ENTERT_PICS, GAME_PICS, LOVE_PICS, MUSIC_PICS, NATURE_PICS, SAYING_PICS, SPACE_PICS, COMIC_PICS, SPORT_PICS, PATTER_PICS, TECHNO_PICS, DESIN_PICS, HOLDAY_PICS, PEOPL_PICS, OTHERS_PICS                      
from config import LOG_CHANNEL, Telegram, DB_URL, DB_NAME
#from wallbot.untils import pyro_cooldown

from wallbot.handlers.broadcast import broadcast
from wallbot.handlers.check_user import handle_user_status
from wallbot.handlers.database import Database


DLE_TIME = 240
db = Database(DB_URL, DB_NAME)

#°st
MW = """
📣 **LOG ALERT** 🏞️🤖

📛**Triggered Command** : /start
👤**Name** : {}
👾**Username** : @{}
💾**DC** : {}
♐**ID** : `{}`
🤖**BOT** : @Wallpepers_xbot

#new_wall_user
"""
cap_txt = """
Hey there {}
Here is the Wallpapers Module, we are just collect wallpapers from defferent platforms.
You can simply to use here. just press down below buttons;)
"""
@wbot.on_message(filters.private & filters.command("start"))
async def wall_hhstart(client, message):
    chat_id = message.from_user.id
    if not await db.is_user_exist(chat_id):
        data = await client.get_me()
        await db.add_user(chat_id)
        if LOG_CHANNEL:
            await client.send_message(
                LOG_CHANNEL,
                f"🥳NEWUSER🥳 \n\n😼New User [{message.from_user.first_name}](tg://user?id={message.from_user.id}) 😹started !!",
            )
        else:
            logging.info(f"🥳NewUser🥳 :- 😼Name : {message.from_user.first_name} 😹ID : {message.from_user.id}")
            
    em=await message.reply_photo(
        photo="https://envs.sh/m5m.jpg",
        caption=cap_txt.format(message.from_user.first_name),
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Channel 📣", "Group 🎵"
            ],[
                "Wallpapers Collections🏞️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    )
    await message.react(choice(Telegram.EMOJIS))
    await em.react(choice(Telegram.EMOJIS_2))
    await asyncio.sleep(DLE_TIME)
    await message.delete()
    await client.send_message(LOG_CHANNEL, MW.format(message.from_user.mention, message.from_user.username, message.from_user.dc_id, message.from_user.id))
    return

@wbot.on_message(filters.private & filters.regex("Group 🎵")) 
async def wallchannnl(client, message):
    m2 = await message.reply_text("https://t.me/music_X_galaxy")
    await asyncio.sleep(DLE_TIME)
    await m2.delete()
    await message.delete()

@wbot.on_message(filters.private & filters.regex("Channel 📣")) 
async def wallgropnl(client, message):
    m2 = await message.reply_text("https://t.me/XBOTS_X")
    await asyncio.sleep(DLE_TIME)
    await m2.delete()
    await message.delete()
#==================BOTTON-REMOVING==============
@wbot.on_message(filters.command("remove_bt")) 
async def reply_rmv(client, message):
    ab = await message.reply_text(
        text="Click Down Botton to Remove keyboard button\n`Message will be delete 4s`", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await ab.delete()
    await message.delete()
    
        
@wbot.on_message(filters.regex("✖️Close✖️"))
async def close_myr2(client, message):
    ae = await message.reply_text(
        text="Bottons removed ✅", 
        reply_markup=ReplyKeyboardRemove() 
    ) 
    await asyncio.sleep(4)
    await ae.delete()
    await message.delete()

@wbot.on_message(filters.private & filters.regex("Cats 🐈"))
async def wall_anim(client, message):
    r = requests.get("https://api.thecatapi.com/v1/images/search")
    if r.status_code == 200:
        data = r.json()
        cat_url = data[0]["url"]
        if cat_url.endswith(".gif"):
            await message.reply_photo(
                photo=cat_url, 
                caption="meow 😺😼", 
                reply_markup=ReplyKeyboardMarkup(
                    [[
                        "Cats 🐈"
                    ],[
                        "⬅️", "✖️Close✖️"
                    ]], 
                    resize_keyboard=True
                ) 
            ) 
            await message.reply_text(morew)
            await asyncio.sleep(4)
            await message.delete()
    else:
        await message.reply_text("Failed to refresh cat picture 🙀")
    

#=================ZEDGE-WALLPEPERS======================

cap_wall = """
Hey {}
Here is the Wallpapers Module, we are just collect wallpapers from defferent platforms.
You can simply to use here.

Just click the below bottons:
"""

wall_tottal = """
```
W Categories | Total Wallpapers
________________________________
Anime-----------> 486
Animal----------> 752
Logos-----------> 353
Cars&Bike-------> 330
Drawings--------> 0
Funny-----------> 0
Entertainment---> 0
Game-s----------> 0
Love------------> 0
Music-----------> 0
Natural---------> 0
Saying----------> 0
Space-----------> 0
Comic-----------> 0
Sports----------> 0
Pattern---------> 0
Technology------> 0
Designs---------> 0
Holiday---------> 0
People----------> 0
________________________________
```
"""

morew = """
If you want More Wallpapers 🏞️like this?, just touch below button again..;)
"""
@wbot.on_message(filters.private & filters.regex("🔽") | filters.private & filters.regex("🛟 CATEGORIES 🛟") | filters.private & filters.regex("Page 2️⃣") | filters.private & filters.regex("Page 1️⃣") | filters.private & filters.regex("➖➖➖➖➖➖➖➖➖➖")) 
async def delete(client, message):
    await message.delete()
    
@wbot.on_message(filters.private & filters.regex("Wallpapers Collections🏞️") & pyro_cooldown.wait(10)) 
async def wallpaper(client, message):
    m1 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.first_name), 
        reply_markup=ReplyKeyboardMarkup(
            [[
               "Page 1️⃣", "✖️Close✖️", "➡️"
            ],[
                "🧿 CATEGORIES 🧿"
            ],[
                "Anime 🧚", "Animals 🦁", "Logos ♑"
            ],[
                "Car&Bike 🏎️", "Drownings 🎑", "Funny 😄"
            ],[
                "Entertainment 🧑‍🎤", "Game 🎮", "Love ❤️"
            ],[
                "Music 🎵", "Nature 🍃", "Sayings 📝"
            ],[
                "Cats 🐈", "Dogs🐕"
            ],[
                "➖➖➖➖➖➖➖➖➖➖"
            ]], 
            resize_keyboard=True
        ) 
    )
    #w1 = await message.reply_text(wall_tottal)
    await message.delete()
    await asyncio.sleep(DLE_TIME)
    await m1.delete()
    await w1.delete()


#=================REGEX=====================
@wbot.on_message(filters.private & filters.regex("⬅️") | filters.private & filters.regex("Wallpapers 🌇")) 
async def wallpaper2(client, message):
    m2 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.first_name),
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Page 1️⃣", "✖️Close✖️", "➡️"
            ],[
                "🛟 CATEGORIES 🛟"
            ],[
                "Anime 🧚", "Animals 🦁", "Logos ♑"
            ],[
                "Car&Bike 🏎️", "Drownings 🎑", "Funny 😄"
            ],[
                "Entertainment 🧑‍🎤", "Game 🎮", "Love ❤️"
            ],[
                "Music 🎵", "Nature 🍃", "Sayings 📝"
            ],[
                "Cats 🐈", "Dogs🐕"
            ],[
                "➖➖➖➖➖➖➖➖➖➖"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.delete()
    await asyncio.sleep(DLE_TIME)
    await m2.delete()

@wbot.on_message(filters.private & filters.regex("➡️"))
async def wallpaper3(client, message):
    m3 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.mention), 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Page 2️⃣", "✖️Close✖️", "⬅️"
            ],[
                "🛟 CATEGORIES 🛟"
            ],[
                "Space 🌠", "Comics 🦸", "Sports ⚽"
            ],[
                "Pattern ☸️", "Technology 📱", "Designs ✨"
            ],[
                "Holiday 🏖️", "People 🧑‍🤝‍🧑", "Scenery" #".Others 🤷"
            ],[
                "➖➖➖➖➖➖➖➖➖➖"
            ]], 
            resize_keyboard=True
        ) 
    )
    await message.delete()
    await asyncio.sleep(DLE_TIME)
    await m3.delete()
    
#=============================PG1=============================
@wbot.on_message(filters.private & filters.regex("Anime 🧚"))
async def wall_anim(client, message):
    await message.reply_photo(
        photo=random.choice(ANIM_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Anime 🧚"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Animals 🦁"))
async def wall_animal(client, message):
    await message.reply_photo(
        photo=random.choice(ANIMALS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Animals 🦁"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Logos ♑"))
async def wall_logo(client, message):
    await message.reply_photo(
        photo=random.choice(LOGO_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Logos ♑"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Car&Bike 🏎️"))
async def wall_car(client, message):
    await message.reply_photo(
        photo=random.choice(CARS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Car&Bike 🏎️"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Drownings 🎑"))
async def wall_drowi(client, message):
    await message.reply_photo(
        photo=random.choice(DROWIG_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Drownings 🎑"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Funny 😄"))
async def wall_funny(client, message):
    await message.reply_photo(
        photo=random.choice(FUNNY_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Funny 😄"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()

@wbot.on_message(filters.private & filters.regex("Entertainment 🧑‍🎤"))
async def wall_endet(client, message):
    await message.reply_photo(
        photo=random.choice(ENTERT_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Entertainment 🧑‍🎤"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Gamee 🎮"))
async def wall_game(client, message):
    await message.reply_photo(
        photo=random.choice(GAME_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Game 🎮"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Love ❤️"))
async def wall_lov(client, message):
    await message.reply_photo(
        photo=random.choice(LOVE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Love ❤️"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Music 🎵"))
async def wall_music(client, message):
    await message.reply_photo(
        photo=random.choice(MUSIC_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Music 🎵"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Nature 🍃"))
async def wall_natur(client, message):
    await message.reply_photo(
        photo=random.choice(NATURE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Nature 🍃"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
    
@wbot.on_message(filters.private & filters.regex("Sayings 📝"))
async def wall_sayin(client, message):
    await message.reply_photo(
        photo=random.choice(SAYING_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Sayings 📝"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
#========≠==================PG2====================
@wbot.on_message(filters.private & filters.regex("Space 🌠"))
async def wall_space(client, message):
    await message.reply_photo(
        photo=random.choice(SPACE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Space 🌠"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete() 
@wbot.on_message(filters.private & filters.regex("Comics 🦸"))
async def wall_comi(client, message):
    await message.reply_photo(
        photo=random.choice(COMIC_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Comics 🦸"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Sports ⚽"))
async def wall_spor(client, message):
    await message.reply_photo(
        photo=random.choice(SPORT_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Sports ⚽"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Pattern ☸️"))
async def wall_pattt(client, message):
    await message.reply_photo(
        photo=random.choice(PATTER_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Pattern ☸️"
            ],[
                "⬅️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Technology 📱"))
async def wall_texhno(client, message):
    await message.reply_photo(
        photo=random.choice(TECHNO_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Technology 📱"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Designs ✨"))
async def wall_desins(client, message):
    await message.reply_photo(
        photo=random.choice(DESIN_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Designs ✨"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Hollyday 🏖️"))
async def wall_hollyd(client, message):
    await message.reply_photo(
        photo=random.choice(HOLDAY_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Hollyday 🏖️"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("People 🧑‍🤝‍🧑"))
async def wall_peopl(client, message):
    await message.reply_photo(
        photo=random.choice(PEOPL_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "People 🧑‍🤝‍🧑"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Others 🤷"))
async def wall_other(client, message):
    await message.reply_photo(
        photo=random.choice(OTHERS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Others 🤷"
            ],[
                "➡️", "✖️Close✖️"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.reply_text(morew)
    await asyncio.sleep(4)
    await message.delete()
#=======================================================

              

#==================•BROADCAST•==================
@wbot.on_message(filters.private & filters.command("broadcast"))
async def broadcast_handler_open(_, m):
    if m.from_user.id not in AUTH_USERS:
        await m.delete()
        return
    if m.reply_to_message is None:
        await m.delete()
    else:
        await broadcast(m, db)

@wbot.on_message(filters.private & filters.command("stats"))
async def sts(c, m):
    if m.from_user.id not in AUTH_USERS:
        await m.delete()
        return
    sat = await m.reply_text(
        text=f"**Total Users in Database 📂:** `{await db.total_users_count()}`\n\n**Total Users with Notification Enabled 🔔 :** `{await db.total_notif_users_count()}`",
        quote=True
    )
    await m.delete()
    await asyncio.sleep(180)
    await sat.delete()

@wbot.on_message(filters.private & filters.command("ban_user"))
async def ban(c, m):
    if m.from_user.id not in AUTH_USERS:
        await m.delete()
        return
    if len(m.command) == 1:
        await m.reply_text(
            f"Use this command to ban 🛑 any user from the bot 🤖.\n\nUsage:\n\n`/ban_user user_id ban_duration ban_reason`\n\nEg: `/ban_user 1234567 28 You misused me.`\n This will ban user with id `1234567` for `28` days for the reason `You misused me`.",
            quote=True,
        )
        return

    try:
        user_id = int(m.command[1])
        ban_duration = int(m.command[2])
        ban_reason = " ".join(m.command[3:])
        ban_log_text = f"Banning user {user_id} for {ban_duration} days for the reason {ban_reason}."

        try:
            await c.send_message(
                user_id,
                f"You are Banned 🚫 to use this bot for **{ban_duration}** day(s) for the reason __{ban_reason}__ \n\n**Message from the admin 🤠**",
            )
            ban_log_text += "\n\nUser notified successfully!"
        except BaseException:
            traceback.print_exc()
            ban_log_text += (
                f"\n\n ⚠️ User notification failed! ⚠️ \n\n`{traceback.format_exc()}`"
            )
        await db.ban_user(user_id, ban_duration, ban_reason)
        print(ban_log_text)
        await m.reply_text(ban_log_text, quote=True)
    except BaseException:
        traceback.print_exc()
        await m.reply_text(
            f"Error occoured ⚠️! Traceback given below\n\n`{traceback.format_exc()}`",
            quote=True
        )

@wbot.on_message(filters.private & filters.command("unban_user"))
async def unban(c, m):
    if m.from_user.id not in AUTH_USERS:
        await m.delete()
        return
    if len(m.command) == 1:
        await m.reply_text(
            f"Use this command to unban 😃 any user.\n\nUsage:\n\n`/unban_user user_id`\n\nEg: `/unban_user 1234567`\n This will unban user with id `1234567`.",
            quote=True,
        )
        return

    try:
        user_id = int(m.command[1])
        unban_log_text = f"Unbanning user 🤪 {user_id}"

        try:
            await c.send_message(user_id, f"Your ban was lifted!")
            unban_log_text += "\n\n✅ User notified successfully! ✅"
        except BaseException:
            traceback.print_exc()
            unban_log_text += (
                f"\n\n⚠️ User notification failed! ⚠️\n\n`{traceback.format_exc()}`"
            )
        await db.remove_ban(user_id)
        print(unban_log_text)
        await m.reply_text(unban_log_text, quote=True)
    except BaseException:
        traceback.print_exc()
        await m.reply_text(
            f"⚠️ Error occoured ⚠️! Traceback given below\n\n`{traceback.format_exc()}`",
            quote=True,
        )

@wbot.on_message(filters.private & filters.command("banned_users"))
async def banned_usrs(c, m):
    if m.from_user.id not in AUTH_USERS:
        await m.delete()
        return
    all_banned_users = await db.get_all_banned_users()
    banned_usr_count = 0
    text = ""
    async for banned_user in all_banned_users:
        user_id = banned_user["id"]
        ban_duration = banned_user["ban_status"]["ban_duration"]
        banned_on = banned_user["ban_status"]["banned_on"]
        ban_reason = banned_user["ban_status"]["ban_reason"]
        banned_usr_count += 1
        text += f"> **User_id**: `{user_id}`, **Ban Duration**: `{ban_duration}`, **Banned on**: `{banned_on}`, **Reason**: `{ban_reason}`\n\n"
    reply_text = f"Total banned user(s) 🤭: `{banned_usr_count}`\n\n{text}"
    if len(reply_text) > 4096:
        with open("banned-users.txt", "w") as f:
            f.write(reply_text)
        await m.reply_document("banned-users.txt", True)
        os.remove("banned-users.txt")
        return
    await m.reply_text(reply_text, True)
