import asyncio
import os
import random
import time
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app


DB_NAME = "flag_quiz"

# ===================================================


mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client[DB_NAME]
players_col = db["players"]

# Active games: {chat_id: {...}}
active_games: Dict[int, dict] = {}

# ===================== FLAGS DATA =====================

FLAGS = [
    {"flag": "🇺🇸", "country": "United States"},
    {"flag": "🇮🇳", "country": "India"},
    {"flag": "🇧🇷", "country": "Brazil"},
    {"flag": "🇫🇷", "country": "France"},
    {"flag": "🇩🇪", "country": "Germany"},
    {"flag": "🇨🇳", "country": "China"},
    {"flag": "🇯🇵", "country": "Japan"},
    {"flag": "🇬🇧", "country": "United Kingdom"},
    {"flag": "🇨🇦", "country": "Canada"},
    {"flag": "🇦🇷", "country": "Argentina"},
    {"flag": "🇮🇹", "country": "Italy"},
    {"flag": "🇷🇺", "country": "Russia"},
    {"flag": "🇪🇸", "country": "Spain"},
    {"flag": "🇦🇺", "country": "Australia"},
    {"flag": "🇿🇦", "country": "South Africa"},
    {"flag": "🇰🇷", "country": "South Korea"},
    {"flag": "🇳🇬", "country": "Nigeria"},
    {"flag": "🇪🇬", "country": "Egypt"},
    {"flag": "🇰🇪", "country": "Kenya"},
    {"flag": "🇲🇽", "country": "Mexico"},
    {"flag": "🇨🇱", "country": "Chile"},
    {"flag": "🇨🇴", "country": "Colombia"},
    {"flag": "🇵🇪", "country": "Peru"},
    {"flag": "🇳🇱", "country": "Netherlands"},
    {"flag": "🇸🇪", "country": "Sweden"},
    {"flag": "🇨🇭", "country": "Switzerland"},
    {"flag": "🇧🇪", "country": "Belgium"},
    {"flag": "🇵🇹", "country": "Portugal"},
    {"flag": "🇳🇴", "country": "Norway"},
    {"flag": "🇹🇷", "country": "Turkey"},
    {"flag": "🇺🇦", "country": "Ukraine"},
    {"flag": "🇵🇱", "country": "Poland"},
    {"flag": "🇮🇩", "country": "Indonesia"},
    {"flag": "🇵🇰", "country": "Pakistan"},
    {"flag": "🇧🇩", "country": "Bangladesh"},
    {"flag": "🇵🇭", "country": "Philippines"},
    {"flag": "🇹🇭", "country": "Thailand"},
    {"flag": "🇻🇳", "country": "Vietnam"},
    {"flag": "🇲🇾", "country": "Malaysia"},
    {"flag": "🇸🇬", "country": "Singapore"},
    {"flag": "🇳🇿", "country": "New Zealand"},
    {"flag": "🇮🇪", "country": "Ireland"},
    {"flag": "🇩🇰", "country": "Denmark"},
    {"flag": "🇫🇮", "country": "Finland"},
    {"flag": "🇸🇦", "country": "Saudi Arabia"},
    {"flag": "🇮🇱", "country": "Israel"},
    {"flag": "🇮🇷", "country": "Iran"},
    {"flag": "🇦🇪", "country": "United Arab Emirates"},
    {"flag": "🇶🇦", "country": "Qatar"},
]


COUNTRIES = [f["country"] for f in FLAGS]

# ===================== HELPERS =====================
async def ensure_player(user_id: int, username: str):
    """Ensure player exists in DB."""
    user = await players_col.find_one({"_id": user_id})
    if not user:
        await players_col.insert_one({
            "_id": user_id,
            "username": username,
            "score": 0,
            "games_played": 0,
            "wins": 0
        })

async def update_score(user_id: int, points: int, won: bool = False):
    """Update score + stats."""
    inc_data = {"score": points, "games_played": 1}
    if won:
        inc_data["wins"] = 1
    await players_col.update_one({"_id": user_id}, {"$inc": inc_data})

async def get_leaderboard(limit: int = 10):
    """Top players by score."""
    cursor = players_col.find().sort("score", -1).limit(limit)
    return await cursor.to_list(length=limit)

# ===================== GAME LOGIC =====================
@app.on_message(filters.command("flgstart"))
async def start_command(client: Client, message: Message):
    await ensure_player(message.from_user.id, message.from_user.username or "")
    await message.reply_text(
        "🌍 Welcome to Flag Quiz!\n\n"
        "Guess the country by its flag.\n\n"
        "Commands:\n"
        "/quiz - Start a quiz\n"
        "/leaderboard - Show top players\n"
        "/profile - Show your stats"
    )

@app.on_message(filters.command("flgquiz") & filters.group)
async def qflguiz_command(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in active_games:
        return await message.reply_text("⚠️ A quiz is already running in this chat!")

    question = random.choice(FLAGS)
    flag = question["flag"]
    answer = question["country"]

    # Generate multiple choice options
    options: List[str] = random.sample(COUNTRIES, 3)
    if answer not in options:
        options[random.randint(0, 2)] = answer
    random.shuffle(options)

    buttons = [[InlineKeyboardButton(opt, callback_data=f"flag_{opt}")] for opt in options]

    msg = await message.reply_text(
        f"🌍 Flag Quiz!\n\nWhat country is this flag?\n\n{flag}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    active_games[chat_id] = {
        "message_id": msg.id,
        "chat_id": chat_id,
        "answer": answer,
        "start_time": time.time(),
        "answered": False
    }

    await asyncio.sleep(5)

    if chat_id in active_games and not active_games[chat_id]["answered"]:
        correct = active_games[chat_id]["answer"]
        await msg.edit_text(f"⏰ Time's up! The correct answer was: {correct}")
        del active_games[chat_id]

@app.on_callback_query(filters.regex(r"flag_"))
async def flhhag_answer(client: Client, cq: CallbackQuery):
    user = cq.from_user
    chat_id = cq.message.chat.id
    chosen = cq.data.replace("flag_", "")

    if chat_id not in active_games:
        return await cq.answer("No active quiz!", show_alert=True)

    game = active_games[chat_id]
    if cq.message.id != game["message_id"]:
        return await cq.answer("This quiz is no longer active!", show_alert=True)

    await ensure_player(user.id, user.username or "")

    if game["answered"]:
        return await cq.answer("Too late! Someone already answered!", show_alert=True)

    if chosen == game["answer"]:
        game["answered"] = True
        reaction_time = round(time.time() - game["start_time"], 2)
        points = max(1, 10 - int(reaction_time))

        await update_score(user.id, points, won=True)

        await cq.message.edit_text(
            f"✅ {user.mention} answered correctly!\n"
            f"Country: {game['answer']}\n"
            f"Time: {reaction_time}s\n"
            f"+{points} points 🎉"
        )
    else:
        await update_score(user.id, 0)
        await cq.answer("❌ Wrong answer!", show_alert=True)

@app.on_message(filters.command("flgleaderboard"))
async def leaderrhrboard_command(client: Client, message: Message):
    top_players = await get_leaderboard()
    if not top_players:
        return await message.reply_text("No players yet.")

    text = "🏆 <b>Leaderboard</b> 🏆\n\n"
    for i, player in enumerate(top_players, start=1):
        uname = f"@{player['username']}" if player.get("username") else f"ID:{player['_id']}"
        text += f"{i}. {uname} - {player['score']} pts\n"

    await message.reply_text(text)

@app.on_message(filters.command("flgprofile"))
async def profilflge_command(client: Client, message: Message):
    user_id = message.from_user.id
    await ensure_player(user_id, message.from_user.username or "")

    profile = await players_col.find_one({"_id": user_id})
    text = (
        f"👤 <b>Profile</b>\n\n"
        f"User: {message.from_user.mention}\n"
        f"Score: {profile['score']}\n"
        f"Games Played: {profile['games_played']}\n"
        f"Wins: {profile['wins']}\n"
    )
    await message.reply_text(text)

