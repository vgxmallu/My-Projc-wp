
from config import DB_URL
from wallbot import wbot as app


# rps_group_bot.py
import random
import asyncio
import uuid
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

DB_NAME = "rps_game"

# ===== INIT =====
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]

# In-memory active challenges: { chat_id: { game_id: {...} } }
# Note: persistent storage is possible but out-of-scope for this example
challenges: Dict[int, Dict[str, Dict[str, Any]]] = {}

CHOICE_MAP = {"R": "Rock 🪨", "P": "Paper 📜", "S": "Scissors ✂️"}
WIN_PAIRS = {("R", "S"), ("S", "P"), ("P", "R")}  # (winner, loser)

# ===== RANKS =====
def get_rank(wins: int) -> str:
    if wins < 5:
        return "🥉 Bronze"
    elif wins < 15:
        return "🥈 Silver"
    elif wins < 30:
        return "🥇 Gold"
    else:
        return "💎 Diamond"

# ===== DB helpers =====
async def update_stats(user_id: int, username: str, outcome: str):
    """
    outcome in {"win","loss","tie"}
    """
    inc = {}
    if outcome == "win":
        inc = {"wins": 1}
    elif outcome == "loss":
        inc = {"losses": 1}
    elif outcome == "tie":
        inc = {"ties": 1}

    await users_col.update_one(
        {"_id": user_id},
        {
            "$inc": inc,
            "$set": {"username": username or ""},
            "$setOnInsert": {"wins": 0, "losses": 0, "ties": 0}
        },
        upsert=True
    )

async def get_stats(user_id: int) -> Dict[str, int]:
    doc = await users_col.find_one({"_id": user_id})
    if not doc:
        return {"wins": 0, "losses": 0, "ties": 0, "username": ""}
    return {
        "wins": doc.get("wins", 0),
        "losses": doc.get("losses", 0),
        "ties": doc.get("ties", 0),
        "username": doc.get("username", "") or ""
    }

# ===== Utilities =====
def new_game_id() -> str:
    # short unique id, safe for callback_data
    return uuid.uuid4().hex[:8]

def ensure_chat_record(chat_id: int):
    if chat_id not in challenges:
        challenges[chat_id] = {}

# ===== COMMANDS =====
@app.on_message(filters.command("rpcchallenge") & filters.group)
async def cmd_rpcchallenge(client, message):
    # Must reply to the user you want to challenge
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("⚠️ Reply to a user to challenge them. Example: reply to a message and send /challenge")
        return

    challenger = message.from_user
    opponent = message.reply_to_message.from_user

    if opponent.is_bot:
        await message.reply_text("⚠️ Can't challenge a bot.")
        return
    if opponent.id == challenger.id:
        await message.reply_text("⚠️ You can't challenge yourself.")
        return

    chat_id = message.chat.id
    ensure_chat_record(chat_id)

    # Create unique game id
    game_id = new_game_id()
    # store essential info and human-friendly names
    challenges[chat_id][game_id] = {
        "challenger_id": challenger.id,
        "opponent_id": opponent.id,
        "challenger_name": challenger.mention or (challenger.first_name or str(challenger.id)),
        "opponent_name": opponent.mention or (opponent.first_name or str(opponent.id)),
        "state": "pending",  # pending -> started -> finished
        "moves": {},  # user_id -> choice_code
        "created_at": asyncio.get_event_loop().time()
    }

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"rps_accept|{game_id}|accept"),
                InlineKeyboardButton("❌ Decline", callback_data=f"rps_accept|{game_id}|decline")
            ]
        ]
    )

    await message.reply_text(
        f"🎮 Challenge: {challenger.mention} has challenged {opponent.mention}!\n\n"
        "Opponent: accept or decline the challenge.",
        reply_markup=buttons
    )

# ===== ACCEPT / DECLINE =====
@app.on_callback_query(filters.regex(r"^rps_accept\|"))
async def cb_accerpspt_decline(client, cq):
    # data: rps_accept|<game_id>|<action>
    try:
        _, game_id, action = cq.data.split("|", 2)
    except ValueError:
        await cq.answer("Invalid data", show_alert=True)
        return

    chat_id = cq.message.chat.id
    ensure_chat_record(chat_id)
    game = challenges[chat_id].get(game_id)
    if not game:
        await cq.answer("This challenge no longer exists.", show_alert=True)
        return

    # Only the opponent may accept/decline
    user_id = cq.from_user.id
    if user_id != game["opponent_id"]:
        await cq.answer("Only the challenged user can accept or decline.", show_alert=True)
        return

    if action == "decline":
        await cq.message.edit_text(f"❌ {cq.from_user.mention} declined the challenge from {game['challenger_name']}.")
        # cleanup
        challenges[chat_id].pop(game_id, None)
        await cq.answer("Challenge declined.")
        return

    # action == "accept" -> start game
    game["state"] = "started"
    # Prepare move buttons (each button sends short code R/P/S)
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🪨 Rock", callback_data=f"rps_move|{game_id}|R"),
                InlineKeyboardButton("📜 Paper", callback_data=f"rps_move|{game_id}|P"),
                InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_move|{game_id}|S")
            ]
        ]
    )

    await cq.message.edit_text(
        f"🎮 Game started: {game['challenger_name']} vs {game['opponent_name']}\n\n"
        "Both players: choose your move (your choice is private).",
        reply_markup=buttons
    )
    await cq.answer("Challenge accepted. Choose a move!")

# ===== HANDLE MOVES =====
@app.on_callback_query(filters.regex(r"^rps_move\|"))
async def cb_rpsmove(client, cq):
    # data: rps_move|<game_id>|<choice>
    try:
        _, game_id, choice = cq.data.split("|", 2)
    except ValueError:
        await cq.answer("Invalid move data", show_alert=True)
        return

    chat_id = cq.message.chat.id
    ensure_chat_record(chat_id)
    game = challenges[chat_id].get(game_id)
    if not game or game.get("state") != "started":
        await cq.answer("No active game found or game not started.", show_alert=True)
        return

    user_id = cq.from_user.id
    # Only challenger or opponent can play
    if user_id != game["challenger_id"] and user_id != game["opponent_id"]:
        await cq.answer("You are not a player in this game.", show_alert=True)
        return

    # Prevent double move
    if user_id in game["moves"]:
        await cq.answer("You already chose a move.", show_alert=True)
        return

    # Validate choice
    if choice not in CHOICE_MAP:
        await cq.answer("Invalid choice.", show_alert=True)
        return

    # Register move
    game["moves"][user_id] = choice
    await cq.answer("Move registered. Waiting for the other player...")

    # If both moves present -> resolve
    if game["challenger_id"] in game["moves"] and game["opponent_id"] in game["moves"]:
        c_id = game["challenger_id"]
        o_id = game["opponent_id"]
        c_choice = game["moves"][c_id]
        o_choice = game["moves"][o_id]

        # Determine result
        if c_choice == o_choice:
            # tie
            result_text = "🤝 It's a tie!"
            # update DB
            await update_stats(c_id, game["challenger_name"], "tie")
            await update_stats(o_id, game["opponent_name"], "tie")
        elif (c_choice, o_choice) in WIN_PAIRS:
            result_text = f"🎉 {game['challenger_name']} (Challenger) wins!"
            await update_stats(c_id, game["challenger_name"], "win")
            await update_stats(o_id, game["opponent_name"], "loss")
        else:
            result_text = f"🎉 {game['opponent_name']} (Opponent) wins!"
            await update_stats(c_id, game["challenger_name"], "loss")
            await update_stats(o_id, game["opponent_name"], "win")

        # Pull updated stats
        c_stats = await get_stats(c_id)
        o_stats = await get_stats(o_id)

        c_rank = get_rank(c_stats["wins"])
        o_rank = get_rank(o_stats["wins"])

        # Final message
        final_text = (
            f"🪨 Rock – 📜 Paper – ✂️ Scissors\n\n"
            f"👤 Challenger: {game['challenger_name']}\n"
            f"➡️ Chose: {CHOICE_MAP[c_choice]}\n\n"
            f"👤 Opponent: {game['opponent_name']}\n"
            f"➡️ Chose: {CHOICE_MAP[o_choice]}\n\n"
            f"{result_text}\n\n"
            f"📊 Stats:\n"
            f"{game['challenger_name']}: {c_stats['wins']}W / {c_stats['losses']}L / {c_stats['ties']}T — {c_rank}\n"
            f"{game['opponent_name']}: {o_stats['wins']}W / {o_stats['losses']}L / {o_stats['ties']}T — {o_rank}\n"
        )

        # Edit message to show result and remove buttons
        try:
            await cq.message.edit_text(final_text)
        except Exception:
            # fallback: send a new message
            await cq.message.reply_text(final_text)

        # Clean up
        challenges[chat_id].pop(game_id, None)

# ===== PROFILE =====
@app.on_message(filters.command("profile"))
async def cmd_rpsprofile(client, message):
    user = message.from_user
    stats = await get_stats(user.id)
    rank = get_rank(stats["wins"])
    await message.reply_text(
        f"👤 {user.mention}\n\n"
        f"📊 Wins: {stats['wins']}\n"
        f"📉 Losses: {stats['losses']}\n"
        f"🤝 Ties: {stats['ties']}\n"
        f"🏅 Rank: {rank}"
    )

# ===== LEADERBOARD =====
@app.on_message(filters.command("leaderboard"))
async def cmd_lrpseaderboard(client, message):
    top_cursor = users_col.find().sort("wins", -1).limit(10)
    lines = ["🏆 Top 10 Players 🏆\n"]
    i = 1
    async for u in top_cursor:
        uname = u.get("username") or f"user{u['_id']}"
        lines.append(f"{i}. {uname} — {u.get('wins',0)}W / {u.get('losses',0)}L")
        i += 1
    await message.reply_text("\n".join(lines))

# ===== FALLBACK: play vs bot (private) =====
@app.on_message(filters.private & filters.command("rps"))
async def cmd_rps_private(client, message):
    # simple play vs bot with same buttons
    user = message.from_user
    game_id = new_game_id()
    # Create a tiny temporary game placed under chat id = user's private chat id
    chat_id = message.chat.id
    ensure_chat_record(chat_id)
    challenges[chat_id][game_id] = {
        "challenger_id": user.id,
        "opponent_id": client.get_me().id,
        "challenger_name": user.mention,
        "opponent_name": "Bot",
        "state": "started",
        "moves": {}
    }
    buttons = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🪨 Rock", callback_data=f"rps_move|{game_id}|R"),
            InlineKeyboardButton("📜 Paper", callback_data=f"rps_move|{game_id}|P"),
            InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_move|{game_id}|S")
        ]]
    )
    await message.reply_text("🎮 Play vs Bot — choose your move:", reply_markup=buttons)

