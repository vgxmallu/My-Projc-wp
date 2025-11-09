#!/usr/bin/env python3
"""
Memory Flash Game Bot (Pyrogram + Motor)

Features:
- /memoryflash starts a game in-group or private
- First user to press "Start" becomes the player (only they can play)
- Bot flashes a sequence of emojis for FLASH_DELAY seconds
- Then shows a pool of emoji buttons; player must pick them in the same order
- MongoDB stores active games (memory_games) and user stats (users)
- /profile and /leaderboard commands
- All callback handlers use filters.regex
- Stale-game cleaner removes abandoned games after CLEANUP_SECONDS
"""

import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from config import DB_URL
from main import wbot as app
load_dotenv()

DB_NAME = os.getenv("DB_NAME", "memory_flash_db")
CLEANUP_SECONDS = int(os.getenv("CLEANUP_SECONDS", "120"))
FLASH_DELAY = int(os.getenv("FLASH_DELAY", "3"))  # seconds to show sequence
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "1"))

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["memory_games"]
users_col = db["users"]

# ---------- Emoji pool ----------
EMOJI_POOL = [
    "🍎", "🍌", "🍉", "🍇", "🍓", "🍒", "🍍", "🥝",
    "⚽", "🏀", "🏈", "🎾", "🏐", "🎱",
    "🐶", "🐱", "🦊", "🐻", "🐼",
    "😀", "😅", "😎", "🤖", "👾",
    "🌞", "🌜", "⭐", "☁️", "⚡",
    "🍕", "🍔", "🍟", "🌮", "🍩",
]

# ---------- In-memory lock to avoid race creating games ----------
GAME_LOCK = asyncio.Lock()

# ---------- Helper functions / DB helpers ----------

async def ensure_user(user_id: int, username: Optional[str]):
    """Ensure user doc exists."""
    u = await users_col.find_one({"user_id": user_id})
    if not u:
        u = {
            "user_id": user_id,
            "username": username or "",
            "score": 0,
            "wins": 0,
            "losses": 0,
            "games_played": 0,
            "created_at": datetime.utcnow()
        }
        await users_col.insert_one(u)
    else:
        # keep username fresh
        if username and u.get("username") != username:
            await users_col.update_one({"user_id": user_id}, {"$set": {"username": username}})
    return u

async def award_win(user_id: int, points: int = 10):
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"score": points, "wins": 1, "games_played": 1}},
        upsert=True
    )

async def award_loss(user_id: int):
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"losses": 1, "games_played": 1}},
        upsert=True
    )

def rank_from_score(score: int) -> str:
    """Simple rank tiers."""
    if score >= 2000:
        return "Legend"
    if score >= 1000:
        return "Master"
    if score >= 500:
        return "Pro"
    if score >= 200:
        return "Experienced"
    if score >= 50:
        return "Apprentice"
    return "Rookie"

def make_sequence(length: int) -> List[str]:
    """Return random sequence of emojis (allow duplicates)."""
    return [random.choice(EMOJI_POOL) for _ in range(length)]

def make_pool(sequence: List[str], pool_extra: int = 2) -> List[str]:
    """Create a pool that includes sequence emojis plus extras, then shuffle."""
    pool = list(set(sequence))  # unique items from sequence
    # add extra random emojis until pool has desired size
    while len(pool) < len(set(sequence)) + pool_extra:
        e = random.choice(EMOJI_POOL)
        if e not in pool:
            pool.append(e)
    # ensure at least sequence unique emojis are present; create final pool larger than sequence
    random.shuffle(pool)
    return pool

def build_start_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Start Memory Flash", callback_data="startgame")]])

def build_pool_kb(pool: List[str], game_id: str, disabled_mask: Optional[List[bool]] = None):
    """
    pool: list of emoji options shown for picking
    disabled_mask: list of booleans same length - True means disable that button (already used)
    callback_data: pick|<game_id>|<index>
    """
    buttons = []
    for i, e in enumerate(pool):
        label = e
        if disabled_mask and disabled_mask[i]:
            # show a check or blank to indicate used
            label = "✅"
            cb = "noop"
        else:
            cb = f"pick|{game_id}|{i}"
        buttons.append(InlineKeyboardButton(label, callback_data=cb))
    # arrange 3 per row
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)

def build_cancel_kb(game_id: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{game_id}")]])

# ---------- Commands ----------

#@app.on_message(filters.command("start") & filters.private)
async def cmd_start_private(_, m: Message):
    txt = (
        "👋 Welcome to Memory Flash!\n\n"
        "Test your short-term memory.\n"
        "• Use /memoryflash to start a round. In groups use the same command.\n"
        "• Tap Start — the first user who taps becomes the player for this round.\n"
        "• Watch the sequence, then reproduce it by tapping emojis in order.\n\n"
        "Commands:\n"
        "/memoryflash — start a new round\n"
        "/profile — view your stats\n"
        "/leaderboard — top players\n"
    )
    await m.reply_text(txt, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("memoryflash"))
async def cmd_memoryflash(_, m: Message):
    """
    Start a new Memory Flash round. The message includes a Start button;
    the first user to press Start becomes the player.
    Optional usage: /memoryflash <difficulty>
      difficulty: easy|normal|hard or int length 3..8
    """
    chat_id = m.chat.id
    # check if a game already active in this chat
    existing = await games_col.find_one({"chat_id": chat_id, "active": True})
    if existing:
        return await m.reply_text("A memory flash round is already active here. Wait for it to finish.")

    # parse difficulty
    length = 4
    if len(m.command) >= 2:
        arg = m.command[1].lower()
        if arg in ("easy", "e"):
            length = 3
        elif arg in ("normal", "n"):
            length = 4
        elif arg in ("hard", "h"):
            length = 6
        else:
            try:
                val = int(arg)
                if 3 <= val <= 8:
                    length = val
            except:
                pass

    # create a DB game doc
    now = datetime.utcnow()
    game_doc = {
        "chat_id": chat_id,
        "active": True,
        "player_id": None,
        "player_username": None,
        "length": length,
        "sequence": [],         # will be filled when player starts
        "pool": [],
        "next_index": 0,
        "disabled_mask": [],    # same length as pool
        "attempts": 0,
        "max_attempts": MAX_ATTEMPTS,
        "created_at": now,
        "last_update": now,
        "message_id": None,
    }
    res = await games_col.insert_one(game_doc)
    game_id = str(res.inserted_id)

    sent = await m.reply_text(
        f"🧠 Memory Flash — difficulty length {length}\nTap Start to become the player (only one player allowed).",
        reply_markup=build_start_kb()
    )
    # store message id & game_id in DB (for edits)
    await games_col.update_one({"_id": ObjectId(game_id)}, {"$set": {"message_id": sent.message_id}})
    LOG.info("Created game %s in chat %s (length=%s)", game_id, chat_id, length)

# ---------- Callback handlers (all use filters.regex) ----------

# startgame pressed -> join as player
@app.on_callback_query(filters.regex(r"^startgame$"))
async def cb_startgame(_, cq: CallbackQuery):
    user = cq.from_user
    chat_id = cq.message.chat.id
    # find active game for this chat
    game = await games_col.find_one({"chat_id": chat_id, "active": True})
    if not game:
        return await cq.answer("No active game found.", show_alert=True)

    # if already has player
    if game.get("player_id"):
        if game["player_id"] != user.id:
            return await cq.answer("Someone already joined as player for this round.", show_alert=True)
        else:
            return await cq.answer("You are already the player. Wait for the round to begin.", show_alert=False)

    # set this user as player (first-come)
    await games_col.update_one({"_id": game["_id"]}, {"$set": {"player_id": user.id, "player_username": user.username or user.first_name, "last_update": datetime.utcnow()}})
    game = await games_col.find_one({"_id": game["_id"]})

    # now prepare sequence and pool
    length = int(game.get("length", 4))
    sequence = make_sequence(length)
    # build pool: include sequence unique emojis plus some extras to increase difficulty
    pool = list(sequence)
    # add extras until pool has length + 2 unique options (but we allow duplicates in sequence)
    extras = 0
    while len(set(pool)) < min(len(set(sequence)) + 2, len(EMOJI_POOL)):
        e = random.choice(EMOJI_POOL)
        if e not in pool:
            pool.append(e)
        extras += 1
        if extras > 10:
            break
    # ensure pool is shuffled and unique options count reasonable
    pool = list(dict.fromkeys(pool))  # keep insertion order but unique
    random.shuffle(pool)
    disabled_mask = [False] * len(pool)

    await games_col.update_one({"_id": game["_id"]}, {"$set": {"sequence": sequence, "pool": pool, "disabled_mask": disabled_mask, "next_index": 0, "attempts": 0, "last_update": datetime.utcnow()}})

    # show the flashing sequence
    display = " ".join(sequence)
    try:
        await cq.message.edit_text(f"🔔 Player: {user.mention}\n\nMemorize this sequence:\n\n{display}\n\n(you have {FLASH_DELAY} seconds)", parse_mode=enums.ParseMode.HTML)
    except Exception:
        # fallback: send new message
        await cq.message.reply_text(f"🔔 Player: {user.mention}\n\nMemorize this sequence:\n\n{display}\n\n(you have {FLASH_DELAY} seconds)", parse_mode=enums.ParseMode.HTML)

    await cq.answer("You are the player! Memorize the sequence.", show_alert=False)

    # wait FLASH_DELAY seconds then hide and show pool
    await asyncio.sleep(FLASH_DELAY)

    # update last_update
    await games_col.update_one({"_id": game["_id"]}, {"$set": {"last_update": datetime.utcnow()}})
    game = await games_col.find_one({"_id": game["_id"]})

    pool = game["pool"]
    disabled_mask = game.get("disabled_mask", [False] * len(pool))
    pool_kb = build_pool_kb(pool, str(game["_id"]), disabled_mask)
    cancel_kb = build_cancel_kb(str(game["_id"]))
    try:
        await cq.message.edit_text(
            f"🧠 Now reproduce the sequence by tapping the emojis in the same order.\n\nSequence length: {len(game['sequence'])}\nPlayer: {user.mention}",
            reply_markup=pool_kb
        )
    except Exception:
        await cq.message.reply_text("Now reproduce the sequence by tapping the emojis in the same order.", reply_markup=pool_kb)

# pick an emoji from pool: pick|<game_id>|<index>
@app.on_callback_query(filters.regex(r"^pick\|"))
async def cb_pick(_, cq: CallbackQuery):
    data = cq.data  # pick|<game_id>|<index>
    parts = data.split("|")
    if len(parts) != 3:
        return await cq.answer("Invalid pick data.", show_alert=True)
    _, gid, idx_s = parts
    try:
        game_oid = ObjectId(gid)
    except:
        return await cq.answer("Invalid game id.", show_alert=True)
    try:
        idx = int(idx_s)
    except:
        return await cq.answer("Invalid index.", show_alert=True)

    user = cq.from_user
    game = await games_col.find_one({"_id": game_oid, "active": True})
    if not game:
        return await cq.answer("This game is not active anymore.", show_alert=True)

    # Only the chosen player can pick
    player_id = game.get("player_id")
    if player_id != user.id:
        return await cq.answer("Only the player who started the round can press buttons.", show_alert=True)

    pool = list(game.get("pool", []))
    if idx < 0 or idx >= len(pool):
        return await cq.answer("Invalid choice.", show_alert=True)

    # if button already used, noop
    disabled_mask = list(game.get("disabled_mask", [False]*len(pool)))
    if disabled_mask[idx]:
        return await cq.answer("This emoji was already selected.", show_alert=False)

    pick_emoji = pool[idx]
    # expected emoji according to sequence and next_index
    next_index = int(game.get("next_index", 0))
    sequence = list(game.get("sequence", []))
    if next_index >= len(sequence):
        return await cq.answer("Round already finished.", show_alert=True)

    expected = sequence[next_index]
    correct = (pick_emoji == expected)

    if correct:
        # mark this pool index used
        disabled_mask[idx] = True
        next_index += 1
        await games_col.update_one({"_id": game_oid}, {"$set": {"disabled_mask": disabled_mask, "next_index": next_index, "last_update": datetime.utcnow()}})
        # edit keyboard to reflect used button
        pool_kb = build_pool_kb(pool, gid, disabled_mask)
        try:
            await cq.message.edit_reply_markup(pool_kb)
        except Exception:
            pass

        if next_index == len(sequence):
            # player completed the sequence -> win
            points = 10 * len(sequence)  # example scoring
            await ensure_user(player_id, game.get("player_username"))
            await award_win(player_id, points=points)
            # mark game inactive
            await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow()}})
            try:
                await cq.message.edit_text(
                    f"🏆 {user.mention}! Correct — you completed the sequence!\n\nSequence: {' '.join(sequence)}\nPoints awarded: {points}",
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass
            await cq.answer("✅ Correct — you win!", show_alert=False)
            return
        else:
            await cq.answer("✅ Correct. Next one!", show_alert=False)
            return
    else:
        # incorrect pick -> handle attempt
        attempts = int(game.get("attempts", 0)) + 1
        await games_col.update_one({"_id": game_oid}, {"$set": {"attempts": attempts, "last_update": datetime.utcnow()}})
        if attempts >= int(game.get("max_attempts", MAX_ATTEMPTS)):
            # game lost
            await ensure_user(player_id, game.get("player_username"))
            await award_loss(player_id)
            await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow()}})
            try:
                await cq.message.edit_text(
                    f"❌ Wrong answer. Round over.\n\nCorrect sequence was: {' '.join(sequence)}",
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass
            await cq.answer("❌ Wrong. Round over.", show_alert=True)
            return
        else:
            await cq.answer("❌ Wrong. Try again.", show_alert=True)
            return

# cancel game: cancel|<game_id>
@app.on_callback_query(filters.regex(r"^cancel\|"))
async def cb_cancel(_, cq: CallbackQuery):
    data = cq.data
    parts = data.split("|")
    if len(parts) != 2:
        return await cq.answer("Invalid cancel data.", show_alert=True)
    _, gid = parts
    try:
        game_oid = ObjectId(gid)
    except:
        return await cq.answer("Invalid game id.", show_alert=True)
    game = await games_col.find_one({"_id": game_oid})
    if not game:
        return await cq.answer("Game not found.", show_alert=True)

    # Only player or chat admin can cancel
    user = cq.from_user
    if game.get("player_id") and user.id == game.get("player_id"):
        allowed = True
    else:
        # allow chat admins (for group)
        allowed = False
        try:
            member = await app.get_chat_member(cq.message.chat.id, user.id)
            if member.status in ("administrator", "creator"):
                allowed = True
        except Exception:
            allowed = False

    if not allowed:
        return await cq.answer("Only the player or group admin may cancel the game.", show_alert=True)

    await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow()}})
    try:
        await cq.message.edit_text("❌ Game cancelled.")
    except:
        pass
    await cq.answer("Game cancelled.", show_alert=False)

# noop (disabled button) handler
@app.on_callback_query(filters.regex(r"^noop$"))
async def cb_noop(_, cq: CallbackQuery):
    await cq.answer()

# ---------- Stale game cleaner ----------
async def stale_cleaner_loop():
    LOG.info("Starting stale game cleaner (CLEANUP_SECONDS=%s)", CLEANUP_SECONDS)
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=CLEANUP_SECONDS)
            stale_games = await games_col.find({"active": True, "last_update": {"$lt": cutoff}}).to_list(length=100)
            for g in stale_games:
                try:
                    # mark inactive
                    await games_col.update_one({"_id": g["_id"]}, {"$set": {"active": False}})
                    # try to edit message to indicate timeout
                    if g.get("message_id"):
                        try:
                            await app.edit_message_text(g["chat_id"], g["message_id"], "⏰ Game timed out due to inactivity.")
                        except Exception:
                            pass
                except Exception:
                    LOG.exception("Error cleaning stale game %s", g.get("_id"))
        except Exception:
            LOG.exception("Stale cleaner loop error")
        await asyncio.sleep(max(10, CLEANUP_SECONDS // 3))

# ---------- Profile & Leaderboard ----------
@app.on_message(filters.command("mfprofile"))
async def cmd_profile(_, m: Message):
    uid = m.from_user.id
    u = await users_col.find_one({"user_id": uid})
    if not u:
        await ensure_user(uid, m.from_user.username or m.from_user.first_name)
        u = await users_col.find_one({"user_id": uid})
    score = u.get("score", 0)
    wins = u.get("wins", 0)
    losses = u.get("losses", 0)
    games = u.get("games_played", 0)
    rank = rank_from_score(score)
    text = (
        f"👤 {m.from_user.mention}\n"
        f"🏷️ Username: {u.get('username','-')}\n"
        f"⭐ Score: {score}\n"
        f"🏆 Wins: {wins}\n"
        f"💔 Losses: {losses}\n"
        f"🎮 Games played: {games}\n"
        f"🔰 Rank: {rank}"
    )
    await m.reply_text(text, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("mfleaderboard"))
async def cmd_leaderboard(_, m: Message):
    top_n = int(os.getenv("TOP_N", "10"))
    top = await users_col.find().sort("score", -1).limit(top_n).to_list(length=top_n)
    if not top:
        return await m.reply_text("No players yet. Be the first to win a round!")
    lines = ["🏅 Leaderboard — Top Players"]
    for i, u in enumerate(top, start=1):
        uname = u.get("username") or str(u.get("user_id"))
        lines.append(f"{i}. {uname} — {u.get('score',0)} pts (wins: {u.get('wins',0)})")
    await m.reply_text("\n".join(lines), parse_mode=enums.ParseMode.HTML)

"""# ---------- Startup / Shutdown ----------
@app.on_start()
async def on_start():
    LOG.info("Memory Flash Bot starting...")
    # DB indexes
    try:
        await games_col.create_index("chat_id")
        await games_col.create_index("active")
        await users_col.create_index("user_id", unique=True)
    except Exception:
        pass
    # start cleaner
    asyncio.create_task(stale_cleaner_loop())
    LOG.info("Ready.")

@app.on_stop()
async def on_stop():
    LOG.info("Stopping Memory Flash Bot...")

# ---------- Run ----------
if __name__ == "__main__":
    app.run()
"""
