import os
import random
import logging
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as bot


# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["odd_one"]
users_col = db["users"]
games_col = db["games"]

# ---------------- GAME POOLS ---------------- #
ODD_SETS = [
    {"set": ["🍏", "🍎"], "odd": "🍎", "main": "🍏"},
    {"set": ["⚽", "🏀"], "odd": "🏀", "main": "⚽"},
    {"set": ["🐱", "🐶"], "odd": "🐶", "main": "🐱"},
    {"set": ["🚗", "🚲"], "odd": "🚲", "main": "🚗"},
    {"set": ["🎸", "🥁"], "odd": "🥁", "main": "🎸"},
    {"set": ["🐟", "🦋"], "odd": "🦋", "main": "🐟"},
    {"set": ["🌞", "🌙"], "odd": "🌙", "main": "🌞"},
    {"set": ["🍔", "🍕"], "odd": "🍕", "main": "🍔"},
    {"set": ["📱", "💻"], "odd": "💻", "main": "📱"},
]

# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str) -> Dict:
    """Fetch or create user profile"""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "name": name, "games_played": 0, "wins": 0, "score": 0}
        await users_col.insert_one(user)
    return user


async def update_stats(user_id: int, name: str, won: bool = False):
    """Update user stats"""
    await get_user(user_id, name)
    update = {"$inc": {"games_played": 1}}
    if won:
        update["$inc"] = {"games_played": 1, "wins": 1, "score": 20}
    await users_col.update_one({"_id": user_id}, update)


async def get_leaderboard() -> str:
    """Return leaderboard text"""
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Tap the Odd One Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (Wins: {user['wins']})\n"
        pos += 1
    return text


def generate_grid(main: str, odd: str) -> str:
    """Create a 3x3 grid with one odd emoji"""
    grid = [main] * 9
    odd_pos = random.randint(0, 8)
    grid[odd_pos] = odd
    rows = [" ".join(grid[i:i+3]) for i in range(0, 9, 3)]
    return "\n".join(rows), odd


# ---------------- COMMANDS ---------------- #
@bot.on_message(filters.command("odostart"))
async def start_cmd(_, message: Message):
    await get_user(message.from_user.id, message.from_user.first_name)
    await message.reply(
        "👋 Welcome to <b>Tap the Odd One!</b>\n\n"
        "Commands:\n"
        "/play – Start a private puzzle (only you can answer)\n"
        "/guess <emoji> – Submit your answer\n"
        "/hint – Get a hint\n"
        "/skip – Skip current puzzle\n"
        "/next – New puzzle\n"
        "/leaderboard – Show top players"
    )


@bot.on_message(filters.command("odoleaderboard"))
async def odoleaderboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("odoplay"))
async def plaodoy_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user

    puzzle_data = random.choice(ODD_SETS)
    grid, odd = generate_grid(puzzle_data["main"], puzzle_data["odd"])

    game = {
        "chat_id": chat_id,
        "owner_id": user.id,
        "owner_name": user.first_name,
        "odd": odd,
        "grid": grid,
        "active": True,
        "guessed": False,
    }
    await games_col.replace_one({"chat_id": chat_id}, game, upsert=True)

    await message.reply(
        f"🎮 <b>Tap the Odd One!</b>\n\n{grid}\n\n"
        f"👉 Only {user.mention} can answer with /guess <emoji>"
    )


@bot.on_message(filters.command("odoguess"))
async def gueodoss_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    args = message.text.split(" ", 1)

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return await message.reply("⚠️ No active game. Use /play to start.")

    if user.id != game["owner_id"]:
        return await message.reply("❌ Only the game owner can guess this round!")

    if len(args) < 2:
        return await message.reply("Usage: /guess <emoji>")

    guess = args[1].strip()

    if game["guessed"]:
        return await message.reply("✅ Puzzle already solved. Use /next for another!")

    if guess == game["odd"]:
        await update_stats(user.id, user.first_name, won=True)
        await games_col.update_one({"chat_id": chat_id}, {"$set": {"guessed": True, "active": False}})
        await message.reply(f"🎉 Correct, {user.mention}! The odd one was {game['odd']}")
    else:
        await message.reply("❌ Wrong guess, try again!")


@bot.on_message(filters.command("odohint"))
async def hint_odocmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return await message.reply("⚠️ No active game to hint.")

    if user.id != game["owner_id"]:
        return await message.reply("❌ Only the game owner can use hints!")

    await message.reply("💡 Hint: Look carefully at the grid, one emoji is different!")


@bot.on_message(filters.command("odoskip"))
async def sdodkip_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return await message.reply("⚠️ No active game to skip.")

    if user.id != game["owner_id"]:
        return await message.reply("❌ Only the game owner can skip!")

    await games_col.update_one({"chat_id": chat_id}, {"$set": {"active": False}})
    await message.reply("⏭️ Puzzle skipped. Use /next to try another!")


@bot.on_message(filters.command("odonext"))
async def nexodot_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    game = await games_col.find_one({"chat_id": chat_id})
    if game and user.id != game["owner_id"]:
        return await message.reply("❌ Only the game owner can start next puzzle!")

    puzzle_data = random.choice(ODD_SETS)
    grid, odd = generate_grid(puzzle_data["main"], puzzle_data["odd"])

    new_game = {
        "chat_id": chat_id,
        "owner_id": user.id,
        "owner_name": user.first_name,
        "odd": odd,
        "grid": grid,
        "active": True,
        "guessed": False,
    }
    await games_col.replace_one({"chat_id": chat_id}, new_game, upsert=True)

    await message.reply(
        f"🎮 <b>Tap the Odd One!</b>\n\n{grid}\n\n"
        f"👉 Only {user.mention} can answer with /guess <emoji>"
    )

