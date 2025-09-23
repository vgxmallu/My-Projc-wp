import os
import random
import logging
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as bot

# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["emoji_combo"]
users_col = db["users"]
games_col = db["games"]


# ---------------- GAME DATA ---------------- #
PUZZLES = [
    {"emoji": "🐍⚡🧙", "answer": ["harry potter", "potter", "harry"]},
    {"emoji": "🦁👑", "answer": ["lion king", "the lion king"]},
    {"emoji": "💍🌋", "answer": ["lord of the rings", "the lord of the rings"]},
    {"emoji": "⭐⚔️", "answer": ["star wars"]},
    {"emoji": "🚢🥶💔", "answer": ["titanic"]},
    {"emoji": "🦖🏞️", "answer": ["jurassic park", "jurassic world"]},
    {"emoji": "🦇🃏", "answer": ["batman", "the dark knight", "joker"]},
    {"emoji": "🦸‍♂️🦸‍♀️⚡", "answer": ["avengers", "marvel", "endgame", "the avengers"]},
    {"emoji": "🕷️🧑", "answer": ["spiderman", "spider man"]},
    {"emoji": "🧊👑", "answer": ["frozen", "elsa"]},
    {"emoji": "🤠🚀🧸", "answer": ["toy story"]},
    {"emoji": "🎈🏠👴", "answer": ["up"]},
    {"emoji": "🐟🐠", "answer": ["finding nemo", "finding dory"]},
    {"emoji": "ALIEN🚲", "answer": ["et", "e.t. the extra-terrestrial"]},
    {"emoji": "🚗🕰️⚡", "answer": ["back to the future"]},
    {"emoji": "👻🚫", "answer": ["ghostbusters"]},
    {"emoji": "🦈🌊", "answer": ["jaws"]},
    {"emoji": "🏃‍♂️🍫🍤", "answer": ["forrest gump"]},
    {"emoji": "🐀👨‍🍳🇫🇷", "answer": ["ratatouille"]},
    {"emoji": "🤖❤️🌱", "answer": ["wall-e", "walle"]},
    {"emoji": "🏠😱", "answer": ["home alone"]},
    {"emoji": "🔫🤵🍸", "answer": ["james bond", "007", "skyfall", "no time to die"]},
    {"emoji": "🏹🔥", "answer": ["the hunger games", "hunger games"]},
    {"emoji": "👠🌪️🌈", "answer": ["the wizard of oz", "wizard of oz"]},
    {"emoji": "😴🔄", "answer": ["inception"]},
    {"emoji": "🥋🐼", "answer": ["kung fu panda"]},
    {"emoji": "💇‍♀️🗼", "answer": ["tangled", "rapunzel"]},
    {"emoji": "🍫🏭", "answer": ["charlie and the chocolate factory", "willy wonka"]},
    {"emoji": "🐒🧞‍♂️", "answer": ["aladdin"]},
    {"emoji": "🌊⛵️🌺", "answer": ["moana"]},
    {"emoji": "🎸💀🇲🇽", "answer": ["coco"]},
    {"emoji": "👨‍💼💼⏰", "answer": ["the wolf of wall street", "wolf of wall street"]},
    {"emoji": "🧑‍🔬➡️🧟", "answer": ["i am legend"]},
    {"emoji": "🦁🧙‍♀️🚪", "answer": ["the chronicles of narnia", "narnia"]},
    {"emoji": "💊🕶️", "answer": ["the matrix", "matrix"]},
    {"emoji": "🦍🗼", "answer": ["king kong"]},
    {"emoji": "🤡🎈", "answer": ["it"]},
    {"emoji": "🐺🌕", "answer": ["twilight"]},
    {"emoji": "🏃‍♂️💥🕶️", "answer": ["mission impossible"]},
    {"emoji": "🦸‍♂️👨‍👩‍👧‍👦", "answer": ["the incredibles", "incredibles"]},
    {"emoji": "🐉🧑‍🤝‍🧑 Viking", "answer": ["how to train your dragon"]},
    {"emoji": "🏴‍☠️🦜⚔️", "answer": ["pirates of the caribbean"]},
    {"emoji": "🍊🤵🇮🇹", "answer": ["the godfather", "godfather"]},
    {"emoji": "💃🕺🍔", "answer": ["pulp fiction"]},
    {"emoji": "👭🚲🚪", "answer": ["the shining"]},
    {"emoji": "🤫👂怪物", "answer": ["a quiet place"]},
    {"emoji": "🧑‍🚀🥔🔴", "answer": ["the martian"]},
    {"emoji": "🚗🔥🎸", "answer": ["mad max fury road", "mad max"]},
    {"emoji": "🕶️👽🔫", "answer": ["men in black", "mib"]},
    {"emoji": "🚗💨👨‍𦲲", "answer": ["fast and furious"]},
    {"emoji": "🤖🚗🚚", "answer": ["transformers"]},
    {"emoji": "🐇🎩☕️", "answer": ["alice in wonderland"]},
    {"emoji": "🎲🐒🦁", "answer": ["jumanji"]},
    {"emoji": "🟢🧅 Donkey", "answer": ["shrek"]},
    {"emoji": "🐿️🌰❄️", "answer": ["ice age"]},
    {"emoji": "🦊🐰🥕", "answer": ["zootopia"]},
    {"emoji": "🌹👹👸", "answer": ["beauty and the beast"]},
    {"emoji": "👠🐭🎃", "answer": ["cinderella"]},
    {"emoji": "🧜‍♀️🦀🐠", "answer": ["the little mermaid"]},
    {"emoji": "🗡️🐉🇨🇳", "answer": ["mulan"]},
    {"emoji": "🐯🎰👶", "answer": ["the hangover", "hangover"]},
    {"emoji": "🗡️💛⚫️", "answer": ["kill bill"]},
    {"emoji": "🏟️⚔️🛡️", "answer": ["gladiator"]},
    {"emoji": "🏴󠁧󠁢󠁳󠁣󠁴󠁿⚔️💙", "answer": ["braveheart"]},
    {"emoji": " D-Day 🎖️🇺🇸", "answer": ["saving private ryan"]},
    {"emoji": "🍑🏠🐛", "answer": ["parasite"]},
    {"emoji": "💃🕺🎹", "answer": ["la la land"]},
    {"emoji": "🐻🥶🛶", "answer": ["the revenant"]},
    {"emoji": "🐦📦🙈", "answer": ["bird box"]},
    {"emoji": "🐾👑 Vibranium", "answer": ["black panther"]},
    {"emoji": "🧙‍♂️👁️⏰", "answer": ["doctor strange"]},
    {"emoji": "🦝🌳📼", "answer": ["guardians of the galaxy"]},
    {"emoji": "👩‍🎤🛡️ lasso", "answer": ["wonder woman"]},
    {"emoji": "🔱🌊🐠", "answer": ["aquaman"]},
    {"emoji": "☕️🧠 Sunken Place", "answer": ["get out"]},
    {"emoji": "✂️👯‍♀️🐰", "answer": ["us"]},
    {"emoji": "🐶✏️🔫", "answer": ["john wick"]},
    {"emoji": "🎪🎩🎤", "answer": ["the greatest showman"]},
    {"emoji": "🎤🎸👩‍🎤", "answer": ["a star is born"]},
    {"emoji": "🔪🍩🧐", "answer": ["knives out"]},
    {"emoji": "🧟‍♂️🌍", "answer": ["zombie world", "world war z"]},
    {"emoji": "🚀🌍", "answer": ["space travel", "interstellar", "gravity"]},
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
        update["$inc"] = {"games_played": 1, "wins": 1, "score": 15}
    await users_col.update_one({"_id": user_id}, update)


async def get_leaderboard() -> str:
    """Return leaderboard text"""
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Emoji Combo Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} - {user['score']} pts (Wins: {user['wins']})\n"
        pos += 1
    return text


def build_game_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💡 Hint", callback_data="hint")],
            [InlineKeyboardButton("⏭️ Skip", callback_data="skip")],
            [InlineKeyboardButton("🔄 Next", callback_data="next")],
        ]
    )



@bot.on_message(filters.command("ecleaderboard"))
async def lefeaderboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)


@bot.on_message(filters.command("ecplay"))
async def plecay_cmd(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user

    puzzle = random.choice(PUZZLES)
    game = {
        "chat_id": chat_id,
        "owner_id": user.id,
        "owner_name": user.first_name,
        "puzzle": puzzle,
        "active": True,
        "guessed": False,
    }
    await games_col.replace_one({"chat_id": chat_id}, game, upsert=True)

    await message.reply(
        f"🎮 <b>Emoji Combo!</b>\n\n{puzzle['emoji']}\n\n"
        f"👉 Only {user.mention} can answer!",
        reply_markup=build_game_buttons(),
    )

# ---------------- GAME LOGIC ---------------- #
@bot.on_message(filters.command("ecguss") & filters.group)
async def guefess_handler(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    #⁶text = message.text.lower().strip()
    text = message.text.split(' ', 1)[1]
    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return

    if user.id != game["owner_id"]:
        return  # only owner can play

    if game["guessed"]:
        return

    if text in game["puzzle"]["answer"]:
        await update_stats(user.id, user.first_name, won=True)
        await games_col.update_one({"chat_id": chat_id}, {"$set": {"guessed": True, "active": False}})
        await message.reply(f"✅ Correct, {user.mention}! You solved {game['puzzle']['emoji']}")
    else:
        await message.reply("❌ Wrong guess, try again!")


# ---------------- CALLBACKS ---------------- #
@bot.on_callback_query(filters.regex(r"^(hint|skip|next)$"))
async def game_buttohhns_cb(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    user = query.from_user
    data = query.data

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or user.id != game["owner_id"]:
        await query.answer("❌ Only the game owner can use this!", show_alert=True)
        return

    if data == "hint":
        hint = game["puzzle"]["answer"][0][0:3] + "..."
        await query.answer(f"💡 Hint: {hint}", show_alert=True)

    elif data == "skip":
        await games_col.update_one({"chat_id": chat_id}, {"$set": {"active": False}})
        await query.message.reply("⏭️ Puzzle skipped!")

    elif data == "next":
        puzzle = random.choice(PUZZLES)
        new_game = {
            "chat_id": chat_id,
            "owner_id": user.id,
            "owner_name": user.first_name,
            "puzzle": puzzle,
            "active": True,
            "guessed": False,
        }
        await games_col.replace_one({"chat_id": chat_id}, new_game, upsert=True)
        await query.message.reply(
            f"🎮 <b>Emoji Combo!</b>\n\n{puzzle['emoji']}\n\n"
            f"👉 Only {user.mention} can answer!",
            reply_markup=build_game_buttons(),
        )
