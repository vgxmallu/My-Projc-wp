import os
import random
import logging
from typing import Dict, List

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

# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["memory_tiles"]
users_col = db["users"]
games_col = db["games"]


# ---------------- GAME DATA ---------------- #
EMOJIS = ["🍎", "🍌", "🍒", "🍇", "🍉", "🍋", "🍓", "🥝"]  # pairs
TILE = "❓"

# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str) -> Dict:
    """Fetch or create user profile"""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "name": name,
            "games_played": 0,
            "matches": 0,
            "score": 0,
        }
        await users_col.insert_one(user)
    return user


async def update_stats(user_id: int, name: str, score: int):
    """Update player stats"""
    await get_user(user_id, name)
    update = {"$inc": {"games_played": 1, "matches": 1, "score": score}}
    await users_col.update_one({"_id": user_id}, update)


async def get_leaderboard() -> str:
    """Return formatted leaderboard"""
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Memory Tiles Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (Matches: {user['matches']})\n"
        pos += 1
    return text


def build_board(board: List[str], revealed: List[bool]) -> InlineKeyboardMarkup:
    """Builds inline keyboard for the board"""
    size = int(len(board) ** 0.5)
    buttons = []
    for i in range(size):
        row = []
        for j in range(size):
            idx = i * size + j
            label = board[idx] if revealed[idx] else TILE
            row.append(InlineKeyboardButton(label, callback_data=f"tile:{idx}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# ---------------- COMMANDS ---------------- #
@bot.on_message(filters.command("mtdfstart"))
async def start_ffcmd(_, message: Message):
    await get_user(message.from_user.id, message.from_user.first_name)
    await message.reply(
        "👋 Welcome to <b>Memory Tiles!</b>\n\n"
        "Use /play to start a new game.\n"
        "Use /leaderboard to see top players."
    )


@bot.on_message(filters.command("mtleaderboard"))
async def leaderddboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("mtplay"))
async def play_mttcmd(_, message: Message):
    user_id = message.from_user.id
    name = message.from_user.first_name

    # Setup game board
    pairs = EMOJIS[:]
    board = pairs * 2
    random.shuffle(board)
    revealed = [False] * len(board)

    game = {
        "user_id": user_id,
        "chat_id": message.chat.id,
        "board": board,
        "revealed": revealed,
        "flipped": [],
        "score": 0,
    }
    await games_col.replace_one({"chat_id": message.chat.id, "user_id": user_id}, game, upsert=True)

    await message.reply(
        f"🎮 <b>{name}</b> started a Memory Tiles game!\n"
        "Only you can play this game. Tap tiles to reveal.",
        reply_markup=build_board(board, revealed),
    )

# ---------------- CALLBACK ---------------- #
@bot.on_callback_query(filters.regex(r"^tile:"))
async def tile_cb(_, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    data = int(query.data.split(":")[1])

    game = await games_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not game:
        await query.answer("❌ This is not your game!", show_alert=True)
        return

    board = game["board"]
    revealed = game["revealed"]
    flipped = game["flipped"]
    score = game["score"]

    if revealed[data]:
        await query.answer("Already revealed!")
        return

    flipped.append(data)
    revealed[data] = True

    if len(flipped) == 2:
        i, j = flipped
        if board[i] == board[j]:
            score += 10
            await update_stats(user_id, query.from_user.first_name, 10)
            await query.answer("✅ Match found! +10 points")
        else:
            revealed[i] = False
            revealed[j] = False
            await query.answer("❌ Not a match!")

        flipped.clear()

    await games_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"board": board, "revealed": revealed, "flipped": flipped, "score": score}},
    )

    await query.message.edit_text(
        f"🎮 Memory Tiles - Score: {score}",
        reply_markup=build_board(board, revealed),
    )

    if all(revealed):
        await query.message.edit_text(
            f"🎉 Game Over! Final Score: {score}\nUse /leaderboard to check ranks."
        )
        await games_col.delete_one({"chat_id": chat_id, "user_id": user_id})

