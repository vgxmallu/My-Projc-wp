 
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, ChatWriteForbidden
from config import DB_URL
from wallbot import wbot as app
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

OWNER_ID = 784589736   # your Telegram ID
LOG_CHANNEL = -1001997285269  # your log channel ID (bot must be admin here)

# --- Init ---
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["broadcast_db"]
users_collection = db["users"]



g_button = InlineKeyboardMarkup(
    [
        [
            
            InlineKeyboardButton("📣My Channel", url="https://t.me/xbots_x"),
        ],
        [
            InlineKeyboardButton(
                text="➕Add Me To Your Chat➕",
                url=f"http://t.me/GomezGamesbot?startgroup=new",
            )
        ],
    ]
) 

h_button = InlineKeyboardMarkup(
    [[
        InlineKeyboardButton("Games Menu🕹️", callback_data="hlp"),
        InlineKeyboardButton("➕ Extra Menu", callback_data="ext"),
        InlineKeyboardButton("About Me ℹ️", callback_data="ab")
    ]]
)


@app.on_message(filters.new_chat_members)
async def notify_when_added(client, message):
    for member in message.new_chat_members:
        if member.id == (await client.get_me()).id:  # Check if it's the bot itself
            chat = message.chat
            text = (
                "🤖 **Bot Added to New Group**\n\n"
                f"🏠 Group: {chat.title}\n"
                f"🪬 G User name: @{chat.username}"
                f"🆔 Group ID: `{chat.id}`\n"
                f"👥 Members Count: {chat.members_count if hasattr(chat, 'members_count') else 'Unknown'}"
            )
            await client.send_message(LOG_CHANNEL, text)


# --- Save user on /start ---
@app.on_message(filters.command("start"))
async def start_game(client, message):
    user = message.from_user
    user_id = user.id
    user_n = user.username
    # Insert if not exists
    result = await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"_id": user_id, "name": user.first_name}},
        upsert=True
    )
    await message.reply_sticker("CAACAgUAAxkBAANmaLk5MLScQyq443axCvBpaNASiJMAAusTAALPLMhV8eSTf4mvJD8eBA")    
    await message.reply_photo(
        photo="https://files.catbox.moe/80bcxh.jpg",
        caption="👋<b>Hey! Welcome to Gomez Games🎮.</b>\n\n<blockquote><b>Here you can:</b>\n⭐ `Play exciting games with friends`\n🏆 `Compete for the top spot on leaderboards`\n📊 `Track your profile & stats`\n🔥 `Join quizzes, puzzles, and more`</blockquote>\n\n💡 Use the menu or type /help to explore commands.\n⚡ Stay active new games and events are added regularly!",
        reply_markup=g_button,
    )
    #await message.reply_audio("AwACAgUAAxkBAANYaLk0cu3EU-vGP2_ZTn2T9-E9ajQAAtcXAAK8T8hVy8L_8RGZVXoeBA")
    
    #message_effect_id=5104841245755180586,
    # If it's a new user, log them
    if result.upserted_id is not None:
        mention = f"[{user.first_name}](tg://user?id={user_id})"
        await client.send_message(
            LOG_CHANNEL,
            f"🆕 New member started the bot!\n\n👤: {mention}\n⛓️‍💥: @{user_n}\n🆔: `{user_id}`"
        )

help_txt="""
📌 **General Commands:**
•/start → Start the bot & register yourself.
•/help → Show this help menu.
•/profile → View your profile, stats, and achievements.
•/leaderboard → Check who’s leading the game.
•/stats → See your gameplay statistics.
"""
@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_photo(
        photo="https://files.catbox.moe/80bcxh.jpg",
        caption=help_txt,
        reply_markup=h_button,
    )

# --- Status command ---
@app.on_message(filters.command("status") & filters.user(OWNER_ID))
async def ggstatus(client, message):
    total = await users_collection.count_documents({})
    await message.reply_text(f"📊 Total registered users: **{total}**")

# --- Broadcast command ---
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def ggbroadcast(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ Reply to a message (text/photo/video/document) with `/broadcast`")
        return

    total = await users_collection.count_documents({})
    sent = 0
    failed = 0
    removed = 0

    status_msg = await message.reply_text(f"📢 Broadcasting to {total} users...")

    async for user in users_collection.find({}):
        user_id = user["_id"]
        try:
            await message.reply_to_message.copy(chat_id=user_id)
            sent += 1
            await asyncio.sleep(0.05)  # prevent flood
        except (UserIsBlocked, PeerIdInvalid, ChatWriteForbidden):
            # Remove dead/blocked users
            await users_collection.delete_one({"_id": user_id})
            removed += 1
            failed += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ Broadcast finished!\n\n"
        f"👥 Total Users Before: {total}\n"
        f"📩 Sent: {sent}\n"
        f"⚠️ Failed: {failed}\n"
        f"🗑️ Removed from DB: {removed}\n"
        f"📊 Active Users Now: {await users_collection.count_documents({})}"
    )

#=======•=•==••=•=•=<pre>
hlp_bt = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("❌⭕Tic Tac Toe 🕹️", callback_data="tic")
        ],[
            InlineKeyboardButton("🔴⚫Gomoku 🎮", callback_data="gmk")
        ],[
            InlineKeyboardButton("🔴🟢Connect 4 🕹️", callback_data="cn4")
        ],[
            InlineKeyboardButton("📊QuizMaster [P]🤖&[G]👥", callback_data="qz")
        ],[
            InlineKeyboardButton("⚔️RPG GomeZzz⚔️", callback_data="gg")
        ],[
            InlineKeyboardButton("⚔️RPG Battle🛡️", callback_data="rpgb"),
            InlineKeyboardButton("🔥RPG Battle Advanced 🛡️⚔️", callback_data="rpga")
        ],[
            InlineKeyboardButton("🔙 Main Menu", callback_data="help"),
            InlineKeyboardButton("❌", callback_data="close")
        ]]
)

ext3_bt = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔙 Back menu", callback_data="ext2"),
            InlineKeyboardButton("❌", callback_data="close")
        ]]

)

ext3_tx="""
**Page: 3️⃣📄**

<blockquote expandable>**Math Commands:**
`/simplify` - simplify a mathematical expression
`/factor` - factor a mathematical expression
`/derive` - find the derivative of a mathematical expression
`/integrate` - find the integral of a mathematical expression
`/zeroes` - find the zeroes of a mathematical expression
`/tangent` - find the tangent line of a mathematical expression at a given point
`/area` - find the area under a mathematical expression between two points
`/cos` - find the cosine of a number
`/sin` - find the sine of a number
`/tan` - find the tangent of a number
`/arccos` - find the arccosine of a number
`/arcsin` - find the arcsine of a number
`/arctan` - find the arctangent of a number
`/abs` - find the absolute value of a number
`/log` - find the logarithm of a number</blockquote>
"""
@app.on_callback_query(filters.regex("^ext3$"))
async def eur_callback(client, query):
    await query.message.edit_text(
        text=ext3_tx,
        reply_markup=ext3_bt,
    )
    await query.answer("😎Gomez Games🎮")

ext2_bt = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔙 Back menu", callback_data="ext2"),
            InlineKeyboardButton("❌", callback_data="close"),
            InlineKeyboardButton("Next 🔜", callback_data="ext3")
        ]]

)
ext2_tx="""
**Page: 2️⃣📄**

<blockquote>`/groupdata` [send_group], `/uinfo` [user_info], `/id`  [user_id], `/dc` `/cinfo`.
`/whois` [user_or_bots_Id], [reply to user or bot], [usernames]
`/jason` - get Jason format.
`/paste` Reply To File / Give Me Text To Paste.
`/sangmata_set` [on/off] - Enable/disable sangmata in groups.
`/telegraph` [reply to photos]
`/imdb` `/tmdb` to get Moves infos.
`/msone` - to get the subtitle file from msone
`/github` - Returns info about a GitHub user or organization.
`/lyrics` - returns the lyrics of that song.
`/ud` - Get the definition of a word from urbandictionary
`/urban` - Same as ud
`/tts` - Convert text to speech
`/getsticker` - <code>Get a sticker png by replying it</blockquote>
"""

@app.on_callback_query(filters.regex("^ext2$"))
async def exx_callback(client, query):
    await query.message.edit_text(
        text=ext2_tx,
        reply_markup=ext2_bt,
    )
    await query.answer("😎Gomez Games🎮")


ext1_bt = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔙 Main menu", callback_data="help"),
            InlineKeyboardButton("❌", callback_data="close"),
            InlineKeyboardButton("Next 🔜", callback_data="ext2")
        ]]
)
 
extone_tx="""
**Some Extras Things.**

<blockquote>**AFK:**
`/afk` [Reason Optional] - Tell others that you are AFK, so that your boyfriend or girlfriend wont look for you 💔.
**All Repos:**
`/allrepo` [github_username] - To get all repos from GitHub.
**Anime:**
`/anime` [anime_name] - To search your favourite animes.
`/airinfo` [anime_name] - airings info
`/charinfo` [anime_characters] - To get info about Anime Characters.
`/mangainfo` [anime_name] - To get info about Mangas.
**Remove Background:**
`/rmbg` [replyTo_photo] - To Remove background from given images.</blockquote>

**To go Next Page 📄.**
"""
@app.on_callback_query(filters.regex("^ext$"))
async def gomz_callback(client, query):
    await query.message.edit_text(
        text=extone_tx,   # <-- fixed here
        reply_markup=ext1_bt,
    )
    await query.answer("😎Gomez Games🎮")

@app.on_callback_query(filters.regex("^help$"))
async def hlp_callback(client, query):
    await query.message.edit_text(
        text=help_txt,
        reply_markup=h_button,
    )
    await query.answer("😎Gomez Games🎮")

@app.on_callback_query(filters.regex("^hlp$"))
async def hlpsk_callback(client, query):
    hlp_tx="""
    Gomez Games 🎮
    """
    await query.message.edit_text(
        text=hlp_tx,
        reply_markup=hlp_bt,
    )
    await query.answer("😎Gomez Games🎮")

xo_tx="""
**🎮 Play Tic Tac Toe game Menu!❌⭕**
First to align three marks wins
    
<blockquote>**Commands Usage:**
• `/pvp_xoxo @username` or reply to group members to Challenge someone.
• `/pve_xoxo easy|medium|hard` → Play with Bot.
• `/xo_leaderboard` → Show top players on Tic Tac Toe.
Also use @TicTacToe_Xbot bot play inline mode to play.</blockquote>
"""
@app.on_callback_query(filters.regex("^tic$"))
async def tic_callback(client, query):
    
    await query.message.edit_text(
        text=xo_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

gmk_tx="""
🎮 **Welcome to Gomoku game Menu!**
First to connect five marks wins
    
<blockquote>**Commands Usage:**
• `/playgomoku` - Start a new PvP Gomoku game.
• `/join_gomoku` <game_id> - Join a game.
• `/go_profile` - View your profile on Gomoku.
• `/go_leaderboard` - View Top group Gomoku leaderboard.
• `/gomoku_stats` - View group statistics.</blockquote>
"""
@app.on_callback_query(filters.regex("^gmk$"))
async def gok_callback(client, query):  
    await query.message.edit_text(
        text=gmk_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

cn4_tx="""
🎮 **Welcome to Connect 4 🎮 game Menu!**
First to connect four dots wins
    
<blockquote>**Commands Usage:**
• /connect4_challenge` (reply to a user) — challenge in group.
• `/c4_pve easy|medium|hard` — play vs bot in private.
• `/c4_profile` — show your stats & ELO.
• `/c4_leaderboard` — top players by ELO.
• `/c4_spectate <game_id>` — view a game's board.</blockquote>

Gameplay: Use column buttons to drop your piece. Red (🔴) starts and is X; Yellow (🟢) is O.
"""
@app.on_callback_query(filters.regex("^cn4$"))
async def cn_callback(client, query):
    await query.message.edit_text(
        text=cn4_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

qz_tx="""
🎮 **Welcome to QuizMaster Bot! 🧠✨!**
Get ready to test your knowledge across tons of fun and serious topics!  

<blockquote>📚**Quiz for Private chat:**
1️⃣ Use `/start_qz` to begin a quiz.
2️⃣ Choose your category.
3️⃣ Answer the questions and earn points! 🏆
• `/qzprofile` - To find your profile on Quiz.
• `/qzleaderboard` - To get Top player on quiz.</blockquote>

<blockquote>📊 **Quiz For Group chats:**
• `/startquiz` - To begin a quiz in group.
• `/stopquiz` - To stop quiz in group 
• `/qzg_leaderboard` - view Group top players.
• `/qz_global_leaderboard` - View global Top players.
• `/qz_profile` - To see your Profile on Quiz</blockquote>
    
**This commands for Admin**

• [P]`/p_seed` - seed the QnA, • `/p_addq` to add more questions.
• [G]`/gqzaddq` - to add more questions on group DB, `/gqzseed` seed Qz, `/gimport` import Qz
💡 Tip: The faster you answer correctly, the more points you score!
"""
@app.on_callback_query(filters.regex("^qz$"))
async def qz_callback(client, query):
    await query.message.edit_text(
        text=qz_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

rpgb_tx="""
🗡️ **Welcome to Mini Battles RPG game Menu!**
    
<blockquote>**Commands Usage:**
• `/battle` (reply to a user) — challenge in group.
• `/rbshop` Shop your inventory.
• `/rbbuy` — buy inventory.
• `/rb_leaderboard` — top players by Battle ELO.
• `/rb_profile check your profile.
• `/rbinventory` Check your inventory.</blockquote>
    
Perfect ⚔️🐉 Let’s level this up into a full simple RPG__
    """
@app.on_callback_query(filters.regex("^rpgb$"))
async def igigcallback(client, query):
    await query.message.edit_text(
        text=rpgb_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

rpga_tx="""
**🛡️Welcome to Advanced RPG Battle!!** ⚔️
Collect stuff, craft gear, run dungeons, duel, gamble & more...
    
<blockquote>💰**Basics Usage:**
• `/rpgprofile` `/me` — your stats.
• `/rpgshop` — buyable items.
• `/rpginventory` — your bag.
• `/recipes_rpg` — crafting list.</blockquote>

<blockquote>🧰**Work**: `/chop_rpg` `/fish_rpg` `/pickup_rpg` `/mine_rpg`
🏦**Economy**: `/buy_rpg` `/sell_rpg` `/trade_rpg`
⛏️**Crafting**: `/craft_rpg` [item].
👥**PvP**: `/duel_rpg @user [bet]`.
🐲**Dungeon**: `/dungeon`
🎰**Gamble**: `/coinflip` `/dice_rpg` `/blackjack` `/slots_rpg` `/wheel_rpg` `/multidice_rpg`
📜**Other**: `/daily_rpg` `/enchant_rpg` `/pet_rpg` `/guild_rpg` `/memerpg` `/rpgleaderboard`.</blockquote>
"""
@app.on_callback_query(filters.regex("^rpga$"))
async def arpgcallback(client, query):
    await query.message.edit_text(
        text=rpga_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")
#======••=•=•==•=•=•==•=•=••=•=•=•=•=•=•=••=•=
@app.on_callback_query(filters.regex("^close$"))
async def colcallback(client, query):
    await query.answer("Closed ❌")
    await asyncio.sleep(3)
    await query.message.delete()
@app.on_callback_query(filters.regex("^gg$"))
async def gg_callback(client, query):
    await query.answer("😎Gomez Games🎮")
