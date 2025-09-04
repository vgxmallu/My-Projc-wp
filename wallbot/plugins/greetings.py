
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, ChatWriteForbidden
from config import DB_URL
from wallbot import wbot as app

OWNER_ID = 784589736   # your Telegram ID
LOG_CHANNEL = -1001997285269  # your log channel ID (bot must be admin here)

# --- Init ---
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["broadcast_db"]
users_collection = db["users"]

# --- Save user on /start ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user = message.from_user
    user_id = user.id
    user_n = message.username
    # Insert if not exists
    result = await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"_id": user_id, "name": user.first_name}},
        upsert=True
    )

    await message.reply_text("👋 <b>Hey! Welcome to Gomez Games🎮.</b>\n\n<b>Here you can;)</b>\n⭐ `Play exciting games with friends`\n🏆 `Compete for the top spot on leaderboards`\n📊 `Track your profile & stats`\n🔥 `Join quizzes, puzzles, and more`\n\n💡 Tip: __Use the menu or type /help to explore commands.__\n⚡ __Stay active — new games and events are added regularly!__\n\n<b>;) Enjoy & have fun, gamerZzz!</b> 🚀")

    # If it's a new user, log them
    if result.upserted_id is not None:
        mention = f"[{user.first_name}](tg://user?id={user_id})"
        await client.send_message(
            LOG_CHANNEL,
            f"🆕 New member started the bot!\n\n👤: {mention}\n⛓️‍💥: @{user_n}\n🆔: `{user_id}`"
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
