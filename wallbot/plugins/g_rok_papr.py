#!/usr/bin/env python3
"""
Advanced Rock-Paper-Scissors Telegram Bot (Pyrogram)

Features:
- Inline button only controls
- MongoDB persistent stats: wins/losses/ties, username
- Global & per-group leaderboards
- 1v1 Group challenge flow (reply /challenge to a user)
- Play vs Bot in private (/rps)
- Profile command (/profile)
- Clean concurrency and validation so only players act on buttons
"""

import os
import uuid
import asyncio
from typing import Dict, Any, Optional, Tuple, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)
from config import DB_URL
from wallbot import wbot as app

load_dotenv()


DB_NAME = os.getenv("DB_NAME", "rps_db")


# ---------- INIT ----------
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]            # { _id: user_id, username, wins, losses, ties }
games_col = db["games"]            # optional persistent games (not required but available)
# Note: We'll keep active games in memory for speed; games_col can be used for persistence if desired

# In-memory active games: { chat_id: { game_id: GameDict } }
# GameDict fields: challenger_id, opponent_id, challenger_name, opponent_name, state, moves, created_at
active_games: Dict[int, Dict[str, Dict[str, Any]]] = {}
# Lock per chat to avoid race conditions
chat_locks: Dict[int, asyncio.Lock] = {}

CHOICE_MAP = {"R": "Rock 🪨", "P": "Paper 📜", "S": "Scissors ✂️"}
WIN_PAIRS = {("R", "S"), ("S", "P"), ("P", "R")}  # winner, loser pairs

# ---------- UTIL ----------
def new_game_id() -> str:
    return uuid.uuid4().hex[:10]

def ensure_chat_struct(chat_id: int) -> None:
    if chat_id not in active_games:
        active_games[chat_id] = {}
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()

def short_name(user: Message.from_user) -> str:
    # Returns mention-friendly string
    if not user:
        return "Unknown"
    if getattr(user, "username", None):
        return f"@{user.username}"
    if getattr(user, "first_name", None):
        return user.first_name
    return str(user.id)

# ---------- RANKS ----------
def get_rank(wins: int) -> str:
    if wins < 5:
        return "🥉 Bronze"
    elif wins < 15:
        return "🥈 Silver"
    elif wins < 30:
        return "🥇 Gold"
    else:
        return "💎 Diamond"

# ---------- DB helpers ----------
async def ensure_user_doc(user_id: int, username: Optional[str]) -> None:
    await users_col.update_one(
        {"_id": user_id},
        {
            "$setOnInsert": {"_id": user_id, "username": username or "", "wins": 0, "losses": 0, "ties": 0},
            "$set": {"username": username or ""},
        },
        upsert=True,
    )

async def update_stats(user_id: int, username: Optional[str], outcome: str) -> None:
    """
    outcome: "win" / "loss" / "tie"
    """
    inc = {}
    if outcome == "win":
        inc = {"wins": 1}
    elif outcome == "loss":
        inc = {"losses": 1}
    elif outcome == "tie":
        inc = {"ties": 1}
    if not inc:
        return
    await users_col.update_one(
        {"_id": user_id},
        {"$inc": inc, "$set": {"username": username or ""}},
        upsert=True,
    )

async def get_stats(user_id: int) -> Dict[str, Any]:
    doc = await users_col.find_one({"_id": user_id})
    if not doc:
        return {"wins": 0, "losses": 0, "ties": 0, "username": ""}
    return {"wins": int(doc.get("wins", 0)), "losses": int(doc.get("losses", 0)), "ties": int(doc.get("ties", 0)), "username": doc.get("username", "") or ""}

async def get_global_leaderboard(limit: int = 10) -> List[Tuple[int, int, str]]:
    cursor = users_col.find().sort("wins", -1).limit(limit)
    out = []
    async for doc in cursor:
        out.append((int(doc["_id"]), int(doc.get("wins", 0)), doc.get("username", "") or ""))
    return out

async def get_group_leaderboard(chat_id: int, limit: int = 10) -> List[Tuple[int, int, str]]:
    # In this example we use global stats, but filter by presence in that chat is complex.
    # If you want strict per-group stats, implement group-scoped collection and increment there.
    # For now, return top players (global) but show for group.
    return await get_global_leaderboard(limit)

# ---------- UI helpers ----------
def buttons_accept_decline(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"rps_accept|{game_id}|accept"),
                InlineKeyboardButton("❌ Decline", callback_data=f"rps_accept|{game_id}|decline"),
            ]
        ]
    )

def buttons_moves(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🪨 Rock", callback_data=f"rps_move|{game_id}|R"),
                InlineKeyboardButton("📜 Paper", callback_data=f"rps_move|{game_id}|P"),
                InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_move|{game_id}|S"),
            ]
        ]
    )


@app.on_message(filters.command("rpaprofile"))
async def cmd_prparofile(client: Client, message: Message):
    user = message.from_user
    target = user
    # allow /profile or /profile @user
    if message.command and len(message.command) > 1:
        # try to parse mention or id
        arg = message.text.split(maxsplit=1)[1]
        # attempt to extract id/username via get_users
        try:
            target_info = await client.get_users(arg)
            if target_info:
                target = target_info
        except Exception:
            # ignore; fallback to sender
            target = user
    stats = await get_stats(target.id)
    rank = get_rank(stats["wins"])
    username_display = stats.get("username") or short_name(target)
    await message.reply_text(
        f"👤 Profile: {username_display}\n\n"
        f"📊 Wins: {stats['wins']}\n"
        f"📉 Losses: {stats['losses']}\n"
        f"🤝 Ties: {stats['ties']}\n"
        f"🏅 Rank: {rank}"
    )

@app.on_message(filters.command("rpssleaderboard"))
async def cmd_lrpseaderboard(client: Client, message: Message):
    # support /leaderboard group or private. If in group, show per-group (currently global)
    limit = 10
    if message.command and len(message.command) > 1:
        try:
            limit = int(message.command[1])
        except Exception:
            limit = 10
    if message.chat.type in ("group", "supergroup"):
        lb = await get_group_leaderboard(message.chat.id, limit)
        header = f"🏆 Top {len(lb)} Players (group view)"
    else:
        lb = await get_global_leaderboard(limit)
        header = f"🏆 Top {len(lb)} Players (global)"
    lines = [header, ""]
    i = 1
    for uid, wins, username in lb:
        uname = username or f"user{uid}"
        lines.append(f"{i}. {uname} — {wins}W")
        i += 1
    await message.reply_text("\n".join(lines))

# ---------- GROUP CHALLENGE FLOW ----------
@app.on_message(filters.command("rpschallenge") & filters.group)
async def cmd_rpschallenge(client: Client, message: Message):
    # Must be a reply to a user's message
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("⚠️ Reply to the user you want to challenge. Example: reply to their message and send /challenge")
        return

    challenger = message.from_user
    opponent = message.reply_to_message.from_user

    if opponent.is_bot:
        await message.reply_text("⚠️ You cannot challenge a bot (use /rps in private to play the bot).")
        return
    if opponent.id == challenger.id:
        await message.reply_text("⚠️ You can't challenge yourself.")
        return

    chat_id = message.chat.id
    ensure_chat_struct(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        # check if opponent already has pending game in this chat
        existing = None
        for gid, g in active_games[chat_id].items():
            if g["state"] in ("pending", "started") and (g["opponent_id"] == opponent.id or g["challenger_id"] == opponent.id):
                existing = g
                break
        if existing:
            await message.reply_text("⚠️ The opponent already has an active or pending game in this group.")
            return

        # create game
        game_id = new_game_id()
        active_games[chat_id][game_id] = {
            "challenger_id": challenger.id,
            "opponent_id": opponent.id,
            "challenger_name": short_name(challenger),
            "opponent_name": short_name(opponent),
            "state": "pending",   # pending -> started -> finished
            "moves": {},          # user_id -> "R"|"P"|"S"
            "created_at": asyncio.get_event_loop().time(),
        }

    # send message with accept/decline buttons
    try:
        await message.reply_text(
            f"🎮 Challenge!\n{short_name(challenger)} has challenged {short_name(opponent)}.\n\n"
            "Opponent: accept or decline the challenge.",
            reply_markup=buttons_accept_decline(game_id)
        )
    except Exception as e:
        # cleanup on failure
        async with lock:
            active_games[chat_id].pop(game_id, None)
        await message.reply_text(f"Failed to send challenge: {e}")

# ---------- CALLBACK: ACCEPT / DECLINE ----------
@app.on_callback_query(filters.regex(r"^rps_accept\|"))
async def cb_arpsccept_decline(client: Client, cq: CallbackQuery):
    # data format: rps_accept|<game_id>|<action>
    try:
        _, game_id, action = cq.data.split("|", 2)
    except ValueError:
        await cq.answer("Invalid data", show_alert=True)
        return

    chat_id = cq.message.chat.id
    ensure_chat_struct(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        game = active_games[chat_id].get(game_id)
        if not game:
            await cq.answer("This challenge no longer exists.", show_alert=True)
            try:
                await cq.message.edit_text("❌ This challenge is no longer available.")
            except Exception:
                pass
            return

        # only opponent can accept/decline
        if cq.from_user.id != game["opponent_id"]:
            await cq.answer("Only the challenged user can accept/decline.", show_alert=True)
            return

        if action == "decline":
            # remove game
            active_games[chat_id].pop(game_id, None)
            await cq.message.edit_text(f"❌ {short_name(cq.from_user)} declined the challenge from {game['challenger_name']}.")
            await cq.answer("Challenge declined.")
            return

        # action == accept -> start game
        game["state"] = "started"
        # reset moves
        game["moves"] = {}

    # edit message to game started and show move buttons
    try:
        await cq.message.edit_text(
            f"🎮 Game started!\n{game['challenger_name']} vs {game['opponent_name']}\n\n"
            "Both players: choose your move (only you can press your button).",
            reply_markup=buttons_moves(game_id),
        )
    except Exception:
        # send fallback message
        await cq.message.reply_text(
            f"🎮 Game started!\n{game['challenger_name']} vs {game['opponent_name']}\n\n"
            "Both players: choose your move (only you can press your button).",
            reply_markup=buttons_moves(game_id),
        )
    await cq.answer("Game started! Choose your move.")

# ---------- CALLBACK: MOVE ----------
@app.on_callback_query(filters.regex(r"^rps_move\|"))
async def cb_rpsmove(client: Client, cq: CallbackQuery):
    # data: rps_move|<game_id>|<choice>
    try:
        _, game_id, choice = cq.data.split("|", 2)
    except ValueError:
        await cq.answer("Invalid move data", show_alert=True)
        return

    if choice not in CHOICE_MAP:
        await cq.answer("Invalid choice", show_alert=True)
        return

    chat_id = cq.message.chat.id
    ensure_chat_struct(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        game = active_games[chat_id].get(game_id)
        if not game or game.get("state") != "started":
            await cq.answer("No active game found.", show_alert=True)
            return

        user_id = cq.from_user.id
        # Only challenger or opponent can press move buttons
        if user_id not in (game["challenger_id"], game["opponent_id"]):
            await cq.answer("You are not a player in this game.", show_alert=True)
            return

        # Prevent double move
        if user_id in game["moves"]:
            await cq.answer("You already selected a move.", show_alert=True)
            return

        # record the move
        game["moves"][user_id] = choice
        await cq.answer("Move recorded. Waiting for opponent...")

        # If both moves present -> resolve
        if game["challenger_id"] in game["moves"] and game["opponent_id"] in game["moves"]:
            c_id = game["challenger_id"]
            o_id = game["opponent_id"]
            c_choice = game["moves"][c_id]
            o_choice = game["moves"][o_id]

            # determine winner
            if c_choice == o_choice:
                result_text = "🤝 It's a tie!"
                # update db: tie for both
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

            # get updated stats for display
            c_stats = await get_stats(c_id)
            o_stats = await get_stats(o_id)
            c_rank = get_rank(c_stats["wins"])
            o_rank = get_rank(o_stats["wins"])

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

            # edit the message (remove buttons)
            try:
                await cq.message.edit_text(final_text)
            except Exception:
                # fallback: send new message
                await cq.message.reply_text(final_text)

            # cleanup
            active_games[chat_id].pop(game_id, None)
            return

        # else: wait for other player
        # Optionally give ephemeral feedback by editing the message to show one move done
        # but avoid revealing which player moved; keep it private (callback answers suffice)

# ---------- PLAY VS BOT (private) ----------
@app.on_message(filters.command("rps") & filters.private)
async def cmd_rps_private(client: Client, message: Message):
    user = message.from_user
    chat_id = message.chat.id
    ensure_chat_struct(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        game_id = new_game_id()
        bot_id = (await client.get_me()).id
        active_games[chat_id][game_id] = {
            "challenger_id": user.id,
            "opponent_id": bot_id,
            "challenger_name": short_name(user),
            "opponent_name": "Bot",
            "state": "started",
            "moves": {},
            "created_at": asyncio.get_event_loop().time(),
        }

    # send move buttons to user
    await message.reply_text("🎮 Play vs Bot — choose your move:", reply_markup=buttons_moves(game_id))

# When user chooses move in private game vs bot, the same cb_move handler runs.
# After the user's move is recorded, detect opponent is bot and auto-play if needed.
# We must ensure cb_move handles the bot-case after recording user's move.
# Modify cb_move to after recording to detect if opponent is bot and auto select random move.
# Since cb_move above already checks and resolves when both moves present, we need to trigger bot move here.

# To handle bot response, add a separate listener that checks for games where opponent is bot and only one move present.
# Simpler: after recording a move, if opponent is bot and other move is missing -> play bot move immediately.

# We'll patch cb_move to handle bot spontaneously by checking the stored game and, if opponent is bot and hasn't moved, pick a move.

# (Note: cb_move already runs under lock; below we add bot auto-play logic inside cb_move after recording move.
# That logic is placed after 'record the move' above; but to keep the code linear we will re-check here by adding a small helper.)

# ---------- CLEANUP OLD GAMES (optional) ----------
# A background task could cleanup stale games; implement small cleanup coroutine.

async def cleanup_task():
    while True:
        try:
            now = asyncio.get_event_loop().time()
            to_remove = []
            for chat_id, games in list(active_games.items()):
                for gid, g in list(games.items()):
                    # remove pending/started games older than 30 minutes
                    if now - g.get("created_at", now) > 60 * 30:
                        to_remove.append((chat_id, gid))
            for chat_id, gid in to_remove:
                if chat_id in active_games and gid in active_games[chat_id]:
                    try:
                        active_games[chat_id].pop(gid, None)
                    except Exception:
                        pass
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(60)



# ---------- Modify cb_move to handle bot auto-move (we re-register a wrapper to ensure logic) ----------
# Remove previous handler and re-register a combined one (to ensure bot handling).
# We'll unregister previous cb_move by using the same function name override - Pyrogram allows multiple decorators, but to be safe we simply add another handler that does bot moves.
# Instead, create a helper function that triggers bot auto-play if needed.

async def maybe_bot_play_and_resolve(chat_id: int, game_id: str):
    """
    If a game exists where one player is bot and only one move present, make bot move and resolve.
    """
    ensure_chat_struct(chat_id)
    lock = chat_locks[chat_id]
    async with lock:
        game = active_games[chat_id].get(game_id)
        if not game or game.get("state") != "started":
            return

        bot_id = (await app.get_me()).id
        # If opponent is bot (either challenger or opponent)
        if game["challenger_id"] == bot_id or game["opponent_id"] == bot_id:
            # if both moves present, nothing to do
            if game["challenger_id"] in game["moves"] and game["opponent_id"] in game["moves"]:
                return
            # pick bot id and opponent id
            # determine who already moved
            if game["challenger_id"] in game["moves"]:
                # challenger moved, bot is opponent
                bot_side = game["opponent_id"]
                other_side = game["challenger_id"]
            elif game["opponent_id"] in game["moves"]:
                bot_side = game["challenger_id"]
                other_side = game["opponent_id"]
            else:
                # no one moved yet, don't auto-play
                return
            # only auto-move for bot side
            if bot_side != bot_id:
                # bot is not the expected id (should match), do nothing
                return
            # choose bot move randomly
            import random
            bot_choice = random.choice(list(CHOICE_MAP.keys()))
            game["moves"][bot_id] = bot_choice

            # resolve now (both moves present)
            c_id = game["challenger_id"]
            o_id = game["opponent_id"]
            c_choice = game["moves"].get(c_id)
            o_choice = game["moves"].get(o_id)
            if not c_choice or not o_choice:
                # something wrong; just return
                return

            # determine result and update DB
            if c_choice == o_choice:
                result_text = "🤝 It's a tie!"
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

            c_stats = await get_stats(c_id)
            o_stats = await get_stats(o_id)
            c_rank = get_rank(c_stats["wins"])
            o_rank = get_rank(o_stats["wins"])

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

            # send/update message in chat - attempt to edit last message of game if possible
            # We can't reliably know which message to edit here, so broadcast the result in the chat
            try:
                await app.send_message(chat_id, final_text)
            except Exception:
                # ignore send errors
                pass

            # cleanup
            active_games[chat_id].pop(game_id, None)
            return

# We need to ensure maybe_bot_play_and_resolve runs after a human move in cb_move.
# Since cb_move currently resolves games when both moves present, we should call maybe_bot_play_and_resolve after recording human move if opponent is bot.
# To integrate, we monkey-patch: rebind cb_move logic to call maybe_bot_play_and_resolve.
# However, since cb_move is already defined above, we'll add a new handler that triggers after any rps_move callback:
@app.on_callback_query(filters.regex(r"^rps_move\|"))
async def cb_move_postprocess(client: Client, cq: CallbackQuery):
    # This handler runs after the main move handler above (Pyrogram executes both).
    # Extract game_id and, if opponent is bot, attempt to auto-play.
    try:
        _, game_id, _ = cq.data.split("|", 2)
    except Exception:
        return
    chat_id = cq.message.chat.id
    # small delay to ensure the main handler processed
    await asyncio.sleep(0.15)
    # attempt bot play
    await maybe_bot_play_and_resolve(chat_id, game_id)

