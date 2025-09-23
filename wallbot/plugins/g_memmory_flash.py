import os
import random
import asyncio
import logging
from typing import List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as bot


# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["memory_flash"]
users_col = db["users"]
games_col = db["games"]

# ---------------- EMOJIS ---------------- #
EMOJIS = ["🍎", "🍌", "🍉", "🍍", "🍇", "🍓", "🍒", "🥝", "🍑", "🥭", "🍊"]

# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "name": name, "games_played": 0, "wins": 0, "score": 0}
        await users_col.insert_one(user)
    return user

async def update_stats(user_id: int, name: str, won: bool = False, difficulty: int = 4):
    await get_user(user_id, name)
    update = {"$inc": {"games_played": 1}}
    if won:
        update["$inc"] = {"games_played": 1, "wins": 1, "score": difficulty * 10}
    await users_col.update_one({"_id": user_id}, update)

async def get_leaderboard() -> str:
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Memory Flash Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (Wins: {user['wins']})\n"
        pos += 1
    return text

def generate_sequence(length: int) -> List[str]:
    return random.sample(EMOJIS, length)

def make_answer_buttons(options: List[str], seq: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    for i in range(0, len(options), 3):
        row = []
        for j in range(3):
            if i + j < len(options):
                choice = options[i + j]
                row.append(InlineKeyboardButton(choice, callback_data=f"mans|{''.join(seq)}|{choice}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

@bot.on_message(filters.command("mfleaderboard"))
async def leadeccrboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)

@bot.on_message(filters.command("mfplay"))
async def plfgay_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    difficulty = 4
    sequence = generate_sequence(difficulty)

    game = {
        "chat_id": chat_id,
        "owner_id": user.id,
        "owner_name": user.first_name,
        "sequence": sequence,
        "difficulty": difficulty,
        "active": True,
        "answered": False,
    }
    await games_col.replace_one({"chat_id": chat_id}, game, upsert=True)

    flash = " ".join(sequence)
    msg = await message.reply(f"⚡ Memorize this sequence:\n\n{flash}")
    await asyncio.sleep(3)

    try:
        options = ["".join(sequence)]
        while len(options) < 6:  # add wrong options
            fake = "".join(random.sample(EMOJIS, difficulty))
            if fake not in options:
                options.append(fake)
        random.shuffle(options)

        await msg.edit_text(
            "❓ Which sequence was correct?",
            reply_markup=make_answer_buttons(options, sequence),
        )
    except Exception:
        pass

# ---------------- CALLBACK HANDLER ---------------- #
@bot.on_callback_query(filters.regex("^mans"))
async def callback_answer(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    user = query.from_user
    data = query.data.split("|")
    correct = data[1]
    choice = data[2]

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return await query.answer("⚠️ No active game!", show_alert=True)

    if user.id != game["owner_id"]:
        return await query.answer("❌ Only the game owner can answer!", show_alert=True)

    if game["answered"]:
        return await query.answer("✅ Already answered! Use /play to start again.", show_alert=True)

    if choice == correct:
        await update_stats(user.id, user.first_name, won=True, difficulty=game["difficulty"])
        await games_col.update_one({"chat_id": chat_id}, {"$set": {"answered": True, "active": False}})
        await query.message.edit_text(f"🎉 Correct, {user.mention}! Sequence was: {correct}")
    else:
        await query.answer("❌ Wrong choice! Try again.", show_alert=True)

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    logger.info("🤖 Memory Flash Bot Started!")
    bot.run()
