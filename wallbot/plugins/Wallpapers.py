import asyncio
import random
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram import filters


from wallbot import wbot
from wallbot.images_db.walls import ANIM_PICS, ANIMALS_PICS, LOGO_PICS, CARS_PICS, DROWIG_PICS, FUNNY_PICS, ENTERT_PICS, GAME_PICS, LOVE_PICS, MUSIC_PICS, NATURE_PICS, SAYING_PICS, SPACE_PICS, COMIC_PICS, SPORT_PICS, PATTER_PICS, TECHNO_PICS, DESIN_PICS, HOLDAY_PICS, PEOPL_PICS, OTHERS_PICS                      
from config import LOG_CHANNEL
from wallbot.untils import pyro_cooldown



#==================BOTTON-REMOVING==============
@wbot.on_message(filters.command("remove_bt") & pyro_cooldown.wait(10)) 
async def reply_rmv(client, message):
    ab = await message.reply_text(
        text="Click Down Botton to KeyboardRemove\n`Message will be delete 4s`", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "✖️Close×"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await ab.delete()
    await message.delete()
    
        
@wbot.on_message(filters.regex("✖️Close×"))
async def close_myr2(client, message):
    ae = await message.reply_text(
        text="Bottons removed ✅", 
        reply_markup=ReplyKeyboardRemove() 
    ) 
    await asyncio.sleep(4)
    await ae.delete()
    await message.delete()


@Mbot.on_message(filters.private & filters.command("start"))
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
    

 

#=================ZEDGE-WALLPEPERS======================
MW = """
📣 **LOG ALERT** 🏞️🤖

📛**Triggered Command** : /start
👤**Name** : {}
👾**Username** : @{}
💾**DC** : {}
♐**ID** : `{}`
🤖**BOT** : @Wallpepers_xbot
"""

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


@wbot.on_message(filters.private & filters.regex("🔽") | filters.private & filters.regex("🛟 CATEGORIES 🛟") | filters.private & filters.regex("Page 2️⃣") | filters.private & filters.regex("Page 1️⃣") | filters.private & filters.regex("➖➖➖➖➖➖➖➖➖➖")) 
async def delete(client, message):
    await message.delete()
    
@wbot.on_message(filters.private & filters.regex("Wallpapers 🏞️") & pyro_cooldown.wait(10)) 
async def wallpaper(client, message):
    m1 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.first_name), 
        reply_markup=ReplyKeyboardMarkup(
            [[
               "Page 1️⃣", "❌ CLOSE ❌", "➡️"
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
            ]], 
            resize_keyboard=True
        ) 
    )
    w1 = await message.reply_text(wall_tottal)
    
    await message.delete()
    await asyncio.sleep(1200)
    await m1.delete()
    await w1.delete()
    
#=================REGEX=====================

@wbot.on_message(filters.private & filters.regex("⬅️") | filters.private & filters.regex("Wallpapers 🌇") & pyro_cooldown.wait(10)) 
async def wallpaper2(client, message):
    m2 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.first_name),
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Page 1️⃣", "❌ CLOSE ❌", "➡️"
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
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await message.delete()
    await asyncio.sleep(1200)
    await m2.delete()

@wbot.on_message(filters.private & filters.regex("➡️"))
async def wallpaper3(client, message):
    m3 = await message.reply_photo(
        photo="https://telegra.ph/file/3068c6123cca8734b4911.jpg",
        caption=cap_wall.format(message.from_user.mention), 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "⬅️", "❌ CLOSE ❌", "Page 2️⃣"
            ],[
                "🛟 CATEGORIES 🛟"
            ],[
                "Space 🌠", "Comics 🦸", "Sports ⚽"
            ],[
                "Pattern ☸️", "Technology 📱", "Designs ✨"
            ],[
                "Holiday 🏖️", "People 🧑‍🤝‍🧑", "Scenery" #".Others 🤷"
            ]], 
            resize_keyboard=True
        ) 
    )
    await message.delete()
    await asyncio.sleep(1200)
    await m3.delete()
    
#=============================PG1=============================
@wbot.on_message(filters.private & filters.regex("Anime 🧚") & pyro_cooldown.wait(10))
async def wall_anim(client, message):
    await message.reply_photo(
        photo=random.choice(ANIM_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Anime 🧚"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Animals 🦁") & pyro_cooldown.wait(10))
async def wall_animal(client, message):
    await message.reply_photo(
        photo=random.choice(ANIMALS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Animals 🦁"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Logos ♑") & pyro_cooldown.wait(10))
async def wall_logo(client, message):
    await message.reply_photo(
        photo=random.choice(LOGO_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Logos ♑"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Car&Bike 🏎️") & pyro_cooldown.wait(10))
async def wall_car(client, message):
    await message.reply_photo(
        photo=random.choice(CARS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Car&Bike 🏎️"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Drownings 🎑") & pyro_cooldown.wait(10))
async def wall_drowi(client, message):
    await message.reply_photo(
        photo=random.choice(DROWIG_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Drownings 🎑"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Funny 😄") & pyro_cooldown.wait(10))
async def wall_funny(client, message):
    await message.reply_photo(
        photo=random.choice(FUNNY_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Funny 😄"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
@wbot.on_message(filters.private & filters.regex("Entertainment 🧑‍🎤") & pyro_cooldown.wait(10))
async def wall_endet(client, message):
    await message.reply_photo(
        photo=random.choice(ENTERT_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Entertainment 🧑‍🎤"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Gamee 🎮") & pyro_cooldown.wait(10))
async def wall_game(client, message):
    await message.reply_photo(
        photo=random.choice(GAME_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Game 🎮"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Love ❤️") & pyro_cooldown.wait(10))
async def wall_lov(client, message):
    await message.reply_photo(
        photo=random.choice(LOVE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Love ❤️"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Music 🎵") & pyro_cooldown.wait(10))
async def wall_music(client, message):
    await message.reply_photo(
        photo=random.choice(MUSIC_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Music 🎵"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Nature 🍃") & pyro_cooldown.wait(10))
async def wall_natur(client, message):
    await message.reply_photo(
        photo=random.choice(NATURE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Nature 🍃"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
@wbot.on_message(filters.private & filters.regex("Sayings 📝") & pyro_cooldown.wait(10))
async def wall_sayin(client, message):
    await message.reply_photo(
        photo=random.choice(SAYING_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Sayings 📝"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
#========≠==================PG2====================
@wbot.on_message(filters.private & filters.regex("Space 🌠") & pyro_cooldown.wait(10))
async def wall_space(client, message):
    await message.reply_photo(
        photo=random.choice(SPACE_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Space 🌠"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete() 
@wbot.on_message(filters.private & filters.regex("Comics 🦸") & pyro_cooldown.wait(10))
async def wall_comi(client, message):
    await message.reply_photo(
        photo=random.choice(COMIC_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Comics 🦸"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Sports ⚽") & pyro_cooldown.wait(10))
async def wall_spor(client, message):
    await message.reply_photo(
        photo=random.choice(SPORT_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Sports ⚽"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Pattern ☸️") & pyro_cooldown.wait(10))
async def wall_pattt(client, message):
    await message.reply_photo(
        photo=random.choice(PATTER_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Pattern ☸️"
            ],[
                "⬅️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Technology 📱") & pyro_cooldown.wait(10))
async def wall_texhno(client, message):
    await message.reply_photo(
        photo=random.choice(TECHNO_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Technology 📱"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Designs ✨") & pyro_cooldown.wait(10))
async def wall_desins(client, message):
    await message.reply_photo(
        photo=random.choice(DESIN_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Designs ✨"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Hollyday 🏖️") & pyro_cooldown.wait(10))
async def wall_hollyd(client, message):
    await message.reply_photo(
        photo=random.choice(HOLDAY_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Hollyday 🏖️"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("People 🧑‍🤝‍🧑") & pyro_cooldown.wait(10))
async def wall_peopl(client, message):
    await message.reply_photo(
        photo=random.choice(PEOPL_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "People 🧑‍🤝‍🧑"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
@wbot.on_message(filters.private & filters.regex("Others 🤷") & pyro_cooldown.wait(10))
async def wall_other(client, message):
    await message.reply_photo(
        photo=random.choice(OTHERS_PICS), #text="Type botton to get more...", 
        reply_markup=ReplyKeyboardMarkup(
            [[
                "Others 🤷"
            ],[
                "➡️", "❌ CLOSE ❌"
            ]], 
            resize_keyboard=True
        ) 
    ) 
    await asyncio.sleep(4)
    await message.delete()
#=======================================================

              
