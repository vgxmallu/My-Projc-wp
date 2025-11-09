import asyncio, random
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as app


client = AsyncIOMotorClient(DB_URL)
db = client["infiltrator"]
players = db["players"]

# ─── ROLES ─────────────────────────────────────────────
ROLES = {
    "🕵️‍♂️ Agent": "Can scan a player per round to check if they’re a Spy.",
    "🧑‍💻 Hacker": "Can block sabotage once per game.",
    "🕶 Spy": "Can hack another player’s vote.",
    "👤 Civilian": "No powers — survive and identify the spy."
}

active_games = {}  # chat_id → game_data

# ─── UTILITIES ─────────────────────────────────────────
async def update_stats(uid, uname, win=False):
    p = await players.find_one({"user_id": uid})
    if not p:
        p = {"user_id": uid, "username": uname, "xp": 0, "wins": 0, "games": 0}
    p["games"] += 1
    if win:
        p["wins"] += 1
        p["xp"] += random.randint(20, 50)
    else:
        p["xp"] += random.randint(5, 15)
    await players.update_one({"user_id": uid}, {"$set": p}, upsert=True)

async def get_leaderboard_text():
    top = players.find().sort("xp", -1).limit(10)
    text = "🏆 **Global Infiltrator Leaderboard**\n\n"
    rank = 1
    async for p in top:
        text += f"#{rank} {p['username']} — 🧠 XP: {p['xp']} | 🕹 Wins: {p['wins']}\n"
        rank += 1
    return text

# ─── START GAME ─────────────────────────────────────────
@app.on_message(filters.command("startaus") & filters.group)
async def startaus_game(_, m: Message):
    chat_id = m.chat.id
    if chat_id in active_games:
        return await m.reply_text("⚠️ A game is already running here!")

    members = []
    async for member in app.get_chat_members(chat_id):
        if not member.user.is_bot:
            members.append(member.user)

    if len(members) < 4:
        return await m.reply_text("Need at least 4 players to start!")

    random.shuffle(members)
    assigned = {}
    chosen_roles = random.sample(list(ROLES.keys()), len(ROLES))
    for i, user in enumerate(members[:len(ROLES)]):
        role = chosen_roles[i]
        assigned[user.id] = role
        try:
            await app.send_message(
                user.id,
                f"🎭 You are **{role}**\n🧩 Ability: {ROLES[role]}\nUse /action in DM to perform your power."
            )
        except:
            pass

    game_data = {
        "chat_id": chat_id,
        "assigned": assigned,
        "alive": list(assigned.keys()),
        "votes": {},
        "round": 1,
        "started": datetime.utcnow(),
        "actions_used": set()
    }
    active_games[chat_id] = game_data

    await m.reply_text(
        "🕵️‍♂️ **Infiltrator Game Started!**\nCheck your DMs for your role.\n\nStarting voting phase in 10 seconds..."
    )
    await asyncio.sleep(10)
    await start_voting(chat_id)

# ─── INLINE VOTING ──────────────────────────────────────
async def start_voting(chat_id):
    game = active_games.get(chat_id)
    if not game: return
    buttons = []
    for uid in game["alive"]:
        u = await app.get_users(uid)
        buttons.append([InlineKeyboardButton(u.first_name, callback_data=f"vote_{uid}")])
    markup = InlineKeyboardMarkup(buttons)
    await app.send_message(chat_id, "🗳 **Vote to eliminate someone!**", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^vote_"))
async def handle_vote(_, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id
    target_id = int(cq.data.split("_")[1])

    game = active_games.get(chat_id)
    if not game or user_id not in game["alive"]:
        return await cq.answer("Not in this game!", show_alert=True)

    game["votes"][user_id] = target_id
    await cq.answer("Vote registered!")
    await cq.message.reply_text(f"🗳 {cq.from_user.first_name} voted.")

    if len(game["votes"]) == len(game["alive"]):
        await resolve_round(chat_id)

# ─── ACTION COMMANDS (DM Only) ──────────────────────────
@app.on_message(filters.private & filters.command("actionaus"))
async def actiauson(_, m: Message):
    uid = m.from_user.id
    # Find which chat the user is in
    for chat_id, game in active_games.items():
        if uid in game["alive"]:
            role = game["assigned"][uid]
            if uid in game["actions_used"]:
                return await m.reply_text("⚠️ You already used your action this game.")
            if role == "🕵️‍♂️ Agent":
                await m.reply_text("Send /scan @username to check if they are a Spy.")
            elif role == "🧑‍💻 Hacker":
                await m.reply_text("Send /block to prevent next sabotage.")
            elif role == "🕶 Spy":
                await m.reply_text("Send /hack @username to alter their next vote.")
            else:
                await m.reply_text("You have no special actions.")
            break

@app.on_message(filters.private & filters.command("scanaus"))
async def scausan(_, m: Message):
    for chat_id, game in active_games.items():
        if m.from_user.id in game["alive"]:
            target_name = m.command[1].replace("@", "") if len(m.command) > 1 else None
            if not target_name:
                return await m.reply_text("Usage: /scan @username")
            for uid in game["alive"]:
                u = await app.get_users(uid)
                if u.username and u.username.lower() == target_name.lower():
                    role = game["assigned"][uid]
                    result = "✅ They are the Spy!" if "Spy" in role else "❌ They are not a Spy."
                    await m.reply_text(result)
                    game["actions_used"].add(m.from_user.id)
                    return
            await m.reply_text("User not found.")
            break

@app.on_message(filters.private & filters.command("hackaus"))
async def hacausk(_, m: Message):
    for chat_id, game in active_games.items():
        if m.from_user.id in game["alive"]:
            if len(m.command) < 2:
                return await m.reply_text("Usage: /hack @username")
            target_name = m.command[1].replace("@", "")
            for uid in game["alive"]:
                u = await app.get_users(uid)
                if u.username and u.username.lower() == target_name.lower():
                    game["votes"][uid] = random.choice(game["alive"])
                    await m.reply_text(f"🧠 You hacked {u.first_name}'s vote!")
                    game["actions_used"].add(m.from_user.id)
                    return
            await m.reply_text("User not found.")
            break

@app.on_message(filters.private & filters.command("blockaus"))
async def bauslock(_, m: Message):
    for chat_id, game in active_games.items():
        if m.from_user.id in game["alive"]:
            game["blocked"] = True
            await m.reply_text("🛡 Sabotage blocked this round!")
            game["actions_used"].add(m.from_user.id)
            break

# ─── ROUND RESOLUTION ───────────────────────────────────
async def resolve_round(chat_id):
    game = active_games.get(chat_id)
    votes = list(game["votes"].values())
    if not votes: return

    target = max(set(votes), key=votes.count)
    game["alive"].remove(target)
    voted_out = await app.get_users(target)
    msg = f"❌ {voted_out.first_name} was eliminated."

    if len(game["alive"]) <= 2:
        survivors = [await app.get_users(u) for u in game["alive"]]
        winner = survivors[0]
        await app.send_message(chat_id, f"🏁 Game Over!\nWinner: {winner.first_name}")
        await update_stats(winner.id, winner.first_name, win=True)
        del active_games[chat_id]
    else:
        await app.send_message(chat_id, f"{msg}\nStarting next round...")
        game["round"] += 1
        game["votes"].clear()
        await asyncio.sleep(3)
        await sabotage_event(chat_id)
        await start_voting(chat_id)

# ─── SABOTAGE EVENTS ─────────────────────────────────────
async def sabotage_event(chat_id):
    game = active_games.get(chat_id)
    if not game or game.get("blocked"):
        game["blocked"] = False
        return await app.send_message(chat_id, "🧑‍💻 Hacker blocked a sabotage this round!")
    sabotages = [
        "💣 Communication jammed — next round votes are delayed!",
        "⚡ Power outage — random player skips voting!",
        "🕶 Spy spread false info, random vote swapped!"
    ]
    await app.send_message(chat_id, random.choice(sabotages))

# ─── PROFILE / LEADERBOARD ───────────────────────────────
@app.on_message(filters.command("profileaus"))
async def profilagae(_, m: Message):
    user = await players.find_one({"user_id": m.from_user.id})
    if not user:
        return await m.reply_text("No profile yet — join a game first!")
    await m.reply_text(
        f"👤 **{m.from_user.first_name}**\n🧠 XP: {user['xp']}\n🏆 Wins: {user['wins']}\n🎮 Games: {user['games']}"
    )

@app.on_message(filters.command("leaderboardaus"))
async def leaderbysyoard(_, m: Message):
    text = await get_leaderboard_text()
    await m.reply_text(text)

# ─── BACKGROUND CLEANUP ─────────────────────────────────
async def cleanup_stale_games():
    while True:
        now = datetime.utcnow()
        for chat_id, game in list(active_games.items()):
            if (now - game["started"]).seconds > 1800:
                await app.send_message(chat_id, "⌛ Game ended due to inactivity.")
                del active_games[chat_id]
        await asyncio.sleep(300)

