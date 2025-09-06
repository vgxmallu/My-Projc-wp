"""
Leveling Bot (Pyrogram + Motor)
Features:
- XP on message with cooldown
- Levels, coins, virtual role rewards
- Rank card generation (Pillow)
- Leaderboard, profile, rank
- Gambling: coinflip, slots
- Boosts (temporary XP multiplier purchasable)
- Giveaways with inline join buttons and automated winner pick
- Admin commands for configuration
- Uses MongoDB only
"""

import os
import asyncio
import random
import math
from datetime import datetime, timedelta
from io import BytesIO

from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import motor.motor_asyncio
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from config import DB_URL
from wallbot import wbot as app

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "leveling_bot_db")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "784589736").split(",") if x.strip()]


mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

users_col = db["users"]            # user stats: coins, xp, level, last_xp, boosts, roles (virtual)
settings_col = db["settings"]      # server settings per chat
giveaways_col = db["giveaways"]    # giveaways with participants
config_col = db["config"]          # global config & xp rates

# Default config
DEFAULT_CONFIG = {
    "xp_min": 5,
    "xp_max": 15,
    "message_cooldown_seconds": 60,   # per-user message xp cooldown
    "level_formula": "50*level",      # base XP required (string to allow customizing)
    "global_multiplier": 1.0,
    "coins_per_xp": 0.5,              # coins rewarded per xp when leveling? (optional)
}

# ---------- UTIL FUNCTIONS ----------
def now_utc():
    return datetime.utcnow()

def level_required_xp(level: int, cfg: dict):
    # basic formula: 5 * level^2 + 50 * level  (or use string config)
    # Allow admin to inject simple expression using 'level' variable
    expr = cfg.get("level_formula", DEFAULT_CONFIG["level_formula"])
    try:
        # safe eval: allow only 'level' and math functions
        allowed = {"level": level, "math": math}
        xp = eval(expr, {"__builtins__": {}}, allowed)
        return int(xp)
    except Exception:
        # fallback
        return int(50 * level)

async def get_config():
    cfg = await config_col.find_one({"_id": "global"})
    if not cfg:
        cfg = DEFAULT_CONFIG.copy()
        cfg["_id"] = "global"
        await config_col.replace_one({"_id": "global"}, cfg, upsert=True)
    return cfg

async def ensure_user(user_id: int, username: str = None):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username or f"user{user_id}",
            "xp": 0,
            "level": 1,
            "coins": 500,
            "fame": 0,
            "last_xp_at": None,
            "boosts": [],      # list of {"mult":1.5, "expires": datetime}
            "roles": [],       # virtual roles rewarded at levels
            "created_at": now_utc(),
            "updated_at": now_utc()
        }
        await users_col.insert_one(user)
    return user

async def add_xp(user_id: int, amount: int):
    """Add xp taking into account boosts and check level up."""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return None
    cfg = await get_config()
    # compute active multiplier from boosts
    mult = 1.0
    now = now_utc()
    new_boosts = []
    for b in user.get("boosts", []):
        expires = b.get("expires")
        if isinstance(expires, datetime):
            exp_dt = expires
        else:
            exp_dt = expires  # in case stored as datetime already
        if exp_dt and exp_dt > now:
            mult = mult * b.get("mult", 1.0)
            new_boosts.append(b)
    # update boosts list (remove expired)
    user["boosts"] = new_boosts
    total_xp = int(amount * mult * cfg.get("global_multiplier",1.0))
    user["xp"] = user.get("xp",0) + total_xp
    user["updated_at"] = now
    user["last_xp_at"] = now
    leveled = False
    gained_levels = 0
    # level up loop
    while True:
        needed = level_required_xp(user.get("level",1), cfg)
        if user["xp"] >= needed:
            user["xp"] -= needed
            user["level"] = user.get("level",1) + 1
            gained_levels += 1
            leveled = True
            # reward coins for leveling (example)
            reward_coins = int(50 * user["level"])
            user["coins"] = user.get("coins",0) + reward_coins
        else:
            break
    await users_col.update_one({"user_id": user_id}, {"$set": user})
    return {"leveled": leveled, "levels_gained": gained_levels, "user": user, "xp_added": total_xp}

def can_gain_xp(user: dict, cfg: dict):
    last = user.get("last_xp_at")
    if not last:
        return True
    if isinstance(last, datetime):
        delta = (now_utc() - last).total_seconds()
    else:
        # stored as string? try to parse
        delta = 9999
    return delta >= cfg.get("message_cooldown_seconds", DEFAULT_CONFIG["message_cooldown_seconds"])

# ---------- RANK CARD ----------
def generate_rank_card(user: dict, global_rank: int = None):
    # Create a simple PNG with Pillow
    WIDTH, HEIGHT = 800, 240
    bg_color = (24, 24, 36)
    card = Image.new("RGB", (WIDTH, HEIGHT), color=bg_color)
    draw = ImageDraw.Draw(card)
    # fonts
    try:
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_med = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_large = ImageFont.load_default()
        font_med = ImageFont.load_default()
        font_small = ImageFont.load_default()
    # header
    name = user.get("username", f"User{user['user_id']}")
    level = user.get("level",1)
    xp = user.get("xp",0)
    draw.text((20, 20), f"{name}", font=font_large, fill=(255,255,255))
    draw.text((20, 70), f"Level: {level}", font=font_med, fill=(200,200,200))
    draw.text((20, 100), f"XP: {xp}", font=font_med, fill=(200,200,200))
    draw.text((20, 130), f"Coins: {user.get('coins',0)}", font=font_med, fill=(200,200,200))
    if global_rank:
        draw.text((WIDTH - 180, 20), f"Rank #{global_rank}", font=font_med, fill=(255,215,0))
    # XP progress bar (simulate target)
    # compute ratio assuming next lvl req
    # For display we compute next required XP using default config
    cfg_dummy = DEFAULT_CONFIG.copy()
    needed = level_required_xp(level, cfg_dummy)
    ratio = min(1.0, xp / max(1, needed))
    # draw bar
    bar_x, bar_y = 20, 170
    bar_w, bar_h = WIDTH - 40, 30
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(50,50,60))
    draw.rectangle([bar_x, bar_y, bar_x + int(bar_w*ratio), bar_y + bar_h], fill=(80,200,120))
    draw.text((bar_x, bar_y + bar_h + 6), f"{xp}/{needed} XP", font=font_small, fill=(220,220,220))
    # convert to bytes
    bio = BytesIO()
    bio.name = "rank_card.png"
    card.save(bio, "PNG")
    bio.seek(0)
    return bio

# ---------- MESSAGE XP HANDLER ----------
@app.on_message(filters.group | filters.private)
async def xp_on_message(_, m: Message):
    # Ignore bot messages
    if not m.from_user or m.from_user.is_bot:
        return
    # ensure user
    user = await ensure_user(m.from_user.id, m.from_user.username or m.from_user.first_name)
    cfg = await get_config()
    # check cooldown
    if not can_gain_xp(user, cfg):
        return
    # compute xp amount
    xp_amt = random.randint(cfg.get("xp_min",5), cfg.get("xp_max",15))
    res = await add_xp(user["user_id"], xp_amt)
    if res:
        # if leveled, announce in chat
        if res.get("leveled"):
            levels = res.get("levels_gained",1)
            await m.reply_text(f"🎉 Congrats {m.from_user.mention}, you leveled up +{levels}! Now level {res['user']['level']}. You got coins as reward.")
            # check for virtual role rewards for this new level
            # load settings for this chat to see role rewards
            s = await settings_col.find_one({"chat_id": m.chat.id})
            if s and s.get("role_rewards"):
                for rr in s.get("role_rewards", []):  # rr = {"level":int, "role_name":str}
                    if res['user']['level'] >= rr["level"] and rr["role_name"] not in res['user'].get("roles", []):
                        # assign virtual role
                        await users_col.update_one({"user_id": user["user_id"]}, {"$push": {"roles": rr["role_name"]}})
                        await m.reply_text(f"🏅 {m.from_user.mention} earned role reward **{rr['role_name']}** for reaching level {rr['level']}!")
        # update user last_xp_at handled in add_xp

# ---------- COMMANDS: profile, rank, leaderboard ----------
@app.on_message(filters.command("gprofile") & (filters.private | filters.group))
async def cmd_profghile(_, m: Message):
    target = m.from_user
    if len(m.command) > 1:
        # if mention or id provided
        try:
            # try parse id
            uid = int(m.command[1])
            target = await app.get_users(uid)
        except:
            try:
                # maybe username
                target = (await app.get_users(m.command[1]))
            except:
                target = m.from_user
    user = await ensure_user(target.id, target.username or target.first_name)
    # get global rank
    rank = await users_col.count_documents({"coins": {"$gt": user.get("coins",0)}}) + 1
    bio = generate_rank_card(user, global_rank=rank)
    await m.reply_photo(photo=bio, caption=f"👤 {user.get('username')} — Level {user.get('level')}, Coins: {user.get('coins',0)}")

@app.on_message(filters.command("rank") & (filters.group | filters.private))
async def cmd_rhank(_, m: Message):
    user = await ensure_user(m.from_user.id, m.from_user.username)
    # compute rank by coins (or level then xp)
    cursor = users_col.find().sort([("level",-1), ("xp",-1), ("coins",-1)])
    rank = 1
    async for doc in cursor:
        if doc["user_id"] == user["user_id"]:
            break
        rank += 1
    await m.reply_text(f"📈 {m.from_user.mention} — Level {user['level']} (Rank #{rank}), XP {user['xp']}, Coins {user['coins']}")

@app.on_message(filters.command("gleaderboard") & (filters.group | filters.private))
async def cmd_leaderboahhrd(_, m: Message):
    # show top 10 by level then xp
    cursor = users_col.find().sort([("level",-1), ("xp",-1), ("coins",-1)]).limit(10)
    text = "🏆 Leaderboard (Top 10):\n"
    i = 1
    async for u in cursor:
        text += f"{i}. {u.get('username','user')} — Lvl {u.get('level',1)} XP {u.get('xp',0)} Coins {u.get('coins',0)}\n"
        i += 1
    await m.reply_text(text)

# ---------- GAMBLING ----------
@app.on_message(filters.command("gcoinflip") & (filters.group | filters.private))
async def cmd_coinflfip(_, m: Message):
    # /coinflip heads 50
    if len(m.command) < 3:
        return await m.reply_text("Usage: /gcoinflip [heads/tails] [amount]")
    pick = m.command[1].lower()
    try:
        amount = int(m.command[2])
    except:
        return await m.reply_text("Invalid amount")
    user = await ensure_user(m.from_user.id, m.from_user.username)
    if amount <= 0 or user.get("coins",0) < amount:
        return await m.reply_text("You do not have enough coins.")
    outcome = random.choice(["heads","tails"])
    if pick == outcome:
        prize = amount * 2
        await users_col.update_one({"user_id": user["user_id"]}, {"$inc": {"coins": prize}})
        await m.reply_text(f"🎉 It's {outcome}! You won {prize} coins.")
    else:
        await users_col.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -amount}})
        await m.reply_text(f"😢 It's {outcome}. You lost {amount} coins.")

@app.on_message(filters.command("gslots") & (filters.group | filters.private))
async def cmd_slots(_, m: Message):
    # /slots 50
    if len(m.command) < 2:
        return await m.reply_text("Usage: /gslots [amount]")
    try:
        amount = int(m.command[1])
    except:
        return await m.reply_text("Invalid amount.")
    user = await ensure_user(m.from_user.id, m.from_user.username)
    if amount <= 0 or user.get("coins",0) < amount:
        return await m.reply_text("You do not have enough coins.")
    # spin
    symbols = ["🍒","🍋","🍇","🍉","🔔","⭐"]
    spin = [random.choice(symbols) for _ in range(3)]
    text = " | ".join(spin)
    # payout rules
    if spin[0] == spin[1] == spin[2]:
        prize = amount * 10
        await users_col.update_one({"user_id": user['user_id']}, {"$inc": {"coins": prize}})
        await m.reply_text(f"{text}\nJackpot! You win {prize} coins!")
    elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
        prize = int(amount * 2.5)
        await users_col.update_one({"user_id": user['user_id']}, {"$inc": {"coins": prize}})
        await m.reply_text(f"{text}\nNice! You win {prize} coins!")
    else:
        await users_col.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -amount}})
        await m.reply_text(f"{text}\nYou lost {amount} coins. Better luck next time!")

# ---------- BOOSTS ----------
@app.on_message(filters.command("gboost") & filters.group)
async def cmd_bohost(_, m: Message):
    # /boost buy <mult> <minutes>
    if len(m.command) < 2:
        return await m.reply_text("Usage: /gboost buy [multiplier] [minutes] OR /boost status")
    action = m.command[1].lower()
    user = await ensure_user(m.from_user.id, m.from_user.username)
    if action == "status":
        now = now_utc()
        active = [b for b in user.get("boosts",[]) if b.get("expires") and b["expires"] > now]
        if not active:
            return await m.reply_text("No active boosts.")
        txt = "Active boosts:\n"
        for b in active:
            txt += f"- x{b.get('mult')} until {b.get('expires')}\n"
        return await m.reply_text(txt)
    if action == "buy":
        if len(m.command) < 4:
            return await m.reply_text("Usage: /gboost buy [mult] [minutes]")
        try:
            mult = float(m.command[2])
            mins = int(m.command[3])
        except:
            return await m.reply_text("Invalid arguments.")
        # price formula: 100 coins per 0.1 multiplier per 10 minutes
        price = int(100 * (mult / 0.1) * (mins / 10))
        if user.get("coins",0) < price:
            return await m.reply_text(f"You need {price} coins to buy that boost.")
        # deduct and add boost
        await users_col.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -price}})
        expires = now_utc() + timedelta(minutes=mins)
        await users_col.update_one({"user_id": user['user_id']}, {"$push": {"boosts": {"mult": mult, "expires": expires}}})
        await m.reply_text(f"✅ Boost x{mult} active for {mins} minutes (cost {price} coins).")

# ---------- GIVEAWAYS ----------
# Admin creates giveaway: /giveaway create <duration_minutes> <prize>
# Users join via inline button; after duration pick random winner and award (coins or custom text).
@app.on_message(filters.command("giveaway") & (filters.group | filters.private))
async def cmd_give°away(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /giveaway create [minutes] [prize] (admin) OR /giveaway list")
    sub = m.command[1].lower()
    if sub == "create":
        if m.from_user.id not in ADMIN_IDS:
            return await m.reply_text("Only admins can create giveaways.")
        if len(m.command) < 4:
            return await m.reply_text("Usage: /giveaway create [minutes] [prize]")
        try:
            minutes = int(m.command[2])
        except:
            return await m.reply_text("Invalid minutes.")
        prize = " ".join(m.command[3:])
        gid = str(random.getrandbits(64))
        doc = {
            "giveaway_id": gid,
            "chat_id": m.chat.id,
            "creator_id": m.from_user.id,
            "prize": prize,
            "ends_at": now_utc() + timedelta(minutes=minutes),
            "participants": [],
            "message_id": None
        }
        res = await giveaways_col.insert_one(doc)
        join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎉 Join", callback_data=f"gw_join:{gid}")]])
        sent = await m.reply_text(f"🎁 Giveaway started! Prize: {prize}\nEnds in {minutes} minutes.\nGiveaway ID: {gid}", reply_markup=join_btn)
        # store message id to update later
        await giveaways_col.update_one({"giveaway_id": gid}, {"$set": {"message_id": sent.message_id}})
        # schedule end
        asyncio.create_task(schedule_giveaway_end(gid, minutes))
    elif sub == "list":
        # list active giveaways
        text = "Active giveaways:\n"
        async for g in giveaways_col.find({"ends_at": {"$gt": now_utc()}}):
            text += f"- ID {g['giveaway_id']} Prize: {g['prize']} Ends: {g['ends_at']}\n"
        await m.reply_text(text or "No active giveaways.")

@app.on_callback_query(filters.regex(r"^gw_join:"))
async def gw_join_cb(_, cq: CallbackQuery):
    gid = cq.data.split(":",1)[1]
    g = await giveaways_col.find_one({"giveaway_id": gid})
    if not g:
        return await cq.answer("Giveaway not found.", show_alert=True)
    uid = cq.from_user.id
    if uid in g.get("participants", []):
        return await cq.answer("You already joined the giveaway.", show_alert=True)
    g["participants"].append(uid)
    await giveaways_col.update_one({"giveaway_id": gid}, {"$set": {"participants": g["participants"]}})
    await cq.answer("🎉 You joined the giveaway!")

async def schedule_giveaway_end(gid: str, minutes: int):
    await asyncio.sleep(minutes * 60)
    g = await giveaways_col.find_one({"giveaway_id": gid})
    if not g:
        return
    participants = g.get("participants", [])
    chat_id = g.get("chat_id")
    if not participants:
        await app.send_message(chat_id, f"❌ Giveaway {gid} ended. No participants.")
    else:
        winner = random.choice(participants)
        # award prize if prize is "coins:1000" format else announce
        prize = g.get("prize")
        if prize.startswith("coins:"):
            try:
                amt = int(prize.split(":",1)[1])
                await users_col.update_one({"user_id": winner}, {"$inc": {"coins": amt}}, upsert=True)
                await app.send_message(chat_id, f"🎉 Giveaway ended! Winner: [user](tg://user?id={winner}) — awarded {amt} coins.")
            except:
                await app.send_message(chat_id, f"🎉 Giveaway ended! Winner: [user](tg://user?id={winner}) — Prize: {prize}")
        else:
            await app.send_message(chat_id, f"🎉 Giveaway ended! Winner: [user](tg://user?id={winner}) — Prize: {prize}")
    # remove giveaway
    await giveaways_col.delete_one({"giveaway_id": gid})

# ---------- ADMIN / SETTINGS ----------
@app.on_message(filters.command("setxp") & (filters.private | filters.group))
async def cmd_setxp(_, m: Message):
    # admin-only command to set xp min/max or cooldown or formula
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply_text("Admin only.")
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setxp <key> <value>. Keys: xp_min xp_max cooldown multiplier formula")
    key = m.command[1].lower()
    value = " ".join(m.command[2:])
    cfg = await get_config()
    if key in ("xp_min","xp_max"):
        try:
            cfg[key] = int(value)
        except:
            return await m.reply_text("Value must be integer.")
    elif key in ("cooldown","message_cooldown_seconds"):
        try:
            cfg["message_cooldown_seconds"] = int(value)
        except:
            return await m.reply_text("Invalid int")
    elif key == "multiplier":
        try:
            cfg["global_multiplier"] = float(value)
        except:
            return await m.reply_text("Invalid float")
    elif key == "formula":
        cfg["level_formula"] = value
    else:
        return await m.reply_text("Unknown key.")
    await config_col.replace_one({"_id":"global"}, cfg, upsert=True)
    await m.reply_text("Config updated.")

@app.on_message(filters.command("reward_add") & filters.group)
async def cmd_rheward_add(_, m: Message):
    # /reward_add <level> <role_name>   (virtual role reward)
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply_text("Admin only.")
    if len(m.command) < 3:
        return await m.reply_text("Usage: /reward_add [level] [role_name]")
    try:
        level = int(m.command[1])
    except:
        return await m.reply_text("Invalid level.")
    role_name = " ".join(m.command[2:])
    s = await settings_col.find_one({"chat_id": m.chat.id}) or {"chat_id": m.chat.id}
    rr = s.get("role_rewards", [])
    rr.append({"level": level, "role_name": role_name})
    s["role_rewards"] = rr
    await settings_col.replace_one({"chat_id": m.chat.id}, s, upsert=True)
    await m.reply_text(f"Role reward set: Level {level} -> {role_name}. This is a virtual role stored in DB and will be announced to user on level up.")

@app.on_message(filters.command("grewards") & (filters.group | filters.private))
async def cmd_rhewards(_, m: Message):
    s = await settings_col.find_one({"chat_id": m.chat.id})
    if not s or not s.get("role_rewards"):
        return await m.reply_text("No role rewards configured for this chat.")
    text = "Role rewards:\n"
    for rr in s["role_rewards"]:
        text += f"- Level {rr['level']}: {rr['role_name']}\n"
    await m.reply_text(text)

# ---------- MISC ----------
@app.on_message(filters.command("givecoins") & (filters.group | filters.private))
async def cmd_givecoins(_, m: Message):
    # admin command: /givecoins <userid> <amount>
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply_text("Admin only.")
    if len(m.command) < 3:
        return await m.reply_text("Usage: /givecoins [user_id] [amount]")
    try:
        uid = int(m.command[1])
        amt = int(m.command[2])
    except:
        return await m.reply_text("Invalid args.")
    await users_col.update_one({"user_id": uid}, {"$inc": {"coins": amt}}, upsert=True)
    await m.reply_text("Done.")

