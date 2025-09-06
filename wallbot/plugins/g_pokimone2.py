"""
PokéExperience — Advanced Telegram Game Bot
Features:
- Catch wild Pokémon (manual / auto spawn)
- Poké Balls & inventory, shop
- Trainer XP, leveling; Pokémon XP, leveling & evolution
- Trades between users
- PvP 1v1 turn-based battles in group chats (request -> accept -> fight)
- Leaderboard, profiles, cooldowns
- MongoDB persistence using motor (async)
- Designed as a starter: extend POKEDEX, items, shop prices, battle logic

Environment variables:
API_ID, API_HASH, BOT_TOKEN, MONGO_URI

Run: python pokegame_advanced.py
"""
import os
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio
from bson import ObjectId
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "pokegame_db"


# ----------------- DB -----------------
mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

users_col = db["users"]          # trainer profiles and inventory
pokemons_col = db["pokemons"]    # pokemons owned by users
spawns_col = db["spawns"]        # active wild pokemons per chat
battles_col = db["battles"]      # active pvps
trades_col = db["trades"]        # pending trades
groups_col = db["groups"]        # group settings (auto spawn, etc.)



# ----------------- POKEDEX (starter) -----------------
# Extend: add more species, base stats, evolutions and evolution level
POKEDEX = {
    "Pidgey": {"base_hp": 18, "base_atk": 6, "evolves_to": "Pidgeotto", "evolve_lvl": 18},
    "Pidgeotto": {"base_hp": 38, "base_atk": 14, "evolves_to": "Pidgeot", "evolve_lvl": 36},
    "Charmander": {"base_hp": 22, "base_atk": 8, "evolves_to": "Charmeleon", "evolve_lvl": 16},
    "Charmeleon": {"base_hp": 44, "base_atk": 16, "evolves_to": "Charizard", "evolve_lvl": 36},
    "Bulbasaur": {"base_hp": 24, "base_atk": 7, "evolves_to": "Ivysaur", "evolve_lvl": 16},
    "Squirtle": {"base_hp": 23, "base_atk": 7, "evolves_to": "Wartortle", "evolve_lvl": 16},
    "Pikachu": {"base_hp": 18, "base_atk": 12, "evolves_to": "Raichu", "evolve_lvl": 30},
}
POKEMON_LIST = list(POKEDEX.keys())

# ----------------- ITEMS & SHOP -----------------
ITEMS = {
    "pokeball": {"name": "Poké Ball", "price": 50, "catch_bonus": 0},
    "greatball": {"name": "Great Ball", "price": 150, "catch_bonus": 15},
    "ultraball": {"name": "Ultra Ball", "price": 500, "catch_bonus": 35},
    # add potions, revives etc later
}

# ----------------- XP CURVES -----------------
def xp_for_level(lvl: int) -> int:
    # simple curve: 10 * lvl^2
    return 10 * (lvl ** 2)

# ----------------- HELPERS -----------------
async def ensure_user(user):
    doc = await users_col.find_one({"user_id": user.id})
    if not doc:
        doc = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "trainer_xp": 0,
            "trainer_level": 1,
            "coins": 200,
            "inventory": {"pokeball": 5},  # starting balls
            "created_at": datetime.utcnow(),
            "last_catch_at": None,
        }
        await users_col.insert_one(doc)
    return doc

async def create_pokemon(owner_id: int, species: str, level: int = 1):
    base = POKEDEX.get(species)
    if not base:
        raise ValueError("Unknown species")
    poke = {
        "owner_id": owner_id,
        "species": species,
        "nickname": species,
        "level": int(level),
        "xp": xp_for_level(level),
        "hp": base["base_hp"] + level * 2,
        "atk": base["base_atk"] + level,
        "created_at": datetime.utcnow(),
    }
    res = await pokemons_col.insert_one(poke)
    poke["_id"] = res.inserted_id
    return poke

def format_pokemon(poke: dict) -> str:
    return f"{poke.get('nickname')} ({poke.get('species')}) — Lv{poke.get('level')} | XP {poke.get('xp')}"

async def maybe_pokemon_levelup_and_evolve(poke_doc):
    # loop to allow multi-level ups if xp large
    leveled = False
    while poke_doc.get("xp", 0) >= xp_for_level(poke_doc["level"] + 1):
        poke_doc["level"] += 1
        leveled = True
        poke_doc["hp"] += 3
        poke_doc["atk"] += 2
    await pokemons_col.update_one({"_id": poke_doc["_id"]}, {"$set": {"level": poke_doc["level"], "hp": poke_doc["hp"], "atk": poke_doc["atk"], "xp": poke_doc["xp"]}})
    # evolve check
    info = POKEDEX.get(poke_doc["species"])
    if info and info.get("evolves_to") and poke_doc["level"] >= info.get("evolve_lvl", 999):
        new_species = info["evolves_to"]
        poke_doc["species"] = new_species
        poke_doc["nickname"] = new_species
        base = POKEDEX.get(new_species, {})
        poke_doc["hp"] += base.get("base_hp", 5)
        poke_doc["atk"] += base.get("base_atk", 2)
        await pokemons_col.update_one({"_id": poke_doc["_id"]}, {"$set": {"species": poke_doc["species"], "nickname": poke_doc["nickname"], "hp": poke_doc["hp"], "atk": poke_doc["atk"]}})
        # notify owner
        try:
            await app.send_message(poke_doc["owner_id"], f"✨ Your {info} evolved into {new_species}!")
        except Exception:
            pass

# ----------------- SPAWNING -----------------
async def spawn_wild_in_chat(chat_id: int, species: Optional[str] = None, level_min: int = 1, level_max: int = 10):
    species = species or random.choice(POKEMON_LIST)
    level = random.randint(level_min, level_max)
    spawn = {
        "chat_id": chat_id,
        "species": species,
        "level": level,
        "spawned_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=7),
    }
    res = await spawns_col.insert_one(spawn)
    spawn["_id"] = res.inserted_id
    return spawn

async def get_active_spawn(chat_id: int):
    now = datetime.utcnow()
    return await spawns_col.find_one({"chat_id": chat_id, "expires_at": {"$gt": now}})

# ----------------- CATCH MECHANICS -----------------
def compute_catch_chance(spawn_level: int, trainer_level: int, ball_bonus: int):
    # base chance: 50 - level_penalty + trainer bonus + ball_bonus
    base = 50
    level_penalty = spawn_level * 2
    trainer_bonus = min(20, trainer_level)
    chance = base + trainer_bonus + ball_bonus - level_penalty
    return max(5, min(95, chance))

# ----------------- COOLDOWNS -----------------
def on_cooldown(user: dict, action: str, seconds: int) -> bool:
    key = f"last_{action}_at"
    last = user.get(key)
    if not last:
        return False
    return (datetime.utcnow() - last).total_seconds() < seconds

# ----------------- COMMANDS -----------------
#@app.on_message(filters.command("start") & filters.private)
async def cmd_starht(_, message: Message):
    await ensure_user(message.from_user)
    await message.reply(
        "👋 Welcome to PokéExperience!\n"
        "Catch, train, trade and battle with friends.\n\n"
        "Group commands: /spawn (admin), /catch, /profile, /pokedex, /shop, /buy, /trade, /pvp\n\n"
        "Type /help for details."
    )

@app.on_message(filters.command("pokex"))
async def cmd_hpedlp(_, message: Message):
    await message.reply(
        "/spawn_poki (group admin) - spawn a wild Pokémon now\n"
        "/catch_poki [ball] - catch the active Pokémon (default pokeball)\n"
        "/profile_poki - show your trainer profile and Pokémon\n"
        "/pokedex - list species\n"
        "/shop_poki - show items\n"
        "/buy_poki <item> <qty> - buy items\n"
        "/trade_poki @user <your_poke_id> for <their_poke_id> - propose trade\n"
        "/pvp_poki @user <your_poke_id> - challenge in group\n    Opponent accepts with /acceptpvp <battle_id> <their_poke_id>\n"
        "/leaderboard_poki - top trainers by level"
    )

@app.on_message(filters.command("pokedex") & (filters.private | filters.group))
async def cmd_pokededx(_, message: Message):
    text = "📘 Pokedex:\n"
    for name, info in POKEDEX.items():
        evo = info.get("evolves_to", "—")
        evo_lvl = info.get("evolve_lvl", "—")
        text += f"- {name}: HP {info['base_hp']} ATK {info['base_atk']} -> {evo} @Lv{evo_lvl}\n"
    await message.reply(text)

@app.on_message(filters.command("profile_poik") & (filters.private | filters.group))
async def cmd_profidle(_, message: Message):
    user = await ensure_user(message.from_user)
    trainer = await users_col.find_one({"user_id": message.from_user.id})
    text = f"🎒 Trainer: {trainer.get('username')} (Lv {trainer.get('trainer_level')})\nXP: {trainer.get('trainer_xp')} | Coins: {trainer.get('coins')}\nInventory: {trainer.get('inventory')}\n\nYour Pokémon:\n"
    cursor = pokemons_col.find({"owner_id": message.from_user.id})
    found = False
    async for p in cursor:
        found = True
        text += f"- ID:{p['_id']} {p['nickname']} ({p['species']}) Lv{p['level']} XP{p['xp']}\n"
    if not found:
        text += "You have no Pokémon yet. Catch some with /catch_poki!"
    await message.reply(text)

# SPAWN (admin)
@app.on_message(filters.command("spawn_poki") & filters.group)
async def cmd_spfawn(client, message: Message):
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply("Only group admins can use /spawn_poki.")
    except Exception:
        return await message.reply("Unable to verify admin status.")
    existing = await get_active_spawn(message.chat.id)
    if existing:
        return await message.reply(f"A wild {existing['species']} (Lv{existing['level']}) is already present. Use /catch_poki.")
    spawn = await spawn_wild_in_chat(message.chat.id)
    await message.reply(f"🦊 A wild *{spawn['species']}* (Lv{spawn['level']}) appeared! Use /catch_poki to try and capture it.")

# CATCH
@app.on_message(filters.command("catch_poki") & filters.group)
async def cmd_cadtch(client, message: Message):
    user = await ensure_user(message.from_user)
    # cooldown per user (prevent spam): 10s
    if on_cooldown(user, "catch", 10):
        return await message.reply("⏳ You're catching too fast — wait a bit.")
    spawn = await get_active_spawn(message.chat.id)
    if not spawn:
        return await message.reply("No wild Pokémon right now.")
    # parse ball param if provided
    ball_key = "pokeball"
    if len(message.command) > 1:
        arg = message.command[1].lower()
        if arg in ITEMS:
            ball_key = arg
    # check inventory
    inv = user.get("inventory", {})
    if inv.get(ball_key, 0) <= 0:
        return await message.reply(f"You don't have any {ITEMS.get(ball_key, {}).get('name', ball_key)}. Buy from /shop_poki.")
    # compute chance
    chance = compute_catch_chance(spawn["level"], user.get("trainer_level", 1), ITEMS.get(ball_key, {}).get("catch_bonus", 0))
    roll = random.randint(1, 100)
    # reduce ball from inventory
    inv[ball_key] = inv.get(ball_key, 0) - 1
    await users_col.update_one({"user_id": user["user_id"]}, {"$set": {"inventory": inv, "last_catch_at": datetime.utcnow()}})
    if roll <= chance:
        # catch success
        new_poke = await create_pokemon(message.from_user.id, spawn["species"], spawn["level"])
        await spawns_col.delete_one({"_id": spawn["_id"]})
        # trainer reward xp & coins
        await users_col.update_one({"user_id": user["user_id"]}, {"$inc": {"trainer_xp": 15, "coins": 20}})
        await maybe_trainer_levelup(user["user_id"])
        await maybe_pokemon_levelup_and_evolve(new_poke)
        await message.reply(f"🎉 {message.from_user.mention} caught a *{spawn['species']}* (Lv{spawn['level']})!\n\n{format_pokemon(new_poke)}")
    else:
        # fail — spawn may run away 30%
        if random.random() < 0.3:
            await spawns_col.delete_one({"_id": spawn["_id"]})
            return await message.reply(f"Oh no! The wild {spawn['species']} escaped...")
        else:
            return await message.reply(f"😅 Failed to catch the {spawn['species']} (rolled {roll} vs {chance}). Try again!")

# SHOP & BUY
@app.on_message(filters.command("shop_poki"))
async def cmd_shdop(_, message: Message):
    text = "🛒 Shop:\n"
    for key, item in ITEMS.items():
        text += f"- {item['name']} (`{key}`) — Price: {item['price']} coins\n"
    text += "\nBuy: /buy_poki [item_key] [qty]"
    await message.reply(text)

@app.on_message(filters.command("buy_poki"))
async def cmd_bduy(_, message: Message):
    user = await ensure_user(message.from_user)
    if len(message.command) < 2:
        return await message.reply("Usage: /buy_poki [item_key] [qty]")
    item_key = message.command[1].lower()
    qty = int(message.command[2]) if len(message.command) > 2 else 1
    if item_key not in ITEMS:
        return await message.reply("Item not found.")
    cost = ITEMS[item_key]["price"] * qty
    if user.get("coins", 0) < cost:
        return await message.reply("You don't have enough coins.")
    # deduct coins and add to inventory
    await users_col.update_one({"user_id": user["user_id"]}, {"$inc": {"coins": -cost, f"inventory.{item_key}": qty}})
    await message.reply(f"✅ Purchased {qty}x {ITEMS[item_key]['name']} for {cost} coins.")

# LEADERBOARD
@app.on_message(filters.command("leaderboard_poki"))
async def cmd_leadergboard(_, message: Message):
    cursor = users_col.find({}).sort("trainer_level", -1).limit(10)
    text = "🏆 Trainer Leaderboard:\n"
    i = 1
    async for u in cursor:
        text += f"{i}. {u.get('username')} — Lv {u.get('trainer_level')} XP {u.get('trainer_xp')}\n"
        i += 1
    await message.reply(text)

# TRADING
@app.on_message(filters.command("trade_poki") & filters.group)
async def cmd_traffde(client, message: Message):
    # /trade @user <your_poke_id> for <their_poke_id>
    if len(message.command) < 5:
        return await message.reply("Usage: /trade_poki @user [your_poke_id] for [their_poke_id]")
    # resolve mentioned user
    mentioned = None
    for ent in message.entities or []:
        if ent.type in ("mention", "text_mention"):
            if ent.type == "mention":
                username = message.text[ent.offset:ent.offset+ent.length].lstrip("@")
                try:
                    userobj = await client.get_users(username)
                    mentioned = userobj
                except Exception:
                    pass
            else:
                mentioned = ent.user
            break
    if not mentioned:
        return await message.reply("Mention a user to trade with.")
    try:
        your_id = ObjectId(message.command[2])
        if message.command[3].lower() != "for":
            return await message.reply("Usage: /trade_poki @user [your_poke_id] for [their_poke_id]")
        their_id = ObjectId(message.command[4])
    except Exception:
        return await message.reply("Invalid Pokémon IDs.")
    # check ownership
    offer = await pokemons_col.find_one({"_id": your_id, "owner_id": message.from_user.id})
    want = await pokemons_col.find_one({"_id": their_id, "owner_id": mentioned.id})
    if not offer or not want:
        return await message.reply("Either offered or wanted Pokémon not found/owned.")
    trade = {
        "from_user": message.from_user.id,
        "to_user": mentioned.id,
        "offer_id": offer["_id"],
        "want_id": want["_id"],
        "status": "pending",
        "chat_id": message.chat.id,
        "created_at": datetime.utcnow(),
    }
    res = await trades_col.insert_one(trade)
    await message.reply(f"Trade request sent to {mentioned.mention}. They can accept with /accepttrade_poki {res.inserted_id}")

@app.on_message(filters.command("accepttrade_poki") & filters.group)
async def cmd_accepttddrade(_, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /accepttrade_poki [trade_id]")
    try:
        trade = await trades_col.find_one({"_id": ObjectId(message.command[1])})
        if not trade:
            return await message.reply("Trade not found.")
        if trade["to_user"] != message.from_user.id:
            return await message.reply("You are not the recipient.")
        # swap owners
        await pokemons_col.update_one({"_id": trade["offer_id"]}, {"$set": {"owner_id": trade["to_user"]}})
        await pokemons_col.update_one({"_id": trade["want_id"]}, {"$set": {"owner_id": trade["from_user"]}})
        await trades_col.update_one({"_id": trade["_id"]}, {"$set": {"status": "completed"}})
        await message.reply("✅ Trade completed!")
    except Exception as e:
        await message.reply(f"Error: {e}")

# PVP: Challenge -> Accept -> Turn-based fight
@app.on_message(filters.command("pvp_poki") & filters.group)
async def cmd_pdvp(client, message: Message):
    # /pvp @user <your_poke_id>
    if len(message.command) < 3:
        return await message.reply("Usage: /pvp_poki @user [your_poke_id]")
    # resolve opponent
    opp = None
    for ent in message.entities or []:
        if ent.type in ("mention", "text_mention"):
            if ent.type == "mention":
                username = message.text[ent.offset:ent.offset+ent.length].lstrip("@")
                try:
                    opp = await client.get_users(username)
                except Exception:
                    pass
            else:
                opp = ent.user
            break
    if not opp:
        return await message.reply("Mention an opponent in this group.")
    try:
        your_poke_id = ObjectId(message.command[2])
    except Exception:
        return await message.reply("Invalid your_poke_id.")
    your_poke = await pokemons_col.find_one({"_id": your_poke_id, "owner_id": message.from_user.id})
    if not your_poke:
        return await message.reply("You don't own that Pokémon.")
    battle = {
        "chat_id": message.chat.id,
        "challenger_id": message.from_user.id,
        "opponent_id": opp.id,
        "challenger_poke": your_poke["_id"],
        "opponent_poke": None,
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    res = await battles_col.insert_one(battle)
    await message.reply(f"{opp.mention}, you have a battle request! Accept with /acceptpvp_poki {res.inserted_id} [your_poke_id]")

@app.on_message(filters.command("acceptpvp_poki") & filters.group)
async def cmd_acdceptpvp(client, message: Message):
    # /acceptpvp <battle_id> <your_poke_id>
    if len(message.command) < 3:
        return await message.reply("Usage: /acceptpvp_poki [battle_id] [your_poke_id]")
    try:
        battle = await battles_col.find_one({"_id": ObjectId(message.command[1])})
        if not battle:
            return await message.reply("Battle not found.")
        if battle["opponent_id"] != message.from_user.id:
            return await message.reply("You are not the intended opponent.")
        opp_poke = await pokemons_col.find_one({"_id": ObjectId(message.command[2]), "owner_id": message.from_user.id})
        if not opp_poke:
            return await message.reply("You don't own that Pokémon.")
        # update battle
        await battles_col.update_one({"_id": battle["_id"]}, {"$set": {"opponent_poke": opp_poke["_id"], "status": "accepted", "turn": battle["challenger_id"]}})
        await message.reply("⚔️ Battle accepted! Running fight...")
        await run_pvp_fight(battle["_id"])
    except Exception as e:
        await message.reply(f"Error: {e}")

async def run_pvp_fight(battle_id):
    battle = await battles_col.find_one({"_id": battle_id})
    if not battle:
        return
    # reload pokes
    ch_poke = await pokemons_col.find_one({"_id": battle["challenger_poke"]})
    op_poke = await pokemons_col.find_one({"_id": battle["opponent_poke"]})
    if not ch_poke or not op_poke:
        await app.send_message(battle["chat_id"], "Error: Could not load Pokémon for battle.")
        await battles_col.update_one({"_id": battle["_id"]}, {"$set": {"status": "failed"}})
        return
    # make mutable copies for HP during battle
    ch_hp = ch_poke["hp"]
    op_hp = op_poke["hp"]
    log = []
    # simple turn-based until one reaches 0
    # determine first turn: challenger
    turn = "challenger"
    while ch_hp > 0 and op_hp > 0:
        await asyncio.sleep(1)  # tiny delay so messages don't flood
        if turn == "challenger":
            damage = ch_poke["atk"] + random.randint(0, 6)
            op_hp -= damage
            log.append(f"{ch_poke['nickname']} hits {op_poke['nickname']} for {damage} dmg (HP left {max(0, op_hp)})")
            turn = "opponent"
        else:
            damage = op_poke["atk"] + random.randint(0, 6)
            ch_hp -= damage
            log.append(f"{op_poke['nickname']} hits {ch_poke['nickname']} for {damage} dmg (HP left {max(0, ch_hp)})")
            turn = "challenger"
    # determine winner
    if ch_hp > 0:
        winner_id = battle["challenger_id"]
        winner_poke_id = ch_poke["_id"]
    else:
        winner_id = battle["opponent_id"]
        winner_poke_id = op_poke["_id"]
    # award xp & coins
    await pokemons_col.update_one({"_id": winner_poke_id}, {"$inc": {"xp": 20}})
    await users_col.update_one({"user_id": winner_id}, {"$inc": {"trainer_xp": 30, "coins": 50}})
    # finalize
    await maybe_pokemon_levelup_and_evolve(await pokemons_col.find_one({"_id": winner_poke_id}))
    await maybe_trainer_levelup(winner_id)
    await battles_col.update_one({"_id": battle["_id"]}, {"$set": {"status": "finished", "winner": winner_id}})
    summary = "\n".join(log[-8:])  # last 8 actions
    await app.send_message(battle["chat_id"], f"⚔️ Battle finished! Winner: <a href='tg://user?id={winner_id}'>player</a>\n\nRecent moves:\n{summary}")

# TRAINER LEVELUP
async def maybe_trainer_levelup(user_id: int):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return
    xp = user.get("trainer_xp", 0)
    lvl = user.get("trainer_level", 1)
    while xp >= xp_for_level(lvl + 1):
        lvl += 1
    if lvl != user.get("trainer_level"):
        await users_col.update_one({"user_id": user_id}, {"$set": {"trainer_level": lvl}})
        try:
            await app.send_message(user_id, f"✨ Congrats, your trainer reached level {lvl}!")
        except Exception:
            pass

# BACKGROUND AUTO-SPAWNER (spawns in groups with auto_spawn: True)
SPAWN_INTERVAL = int(os.getenv("SPAWN_INTERVAL", "180"))  # seconds
async def auto_spawner():
    await app.start()  # ensure client ready
    while True:
        try:
            async for grp in groups_col.find({"auto_spawn": True}):
                chat_id = grp["chat_id"]
                existing = await get_active_spawn(chat_id)
                if not existing:
                    spawn = await spawn_wild_in_chat(chat_id, level_min=1, level_max=10)
                    try:
                        await app.send_message(chat_id, f"🦊 Wild *{spawn['species']}* appeared! Lv{spawn['level']}. Use /catch_poki")
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(SPAWN_INTERVAL)

# GROUP COMMANDS: toggle auto spawn
@app.on_message(filters.command("togglespawn_poki") & filters.group)
async def cmd_togglesdpawn(client, message: Message):
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply("Only admins can toggle auto-spawn.")
    except Exception:
        return await message.reply("Cannot verify admin status.")
    existing = await groups_col.find_one({"chat_id": message.chat.id})
    if existing and existing.get("auto_spawn"):
        await groups_col.update_one({"chat_id": message.chat.id}, {"$set": {"auto_spawn": False}})
        await message.reply("Auto spawn disabled for this group.")
    else:
        await groups_col.update_one({"chat_id": message.chat.id}, {"$set": {"auto_spawn": True}}, upsert=True)
        await message.reply("Auto spawn enabled for this group.")

# ----------------- START -----------------
@app.on_message(filters.command("startpokigame") & filters.private)
async def cmd_starhtgame(_, message: Message):
    await ensure_user(message.from_user)
    await message.reply("Game initialized for your trainer. Use /profile_poki to view stats.")
