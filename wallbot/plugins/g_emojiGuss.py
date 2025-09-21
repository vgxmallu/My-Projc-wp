import asyncio
import os
import random
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)

from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

# ================= DATABASE =================
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["emoji_guess"]
users_col = db["users"]
games_col = db["games"]



# ================= EMOJI PUZZLES =================
PUZZLES = [
    {"emoji": "🍕+🍍=❓", "answer": ["pineapple pizza", "pizza", "hawaiian pizza"]},
    {"emoji": "🦁+👑=❓", "answer": ["lion king", "the lion king"]},
    {"emoji": "🚗+⚡=❓", "answer": ["electric car", "tesla"]},
    {"emoji": "🎩+🐇=❓", "answer": ["magic", "magician", "magic trick"]},
    {"emoji": "🌍+🚀=❓", "answer": ["space travel", "astronaut", "spacex"]},
    {"emoji": "🍎+📱=❓", "answer": ["apple iphone", "iphone", "apple"]},
    {"emoji": "🎸+👨=❓", "answer": ["guitarist", "rockstar", "musician"]},
    {"emoji": "⚽+🥅=❓", "answer": ["football", "soccer", "goal"]},
    {"emoji": "🎥+🍿=❓", "answer": ["movie night", "cinema", "film"]},
    {"emoji": "👩‍🚀+🌌=❓", "answer": ["astronaut", "space explorer"]},
    {"emoji": "🐍+💻=❓", "answer": ["python programming", "python"]},
    {"emoji": "🍔+🍟=❓", "answer": ["burger and fries", "fast food", "combo meal"]},
    {"emoji": "🐭+🧀=❓", "answer": ["mickey mouse", "rat loves cheese", "tom and jerry"]},
    {"emoji": "🏰+🐉=❓", "answer": ["fairy tale", "castle dragon", "fantasy"]},
    {"emoji": "🧛+🌙=❓", "answer": ["vampire", "dracula"]},
    {"emoji": "🦸+♂️=❓", "answer": ["superhero", "superman"]},
    {"emoji": "🐼+🥋=❓", "answer": ["kung fu panda", "panda fighter"]},
    {"emoji": "❄️+⛄=❓", "answer": ["snowman", "winter", "frozen"]},
    {"emoji": "🕷️+🕸️=❓", "answer": ["spider", "spiderman"]},
    {"emoji": "👑+🎤=❓", "answer": ["queen", "queen band", "singer"]},
    {"emoji": "☕+🍩=❓", "answer": ["coffee and donut", "breakfast"]},
    {"emoji": "🚢+🧊=❓", "answer": ["titanic", "ship iceberg"]},
    {"emoji": "🎮+👾=❓", "answer": ["video game", "gamer"]},
    {"emoji": "🐒+🍌=❓", "answer": ["monkey and banana", "banana monkey"]},
    {"emoji": "💤+😴=❓", "answer": ["sleep", "nap", "dream"]},
]


# ================= HELPERS =================
async def get_user(user_id: int, username: str, full_name: str):
    """Ensure user exists in DB."""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "score": 0,
            "games_played": 0,
            "created_at": datetime.utcnow(),
        }
        await users_col.insert_one(user)
    return user

async def update_score(user_id: int, points: int):
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"score": points, "games_played": 1}},
    )

async def get_leaderboard(limit=10):
    cursor = users_col.find().sort("score", -1).limit(limit)
    users = await cursor.to_list(length=limit)
    return users

# ================= COMMANDS =================
@app.on_message(filters.command("gusstart"))
async def guddstart(_, message: Message):
    await get_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.reply_text(
        "👋 Welcome to *Emoji Guess Game!* 🎉\n\n"
        "I will show you emojis like `🍕+🍍=❓`\n"
        "You guess the word or concept!\n\n"
        "Commands:\n"
        " - /play → Start a new game\n"
        " - /leaderboard → Show top players\n"
        " - /profile → Your stats\n",
        quote=True,
    )

@app.on_message(filters.command("gusprofile"))
async def profile(_, message: Message):
    user = await get_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.reply_text(
        f"👤 Profile for {message.from_user.mention}\n\n"
        f"🏆 Score: {user['score']}\n"
        f"🎮 Games Played: {user['games_played']}\n"
    )

@app.on_message(filters.command("gusleaderboard"))
async def leaderboard(_, message: Message):
    users = await get_leaderboard()
    text = "🏆 *Top Players:*\n\n"
    for idx, u in enumerate(users, start=1):
        name = u.get("username") or u.get("full_name") or "Unknown"
        text += f"{idx}. {name} — {u['score']} pts\n"
    await message.reply_text(text)

# ================= GAME =================
@app.on_message(filters.command("playgus"))
async def pjlay_game(_, message: Message):
    puzzle = random.choice(PUZZLES)
    game_id = str(message.chat.id) + "_" + str(message.id)

    await games_col.insert_one(
        {
            "_id": game_id,
            "chat_id": message.chat.id,
            "puzzle": puzzle,
            "guessed": False,
            "created_at": datetime.utcnow(),
        }
    )

    await message.reply_text(
        f"🤔 Guess this!\n\n{puzzle['emoji']}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ I give up", callback_data=f"giveup:{game_id}")]]
        ),
    )

@app.on_message(filters.command("guss") & filters.group)
async def handle_guess(_, message: Message):
    game = await games_col.find_one({"chat_id": message.chat.id, "guessed": False})
    if not game:
        return
    puzzle = game["puzzle"]
    #guess = message.text.lower().strip()
    guess = message.text.split(" ", 1)[1].strip()
    if any(ans.lower() == guess for ans in puzzle["answer"]):
        await update_score(message.from_user.id, 10)
        await games_col.update_one({"_id": game["_id"]}, {"$set": {"guessed": True}})

        await message.reply_text(
            f"🎉 Correct! {message.from_user.mention} got it right!\n"
            f"Answer: *{puzzle['answer'][0].title()}*\n"
            f"+10 points 🏆"
        )

@app.on_callback_query(filters.regex(r"giveup:(.+)"))
async def giveup(_, cq: CallbackQuery):
    game_id = cq.data.split(":")[1]
    game = await games_col.find_one({"_id": game_id, "guessed": False})
    if not game:
        await cq.answer("This game is already over!", show_alert=True)
        return

    await games_col.update_one({"_id": game_id}, {"$set": {"guessed": True}})
    await cq.message.edit_text(
        f"❌ Game over! Nobody guessed.\nCorrect answer was: *{game['puzzle']['answer'][0].title()}*"
    )


