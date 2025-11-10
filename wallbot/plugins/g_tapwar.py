import asyncio
import os
import random
import motor.motor_asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from config import DB_URL
from main import wbot as bot


DB_NAME = "TapWarsDB"


mongo_client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo_client[DB_NAME]
users_col = db["users"]
games_col = db["games"]

# ========================
# DB Functions
# ========================
async def ensure_user(user_id, username):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        await users_col.insert_one({
            "_id": user_id,
            "username": username or "",
            "wins": 0,
            "losses": 0,
            "points": 0
        })

async def update_score(user_id, won=False):
    if won:
        await users_col.update_one({"_id": user_id}, {"$inc": {"wins": 1, "points": 10}})
    else:
        await users_col.update_one({"_id": user_id}, {"$inc": {"losses": 1, "points": -5}})

async def get_leaderboard():
    cursor = users_col.find().sort("points", -1).limit(10)
    return await cursor.to_list(length=10)

# ========================
# GAME START
# ========================
@bot.on_message(filters.command("tapwar") & filters.group)
async def start_tjjapwar(client: Client, message: Message):
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply("⚔️ Usage: `/tapwar @username` (reply or mention)", quote=True)

    challenger = message.from_user
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) >= 2:
        username = message.command[1].replace("@", "")
        target = await client.get_users(username)

    if not target or target.is_bot:
        return await message.reply("❌ Invalid target!", quote=True)

    if challenger.id == target.id:
        return await message.reply("❌ You cannot challenge yourself!", quote=True)

    await ensure_user(challenger.id, challenger.username)
    await ensure_user(target.id, target.username)

    game_id = str(message.id) + "_" + str(random.randint(1000, 9999))
    await games_col.insert_one({
        "_id": game_id,
        "challenger": challenger.id,
        "opponent": target.id,
        "scores": {str(challenger.id): 0, str(target.id): 0},
        "status": "pending"
    })

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"awaccept:{game_id}")]
    ])

    await message.reply(
        f"⚔️ <b>{challenger.mention}</b> has challenged <b>{target.mention}</b> to a Tap War!\n\n"
        f"{target.mention}, will you accept?",
        reply_markup=btns
    )

# ========================
# ACCEPT GAME
# ========================
@bot.on_callback_query(filters.regex(r"^awaccept:(.+)"))
async def accept_game(client: Client, cq: CallbackQuery):
    game_id = cq.data.split(":")[1]
    game = await games_col.find_one({"_id": game_id})

    if not game:
        return await cq.answer("❌ Game not found!", show_alert=True)

    if cq.from_user.id != game["opponent"]:
        return await cq.answer("❌ Only the challenged player can accept!", show_alert=True)

    await games_col.update_one({"_id": game_id}, {"$set": {"status": "active"}})

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("👊 TAP", callback_data=f"awtap:{game_id}:{game['challenger']}"),
         InlineKeyboardButton("👊 TAP", callback_data=f"awtap:{game_id}:{game['opponent']}")],
        [InlineKeyboardButton("🏁 Finish", callback_data=f"awfinish:{game_id}")]
    ])

    await cq.message.edit_text(
        f"🔥 <b>Tap War Started!</b>\n\n"
        f"<b>{cq.from_user.mention}</b> vs <b><a href='tg://user?id={game['challenger']}'>Challenger</a></b>\n"
        f"Spam the button FASTEST to win!\n\n"
        f"👊 Let the battle begin!",
        reply_markup=btns
    )

# ========================
# TAP HANDLER
# ========================
@bot.on_callback_query(filters.regex(r"^awtap:(.+):(.+)"))
async def tap_handler(client: Client, cq: CallbackQuery):
    game_id, user_id = cq.data.split(":")[1:]
    game = await games_col.find_one({"_id": game_id})

    if not game or game["status"] != "active":
        return await cq.answer("❌ Game not active!", show_alert=True)

    if cq.from_user.id != int(user_id):
        return await cq.answer("❌ This is not your button!", show_alert=True)

    await games_col.update_one(
        {"_id": game_id},
        {"$inc": {f"scores.{user_id}": 1}}
    )

    new_game = await games_col.find_one({"_id": game_id})
    challenger_score = new_game["scores"].get(str(game["challenger"]), 0)
    opponent_score = new_game["scores"].get(str(game["opponent"]), 0)

    await cq.answer(f"👊 Your taps: {new_game['scores'][user_id]}", show_alert=False)

    await cq.message.edit_text(
        f"🔥 <b>Tap War!</b>\n\n"
        f"<a href='tg://user?id={game['challenger']}'>Challenger</a>: {challenger_score} taps\n"
        f"<a href='tg://user?id={game['opponent']}'>Opponent</a>: {opponent_score} taps\n\n"
        f"👊 Keep tapping!",
        reply_markup=cq.message.reply_markup
    )

# ========================
# FINISH GAME
# ========================
@bot.on_callback_query(filters.regex(r"^awfinish:(.+)"))
async def finish_game(client: Client, cq: CallbackQuery):
    game_id = cq.data.split(":")[1]
    game = await games_col.find_one({"_id": game_id})

    if not game or game["status"] != "active":
        return await cq.answer("❌ Game already finished!", show_alert=True)

    await games_col.update_one({"_id": game_id}, {"$set": {"status": "finished"}})

    challenger_score = game["scores"].get(str(game["challenger"]), 0)
    opponent_score = game["scores"].get(str(game["opponent"]), 0)

    winner = None
    if challenger_score > opponent_score:
        winner = game["challenger"]
    elif opponent_score > challenger_score:
        winner = game["opponent"]

    if winner:
        await update_score(winner, won=True)
        loser = game["opponent"] if winner == game["challenger"] else game["challenger"]
        await update_score(loser, won=False)
        result_text = f"🏆 <a href='tg://user?id={winner}'>Winner</a>!\n\n"
    else:
        result_text = "🤝 It's a draw!\n\n"

    await cq.message.edit_text(
        f"✅ <b>Game Finished!</b>\n\n"
        f"<a href='tg://user?id={game['challenger']}'>Challenger</a>: {challenger_score}\n"
        f"<a href='tg://user?id={game['opponent']}'>Opponent</a>: {opponent_score}\n\n"
        f"{result_text}"
    )

# ========================
# LEADERBOARD
# ========================
@bot.on_message(filters.command("awleaderboard") & filters.group)
async def leaderbawoard(client: Client, message: Message):
    leaders = await get_leaderboard()
    if not leaders:
        return await message.reply("📊 No players yet!")

    text = "📊 <b>Top 10 Tap Warriors</b>\n\n"
    for i, u in enumerate(leaders, start=1):
        text += f"{i}. @{u.get('username', 'unknown')} - {u['points']} pts (W:{u['wins']} / L:{u['losses']})\n"

    await message.reply(text)

