import asyncio
import os
import random
import string
import logging
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from config import DB_URL
from wallbot import wbot as bot


# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["memory_tiles"]
users_col = db["users"]
games_col = db["games"]


# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str):
    """Fetch or create user profile"""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "name": name,
            "score": 0,
            "games_played": 0,
            "wins": 0
        }
        await users_col.insert_one(user)
    return user


async def update_score(user_id: int, name: str, points: int):
    """Update player score"""
    await get_user(user_id, name)
    await users_col.update_one(
        {"_id": user_id},
        {"$inc": {"score": points, "games_played": 1}}
    )


async def get_leaderboard() -> str:
    """Return formatted leaderboard"""
    top = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Leaderboard</b>\n\n"
    pos = 1
    async for user in top:
        text += f"{pos}. {user['name']} - {user['score']} pts\n"
        pos += 1
    return text


def generate_tiles(size: int = 4) -> List[List[str]]:
    """Generate shuffled tiles (pairs of emojis hidden behind buttons)"""
    emojis = ["🍎", "🍌", "🍇", "🍉", "🍓", "🍒", "🍑", "🥑"]
    needed = (size * size) // 2
    chosen = random.sample(emojis, needed)
    pairs = chosen * 2
    random.shuffle(pairs)
    grid = [pairs[i:i + size] for i in range(0, len(pairs), size)]
    return grid


def build_keyboard(size: int, revealed: List[List[bool]], grid: List[List[str]]) -> InlineKeyboardMarkup:
    """Build InlineKeyboard for current game state"""
    keyboard = []
    for i in range(size):
        row = []
        for j in range(size):
            if revealed[i][j]:
                row.append(InlineKeyboardButton(grid[i][j], callback_data=f"noop"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"tile:{i}:{j}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


def game_id_gen():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


# ---------------- GAME LOGIC ---------------- #
@bot.on_message(filters.command("mtstart"))
async def start_djjgame(_, message: Message):
    await get_user(message.from_user.id, message.from_user.first_name)
    await message.reply("👋 Welcome to <b>Memory Tiles!</b>\nUse /play to start a game.\nUse /leaderboard to see top players.")


@bot.on_message(filters.command("mtleaderboard"))
async def leaderboardud_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("mtplay"))
async def play_gmreame(_, message: Message):
    size = 4
    grid = generate_tiles(size)
    revealed = [[False for _ in range(size)] for _ in range(size)]
    game_id = game_id_gen()

    game_data = {
        "_id": game_id,
        "chat_id": message.chat.id,
        "grid": grid,
        "revealed": revealed,
        "moves": [],
        "found": [],
        "turn": None,
        "players": {},
        "finished": False
    }
    await games_col.insert_one(game_data)

    keyboard = build_keyboard(size, revealed, grid)
    await message.reply("🧩 <b>Memory Tiles started!</b>\nTap tiles to reveal.", reply_markup=keyboard)


@bot.on_callback_query(filters.regex(r"^tile:"))
async def tile_pressed(_, query: CallbackQuery):
    user = query.from_user
    game = await games_col.find_one({"chat_id": query.message.chat.id, "finished": False})
    if not game:
        await query.answer("❌ No active game!", show_alert=True)
        return

    size = len(game["grid"])
    _, i, j = query.data.split(":")
    i, j = int(i), int(j)

    if game["revealed"][i][j]:
        await query.answer("Already revealed!", show_alert=False)
        return

    # Reveal selected tile
    game["revealed"][i][j] = True
    game["moves"].append((i, j, user.id, user.first_name))

    # Save move
    await games_col.update_one({"_id": game["_id"]}, {"$set": {"revealed": game["revealed"], "moves": game["moves"]}})

    # If two moves made
    if len(game["moves"]) % 2 == 0:
        m1, m2 = game["moves"][-2], game["moves"][-1]
        x1, y1, u1, _ = m1
        x2, y2, u2, _ = m2

        if game["grid"][x1][y1] == game["grid"][x2][y2]:
            # Matched
            game["found"].append((x1, y1))
            game["found"].append((x2, y2))
            await update_score(user.id, user.first_name, 10)
            await query.answer("✅ Matched! +10 points")
        else:
            # Wrong match: flip back after short delay
            await asyncio.sleep(2)
            game["revealed"][x1][y1] = False
            game["revealed"][x2][y2] = False
            await query.answer("❌ No match!")

        await games_col.update_one({"_id": game["_id"]}, {"$set": {"revealed": game["revealed"], "found": game["found"]}})

    # Check if finished
    total_pairs = (size * size)
    if len(game["found"]) == total_pairs:
        await games_col.update_one({"_id": game["_id"]}, {"$set": {"finished": True}})
        lb = await get_leaderboard()
        await query.message.edit_text("🎉 <b>Game finished!</b>\n\n" + lb)
        return

    # Update board
    keyboard = build_keyboard(size, game["revealed"], game["grid"])
    try:
        await query.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
