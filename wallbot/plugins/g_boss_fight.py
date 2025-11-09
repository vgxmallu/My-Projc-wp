import os
import random
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as bot

# ---------------- DATABASE ---------------- #
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["boss_fight"]
users_col = db["users"]
games_col = db["games"]


# ---------------- HELPERS ---------------- #
async def get_user(user_id: int, name: str):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "name": name, "games_played": 0, "wins": 0, "score": 0, "damage": 0}
        await users_col.insert_one(user)
    return user

async def update_stats(user_id: int, name: str, damage: int, won: bool = False):
    await get_user(user_id, name)
    update = {"$inc": {"games_played": 1, "damage": damage, "score": damage}}
    if won:
        update["$inc"]["wins"] = 1
    await users_col.update_one({"_id": user_id}, update)

async def get_leaderboard() -> str:
    cursor = users_col.find().sort("score", -1).limit(10)
    text = "🏆 <b>Boss Fight Leaderboard</b>\n\n"
    pos = 1
    async for user in cursor:
        text += f"{pos}. {user['name']} – {user['score']} pts (Wins: {user['wins']}, Dmg: {user['damage']})\n"
        pos += 1
    return text

def boss_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Attack", callback_data="bfattack")]])


@bot.on_message(filters.command("bfleaderboard"))
async def leadefgrboard_cmd(_, message: Message):
    text = await get_leaderboard()
    await message.reply(text)

@bot.on_message(filters.private & filters.command("bf_fight"))
async def figsjs_cmd(_, message: Message):
    await message.reply_text("Play this on Group!!")
@bot.on_message(filters.group & filters.command("bf_fight"))
async def figggt_cmd(_, message: Message):
    chat_id = message.chat.id
    boss_hp = random.randint(200, 500)
    boss_name = random.choice(["Dragon", "Giant Troll", "Shadow Beast", "Hydra", "Dark Knight"])

    game = {
        "chat_id": chat_id,
        "boss_name": boss_name,
        "boss_hp": boss_hp,
        "max_hp": boss_hp,
        "active": True,
        "attackers": {}
    }
    await games_col.replace_one({"chat_id": chat_id}, game, upsert=True)

    await message.reply(
        f"🔥 A wild <b>{boss_name}</b> appeared with ❤️ {boss_hp} HP!\n\n"
        "Tap ⚔️ to attack and help your team defeat it!",
        reply_markup=boss_buttons()
    )

# ---------------- CALLBACK HANDLER ---------------- #
@bot.on_callback_query(filters.regex("^bfattack$"))
async def attavjck_cb(_, query: CallbackQuery):
    user = query.from_user
    chat_id = query.message.chat.id

    game = await games_col.find_one({"chat_id": chat_id})
    if not game or not game["active"]:
        return await query.answer("⚠️ No active boss fight!", show_alert=True)

    damage = random.randint(10, 40)
    game["boss_hp"] -= damage
    game["attackers"][str(user.id)] = game["attackers"].get(str(user.id), 0) + damage

    await update_stats(user.id, user.first_name, damage)

    if game["boss_hp"] <= 0:
        game["active"] = False
        await games_col.update_one({"chat_id": chat_id}, {"$set": game})

        # Mark all contributors as winners
        for uid in game["attackers"]:
            await update_stats(int(uid), "Player", 0, won=True)

        text = f"🎉 The <b>{game['boss_name']}</b> was defeated!\n\n"
        text += "Final Damage Board:\n"
        sorted_attackers = sorted(game["attackers"].items(), key=lambda x: x[1], reverse=True)
        for uid, dmg in sorted_attackers:
            player = await users_col.find_one({"_id": int(uid)})
            text += f"- {player['name']} dealt {dmg} dmg\n"
        await query.message.edit_text(text)
    else:
        await games_col.update_one({"chat_id": chat_id}, {"$set": game})
        hp_left = game["boss_hp"]
        await query.message.edit_text(
            f"👹 <b>{game['boss_name']}</b>\n"
            f"❤️ HP Left: {hp_left}/{game['max_hp']}\n\n"
            "Keep attacking!",
            reply_markup=boss_buttons()
        )

