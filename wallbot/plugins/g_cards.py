"""
Advanced Cards (Blackjack) Bot for Telegram
- Pyrogram v2.x
- MongoDB (pymongo)
Features:
- PvE Blackjack (vs bot) with difficulty levels
- PvP Blackjack duel (challenge/join)
- Wagers (coins)
- Profiles (coins, xp, wins/losses)
- Leaderboard
- Tournament mode (simple bracket)
- Spectator mode (watch games)
- Inline button controls for gameplay (hit/stand/join/start)
- Auto-cleanup of inactive games
"""

import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from pymongo import MongoClient, DESCENDING
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
)
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "cards_game_db"

START_COINS = 500
AUTO_CLEANUP_MINUTES = 20
BLACKJACK_PAYOUT = 1.5  # blackjack natural payout multiplier

mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]
games_col = db["games"]
tournaments_col = db["tournaments"]

# ----------------- UTIL -----------------
RANKS = [
    (0, "Rookie"),
    (1000, "Player"),
    (3000, "Pro"),
    (8000, "Champion"),
    (20000, "Legend"),
]


def rank_for_xp(xp: int) -> str:
    r = RANKS[0][1]
    for threshold, name in RANKS:
        if xp >= threshold:
            r = name
    return r


def ensure_user(user_id: int, name: str) -> Dict[str, Any]:
    """Ensure user profile exists."""
    user = users_col.find_one_and_update(
        {"_id": user_id},
        {"$setOnInsert": {
            "_id": user_id,
            "name": name,
            "coins": START_COINS,
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "blackjacks": 0,
            "created_at": datetime.utcnow()
        }},
        upsert=True,
        return_document=True
    )
    if not user:
        user = users_col.find_one({"_id": user_id})
    return user


def add_coins(user_id: int, amount: int):
    users_col.update_one({"_id": user_id}, {"$inc": {"coins": amount}})


def add_xp(user_id: int, amount: int):
    users_col.update_one({"_id": user_id}, {"$inc": {"xp": amount}})


def record_result(user_id: int, win: bool, blackjack: bool = False):
    if win:
        users_col.update_one({"_id": user_id}, {"$inc": {"wins": 1}})
        if blackjack:
            users_col.update_one({"_id": user_id}, {"$inc": {"blackjacks": 1}})
    else:
        users_col.update_one({"_id": user_id}, {"$inc": {"losses": 1}})


def pretty_money(n: int) -> str:
    return f"{n}c"


# ----------------- CARDS / BLACKJACK LOGIC -----------------
SUITS = ["♠", "♥", "♦", "♣"]
RANK_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def new_deck(shuffle: bool = True) -> List[str]:
    deck = [f"{r}{s}" for r in RANK_ORDER for s in SUITS]
    if shuffle:
        random.shuffle(deck)
    return deck


def card_value(card: str) -> int:
    rank = card[:-1]  # A,2,...,10,J,Q,K
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11  # treat as 11 initially
    return int(rank)


def hand_value(hand: List[str]) -> int:
    total = 0
    aces = 0
    for c in hand:
        v = card_value(c)
        total += v
        if c[:-1] == "A":
            aces += 1
    # adjust aces from 11 to 1 as needed
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def render_hand(hand: List[str], hide_first: bool = False) -> str:
    if hide_first and hand:
        return "🂠 " + " ".join(hand[1:])
    return " ".join(hand)


# ----------------- GAME HELPERS -----------------
def create_blackjack_game(game_id: str, owner_id: int, wager: int = 0, mode: str = "pve", level: str = "normal"):
    game = {
        "_id": game_id,
        "owner": owner_id,
        "players": [owner_id] if mode == "pve" else [owner_id],
        "mode": mode,  # pve or pvp
        "level": level,
        "wager": wager,
        "deck": new_deck(),
        "hands": {},  # user_id -> list of cards
        "turn": owner_id,
        "started": datetime.utcnow(),
        "finished": False,
        "spectators": [],
        "created_at": datetime.utcnow()
    }
    games_col.insert_one(game)
    return game


def get_game(game_id: str) -> Optional[Dict[str, Any]]:
    return games_col.find_one({"_id": game_id})


def save_game(game: Dict[str, Any]):
    games_col.replace_one({"_id": game["_id"]}, game, upsert=True)


def cleanup_old_games():
    cutoff = datetime.utcnow() - timedelta(minutes=AUTO_CLEANUP_MINUTES)
    games_col.update_many({"finished": False, "started": {"$lt": cutoff}}, {"$set": {"finished": True}})


# ----------------- UI (INLINE) -----------------
def lobby_buttons():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("♠ PvE (normal)", callback_data="start_pve_normal"),
             InlineKeyboardButton("♠ PvE (hard)", callback_data="start_pve_hard")],
            [InlineKeyboardButton("⚔️ PvP Challenge", callback_data="start_pvp")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
        ]
    )


def pvp_join_buttons(owner_id: int, wager: int = 0):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Join", callback_data=f"pvp_join_{owner_id}")],
            [InlineKeyboardButton("▶️ Start", callback_data=f"pvp_start_{owner_id}")]
        ]
    )


def blackjack_action_buttons(user_id: int):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🃏 Hit", callback_data=f"hit_{user_id}"),
             InlineKeyboardButton("✋ Stand", callback_data=f"stand_{user_id}")],
            [InlineKeyboardButton("👀 Spectate", callback_data=f"spectate_{user_id}")]
        ]
    )


# ----------------- COMMANDS -----------------
@app.on_message(filters.command("strj"))
async def cmd_sfmjart(_, msg: Message):
    ensure_user(msg.from_user.id, msg.from_user.first_name)
    await msg.reply_text(
        "♠ Welcome to Cards Bot (Blackjack)\n"
        "Play PvE or challenge friends in PvP.\n"
        "Use the buttons to start.",
        reply_markup=lobby_buttons()
    )


@app.on_message(filters.command("cprofile"))
async def cmd_bdrofile(_, msg: Message):
    ensure_user(msg.from_user.id, msg.from_user.first_name)
    user = users_col.find_one({"_id": msg.from_user.id})
    text = (
        f"👤 {msg.from_user.mention}\n"
        f"💰 Coins: {pretty_money(user.get('coins', 0))}\n"
        f"⭐ XP: {user.get('xp', 0)} ({rank_for_xp(user.get('xp', 0))})\n"
        f"🏆 Wins: {user.get('wins', 0)} | Losses: {user.get('losses', 0)}\n"
        f"🂡 Blackjacks: {user.get('blackjacks', 0)}"
    )
    await msg.reply_text(text)


@app.on_message(filters.command("cleaderboard"))
async def cmd_lceaderboard(_, msg: Message):
    top = users_col.find().sort("coins", DESCENDING).limit(10)
    text = "🏆 Leaderboard — Top Coins\n\n"
    for i, u in enumerate(top, 1):
        text += f"{i}. {u.get('name','?')} — {u.get('coins',0)}c — XP {u.get('xp',0)}\n"
    await msg.reply_text(text)


@app.on_message(filters.command("cblackjack"))
async def cmd_bclackjack(_, msg: Message):
    # quick start pve normal with optional wager: /blackjack 50 or /blackjack wager 50
    ensure_user(msg.from_user.id, msg.from_user.first_name)
    args = msg.command[1:]
    wager = 0
    if args:
        try:
            wager = int(args[0])
        except:
            wager = 0
    game_id = f"pve_{msg.from_user.id}_{int(datetime.utcnow().timestamp())}"
    game = create_blackjack_game(game_id, msg.from_user.id, wager=wager, mode="pve", level="normal")
    # deal initial hands
    for uid in game["players"]:
        game["hands"][str(uid)] = [game["deck"].pop(), game["deck"].pop()]
    save_game(game)
    await msg.reply_text(
        f"♠ Blackjack (PvE) started for {msg.from_user.mention}\n"
        f"Wager: {pretty_money(wager)}\n"
        f"Your hand: {render_hand(game['hands'][str(msg.from_user.id)])} — {hand_value(game['hands'][str(msg.from_user.id)])}",
        reply_markup=blackjack_action_buttons(msg.from_user.id)
    )


# ----------------- CALLBACKS (single regex based handler) -----------------
@app.on_callback_query(filters.regex(r"^(start_pve|start_pvp|pvp_join|pvp_start|hit|stand|spectate|leaderboard)"))
async def callback_rouhter(_, cq: CallbackQuery):
    data = cq.data
    user = cq.from_user
    # START PVE
    if data.startswith("start_pve"):
        _, _, level = data.partition("_")
        # create pve game
        game_id = f"pve_{user.id}_{int(datetime.utcnow().timestamp())}"
        game = create_blackjack_game(game_id, user.id, wager=0, mode="pve", level=level or "normal")
        # deal
        game["hands"][str(user.id)] = [game["deck"].pop(), game["deck"].pop()]
        save_game(game)
        await cq.message.edit_text(
            f"♠ Blackjack PvE started for {user.mention}\nHand: {render_hand(game['hands'][str(user.id)])} — {hand_value(game['hands'][str(user.id)])}",
            reply_markup=blackjack_action_buttons(user.id)
        )
        await cq.answer()

    # START PVP: create lobby for others to join
    elif data == "start_pvp":
        game_id = f"pvp_{user.id}_{int(datetime.utcnow().timestamp())}"
        create_blackjack_game(game_id, user.id, wager=0, mode="pvp")
        await cq.message.reply_text(
            f"⚔️ PvP challenge created by {user.mention}\nOthers can join.",
            reply_markup=pvp_join_buttons(user.id)
        )
        await cq.answer()

    elif data.startswith("pvp_join_"):
        owner_id = int(data.split("_")[-1])
        # find pending game by owner
        game = games_col.find_one({"_id": {"$regex": f"^pvp_{owner_id}"}, "mode": "pvp", "finished": False})
        if not game:
            await cq.answer("No pending game found.", show_alert=True)
            return
        if str(user.id) in game.get("hands", {}):
            await cq.answer("You already joined.", show_alert=True)
            return
        # add player
        game["players"].append(user.id)
        game["hands"][str(user.id)] = []
        save_game(game)
        await cq.message.edit_text(f"Player {user.mention} joined the PvP lobby.", reply_markup=pvp_join_buttons(owner_id))
        await cq.answer("Joined lobby.")

    elif data.startswith("pvp_start_"):
        owner_id = int(data.split("_")[-1])
        game = games_col.find_one({"_id": {"$regex": f"^pvp_{owner_id}"}, "mode": "pvp", "finished": False})
        if not game:
            await cq.answer("No pending game found.", show_alert=True)
            return
        if len(game["players"]) < 2:
            await cq.answer("Need at least 2 players to start.", show_alert=True)
            return
        # deal two cards to each player
        for uid in game["players"]:
            game["hands"][str(uid)] = [game["deck"].pop(), game["deck"].pop()]
        # set turn to first player
        game["turn"] = game["players"][0]
        save_game(game)
        # notify chat
        await cq.message.edit_text(
            f"⚔️ PvP started!\nTurn: <a href='tg://user?id={game['turn']}'>player</a>\nUse inline buttons to play.",
            reply_markup=blackjack_action_buttons(game["turn"])
        )
        await cq.answer()

    # HIT
    elif data.startswith("hit_"):
        uid = int(data.split("_")[1])
        # find active game where it's this user's turn
        game = games_col.find_one({"finished": False, "hands." + str(uid): {"$exists": True}})
        if not game:
            await cq.answer("No active game found for you.", show_alert=True)
            return
        if game["turn"] != uid:
            await cq.answer("Not your turn.", show_alert=True)
            return
        # draw card
        card = game["deck"].pop()
        game["hands"][str(uid)].append(card)
        hv = hand_value(game["hands"][str(uid)])
        # check bust
        msg_text = f"{cq.from_user.mention} drew {card}. Hand: {render_hand(game['hands'][str(uid)])} — {hv}"
        if hv > 21:
            # bust -> end for this player, if PvE compare, if PvP pass turn or resolve
            msg_text += "\n💥 BUST!"
            # For PvE: bot wins
            if game["mode"] == "pve":
                # settle wager if any
                add_xp(uid, 5)
                record_result(uid, False)
                game["finished"] = True
                save_game(game)
                await cq.message.edit_text(msg_text + f"\nDealer wins. Game over.")
                await cq.answer()
                return
            else:
                # PvP: remove player's ability (mark as finished)
                # simplest: player loses immediately against remaining players (we'll mark loss)
                game["finished"] = True
                save_game(game)
                # naive resolution: other player wins (if 2 players)
                if len(game["players"]) == 2:
                    opponent = [p for p in game["players"] if p != uid][0]
                    add_coins(opponent, game.get("wager", 0))
                    add_xp(opponent, 20)
                    record_result(opponent, True)
                    record_result(uid, False)
                    await cq.message.edit_text(msg_text + f"\nPlayer busted. <a href='tg://user?id={opponent}'>Opponent</a> wins!")
                    await cq.answer()
                    return
        else:
            # not busted: advance turn (for PvP go to next player; for PvE let dealer act when player stands)
            if game["mode"] == "pvp":
                idx = game["players"].index(uid)
                next_idx = (idx + 1) % len(game["players"])
                game["turn"] = game["players"][next_idx]
                save_game(game)
                await cq.message.edit_text(msg_text + f"\nNext turn: <a href='tg://user?id={game['turn']}'>player</a>", reply_markup=blackjack_action_buttons(game["turn"]))
                await cq.answer()
                return
            else:
                # PvE: after hit, still player's turn until stand or bust
                save_game(game)
                await cq.message.edit_text(msg_text + "\nYour move.", reply_markup=blackjack_action_buttons(uid))
                await cq.answer()
                return

    # STAND
    elif data.startswith("stand_"):
        uid = int(data.split("_")[1])
        game = games_col.find_one({"finished": False, "hands." + str(uid): {"$exists": True}})
        if not game:
            await cq.answer("No active game.", show_alert=True)
            return
        if game["turn"] != uid:
            await cq.answer("Not your turn.", show_alert=True)
            return

        # PvE: dealer plays
        if game["mode"] == "pve":
            # dealer draws until 17
            dealer_hand = []
            # create dealer hand from deck top (we'll simulate dealer)
            # if we stored dealer elsewhere, but for simplicity use deck
            dealer_hand = [game["deck"].pop(), game["deck"].pop()]
            player_hand = game["hands"][str(uid)]
            phv = hand_value(player_hand)
            # dealer draw
            while hand_value(dealer_hand) < 17:
                dealer_hand.append(game["deck"].pop())
            dhv = hand_value(dealer_hand)
            # determine winner
            result_text = f"You: {render_hand(player_hand)} — {phv}\nDealer: {render_hand(dealer_hand)} — {dhv}\n"
            if (phv > dhv and phv <= 21) or (dhv > 21 and phv <= 21):
                # player wins
                add_coins(uid, int(game.get("wager", 0) * 2))
                add_xp(uid, 20)
                record_result(uid, True, blackjack=(phv == 21 and len(player_hand) == 2))
                result_text += "🏆 You win!"
            elif phv == dhv:
                result_text += "🤝 Draw!"
            else:
                record_result(uid, False)
                result_text += "💀 Dealer wins!"
            game["finished"] = True
            save_game(game)
            await cq.message.edit_text(result_text)
            await cq.answer()
            return

        else:
            # PvP: mark player as stood, and check if all stood to resolve showdown
            # We'll store per-player state: 'stood' flag
            if "states" not in game:
                game["states"] = {}
            game["states"][str(uid)] = "stood"
            # find next player who hasn't stood; else resolve
            all_stood = all(game["states"].get(str(p)) == "stood" for p in game["players"])
            if not all_stood:
                # advance to next player
                idx = game["players"].index(uid)
                next_idx = (idx + 1) % len(game["players"])
                game["turn"] = game["players"][next_idx]
                save_game(game)
                await cq.message.edit_text(f"{cq.from_user.mention} stands. Next: <a href='tg://user?id={game['turn']}'>player</a>", reply_markup=blackjack_action_buttons(game["turn"]))
                await cq.answer()
                return
            else:
                # showdown: highest hand <=21 wins
                best = None
                best_uid = None
                tie = []
                for p in game["players"]:
                    hv = hand_value(game["hands"][str(p)])
                    if hv > 21:
                        continue
                    if best is None or hv > best:
                        best = hv
                        best_uid = p
                        tie = [p]
                    elif hv == best:
                        tie.append(p)
                if not tie:
                    out = "All busted — no winners."
                elif len(tie) > 1:
                    out = "Tie between: " + ", ".join(f"<a href='tg://user?id={p}'>player</a>" for p in tie)
                    # split wager if any
                    if game.get("wager", 0):
                        split = int(game["wager"] * 2 / len(tie))
                        for p in tie:
                            add_coins(p, split)
                else:
                    winner = tie[0]
                    add_coins(winner, game.get("wager", 0) * 2)
                    add_xp(winner, 30)
                    record_result(winner, True)
                    out = f"🏆 Winner: <a href='tg://user?id={winner}'>player</a> with {best} points!"
                game["finished"] = True
                save_game(game)
                await cq.message.edit_text("Showdown!\n" + out)
                await cq.answer()
                return

    # SPECTATE
    elif data.startswith("spectate_"):
        target_uid = int(data.split("_")[1])
        # find game containing target
        game = games_col.find_one({"finished": False, "hands." + str(target_uid): {"$exists": True}})
        if not game:
            await cq.answer("No active game to spectate.", show_alert=True)
            return
        # add spectator
        if user.id not in game.get("spectators", []):
            game["spectators"].append(user.id)
            save_game(game)
        # render current hands but hide unrevealed data
        text = "👀 Spectating game\n\n"
        for p in game["players"]:
            hand = game["hands"].get(str(p), [])
            text += f"<a href='tg://user?id={p}'>player</a>: {render_hand(hand)} — {hand_value(hand)}\n"
        await cq.message.edit_text(text)
        await cq.answer("You are now spectating.")

    # LEADERBOARD (inline button)
    elif data == "leaderboard":
        top = users_col.find().sort("coins", DESCENDING).limit(10)
        text = "🏆 Leaderboard — Top Coins\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {u.get('name','?')} — {u.get('coins',0)}c — XP {u.get('xp',0)}\n"
        await cq.message.edit_text(text)
        await cq.answer()

    else:
        await cq.answer()

# ----------------- AUTO CLEANUP TASK -----------------
async def cleanup_task():
    while True:
        try:
            cleanup_old_games()
        except Exception:
            pass
        await asyncio.sleep(60 * 5)


@app.on_message(filters.command("ctournament"))
async def cmd_tghournament(_, msg: Message):
    """Create a quick tournament: /tournament join -> others join, /tournament start to run bracket"""
    ensure_user(msg.from_user.id, msg.from_user.first_name)
    args = msg.command[1:]
    if not args:
        # create joinable tournament
        tour_id = f"tour_{msg.from_user.id}_{int(datetime.utcnow().timestamp())}"
        tournaments_col.insert_one({
            "_id": tour_id,
            "owner": msg.from_user.id,
            "players": [msg.from_user.id],
            "started": False,
            "created_at": datetime.utcnow()
        })
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Join", callback_data=f"tour_join_{tour_id}")],
                                         [InlineKeyboardButton("▶️ Start", callback_data=f"tour_start_{tour_id}")]])
        await msg.reply_text("🏆 Tournament created. Others can join.", reply_markup=keyboard)
        return
    cmd = args[0].lower()
    if cmd == "start":
        # start already handled by callback; provide helper
        await msg.reply_text("Use the Start button in the tournament message to begin.")

@app.on_callback_query(filters.regex(r"^tour_join_|^tour_start_"))
async def tour_cb(_, cq: CallbackQuery):
    data = cq.data
    if data.startswith("tour_join_"):
        tour_id = data.split("_", 2)[2]
        tour = tournaments_col.find_one({"_id": tour_id})
        if not tour:
            await cq.answer("Tournament not found.", show_alert=True)
            return
        if cq.from_user.id in tour.get("players", []):
            await cq.answer("Already joined.", show_alert=True)
            return
        tournaments_col.update_one({"_id": tour_id}, {"$push": {"players": cq.from_user.id}})
        await cq.answer("Joined tournament.")
    elif data.startswith("tour_start_"):
        tour_id = data.split("_", 2)[2]
        tour = tournaments_col.find_one({"_id": tour_id})
        if not tour:
            await cq.answer("Tournament not found.", show_alert=True)
            return
        if tour.get("started"):
            await cq.answer("Already started.", show_alert=True)
            return
        players = tour.get("players", [])
        if len(players) < 2:
            await cq.answer("Need at least 2 players.", show_alert=True)
            return
        # simple bracket pairing: pair sequentially, winners advance by random (placeholder)
        random.shuffle(players)
        bracket = []
        while len(players) >= 2:
            a = players.pop()
            b = players.pop()
            bracket.append((a, b))
        winner = None
        results_text = "🏆 Tournament Results\n\n"
        for a, b in bracket:
            # simulate one-round blackjack: compare random scores
            score_a = random.randint(1, 21)
            score_b = random.randint(1, 21)
            if score_a >= score_b:
                winner = a
            else:
                winner = b
            results_text += f"<a href='tg://user?id={a}'>A</a> ({score_a}) vs <a href='tg://user?id={b}'>B</a> ({score_b}) -> Winner: <a href='tg://user?id={winner}'>W</a>\n"
            add_xp(winner, 50)
            users_col.update_one({"_id": winner}, {"$inc": {"coins": 200}})
        tournaments_col.update_one({"_id": tour_id}, {"$set": {"started": True, "finished_at": datetime.utcnow()}})
        await cq.message.edit_text(results_text)
        await cq.answer("Tournament finished.")
