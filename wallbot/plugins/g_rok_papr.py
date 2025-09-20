import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app
# === CONFIG ===

DB_NAME = "rps_game"

# === INIT ===
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]

CHOICES = ["Rock 🪨", "Paper 📜", "Scissors ✂️"]

# === RANKS ===
def get_rank(wins):
    if wins < 5:
        return "🥉 Bronze"
    elif wins < 15:
        return "🥈 Silver"
    elif wins < 30:
        return "🥇 Gold"
    else:
        return "💎 Diamond"

# === SAVE RESULT ===
async def update_stats(user_id, username, result):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username, "wins": 0, "losses": 0, "ties": 0}
    if result == "win":
        user["wins"] += 1
    elif result == "loss":
        user["losses"] += 1
    else:
        user["ties"] += 1
    await users_col.update_one({"_id": user_id}, {"$set": user}, upsert=True)

# === CHALLENGE SYSTEM ===
# Store active challenges: {group_id: {challenger_id: {...}}}
challenges = {}

@app.on_message(filters.command("rcchallenge") & filters.group)
async def challenge_user(client, message):
    if not message.reply_to_message:
        await message.reply_text("⚠️ Reply to someone to challenge them!")
        return

    challenger = message.from_user
    opponent = message.reply_to_message.from_user
    chat_id = message.chat.id

    if chat_id not in challenges:
        challenges[chat_id] = {}

    if opponent.id in challenges[chat_id]:
        await message.reply_text("⚠️ That user already has a pending challenge.")
        return

    challenges[chat_id][opponent.id] = {"challenger": challenger.id}

    buttons = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"rcaccept_{challenger.id}_{opponent.id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"rcdecline_{challenger.id}_{opponent.id}")
        ]
    ]
    await message.reply_text(
        f"🎮 {challenger.mention} challenged {opponent.mention} to Rock–Paper–Scissors!",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"^(rcaccept|rcdecline)_(\d+)_(\d+)$"))
async def handle_challenge_response(client, cq):
    action, challenger_id, opponent_id = cq.data.split("_")
    challenger_id, opponent_id = int(challenger_id), int(opponent_id)
    chat_id = cq.message.chat.id

    if action == "decline":
        await cq.message.edit_text("❌ Challenge declined.")
        challenges[chat_id].pop(opponent_id, None)
        return

    # Start game
    buttons = [
        [InlineKeyboardButton(c, callback_data=f"move_{c}_{challenger_id}_{opponent_id}")]
        for c in CHOICES
    ]
    await cq.message.edit_text(
        f"🎮 Game Started!\n\n"
        f"{cq.from_user.mention} vs <a href='tg://user?id={challenger_id}'>Opponent</a>\n\n"
        "Both players, choose your moves:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    challenges[chat_id][opponent_id]["moves"] = {}

# === HANDLE MOVES ===
@app.on_callback_query(filters.regex(r"^move_(.*)_(\d+)_(\d+)$"))
async def handlgge_move(client, cq):
    move, challenger_id, opponent_id = cq.data.split("_")[1:]
    challenger_id, opponent_id = int(challenger_id), int(opponent_id)
    chat_id = cq.message.chat.id

    if chat_id not in challenges or opponent_id not in challenges[chat_id]:
        await cq.answer("❌ No active game found.", show_alert=True)
        return

    game = challenges[chat_id][opponent_id]
    if "moves" not in game:
        game["moves"] = {}

    game["moves"][cq.from_user.id] = move

    # Wait until both moves
    if len(game["moves"]) < 2:
        await cq.answer("✅ Move registered. Waiting for opponent.")
        return

    # Both moves are in
    challenger_move = game["moves"].get(challenger_id)
    opponent_move = game["moves"].get(opponent_id)

    result_text = ""
    if challenger_move == opponent_move:
        winner, loser, result_text = None, None, "🤝 It's a tie!"
        await update_stats(challenger_id, "challenger", "tie")
        await update_stats(opponent_id, "opponent", "tie")
    elif (challenger_move == "Rock 🪨" and opponent_move == "Scissors ✂️") or \
         (challenger_move == "Scissors ✂️" and opponent_move == "Paper 📜") or \
         (challenger_move == "Paper 📜" and opponent_move == "Rock 🪨"):
        winner, loser, result_text = challenger_id, opponent_id, "🎉 Challenger wins!"
        await update_stats(challenger_id, "challenger", "win")
        await update_stats(opponent_id, "opponent", "loss")
    else:
        winner, loser, result_text = opponent_id, challenger_id, "🎉 Opponent wins!"
        await update_stats(challenger_id, "challenger", "loss")
        await update_stats(opponent_id, "opponent", "win")

    await cq.message.edit_text(
        f"🪨 Rock – 📜 Paper – ✂️ Scissors\n\n"
        f"👤 Challenger chose: {challenger_move}\n"
        f"👤 Opponent chose: {opponent_move}\n\n"
        f"{result_text}"
    )

    # Clean up
    challenges[chat_id].pop(opponent_id, None)

# === PROFILE ===
@app.on_message(filters.command("rcprofile"))
async def rcprofile(client, message):
    user = await users_col.find_one({"_id": message.from_user.id})
    if not user:
        await message.reply_text("You have no stats yet. Play a game first.")
        return
    rank = get_rank(user["wins"])
    await message.reply_text(
        f"👤 {message.from_user.mention}\n"
        f"📊 Wins: {user['wins']}\n"
        f"📉 Losses: {user['losses']}\n"
        f"🤝 Ties: {user['ties']}\n"
        f"🏅 Rank: {rank}"
    )

# === LEADERBOARD ===
@app.on_message(filters.command("rcleaderboard"))
async def rcleaderboard(client, message):
    top = users_col.find().sort("wins", -1).limit(10)
    leaderboard_text = "🏆 Top 10 Players 🏆\n\n"
    i = 1
    async for user in top:
        leaderboard_text += f"{i}. @{user.get('username','unknown')} – {user['wins']}W\n"
        i += 1
    await message.reply_text(leaderboard_text)


