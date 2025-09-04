import random
import asyncio
from datetime import datetime, timedelta
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from config import DB_URL
from wallbot import wbot as app
# ---------------- CONFIG ----------------

DB_NAME = "wordchain_db"
GAME_TIMEOUT = 10  # in minutes
# ----------------------------------------

mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]
users_col = db["users"]

# ---------------- HELPERS -----------------
WORD_LIST = ["apple","elephant","tiger","rabbit","tree","egg","goat","top","pen","nose","ear","rat","tap","parrot","tank","kangaroo","owl","lion"]

def start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 PvE Game", callback_data="start_game_pve")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="wcleaderboard")]
    ])

def update_user_stats(user_id, wins=0, losses=0, games=0, longest_chain=0, xp=0):
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"wins": wins, "losses": losses, "games": games, "xp": xp},
         "$max": {"longest_chain": longest_chain}},
        upsert=True
    )

def get_rank(xp):
    if xp >= 1000:
        return "Legend"
    elif xp >= 500:
        return "Pro"
    elif xp >= 250:
        return "Intermediate"
    else:
        return "Beginner"

def leaderboard_text():
    top = users_col.find().sort([("xp", -1)]).limit(10)
    text = "🏆 Word Chain Leaderboard 🏆\n\n"
    for i, u in enumerate(top, 1):
        rank = get_rank(u.get("xp",0))
        text += f"{i}. `{u['user_id']}` → XP: {u.get('xp',0)} | Wins: {u.get('wins',0)} | Rank: {rank}\n"
    return text

def valid_word(word, last_letter, used_words):
    if not word.isalpha():
        return False
    if last_letter and word[0].lower() != last_letter.lower():
        return False
    if word.lower() in used_words:
        return False
    return True

def bot_word(last_letter, used_words, level="easy"):
    candidates = [w for w in WORD_LIST if valid_word(w, last_letter, used_words)]
    if not candidates:
        return None
    if level == "easy":
        return random.choice(candidates)
    elif level == "medium":
        return max(candidates, key=len)
    elif level == "hard":
        return random.choice(candidates)
    return random.choice(candidates)

# ---------------- COMMANDS -----------------
@app.on_message(filters.command("swt"))
async def staw_cmd(_, msg: Message):
    await msg.reply(
        "🎮 Welcome to Word Chain Bot!\n\n"
        "Rules:\n"
        "- Each word must start with the last letter of previous word.\n"
        "- No repeats allowed.\n"
        "Click below to start:",
        reply_markup=start_buttons()
    )

@app.on_message(filters.command("wrdprofile"))
async def pwrdrofile_cmd(_, msg: Message):
    user = users_col.find_one({"user_id": msg.from_user.id})
    if not user:
        return await msg.reply("You have no stats yet. Play a game first!")
    rank = get_rank(user.get("xp",0))
    await msg.reply(
        f"📊 Profile for {msg.from_user.first_name}\n"
        f"🏆 Wins: {user.get('wins',0)}\n"
        f"💀 Losses: {user.get('losses',0)}\n"
        f"🎮 Games: {user.get('games',0)}\n"
        f"🔗 Longest Chain: {user.get('longest_chain',0)}\n"
        f"✨ XP: {user.get('xp',0)}\n"
        f"🎖️ Rank: {rank}"
    )

@app.on_message(filters.command("wrdchallenge"))
async def wrdchallenge_cmd(_, msg: Message):
    if not msg.reply_to_message and len(msg.command) < 2:
        return await msg.reply("Reply to someone or use `/challenge @username`")
    if msg.reply_to_message:
        opponent_id = msg.reply_to_message.from_user.id
    else:
        try:
            opponent_id = (await app.get_users(msg.command[1])).id
        except:
            return await msg.reply("Invalid user!")

    challenger_id = msg.from_user.id
    if opponent_id == challenger_id:
        return await msg.reply("❌ You cannot challenge yourself!")

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"wcaccept_{challenger_id}_{opponent_id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"wcdecline_{challenger_id}_{opponent_id}")]
    ])

    await msg.reply(
        f"🎮 <a href='tg://user?id={challenger_id}'>Player 1</a> challenged "
        f"<a href='tg://user?id={opponent_id}'>Player 2</a> to a Word Chain game!",
        reply_markup=buttons
    )

@app.on_message(filters.command("wrdjoin"))
async def wrdjoin_game(_, msg: Message):
    user_id = msg.from_user.id
    game = games_col.find_one({
        "mode": "pvp",
        "finished": False,
        "started": {"$exists": False},
        "players": {"$ne": user_id}
    })
    if not game:
        return await msg.reply("❌ No pending PvP game to join!")
    games_col.update_one({"_id": game["_id"]}, {"$push": {"players": user_id}})
    await msg.reply(f"✅ {msg.from_user.first_name} joined the game!\nCurrent players: {len(game['players']) + 1}")

# ---------------- CALLBACKS -----------------
@app.on_callback_query(filters.regex("wcaccept|wcdecline|start_game_pve|wcleaderboard"))
async def cwallback_cb(_, cq: CallbackQuery):
    data = cq.data
    if data.startswith("accept") or data.startswith("decline"):
        action, challenger_id, opponent_id = data.split("_")
        challenger_id, opponent_id = int(challenger_id), int(opponent_id)
        if cq.from_user.id != opponent_id:
            return await cq.answer("This challenge is not for you!", show_alert=True)
        if action == "decline":
            await cq.message.edit(f"❌ <a href='tg://user?id={opponent_id}'>Player 2</a> declined the challenge.")
            return
        # Accept: start game
        game_id = f"pvp_{challenger_id}_{opponent_id}"
        games_col.insert_one({
            "_id": game_id,
            "players": [challenger_id, opponent_id],
            "turn": 0,
            "words": [],
            "last_letter": "",
            "started": datetime.utcnow(),
            "finished": False,
            "mode": "pvp"
        })
        await cq.message.edit(
            f"🎮 Word Chain PvP Started!\nTurn: <a href='tg://user?id={challenger_id}'>Player 1</a>"
        )
    elif data == "start_game_pve":
        user_id = cq.from_user.id
        game_id = f"pve_{user_id}"
        games_col.insert_one({
            "_id": game_id,
            "players": [user_id],
            "turn": 0,
            "words": [],
            "last_letter": "",
            "started": datetime.utcnow(),
            "finished": False,
            "mode": "pve",
            "level": "medium"
        })
        await cq.message.edit(f"🎮 Word Chain PvE Started! Your turn.", reply_markup=None)
    elif data == "leaderboard":
        await cq.message.edit(leaderboard_text())

# ---------------- WORD PLAY -----------------
@app.on_message(filters.text & ~filters.bot)
async def word_play(_, msg: Message):
    game = games_col.find_one({"players": msg.from_user.id, "finished": False})
    if not game:
        return
    turn_player_id = game["players"][game["turn"]]
    if msg.from_user.id != turn_player_id:
        return await msg.reply("❌ Not your turn!")

    word = msg.text.strip().lower()
    last_letter = game.get("last_letter", "")
    used_words = game.get("words", [])

    if not valid_word(word, last_letter, used_words):
        return await msg.reply(f"❌ Invalid word! Must start with '{last_letter}' and not be repeated.")

    used_words.append(word)
    last_letter = word[-1]

    if game["mode"] == "pve":
        bot_choice = bot_word(last_letter, used_words, level=game.get("level","medium"))
        if bot_choice:
            used_words.append(bot_choice)
            last_letter = bot_choice[-1]
            await msg.reply(f"🤖 Bot played: {bot_choice}\nNext letter: {last_letter.upper()}\nWords used: {', '.join(used_words)}")
        else:
            # User wins
            update_user_stats(msg.from_user.id, wins=1, games=1, longest_chain=len(used_words), xp=len(used_words)*10)
            games_col.update_one({"_id": game["_id"]}, {"$set": {"finished": True}})
            await msg.reply(f"🏆 You win! No more valid bot words.\nChain length: {len(used_words)}")
            return

    next_turn = (game["turn"] + 1) % len(game["players"])
    games_col.update_one({"_id": game["_id"]}, {"$set": {"words": used_words, "last_letter": last_letter, "turn": next_turn}})

    if game["mode"] == "pvp":
        next_player = game["players"][next_turn]
        await msg.reply(f"✅ {msg.from_user.first_name} played: {word}\nNext turn: <a href='tg://user?id={next_player}'>Player</a>\nWords used: {', '.join(used_words)}")
    else:
        await msg.reply(f"✅ {msg.from_user.first_name} played: {word}\nYour turn next.\nWords used: {', '.join(used_words)}")

# ---------------- AUTO CLEANUP -----------------
async def cleanup_inactive_games():
    while True:
        now = datetime.utcnow()
        timeout = timedelta(minutes=GAME_TIMEOUT)
        expired_games = games_col.find({"finished": False, "started": {"$exists": True}})
        for game in expired_games:
            if now - game["started"] > timeout:
                games_col.update_one({"_id": game["_id"]}, {"$set": {"finished": True}})
        await asyncio.sleep(60)

asyncio.create_task(cleanup_inactive_games())


