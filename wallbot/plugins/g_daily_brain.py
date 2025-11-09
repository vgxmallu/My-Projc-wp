import asyncio
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as app

ADMIN_ID = 784589736
db = AsyncIOMotorClient(DB_URL)["mindzone_db"]
users_col = db["users"]
puzzles_col = db["puzzles"]

# ---------------- DAILY PUZZLES ----------------


PUZZLES = {
    "easy": [
        ("What has to be broken before you can use it?", "egg"),
        ("What has hands but cannot clap?", "clock"),
        ("What gets wetter as it dries?", "towel"),
        ("What has a face and two hands but no arms or legs?", "clock"),
        ("What comes down but never goes up?", "rain"),
        ("I’m tall when I’m young, and I’m short when I’m old. What am I?", "candle"),
        ("What has words, but never speaks?", "book"),
        ("What can you catch, but not throw?", "cold"),
        ("The more of this there is, the less you see. What is it?", "darkness"),
        ("What is full of holes but still holds water?", "sponge"),
    ],

    "medium": [
        ("I speak without a mouth and hear without ears. What am I?", "echo"),
        ("What disappears as soon as you say its name?", "silence"),
        ("The more you take, the more you leave behind. What am I?", "footsteps"),
        ("I’m light as a feather, yet the strongest person can’t hold me for five minutes. What am I?", "breath"),
        ("Forward I am heavy, but backward I am not. What am I?", "ton"),
        ("I have keys but no locks. I have space but no room. You can enter but not go outside. What am I?", "keyboard"),
        ("I shave every day, but my beard stays the same. What am I?", "barber"),
        ("What runs all around a backyard, yet never moves?", "fence"),
        ("What has one eye but cannot see?", "needle"),
        ("What invention lets you look right through a wall?", "window"),
    ],

    "hard": [
        ("You see me once in June, twice in November, but not at all in May. What am I?", "e"),
        ("I am taken from a mine, locked up in a wooden case, never released, yet almost every person uses me. What am I?", "pencil lead"),
        ("I’m found in Mercury, Earth, Mars, and Jupiter, but not in Venus or Neptune. What am I?", "r"),
        ("I am not alive, but I grow; I don’t have lungs, but I need air. What am I?", "fire"),
        ("If you drop me, I’m sure to crack, but give me a smile and I’ll smile back. What am I?", "mirror"),
        ("The person who makes it, sells it. The person who buys it, never uses it. The person who uses it doesn’t know it. What is it?", "coffin"),
        ("I am always hungry and will die if not fed, but whatever I touch will soon turn red. What am I?", "fire"),
        ("What flies without wings and cries without eyes?", "cloud"),
        ("What goes up but never comes down?", "age"),
        ("I am something people love or hate. I change people's appearances and thoughts. What am I?", "mirror"),
    ],

    "insane": [
        ("I am the beginning of eternity, the end of time and space, the beginning of every end and the end of every place. What am I?", "e"),
        ("You measure my life in hours and I serve you by expiring. I’m quick when I’m thin and slow when I’m fat. What am I?", "candle"),
        ("The more you take away from me, the bigger I get. What am I?", "hole"),
        ("I have cities, but no houses; forests, but no trees; and water, but no fish. What am I?", "map"),
        ("I can fly without wings. I cry without eyes. Wherever I go, darkness flies. What am I?", "cloud"),
        ("What can run but never walks, has a bed but never sleeps, has a mouth but never eats?", "river"),
        ("I am an odd number. Take away one letter and I become even. What number am I?", "seven"),
        ("I can be cracked, made, told, and played. What am I?", "joke"),
        ("The one who makes it doesn’t want it, the one who buys it doesn’t need it, and the one who uses it doesn’t know it. What am I?", "coffin"),
        ("What walks on four legs in the morning, two legs at noon, and three legs in the evening?", "man"),
    ]
}

# ---------------- UTILS ----------------

async def get_user(uid, uname):
    user = await users_col.find_one({"_id": uid})
    if not user:
        user = {
            "_id": uid,
            "username": uname,
            "xp": 0,
            "streak": 0,
            "last_solved": None,
            "rank": "Beginner",
        }
        await users_col.insert_one(user)
    return user


async def give_xp(uid, amount):
    await users_col.update_one({"_id": uid}, {"$inc": {"xp": amount}})
    user = await users_col.find_one({"_id": uid})
    xp = user["xp"]
    if xp >= 1000:
        rank = "Mastermind"
    elif xp >= 500:
        rank = "Expert"
    elif xp >= 200:
        rank = "Thinker"
    else:
        rank = "Beginner"
    await users_col.update_one({"_id": uid}, {"$set": {"rank": rank}})


# ---------------- PUZZLE SYSTEM ----------------

async def post_daily_puzzle():
    """Automatically posts new puzzles every day at midnight UTC"""
    while True:
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        delay = (next_midnight - now).total_seconds()
        await asyncio.sleep(delay)

        difficulty = random.choice(["easy", "medium", "hard"])
        puzzle, answer = random.choice(PUZZLES[difficulty])
        await puzzles_col.insert_one({
            "text": puzzle,
            "answer": answer.lower(),
            "difficulty": difficulty,
            "date": datetime.utcnow().date().isoformat(),
        })

        # Notify group or admin
        await app.send_message(
            ADMIN_ID,
            f"🧩 New Daily Puzzle ({difficulty.title()}):\n\n{puzzle}\n\nUse /puzzle to play!"
        )


@app.on_message(filters.command("bcpuzzle"))
async def sebcnd_puzzle(_, m):
    today = datetime.utcnow().date().isoformat()
    puzzle = await puzzles_col.find_one({"date": today})
    if not puzzle:
        await m.reply_text("⏳ Today's puzzle is not ready yet. Try again later!")
        return

    user = await get_user(m.from_user.id, m.from_user.username)
    await m.reply_text(
        f"🧠 *Today's Puzzle* ({puzzle['difficulty'].title()})\n\n"
        f"{puzzle['text']}\n\nSend your answer as a message!",
        parse_mode="markdown"
    )


@app.on_message(filters.command(["puzzle", "profile", "leaderboard"]))
async def answer_check(_, m):
    today = datetime.utcnow().date().isoformat()
    puzzle = await puzzles_col.find_one({"date": today})
    if not puzzle:
        return

    answer = puzzle["answer"].lower().strip()
    if m.text.lower().strip() == answer:
        user = await get_user(m.from_user.id, m.from_user.username)
        if user["last_solved"] == today:
            return await m.reply_text("✅ You already solved today's puzzle!")

        await give_xp(m.from_user.id, 10)
        await users_col.update_one({"_id": m.from_user.id}, {"$set": {"last_solved": today}})
        await users_col.update_one({"_id": m.from_user.id}, {"$inc": {"streak": 1}})

        return await m.reply_text("🎉 Correct! +10 XP awarded. Keep your streak alive!")
    else:
        await m.reply_text("❌ Not quite right. Try again!")


# ---------------- PROFILE & LEADERBOARD ----------------

@app.on_message(filters.command("bcprofile"))
async def prbcofile(_, m):
    user = await get_user(m.from_user.id, m.from_user.username)
    text = (
        f"👤 *Profile: {m.from_user.first_name}*\n"
        f"🏅 Rank: {user['rank']}\n"
        f"🧠 XP: {user['xp']}\n"
        f"🔥 Streak: {user['streak']} days"
    )
    await m.reply_text(text, parse_mode="markdown")


@app.on_message(filters.command("bcleaderboard"))
async def lebdaderboard(_, m):
    top = users_col.find().sort("xp", -1).limit(10)
    text = "🏆 *Top Thinkers Leaderboard:*\n\n"
    async for u in top:
        text += f"👤 {u.get('username', 'Anon')} — 🧠 {u['xp']} XP ({u['rank']})\n"
    await m.reply_text(text, parse_mode="markdown")


# ---------------- AUTO TASK ----------------

async def run_background_tasks():
    await asyncio.sleep(5)
    asyncio.create_task(post_daily_puzzle())


# ---------------- RUN BOT ----------------

#@app.on_message(filters.command("start"))
async def start(_, m):
    await get_user(m.from_user.id, m.from_user.username)
    await m.reply_text(
        "🧠 Welcome to *MindZone* — your daily brain challenge!\n\n"
        "Commands:\n"
        "/puzzle — get today’s puzzle\n"
        "/profile — view your stats\n"
        "/leaderboard — global leaderboard\n\n"
        "Stay sharp and think daily! 🧩",
        parse_mode="markdown"
    )
