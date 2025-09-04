import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from pymongo import MongoClient, ReturnDocument
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import DB_URL
from wallbot import wbot as app
# ------------------------ CONFIG ------------------------
DB_NAME = "rpg_bot"
START_COINS = 200
COOLDOWN_SECONDS = {
    "chop": 25,
    "fish": 25,
    "pickup": 25,
    "mine": 40,
    "daily": 24 * 60 * 60,
    "dungeon": 60,
    "duel": 60,
}

# ------------------------ APP/DB ------------------------
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users = db["users"]
guilds = db["guilds"]

# --------------------- GAME DATA ------------------------
SHOP: Dict[str, Dict] = {
    # name: {price, sell, type, power?}
    "wood": {"price": 15, "sell": 7, "type": "mat"},
    "fish": {"price": 18, "sell": 9, "type": "mat"},
    "stone": {"price": 20, "sell": 10, "type": "mat"},
    "ore": {"price": 35, "sell": 17, "type": "mat"},

    "sword1": {"price": 120, "sell": 60, "type": "weapon", "atk": 3},
    "sword2": {"price": 450, "sell": 225, "type": "weapon", "atk": 7},
    "armor1": {"price": 150, "sell": 75, "type": "armor", "def": 2},
    "armor2": {"price": 520, "sell": 260, "type": "armor", "def": 5},

    "bait": {"price": 30, "sell": 15, "type": "tool"},
    "pickaxe": {"price": 200, "sell": 100, "type": "tool"},
}

RECIPES = {
    # item: {requires, result_item}
    "sword1": {"requires": {"wood": 10, "ore": 2}, "makes": "sword1"},
    "sword2": {"requires": {"wood": 15, "ore": 6, "stone": 6}, "makes": "sword2"},
    "armor1": {"requires": {"wood": 6, "stone": 8}, "makes": "armor1"},
    "armor2": {"requires": {"stone": 15, "ore": 8}, "makes": "armor2"},
}

MEMES = [
    "When you fail a 95% craft: *it was 5% skill issue* 😭",
    "Me: I’ll save coins. Also me: *sees shop* — TAKE MY MONEY 💸",
    "Dungeons be like: You vs the guy she told you not to worry about 🗡️🐉",
    "If mining gave XP IRL I’d be level 999 from procrastination ⛏️",
]

RANKS = [
    (0, "Peasant"),
    (500, "Squire"),
    (1500, "Knight"),
    (3500, "Warlord"),
    (8000, "Mythic"),
]

# --------------------- HELPERS --------------------------
def now() -> datetime:
    return datetime.utcnow()

def rank_from_xp(xp: int) -> str:
    best = "Peasant"
    for req, name in RANKS:
        if xp >= req:
            best = name
    return best

def ensure_user(uid: int, name: str):
    return users.find_one_and_update(
        {"_id": uid},
        {
            "$setOnInsert": {
                "_id": uid,
                "name": name,
                "coins": START_COINS,
                "xp": 0,
                "inv": {},          # inventory dict
                "equip": {"weapon": None, "armor": None},
                "wins": 0,
                "losses": 0,
                "cooldowns": {},    # action: iso timestamp
                "pets": [],
                "guild": None,
                "stats": {"dungeons": 0, "bosses": 0, "gamble_net": 0},
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

def can_do(uid: int, action: str) -> (bool, int):
    u = users.find_one({"_id": uid}) or {}
    cd = u.get("cooldowns", {})
    if action not in cd:
        return True, 0
    last = datetime.fromisoformat(cd[action])
    diff = (now() - last).total_seconds()
    need = COOLDOWN_SECONDS.get(action, 0)
    if diff >= need:
        return True, 0
    return False, int(need - diff)

def set_cd(uid: int, action: str):
    users.update_one({"_id": uid}, {"$set": {f"cooldowns.{action}": now().isoformat()}})

def add_item(uid: int, item: str, qty: int = 1):
    users.update_one({"_id": uid}, {"$inc": {f"inv.{item}": qty}})

def rem_item(uid: int, item: str, qty: int = 1) -> bool:
    u = users.find_one({"_id": uid}) or {}
    have = (u.get("inv", {}) or {}).get(item, 0)
    if have < qty:
        return False
    users.update_one({"_id": uid}, {"$inc": {f"inv.{item}": -qty}})
    # cleanup zeroes
    users.update_one({"_id": uid}, {"$unset": {f"inv.{item}": ""}}, upsert=False)
    return True

def add_coins(uid: int, amount: int):
    users.update_one({"_id": uid}, {"$inc": {"coins": amount}})

def add_xp(uid: int, amount: int):
    users.update_one({"_id": uid}, {"$inc": {"xp": amount}})

def inv_text(inv: Dict[str, int]) -> str:
    if not inv:
        return "— empty —"
    return ", ".join(f"{k}×{v}" for k, v in inv.items())

def equip_power(u) -> (int, int):
    atk = 1
    df = 0
    weapon = u.get("equip", {}).get("weapon")
    armor = u.get("equip", {}).get("armor")
    if weapon and weapon in SHOP and "atk" in SHOP[weapon]:
        atk += SHOP[weapon]["atk"]
    if armor and armor in SHOP and "def" in SHOP[armor]:
        df += SHOP[armor]["def"]
    return atk, df

def parse_amount(arg: str, default=1) -> int:
    try:
        v = int(arg)
        return max(1, v)
    except:
        return default

# --------------------- GENERIC --------------------------
@app.on_message(filters.command("strpg"))
async def start_djcmd(_, m: Message):
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    await m.reply(
        "🛡️ **Welcome to MiniRPG!**\n"
        "Collect stuff, craft gear, run dungeons, duel, gamble & more.\n\n"
        "**Basics**\n"
        "• /rpgprofile /me — your stats\n"
        "• /rpgshop — buyable items\n"
        "• /rpginventory — your bag\n"
        "• /recipes_rpg — crafting list\n\n"
        "**Work**: /chop_rpg, /fish_rpg, /pickup_rpg, /mine_rpg\n"
        "**Economy**: /buy_rpg, /sell_rpg, /trade_rpg\n"
        "**Crafting**: /craft_rpg <item>\n"
        "**PvP**: /duel_rpg @user <bet>\n"
        "**Dungeon**: /dungeon\n"
        "**Gamble**: /coinflip, /dice_rpg, /blackjack, /slots_rpg, /wheel_rpg, /multidice_rpg\n"
        "**Other**: /daily_rpg, /enchant_rpg, /pet_rph, /guild_rpg, /meme_rpg, /rpgleaderboard"
    )

@app.on_message(filters.command(["rpgprofile", "me"]))
async def profilerpg_cmd(_, m: Message):
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    atk, df = equip_power(u)
    r = rank_from_xp(u.get("xp", 0))
    await m.reply(
        f"👤 **{m.from_user.first_name}**\n"
        f"💰 Coins: `{u.get('coins',0)}`\n"
        f"⭐ XP: `{u.get('xp',0)}` • Rank: **{r}**\n"
        f"🎒 Inventory: {inv_text(u.get('inv', {}))}\n"
        f"⚔️ Weapon: `{u.get('equip',{}).get('weapon')}` • 🛡️ Armor: `{u.get('equip',{}).get('armor')}`\n"
        f"🗡️ ATK: `{atk}` • 🧱 DEF: `{df}`\n"
        f"🏆 W/L: `{u.get('wins',0)}`/`{u.get('losses',0)}`\n"
        f"🦴 Pets: {', '.join(u.get('pets', [])) or '—'}\n"
        f"👥 Guild: `{u.get('guild') or '—'}`\n"
        f"📊 Dungeons: `{u.get('stats',{}).get('dungeons',0)}` • Bosses: `{u.get('stats',{}).get('bosses',0)}`"
    )

@app.on_message(filters.command("rpginventory"))
async def inv_dcmd(_, m: Message):
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    await m.reply(f"🎒 **Inventory**\n{inv_text(u.get('inv', {}))}")

# --------------------- SHOP / ECONOMY -------------------rpg
@app.on_message(filters.command("rpgshop"))
async def shoprpg_cmd(_, m: Message):
    lines = ["🛒 **Shop** (buy/sell with /buy /sell)"]
    for item, d in SHOP.items():
        desc = []
        if "atk" in d: desc.append(f"ATK+{d['atk']}")
        if "def" in d: desc.append(f"DEF+{d['def']}")
        lines.append(f"• `{item}` — buy {d['price']}c / sell {d['sell']}c {'• ' + ', '.join(desc) if desc else ''}")
    await m.reply("\n".join(lines))

@app.on_message(filters.command("buy_rpg"))
async def buy_rpgcmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /buy [item] [qty]")
    item = args[0].lower()
    qty = parse_amount(args[1], 1) if len(args) > 1 else 1
    if item not in SHOP:
        return await m.reply("Item not in shop.")
    cost = SHOP[item]["price"] * qty
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    if u["coins"] < cost:
        return await m.reply("Not enough coins.")
    add_coins(u["_id"], -cost)
    add_item(u["_id"], item, qty)
    await m.reply(f"✅ Bought `{qty}× {item}` for `{cost}` coins.")

@app.on_message(filters.command("sell_rpg"))
async def sellss_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /sell [item] [qty]")
    item = args[0].lower()
    qty = parse_amount(args[1], 1) if len(args) > 1 else 1
    if item not in SHOP:
        return await m.reply("You can only sell shop items.")
    if not rem_item(m.from_user.id, item, qty):
        return await m.reply("You don't have enough to sell.")
    gain = SHOP[item]["sell"] * qty
    add_coins(m.from_user.id, gain)
    await m.reply(f"💰 Sold `{qty}× {item}` for `{gain}` coins.")

@app.on_message(filters.command("trade_rpg"))
async def traded_cmd(_, m: Message):
    # Simple flavor: trade mats 1:1 by value bracket
    args = m.command[1:]
    if len(args) < 2:
        return await m.reply("Usage: /trade [give_item] [want_item]")
    give, want = args[0].lower(), args[1].lower()
    if give not in SHOP or want not in SHOP:
        return await m.reply("Only shop items can be traded.")
    # require equal or close value
    if abs(SHOP[give]["sell"] - SHOP[want]["sell"]) > 5:
        return await m.reply("These items are not similar value enough to trade 1:1.")
    if not rem_item(m.from_user.id, give, 1):
        return await m.reply("You don't have the item to trade.")
    add_item(m.from_user.id, want, 1)
    await m.reply(f"🔁 Traded `1× {give}` → `1× {want}`")

# --------------------- WORK / GATHER --------------------
async def do_work(m: Message, action: str, loot_table: List[str], qty_range=(1, 3), xp_gain=(5, 10), coin_range=(1, 6)):
    ok, wait = can_do(m.from_user.id, action)
    if not ok:
        return await m.reply(f"⏳ Cooldown `{wait}s` remaining.")
    set_cd(m.from_user.id, action)
    qty = random.randint(*qty_range)
    got = random.choice(loot_table)
    add_item(m.from_user.id, got, qty)
    add_xp(m.from_user.id, random.randint(*xp_gain))
    add_coins(m.from_user.id, random.randint(*coin_range))
    await m.reply(f"✅ You {action} and found `{qty}× {got}`! +coins, +xp.")

@app.on_message(filters.command("chop_rpg"))
async def chopd_cmd(_, m: Message):
    await do_work(m, "chop", ["wood"])

@app.on_message(filters.command("fish_rpg"))
async def fisdh_cmd(_, m: Message):
    # bait slightly improves qty
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    bonus = 1 if u.get("inv", {}).get("bait", 0) > 0 else 0
    await do_work(m, "fish", ["fish"], (1+bonus, 3+bonus))

@app.on_message(filters.command("pickup_rpg"))
async def pickupr_cmd(_, m: Message):
    await do_work(m, "pickup", ["wood", "stone"])

@app.on_message(filters.command("mine_rpg"))
async def minerr_cmd(_, m: Message):
    # pickaxe boosts ore chance
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    table = ["stone", "ore", "stone", "stone"] + (["ore"] * 2 if u.get("inv", {}).get("pickaxe", 0) > 0 else [])
    await do_work(m, "mine", table, (1, 2), (8, 14), (2, 7))

# --------------------- CRAFTING -------------------------
@app.on_message(filters.command("recipes_rpg"))
async def recipedsr_cmd(_, m: Message):
    lines = ["📜 **Recipes**"]
    for k, r in RECIPES.items():
        reqs = ", ".join(f"{i}×{q}" for i, q in r["requires"].items())
        lines.append(f"• `{k}` = {reqs}")
    await m.reply("\n".join(lines))

@app.on_message(filters.command("craft_rpg"))
async def craftrr_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /craft [item]")
    item = args[0].lower()
    if item not in RECIPES:
        return await m.reply("Unknown recipe.")
    req = RECIPES[item]["requires"]
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    have = u.get("inv", {})
    for it, q in req.items():
        if have.get(it, 0) < q:
            return await m.reply("You don't have required materials.")
    for it, q in req.items():
        rem_item(m.from_user.id, it, q)
    add_item(m.from_user.id, RECIPES[item]["makes"], 1)
    add_xp(m.from_user.id, 30)
    await m.reply(f"🛠️ Crafted `1× {item}`! (+30 XP)")

# --------------------- EQUIP / ENCHANT ------------------
@app.on_message(filters.command("equip_rpg"))
async def equddip_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /equip [item]")
    item = args[0].lower()
    if item not in SHOP:
        return await m.reply("Only shop/crafted gear can be equipped.")
    t = SHOP[item]["type"]
    if t not in ("weapon", "armor"):
        return await m.reply("You can only equip weapons/armors.")
    # require to own
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    if u.get("inv", {}).get(item, 0) <= 0:
        return await m.reply("You don't own this item.")
    slot = "weapon" if t == "weapon" else "armor"
    users.update_one({"_id": u["_id"]}, {"$set": {f"equip.{slot}": item}})
    await m.reply(f"✅ Equipped `{item}` in `{slot}` slot.")

@app.on_message(filters.command("enchant_rpg"))
async def enchadnt_cmd(_, m: Message):
    # very simple: pay 100 coins → +1 atk if weapon equipped
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    if u["coins"] < 100:
        return await m.reply("Need 100 coins to enchant.")
    weapon = u.get("equip", {}).get("weapon")
    if not weapon or weapon not in SHOP or "atk" not in SHOP[weapon]:
        return await m.reply("Equip a weapon first.")
    # “virtual” enchant: add phantom +1 atk tracked as pseudo item
    add_coins(u["_id"], -100)
    # store enchant stacks in stats
    users.update_one({"_id": u["_id"]}, {"$inc": {f"stats.enchant_{weapon}": 1}})
    await m.reply("✨ Enchant successful! (effect included in duels & dungeons)")

def weapon_enchant_bonus(u):
    weapon = u.get("equip", {}).get("weapon")
    if not weapon:
        return 0
    return (u.get("stats", {}) or {}).get(f"enchant_{weapon}", 0)

# --------------------- DAILY / PET / TIME ----------------
@app.on_message(filters.command("daily_rpg"))
async def daiddly_cmd(_, m: Message):
    ok, wait = can_do(m.from_user.id, "daily")
    if not ok:
        hrs = max(1, wait // 3600)
        return await m.reply(f"⏳ Daily ready in ~{hrs}h.")
    set_cd(m.from_user.id, "daily")
    reward = random.randint(120, 220)
    add_coins(m.from_user.id, reward)
    add_xp(m.from_user.id, 50)
    await m.reply(f"🎁 Daily claimed: `{reward}` coins + `50` XP!")

PETS = ["slime", "wolf", "eagle", "fox", "dragonling"]

@app.on_message(filters.command("pet_rpg"))
async def petd_cmd(_, m: Message):
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    if len(u.get("pets", [])) >= 3:
        return await m.reply("You already have 3 pets.")
    price = 150
    if u["coins"] < price:
        return await m.reply("Need 150 coins to adopt a pet.")
    pet = random.choice(PETS)
    add_coins(u["_id"], -price)
    users.update_one({"_id": u["_id"]}, {"$push": {"pets": pet}})
    await m.reply(f"🦴 You adopted a `{pet}`!")

@app.on_message(filters.command("timetravel"))
async def timetravedl_cmd(_, m: Message):
    # Reduces all cooldown timestamps by 10 minutes (cost coins)
    cost = 120
    u = ensure_user(m.from_user.id, m.from_user.first_name)
    if u["coins"] < cost:
        return await m.reply("Need 120 coins to bend time.")
    add_coins(u["_id"], -cost)
    cds = u.get("cooldowns", {})
    reduced = {}
    for k, iso in cds.items():
        t = datetime.fromisoformat(iso) - timedelta(minutes=10)
        reduced[k] = t.isoformat()
    users.update_one({"_id": u["_id"]}, {"$set": {"cooldowns": reduced}})
    await m.reply("⏱️ Time shifted! Your cooldowns were reduced by 10 minutes.")

# --------------------- GUILDS (simple) -------------------
@app.on_message(filters.command("guild_rpg"))
async def guildd_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Guild commands: /guild create [name] | /guild join [name] | /guild leave")
    sub = args[0].lower()
    u = ensure_user(m.from_user.id, m.from_user.first_name)

    if sub == "create":
        if u.get("guild"):
            return await m.reply("Leave current guild first.")
        if len(args) < 2:
            return await m.reply("Usage: /guild create [name]")
        name = " ".join(args[1:])[:24]
        if guilds.find_one({"_id": name}):
            return await m.reply("Guild already exists.")
        guilds.insert_one({"_id": name, "owner": u["_id"], "members": [u["_id"]], "bank": 0})
        users.update_one({"_id": u["_id"]}, {"$set": {"guild": name}})
        await m.reply(f"🏰 Created guild **{name}**!")

    elif sub == "join":
        if len(args) < 2:
            return await m.reply("Usage: /guild join [name]")
        name = " ".join(args[1:])
        g = guilds.find_one({"_id": name})
        if not g:
            return await m.reply("No such guild.")
        if u.get("guild") == name:
            return await m.reply("You are already in this guild.")
        if u.get("guild"):
            return await m.reply("Leave current guild first.")
        guilds.update_one({"_id": name}, {"$addToSet": {"members": u["_id"]}})
        users.update_one({"_id": u["_id"]}, {"$set": {"guild": name}})
        await m.reply(f"🏰 Joined guild **{name}**.")

    elif sub == "leave":
        if not u.get("guild"):
            return await m.reply("You are not in a guild.")
        name = u["guild"]
        guilds.update_one({"_id": name}, {"$pull": {"members": u["_id"]}})
        users.update_one({"_id": u["_id"]}, {"$unset": {"guild": ""}})
        await m.reply(f"🏰 Left guild **{name}**.")

# --------------------- PVP DUEL --------------------------
@app.on_message(filters.command("duel_rpg"))
async def duel_cmd(_, m: Message):
    if not m.reply_to_message or len(m.command) < 2:
        return await m.reply("Reply to an opponent: /duel [bet]")
    bet = parse_amount(m.command[1], 1)
    me = ensure_user(m.from_user.id, m.from_user.first_name)
    opp = ensure_user(m.reply_to_message.from_user.id, m.reply_to_message.from_user.first_name)
    if me["coins"] < bet or opp["coins"] < bet:
        return await m.reply("Both players need enough coins.")

    ok, wait = can_do(m.from_user.id, "duel")
    if not ok:
        return await m.reply(f"⏳ Cooldown `{wait}s` remaining.")
    set_cd(m.from_user.id, "duel")

    # simple fight: 3 rounds, random + gear atk/def bonuses
    me_atk, me_def = equip_power(me)
    opp_atk, opp_def = equip_power(opp)
    me_atk += weapon_enchant_bonus(me)
    opp_atk += weapon_enchant_bonus(opp)

    me_hp = 20 + me_def * 2
    opp_hp = 20 + opp_def * 2
    log = ["⚔️ **Duel begins!**"]
    for r in range(1, 6):
        d1 = random.randint(1, 6) + me_atk
        d2 = random.randint(1, 6) + opp_atk
        opp_hp -= max(1, d1 - opp_def)
        me_hp -= max(1, d2 - me_def)
        log.append(f"Round {r}: You hit `{d1}` / Opp hits `{d2}` → HP You `{me_hp}` / Opp `{opp_hp}`")
        if me_hp <= 0 or opp_hp <= 0:
            break

    if me_hp > opp_hp:
        add_coins(me["_id"], bet)
        add_coins(opp["_id"], -bet)
        users.update_one({"_id": me["_id"]}, {"$inc": {"wins": 1}})
        users.update_one({"_id": opp["_id"]}, {"$inc": {"losses": 1}})
        add_xp(me["_id"], 40)
        res = f"🏆 You win `{bet}` coins!"
    elif opp_hp > me_hp:
        add_coins(me["_id"], -bet)
        add_coins(opp["_id"], bet)
        users.update_one({"_id": opp["_id"]}, {"$inc": {"wins": 1}})
        users.update_one({"_id": me["_id"]}, {"$inc": {"losses": 1}})
        add_xp(opp["_id"], 40)
        res = f"💀 You lost `{bet}` coins!"
    else:
        res = "🤝 Draw! No coins exchanged."

    await m.reply("\n".join(log + [res]))

# --------------------- DUNGEON ---------------------------
@app.on_message(filters.command("dungeon"))
async def dungeon_cmd(_, m: Message):
    ok, wait = can_do(m.from_user.id, "dungeon")
    if not ok:
        return await m.reply(f"⏳ Dungeon cooldown `{wait}s`.")
    set_cd(m.from_user.id, "dungeon")

    u = ensure_user(m.from_user.id, m.from_user.first_name)
    atk, df = equip_power(u)
    atk += weapon_enchant_bonus(u)
    hp = 30 + df * 3
    floors = random.randint(2, 4)
    loot_total = {}
    coins_gain = 0
    log = [f"🕳️ **Dungeon** — {floors} floors"]

    for fl in range(1, floors + 1):
        enemy_hp = random.randint(16, 26)
        enemy_atk = random.randint(2, 5)
        log.append(f"Floor {fl}: Enemy HP `{enemy_hp}` ATK `{enemy_atk}`")

        while enemy_hp > 0 and hp > 0:
            enemy_hp -= max(1, random.randint(1, 6) + atk - 1)
            if enemy_hp <= 0: break
            hp -= max(1, random.randint(1, 6) + enemy_atk - df)

        if hp <= 0:
            log.append("❌ You were defeated...")
            users.update_one({"_id": u["_id"]}, {"$inc": {"losses": 1}})
            return await m.reply("\n".join(log))

        # loot
        drop = random.choice(["wood", "stone", "ore", "fish"])
        qty = random.randint(1, 3)
        loot_total[drop] = loot_total.get(drop, 0) + qty
        coins_gain += random.randint(10, 25)
        log.append(f"✅ Cleared floor {fl}! Loot `{qty}× {drop}`; +coins")

    for k, v in loot_total.items():
        add_item(u["_id"], k, v)
    add_coins(u["_id"], coins_gain)
    add_xp(u["_id"], 80 + floors * 20)
    users.update_one({"_id": u["_id"]}, {"$inc": {"stats.dungeons": 1}})
    await m.reply("\n".join(log + [f"🏅 Victory! Coins `+{coins_gain}` • Loot: {inv_text(loot_total)} • +XP"]))

# --------------------- GAMBLING --------------------------
def pay_bet(uid: int, bet: int) -> bool:
    u = users.find_one({"_id": uid})
    if not u or u["coins"] < bet or bet <= 0:
        return False
    add_coins(uid, -bet)
    users.update_one({"_id": uid}, {"$inc": {"stats.gamble_net": -bet}})
    return True

def win_bet(uid: int, amount: int):
    add_coins(uid, amount)
    users.update_one({"_id": uid}, {"$inc": {"stats.gamble_net": amount}})

@app.on_message(filters.command("coinflip"))
async def coinflipdd_cmd(_, m: Message):
    args = m.command[1:]
    if len(args) < 2:
        return await m.reply("Usage: /coinflip [bet] [heads|tails]")
    bet = parse_amount(args[0], 1)
    pick = args[1].lower()
    if pick not in ("heads", "tails"):
        return await m.reply("Choose heads or tails.")
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    res = random.choice(["heads", "tails"])
    if res == pick:
        win_bet(m.from_user.id, bet * 2)
        return await m.reply(f"🪙 It’s **{res}** — you win `{bet}`!")
    return await m.reply(f"🪙 It’s **{res}** — you lose `{bet}`.")

@app.on_message(filters.command("dice_rpg"))
async def dicdde_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /dice [bet]")
    bet = parse_amount(args[0], 1)
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    roll = random.randint(1, 6)
    if roll >= 4:
        win_bet(m.from_user.id, int(bet * 1.8))
        return await m.reply(f"🎲 Rolled **{roll}** → WIN `{int(bet*0.8)}` profit")
    return await m.reply(f"🎲 Rolled **{roll}** → LOST `{bet}`")

@app.on_message(filters.command("multidice_rpg"))
async def multidicdde_cmd(_, m: Message):
    args = m.command[1:]
    if len(args) < 2:
        return await m.reply("Usage: /multidice [bet] [count 2-5]")
    bet = parse_amount(args[0], 1)
    cnt = min(5, max(2, parse_amount(args[1], 2)))
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    rolls = [random.randint(1, 6) for _ in range(cnt)]
    score = sum(1 for r in rolls if r >= 4)
    if score >= (cnt//2 + 1):
        prize = int(bet * (1 + 0.5 * score))
        win_bet(m.from_user.id, prize)
        return await m.reply(f"🎲 Rolls {rolls} → **WIN**! You got `{prize-bet}` profit.")
    return await m.reply(f"🎲 Rolls {rolls} → **LOSE** `{bet}`")

@app.on_message(filters.command("wheel_rpg"))
async def wheeddl_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /wheel [bet]")
    bet = parse_amount(args[0], 1)
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    slot = random.choices(
        population=[0, 1, 2, 5, 10],
        weights=[45, 30, 15, 8, 2], k=1
    )[0]
    if slot == 0:
        return await m.reply("🎡 Wheel: **0x** — lost it all!")
    win_bet(m.from_user.id, bet * slot * 2)  # generous
    await m.reply(f"🎡 Wheel: **{slot}x** — BIG WIN `{bet * slot}` profit!")

@app.on_message(filters.command("slots_rpg"))
async def slotsdd_cmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /slots [bet]")
    bet = parse_amount(args[0], 1)
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    reels = ["🍒","🍋","🔔","⭐","7️⃣"]
    r = [random.choice(reels) for _ in range(3)]
    prize = 0
    if len(set(r)) == 1:
        prize = bet * 5
    elif len(set(r)) == 2:
        prize = bet * 2
    if prize:
        win_bet(m.from_user.id, bet + prize)
        return await m.reply(f"🎰 {' '.join(r)} → WIN `{prize}`!")
    return await m.reply(f"🎰 {' '.join(r)} → Lose `{bet}`")

@app.on_message(filters.command("blackjack"))
async def bj_rpcmd(_, m: Message):
    args = m.command[1:]
    if not args:
        return await m.reply("Usage: /blackjack [bet]")
    bet = parse_amount(args[0], 1)
    if not pay_bet(m.from_user.id, bet):
        return await m.reply("Not enough coins.")
    def draw(): return random.randint(2, 11)
    player = [draw(), draw()]
    dealer = [draw(), draw()]
    # simple AI: dealer hits until >=17
    while sum(dealer) < 17:
        dealer.append(draw())
    # player auto strategy: hit if < 15
    while sum(player) < 15:
        player.append(draw())
    p, d = sum(player), sum(dealer)
    if p > 21: return await m.reply(f"🃏 You {player}={p} vs Dealer {dealer}={d} → **BUST** lose `{bet}`")
    if d > 21 or p > d:
        win_bet(m.from_user.id, bet * 2)
        return await m.reply(f"🃏 You {player}={p} vs Dealer {dealer}={d} → **WIN** +`{bet}`")
    if p == d:
        win_bet(m.from_user.id, bet)  # push
        return await m.reply(f"🃏 You {player}={p} vs Dealer {dealer}={d} → **PUSH** (refund)")
    return await m.reply(f"🃏 You {player}={p} vs Dealer {dealer}={d} → **LOSE** `{bet}`")

# --------------------- LEADERBOARD / MEME ----------------
@app.on_message(filters.command("rpgleaderboard"))
async def lb_cmd(_, m: Message):
    top = users.find().sort([("coins", -1), ("xp", -1)]).limit(10)
    lines = ["🏆 **Leaderboard** (Top Coins)**"]
    for i, u in enumerate(top, 1):
        lines.append(f"{i}. `{u.get('name','?')}` — 💰 {u.get('coins',0)} • ⭐ {u.get('xp',0)}")
    await m.reply("\n".join(lines))

@app.on_message(filters.command("memerpg"))
async def meme_cmd(_, m: Message):
    await m.reply(random.choice(MEMES))

# --------------------- CLEANUP TASK ----------------------
async def cleanup_zero_inventories():
    while True:
        # optional maintenance
        await asyncio.sleep(600)


