import os
import random
import logging
from typing import List, Dict

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)
from config import DB_URL
from main import wbot as bot

from motor.motor_asyncio import AsyncIOMotorClient
MONGO_URL = os.getenv("DB_URL")


# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["truth_or_dare"]
users_col = db["users"]

# ---------------- DATA ---------------- #
TRUTHS: List[str] = [
    "What’s your most embarrassing moment?",
    "What’s a secret you’ve never told anyone?",
    "Who was your first crush?",
    "What’s the silliest thing you’ve done to impress someone?",
    "What is your guilty pleasure?",
]

DARES: List[str] = [
    "Send your last photo from gallery.",
    "Do 10 pushups right now and send proof!",
    "Send a voice note singing a song.",
    "Change your profile picture to a funny meme for 1 hour.",
    "Type a message using only emojis for the next 5 minutes.",
]

# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str) -> Dict:
    """Fetch or create user profile"""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "name": name,
            "games_played": 0,
            "truths_done": 0,
            "dares_done": 0,
            "score": 0,
        }
        await users_col.insert_one(user)
    return user


async def update_stats(user_id: int, name: str, truth: bool = False, dare: bool = False):
    """Update truth/dare stats"""
    await get_user(user_id, name)
    update = {"$inc": {"games_played": 1}}
    if truth:
        update["$inc"]["truths_done"] = 1
        update["$inc"]["score"] = 5
    if dare:
        update["$inc"]["dares_done"] = 1
        update["$inc"]["score"] = 10
    await users_col.update_one({"_id": user_id}, update)


async def get_leaderboard() -> str:
    """Return formatted leaderboard"""
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Truth or Dare Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (T:{user['truths_done']} D:{user['dares_done']})\n"
        pos += 1
    return text


def build_choice_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎭 Truth", callback_data=f"truth:{user_id}"),
                InlineKeyboardButton("🔥 Dare", callback_data=f"dare:{user_id}"),
            ]
        ]
    )

# ---------------- COMMANDS ---------------- #
@bot.on_message(filters.command("tddstart"))
async def stdddart_cmd(_, message: Message):
    await get_user(message.from_user.id, message.from_user.first_name)
    await message.reply(
        "👋 Welcome to <b>Truth or Dare Bot!</b>\n\n"
        "Use /truthdare @username to challenge someone!\n"
        "Use /leaderboard to see top players."
    )


@bot.on_message(filters.command("tdleaderboard"))
async def leadertdfboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("truthdare"))
async def truth_dare_cmd(_, message: Message):
    if not message.reply_to_message and not message.entities:
        await message.reply("Usage: <code>/truthdare @username</code> or reply to a user.")
        return

    # Get target user
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        if len(message.command) < 2:
            await message.reply("Tag someone to play!")
            return
        target = message.entities[1].user

    if not target:
        await message.reply("❌ Could not find user.")
        return

    await get_user(target.id, target.first_name)

    await message.reply(
        f"🎯 <b>{target.first_name}</b>, choose your fate!",
        reply_markup=build_choice_keyboard(target.id),
    )

# ---------------- CALLBACKS ---------------- #
@bot.on_callback_query(filters.regex(r"^(truth|dare):"))
async def choice_cb(_, query: CallbackQuery):
    action, target_id = query.data.split(":")
    target_id = int(target_id)

    if query.from_user.id != target_id:
        await query.answer("This choice is not for you!", show_alert=True)
        return

    if action == "truth":
        truth = random.choice(TRUTHS)
        await update_stats(query.from_user.id, query.from_user.first_name, truth=True)
        await query.message.reply(f"🎭 Truth for {query.from_user.mention}:\n\n<b>{truth}</b>")
        await query.answer("Truth chosen!")
    else:
        dare = random.choice(DARES)
        await update_stats(query.from_user.id, query.from_user.first_name, dare=True)
        await query.message.reply(f"🔥 Dare for {query.from_user.mention}:\n\n<b>{dare}</b>")
        await query.answer("Dare chosen!")

    try:
        await query.message.edit_reply_markup(None)
    except Exception:
        pass
