 
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
        InlineKeyboardButton("📔 Helps Menu🕹️", callback_data="hlp"),
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

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_photo(
        photo="https://files.catbox.moe/80bcxh.jpg",
        caption="📌 **General Commands:**\n/start → Start the bot & register yourself.\n/help → Show this help menu.\n/profile → View your profile, stats, and achievements.\n/leaderboard → Check who’s leading the game.\n/stats → See your gameplay statistics.",
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
            InlineKeyboardButton("🥇📊Quiz ⤵️", callback_data="gg")
        ],[
            InlineKeyboardButton("📊QuizMaster [P]🤖&[G]👥", callback_data="qz")
        ],[
            InlineKeyboardButton("⚔️RPG GomeZzz⚔️", callback_data="gg")
        ],[
            InlineKeyboardButton("⚔️RPG Battle🛡️", callback_data="rpgb"),
            InlineKeyboardButton("🔥RPG Battle Advanced 🛡️⚔️", callback_data="rpga")
        ],[
            InlineKeyboardButton("❌", callback_data="close")
        ]]
)

bak_bt = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔙 Back to Healp Menu", callback_data="hlp")
        ]]
)
@app.on_callback_query(filters.regex("^hlp$"))
async def hlp_callback(client, query):
    hlp_tx="""
    Gomez Games 🎮
    """
    await query.message.edit_text(
        text=hlp_tx,
        reply_markup=hlp_bt,
    )
    await query.answer("😎Gomez Games🎮")

@app.on_callback_query(filters.regex("^tic$"))
async def tic_callback(client, query):
    xo_tx="""
    **🎮 Play Tic Tac Toe game Menu!❌⭕**
    First to align three marks wins
    
    <blockquote>**Commands Usage:**
    • `/pvp_xoxo @username` or reply to group members to Challenge someone.
    • `/pve_xoxo easy|medium|hard` → Play with Bot.
    • `/xo_leaderboard` → Show top players on Tic Tac Toe.
    Also use @TicTacToe_Xbot bot play inline mode to play.</blockquote>
    """
    await query.message.edit_text(
        text=xo_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

@app.on_callback_query(filters.regex("^gmk$"))
async def gok_callback(client, query):
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
    await query.message.edit_text(
        text=gmk_tx,
        reply_markup=bak_bt,
    )
    await query.answer("😎Gomez Games🎮")

@app.on_callback_query(filters.regex("^cn4$"))
async def cn_callback(client, query):
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
    await asyncio.sleep(5)
    await query.message.delete()
@app.on_callback_query(filters.regex("^gg$"))
async def gg_callback(client, query):
    await query.answer("😎Gomez Games🎮")
