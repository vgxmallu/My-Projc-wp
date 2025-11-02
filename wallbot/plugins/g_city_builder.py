import asyncio, random, os, datetime
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_URL
from wallbot import wbot as app
load_dotenv()



db = AsyncIOMotorClient(DB_URL).city_builder
players = db.players

# ---------- UTILITIES ----------

async def get_player(user_id, username):
    user = await players.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "gold": 100,
            "wood": 50,
            "stone": 50,
            "population": 10,
            "level": 1,
            "buildings": {"houses": 0, "factories": 0, "landmarks": 0},
            "last_collected": None
        }
        await players.insert_one(user)
    return user

async def update_player(user_id, data):
    await players.update_one({"user_id": user_id}, {"$set": data})

# ---------- COMMANDS ----------

#@app.on_message(filters.command("start"))
async def start(_, m):
    user = await get_player(m.from_user.id, m.from_user.username)
    await m.reply_text(
        f"🏙 Welcome to *Emoji Empire*, {m.from_user.first_name}!\n"
        "Build your city, manage resources, and dominate the world!\n\n"
        "Use /city to view your stats.\nUse /build to expand your empire.",
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("city"))
async def ccbity(_, m):
    user = await get_player(m.from_user.id, m.from_user.username)
    b = user["buildings"]
    await m.reply_text(
        f"🏙 *Your City — Emoji Empire*\n"
        f"🏠 Houses: {b['houses']}\n"
        f"🏭 Factories: {b['factories']}\n"
        f"🏰 Landmarks: {b['landmarks']}\n\n"
        f"👥 Population: {user['population']}\n"
        f"💰 Gold: {user['gold']}\n🌲 Wood: {user['wood']}\n🪨 Stone: {user['stone']}\n\n"
        f"🏅 Level: {user['level']}",
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("build"))
async def buicbld_menu(_, m):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Build House (10 wood)", callback_data="build_house")],
        [InlineKeyboardButton("🏭 Build Factory (20 stone, 15 wood)", callback_data="build_factory")],
        [InlineKeyboardButton("🏰 Build Landmark (100 gold, 50 stone)", callback_data="build_landmark")]
    ])
    await m.reply_text("🏗 Choose what to build:", reply_markup=kb)

@app.on_callback_query(filters.regex("^build_"))
async def build_callback(_, cq):
    user = await get_player(cq.from_user.id, cq.from_user.username)
    data = cq.data.split("_")[1]

    msg = ""
    b = user["buildings"]

    if data == "house":
        if user["wood"] < 10:
            msg = "❌ Not enough wood!"
        else:
            b["houses"] += 1
            user["wood"] -= 10
            user["population"] += 5
            msg = "🏠 Built a house! Population increased."
    elif data == "factory":
        if user["wood"] < 15 or user["stone"] < 20:
            msg = "❌ Not enough materials!"
        else:
            b["factories"] += 1
            user["wood"] -= 15
            user["stone"] -= 20
            user["gold"] += 10
            msg = "🏭 Factory built! Produces gold daily."
    elif data == "landmark":
        if user["gold"] < 100 or user["stone"] < 50:
            msg = "❌ Not enough resources!"
        else:
            b["landmarks"] += 1
            user["gold"] -= 100
            user["stone"] -= 50
            user["level"] += 1
            msg = "🏰 Landmark completed! Prestige increased."

    await update_player(user["user_id"], {"buildings": b, "wood": user["wood"], "stone": user["stone"], "gold": user["gold"], "population": user["population"], "level": user["level"]})
    await cq.answer(msg, show_alert=True)

@app.on_message(filters.command("tax"))
async def tax(_, m):
    user = await get_player(m.from_user.id, m.from_user.username)
    now = datetime.datetime.utcnow()
    last = user.get("last_collected")

    if last and (now - last).seconds < 3600:
        await m.reply_text("🕒 You can only collect taxes once per hour.")
        return

    income = user["population"] + (user["buildings"]["factories"] * 10)
    user["gold"] += income
    await update_player(user["user_id"], {"gold": user["gold"], "last_collected": now})
    await m.reply_text(f"💰 Collected {income} gold in taxes!")

@app.on_message(filters.command("explore_cb"))
async def cbexplore(_, m):
    user = await get_player(m.from_user.id, m.from_user.username)
    outcomes = [
        ("🌲 Found 15 wood!", {"wood": 15}),
        ("🪨 Mined 10 stone!", {"stone": 10}),
        ("💰 Found 20 gold!", {"gold": 20}),
        ("🔥 Oh no! Bandits stole 10 gold!", {"gold": -10}),
        ("🌊 Flood damaged houses!", {"houses": -1})
    ]
    msg, result = random.choice(outcomes)
    b = user["buildings"]
    for key, val in result.items():
        if key in user:
            user[key] = max(0, user[key] + val)
        elif key in b:
            b[key] = max(0, b[key] + val)
    await update_player(user["user_id"], {"gold": user["gold"], "wood": user["wood"], "stone": user["stone"], "buildings": b})
    await m.reply_text(msg)

@app.on_message(filters.command("leaderboardcb"))
async def leadcberboard(_, m):
    top = players.find().sort("gold", -1).limit(10)
    msg = "🏆 *Top 10 Richest Cities*\n\n"
    i = 1
    async for u in top:
        msg += f"{i}. @{u.get('username', 'Unknown')} — 💰 {u['gold']} gold\n"
        i += 1
    await m.reply_text(msg, parse_mode=enums.ParseMode.MARKDOWN)

# ---------- AUTO TASKS ----------

async def background_tasks():
    while True:
        await asyncio.sleep(3600)
        async for u in players.find():
            growth = u["buildings"]["houses"] * 2
            disasters = ["none", "fire", "flood", "earthquake", "bandits"]
            event = random.choice(disasters)
            msg = None
            if event != "none":
                msg = f"⚠️ Disaster struck {u.get('username', 'a city')}! ({event})"
                if event == "fire":
                    u["wood"] = max(0, u["wood"] - 10)
                elif event == "flood":
                    u["stone"] = max(0, u["stone"] - 10)
                elif event == "earthquake":
                    u["gold"] = max(0, u["gold"] - 20)
            u["population"] += growth
            await update_player(u["user_id"], u)
            if msg:
                try:
                    await app.send_message(u["user_id"], msg)
                except:
                    pass

#@app.on_message(filters.command("help"))
async def help_cmd(_, m):
    await m.reply_text(
        "🏙 *Emoji Empire — Commands*\n"
        "/city — Show your city\n"
        "/build — Construct buildings\n"
        "/tax — Collect taxes hourly\n"
        "/explore — Explore for resources\n"
        "/leaderboard — View top cities",
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ---------- START BOT ----------
@app.on_message(filters.command("init"))
async def inisbt_task(_, m):
    asyncio.create_task(background_tasks())
    await m.reply_text("♻️ Background growth system started.")

