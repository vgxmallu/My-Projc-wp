import asyncio
import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as app



# MongoDB setup
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["emoji_equations_db"]
users_col = db["users"]

# =============== EQUATIONS ===============
PUZZLES = [
    # Addition
    {"equation": "🍎 + 🍎 = ❓", "answer": "2", "options": ["2", "3", "4", "5"]},
    {"equation": "🍌 + 🍌 + 🍌 = ❓", "answer": "3", "options": ["2", "3", "4", "5"]},
    {"equation": "🍕 + 🍕 + 🍕 + 🍕 = ❓", "answer": "4", "options": ["3", "4", "5", "6"]},
    {"equation": "🍪 + 🍪 + 🍪 + 🍪 + 🍪 = ❓", "answer": "5", "options": ["4", "5", "6", "7"]},
    {"equation": "⭐ + ⭐ + ⭐ = ❓", "answer": "3", "options": ["1", "2", "3", "4"]},
    {"equation": "🚗 + 🚗 = ❓", "answer": "2", "options": ["1", "2", "3", "4"]},
    {"equation": "🐶 + 🐶 + 🐶 + 🐶 = ❓", "answer": "4", "options": ["3", "4", "5", "6"]},
    {"equation": "☀️ + ☀️ + ☀️ + ☀️ + ☀️ = ❓", "answer": "5", "options": ["5", "6", "7", "8"]},
    {"equation": "❤️ + ❤️ + ❤️ = ❓", "answer": "3", "options": ["2", "3", "4", "5"]},
    {"equation": "🎸 + 🎸 = ❓", "answer": "2", "options": ["2", "4", "6", "8"]},
    {"equation": "⭐⭐⭐ - ⭐ = ❓", "answer": "2", "options": ["1", "2", "3", "4"]},
    {"equation": "🎈🎈🎈🎈🎈 - 🎈🎈 = ❓", "answer": "3", "options": ["1", "2", "3", "5"]},
    {"equation": "⚽⚽⚽⚽ - ⚽⚽⚽ = ❓", "answer": "1", "options": ["1", "2", "3", "4"]},
    {"equation": "🍦🍦🍦 - 🍦🍦 = ❓", "answer": "1", "options": ["0", "1", "2", "3"]},
    {"equation": "🎃🎃🎃🎃 - 🎃 = ❓", "answer": "3", "options": ["1", "2", "3", "4"]},
    {"equation": "🚀🚀🚀 - 🚀🚀 = ❓", "answer": "1", "options": ["1", "3", "5", "0"]},
    {"equation": "🌍🌍🌍🌍 - 🌍🌍 = ❓", "answer": "2", "options": ["1", "2", "4", "6"]},
    {"equation": "🍒 + 🍒 x 🍒 = ❓ (where 🍒=2)", "answer": "6", "options": ["4", "6", "8", "10"]},
    {"equation": "🍎🍎 x 🍎 = ❓ (2 x 1)", "answer": "2", "options": ["1", "2", "3", "4"]},
    {"equation": "⭐⭐ x ⭐⭐ = ❓ (2 x 2)", "answer": "4", "options": ["2", "3", "4", "5"]},
    {"equation": "🍌🍌🍌 x 🍌🍌 = ❓ (3 x 2)", "answer": "6", "options": ["5", "6", "8", "9"]},
    {"equation": "🚗 x 🚗🚗🚗 = ❓ (1 x 3)", "answer": "3", "options": ["1", "2", "3", "4"]},
    {"equation": "🍎 + 🍎 = 4, then 🍎 x 🍎 = ❓", "answer": "4", "options": ["2", "4", "6", "8"]},
    {"equation": "🍌🍌🍌 = 3, then 🍌 + 🍌 = ❓", "answer": "2", "options": ["1", "2", "3", "4"]},
    {"equation": "⭐ + ⭐ = 6, then ⭐ + ⭐ + ⭐ = ❓", "answer": "9", "options": ["6", "7", "8", "9"]},
    {"equation": "🚗🚗 = 10, then 🚗 - 🚗🚗 = ❓", "answer": "-5", "options": ["0", "5", "-5", "10"]},
    {"equation": "🐶 + 🐶 + 🐶 = 12, then 🐶 x 🐶 = ❓", "answer": "16", "options": ["8", "12", "16", "24"]},
    {"equation": "🍕 -  Grapes = 5, 🍕 = 7, Grapes = ❓", "answer": "2", "options": ["1", "2", "3", "4"]},
    {"equation": "(🍎+🍎) + (🍌+🍌+🍌) = ❓", "answer": "5", "options": ["4", "5", "6", "7"]},
    {"equation": "(⭐⭐⭐⭐) - (⭐+⭐) = ❓", "answer": "2", "options": ["1", "2", "3", "4"]},
]



# Active sessions
active_games = {}  # {chat_id: {"answer": str, "scores": {}, "running": bool}}


# =============== DB HELPERS ===============
async def update_user(user_id, name, score):
    """Update Mongo user score"""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({"user_id": user_id, "name": name, "score": score})
    else:
        await users_col.update_one({"user_id": user_id}, {"$inc": {"score": score}, "$set": {"name": name}})


async def get_leaderboard():
    """Return global leaderboard text"""
    cursor = users_col.find().sort("score", -1).limit(10)
    top = await cursor.to_list(length=10)
    text = "🏆 **Global Leaderboard** 🏆\n\n"
    for i, user in enumerate(top, 1):
        text += f"{i}. {user['name']} → {user['score']} pts\n"
    return text



@app.on_message(filters.command("emoji_math") & filters.group)
async def start_equahfftion(_, message):
    chat_id = message.chat.id
    if chat_id in active_games and active_games[chat_id]["running"]:
        return await message.reply_text("⚠️ A game is already running in this group!")

    puzzle = random.choice(PUZZLES)
    options = puzzle["options"]
    random.shuffle(options)

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"em_{chat_id}_{opt}")]
        for opt in options
    ]

    sent = await message.reply_text(
        f"🧮 **Solve the Emoji Equation!**\n\n{puzzle['equation']}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    active_games[chat_id] = {
        "answer": puzzle["answer"],
        "scores": {},
        "running": True,
        "msg_id": sent.id,
    }

    await asyncio.sleep(15)  # 15 seconds round timer
    if chat_id in active_games and active_games[chat_id]["running"]:
        await end_game(chat_id, message)


@app.on_callback_query(filters.regex(r"^em_(\-?\d+)_(.+)"))
async def handle_guess(_, query):
    chat_id = int(query.data.split("_")[1])
    guess = query.data.split("_", 2)[2]
    user = query.from_user

    session = active_games.get(chat_id)
    if not session or not session["running"]:
        return await query.answer("⚠️ No active game!", show_alert=True)

    if guess == session["answer"]:
        session["scores"][user.id] = session["scores"].get(user.id, 0) + 1
        await update_user(user.id, user.first_name, 1)
        await query.answer("✅ Correct!", show_alert=True)
    else:
        await query.answer("❌ Wrong!", show_alert=True)


async def end_game(chat_id, message):
    """End round and show results"""
    session = active_games.get(chat_id)
    if not session:
        return

    scores = session["scores"]
    if not scores:
        await message.reply_text("⏰ Time's up! Nobody solved it.")
    else:
        winner_id, max_score = max(scores.items(), key=lambda x: x[1])
        winner_name = (await app.get_users(winner_id)).first_name
        leaderboard_text = await get_leaderboard()
        result = f"🏁 **Round Over!**\n\n👑 Winner: {winner_name} ({max_score} pts)\n\n{leaderboard_text}"
        await app.send_message(chat_id, result)

    active_games[chat_id]["running"] = False


@app.on_message(filters.command("emleaderboard"))
async def shobdw_leaderboard(_, message):
    text = await get_leaderboard()
    await message.reply_text(text)


