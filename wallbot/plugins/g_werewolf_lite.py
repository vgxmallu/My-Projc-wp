import os
import random
import logging
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from config import DB_URL
from wallbot import wbot as bot



# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["werewolf_lite"]
users_col = db["users"]
games_col = db["games"]

# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str) -> Dict:
    """Fetch or create user profile"""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "name": name,
            "games_played": 0,
            "wins": 0,
            "score": 0,
        }
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
    text = "🏆 <b>Werewolf Lite Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (Wins: {user['wins']})\n"
        pos += 1
    return text


def build_join_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ Join Game", callback_data="join")]])


def build_vote_keyboard(players: List[Dict]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(p["name"], callback_data=f"vote:{p['_id']}")] for p in players if p["alive"]]
    return InlineKeyboardMarkup(buttons)


def build_seer_keyboard(players: List[Dict]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(p["name"], callback_data=f"seer:{p['_id']}")] for p in players if p["alive"]]
    return InlineKeyboardMarkup(buttons)




@bot.on_message(filters.command("wlleaderboard"))
async def leaderboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("wwnewgame"))
async def newgame_cmd(_, message: Message):
    chat_id = message.chat.id

    # Create empty game
    game = {
        "chat_id": chat_id,
        "players": [],
        "started": False,
        "phase": "lobby",
    }
    await games_col.replace_one({"chat_id": chat_id}, game, upsert=True)

    await message.reply("🎮 New game started! Press below to join.", reply_markup=build_join_button())

# ---------------- CALLBACKS ---------------- #
@bot.on_callback_query(filters.regex(r"^join$"))
async def join_cb(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    user = query.from_user
    game = await games_col.find_one({"chat_id": chat_id})

    if not game or game["started"]:
        await query.answer("❌ No active lobby!", show_alert=True)
        return

    if any(p["_id"] == user.id for p in game["players"]):
        await query.answer("Already joined!")
        return

    game["players"].append({"_id": user.id, "name": user.first_name, "alive": True, "role": None})
    await games_col.update_one({"chat_id": chat_id}, {"$set": {"players": game["players"]}})

    await query.message.edit_text(
        f"🎮 Players joined: {len(game['players'])}\n"
        "➕ Tap to join!",
        reply_markup=build_join_button(),
    )


@bot.on_message(filters.command("wstartgame"))
async def startgamjje_cmd(_, message: Message):
    chat_id = message.chat.id
    game = await games_col.find_one({"chat_id": chat_id})

    if not game or game["started"]:
        await message.reply("❌ No lobby available!")
        return

    players = game["players"]
    if len(players) < 3:
        await message.reply("❌ Need at least 3 players to start.")
        return

    # Assign roles
    roles = ["wolf", "seer"] + ["villager"] * (len(players) - 2)
    random.shuffle(roles)
    for i, p in enumerate(players):
        p["role"] = roles[i]

    await games_col.update_one({"chat_id": chat_id}, {"$set": {"players": players, "started": True, "phase": "night"}})

    # DM players their roles
    for p in players:
        try:
            if p["role"] == "wolf":
                await bot.send_message(p["_id"], "🐺 You are the Wolf! Work secretly to eliminate others.")
            elif p["role"] == "seer":
                await bot.send_message(p["_id"], "🔮 You are the Seer! Each night you can check a player’s role.")
            else:
                await bot.send_message(p["_id"], "👨 You are a Villager! Try to find the wolf.")
        except Exception:
            pass

    await message.reply("🌙 Night falls! Wolves and Seer, act now.")


@bot.on_callback_query(filters.regex(r"^vote:"))
async def vote_cb(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    voter = query.from_user
    target_id = int(query.data.split(":")[1])

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["started"] or game["phase"] != "day":
        await query.answer("❌ Not voting phase!", show_alert=True)
        return

    voter_data = next((p for p in game["players"] if p["_id"] == voter.id and p["alive"]), None)
    if not voter_data:
        await query.answer("❌ You are dead or not in the game!", show_alert=True)
        return

    target = next((p for p in game["players"] if p["_id"] == target_id), None)
    if not target:
        await query.answer("Invalid target")
        return

    target["alive"] = False
    await games_col.update_one({"chat_id": chat_id}, {"$set": {"players": game["players"], "phase": "night"}})

    await query.message.reply(f"☀️ Day vote: {target['name']} was eliminated.")
    await query.answer("Vote recorded!")


@bot.on_callback_query(filters.regex(r"^seer:"))
async def seer_cb(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    seer = query.from_user
    target_id = int(query.data.split(":")[1])

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["started"] or game["phase"] != "night":
        await query.answer("❌ Not night phase!", show_alert=True)
        return

    seer_data = next((p for p in game["players"] if p["_id"] == seer.id and p["alive"] and p["role"] == "seer"), None)
    if not seer_data:
        await query.answer("❌ You are not the Seer!", show_alert=True)
        return

    target = next((p for p in game["players"] if p["_id"] == target_id), None)
    if not target:
        await query.answer("Invalid target")
        return

    await bot.send_message(seer.id, f"🔮 {target['name']} is a <b>{target['role'].capitalize()}</b>")
    await query.answer("Seer vision sent!")
