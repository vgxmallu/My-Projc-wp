 
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, ChatWriteForbidden
from config import DB_URL
from wallbot import wbot as app
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
        InlineKeyboardButton("📣My Channel", url="https://t.me/xbots_x"),
    ]]
)
    
        

# --- Save user on /start ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
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
        caption="👋<b>Hey! Welcome to Gomez Games🎮.</b>\n\n<b>Here you can:</b>\n⭐ `Play exciting games with friends`\n🏆 `Compete for the top spot on leaderboards`\n📊 `Track your profile & stats`\n🔥 `Join quizzes, puzzles, and more`\n\n💡 Use the menu or type /help to explore commands.\n⚡ Stay active new games and events are added regularly!",
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
