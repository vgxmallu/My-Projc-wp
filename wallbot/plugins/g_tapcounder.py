import asyncio
import random
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

# Mongo
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["tapcounter_db"]
users_col = db["users"]


# Global sessions
game_sessions = {}  # {chat_id: {"msg_id": int, "scores": {}, "start_time": float, "running": bool}}


# ================= FUNCTIONS =================
async def update_user(user_id, name, score):
    """Update Mongo user score"""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({"user_id": user_id, "name": name, "score": score})
    else:
        await users_col.update_one({"user_id": user_id}, {"$inc": {"score": score}, "$set": {"name": name}})


async def get_leaderboard():
    """Top 10 leaderboard"""
    cursor = users_col.find().sort("score", -1).limit(10)
    top = await cursor.to_list(length=10)
    text = "🏆 **Global Leaderboard** 🏆\n\n"
    for i, user in enumerate(top, 1):
        text += f"{i}. {user['name']} → {user['score']} taps\n"
    return text


# ================= HANDLERS =================
@app.on_message(filters.command("tapcounter") & filters.group)
async def start_tgapcounter(_, message):
    chat_id = message.chat.id
    if chat_id in game_sessions and game_sessions[chat_id]["running"]:
        return await message.reply_text("⚠️ A TapCounter game is already running here!")

    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👆 Tap!", callback_data=f"tap_{chat_id}")]]
    )

    sent = await message.reply_text(
        "🔥 **Tap Counter Game Started!**\n\nSpam the button as fast as possible!\nYou have 15 seconds!",
        reply_markup=btn
    )

    game_sessions[chat_id] = {
        "msg_id": sent.id,
        "scores": {},
        "start_time": time.time(),
        "running": True
    }

    # Game duration
    await asyncio.sleep(15)

    session = game_sessions.get(chat_id)
    if not session or not session["running"]:
        return

    scores = session["scores"]
    if not scores:
        await message.reply_text("Nobody tapped! 😭")
    else:
        winner_id, max_taps = max(scores.items(), key=lambda x: x[1])
        winner_name = (await app.get_users(winner_id)).first_name

        # Update DB
        for uid, taps in scores.items():
            user = await app.get_users(uid)
            await update_user(uid, user.first_name, taps)

        leaderboard_text = await get_leaderboard()

        result = f"🏁 **Game Over!**\n\n👑 Winner: {winner_name} with {max_taps} taps!\n\n{leaderboard_text}"
        await app.send_message(chat_id, result)

    game_sessions[chat_id]["running"] = False


@app.on_callback_query(filters.regex(r"^tap_(\-\d+)$"))
async def handle_tap(_, query):
    chat_id = int(query.data.split("_")[1])
    user = query.from_user

    session = game_sessions.get(chat_id)
    if not session or not session["running"]:
        return await query.answer("⚠️ No active game!", show_alert=True)

    # Update score
    session["scores"][user.id] = session["scores"].get(user.id, 0) + 1
    await query.answer(f"👆 Taps: {session['scores'][user.id]}")


@app.on_message(filters.command("leaderboard"))
async def show_leaderboard(_, message):
    text = await get_leaderboard()
    await message.reply_text(text)


