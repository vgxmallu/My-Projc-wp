"""
Poké-Experience Telegram Game Bot (Pyrogram + Motor)

Basic gameplay:
- Wild Pokémon spawn in group chats (background or /spawn).
- Users use /catch <ball_type optional> to catch (default: poke ball).
- Pokémon have xp and levels; level-ups can trigger evolve if species has evolution.
- Users can /profile to view their Pokémon.
- Simple /battle @opponent <your_pokemon_id> to challenge another trainer (opponent must accept).
- /trade @user offer_poke_id for_poke_id starts a trade request.

This is a starter, meant to be extended. Keep mechanics simple for readability.

Author: ChatGPT
"""

import os
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from pyrogram import Client, filters, idle
from pyrogram.types import Message, User
import motor.motor_asyncio
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "pokegame_db"


# ----------------- DB -----------------
mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]           # user_id -> trainer info, inventory
pokemons_col = db["pokemons"]     # pokemon docs owned by players
spawns_col = db["spawns"]         # active wild pokemons per chat
battles_col = db["battles"]       # ongoing battle requests
trades_col = db["trades"]         # pending trades



# ----------------- Simple Pokedex -----------------
# Minimal starter pokedex — extend as needed.
POKEDEX = {
    "Pidgey": {"base_hp": 20, "base_atk": 6, "evolves_to": "Pidgeotto", "evolve_lvl": 18},
    "Pidgeotto": {"base_hp": 40, "base_atk": 14, "evolves_to": "Pidgeot", "evolve_lvl": 36},
    "Charmander": {"base_hp": 22, "base_atk": 8, "evolves_to": "Charmeleon", "evolve_lvl": 16},
    "Charmeleon": {"base_hp": 44, "base_atk": 16, "evolves_to": "Charizard", "evolve_lvl": 36},
    "Bulbasaur": {"base_hp": 24, "base_atk": 7, "evolves_to": "Ivysaur", "evolve_lvl": 16},
    "Squirtle": {"base_hp": 23, "base_atk": 7, "evolves_to": "Wartortle", "evolve_lvl": 16},
    "Pikachu": {"base_hp": 18, "base_atk": 12, "evolves_to": "Raichu", "evolve_lvl": 30},
    # Add more species here...
}

POKEMON_LIST = list(POKEDEX.keys())

# XP curve (simple): lvl^2 * 10
def xp_for_level(lvl: int) -> int:
    return (lvl ** 2) * 10

# ----------------- Helper Utilities -----------------
async def ensure_user(user: User):
    """Ensure trainer document exists."""
    doc = await users_col.find_one({"user_id": user.id})
    if not doc:
        doc = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "trainer_xp": 0,
            "trainer_level": 1,
            "created_at": datetime.utcnow(),
        }
        await users_col.insert_one(doc)
    return doc

async def create_pokemon(owner_id: int, species: str, level: int = 1):
    """Create a pokemon doc and return it."""
    base = POKEDEX.get(species)
    if not base:
        raise ValueError("Unknown species")
    pokemon = {
        "owner_id": owner_id,
        "species": species,
        "level": int(level),
        "xp": xp_for_level(level),
        "hp": base["base_hp"] + level * 2,
        "atk": base["base_atk"] + level,
        "created_at": datetime.utcnow(),
        "nickname": species,
    }
    res = await pokemons_col.insert_one(pokemon)
    pokemon["_id"] = res.inserted_id
    return pokemon

def format_pokemon_doc(poke: dict) -> str:
    return (f"#{poke.get('_id')} {poke.get('nickname')} ({poke.get('species')})\n"
            f"Lv {poke.get('level')} | XP {poke.get('xp')} | HP {poke.get('hp')} | ATK {poke.get('atk')}")

# ----------------- Spawning -----------------
async def spawn_wild(chat_id: int) -> Optional[dict]:
    """Create a wild pokemon in chat spawn collection. Returns spawn doc."""
    species = random.choice(POKEMON_LIST)
    level = random.randint(1, 10)
    spawn = {
        "chat_id": chat_id,
        "species": species,
        "level": level,
        "spawned_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }
    res = await spawns_col.insert_one(spawn)
    spawn["_id"] = res.inserted_id
    return spawn

async def get_active_spawn(chat_id: int) -> Optional[dict]:
    now = datetime.utcnow()
    sp = await spawns_col.find_one({"chat_id": chat_id, "expires_at": {"$gt": now}})
    return sp

# ----------------- Commands -----------------
@app.on_message(filters.command("stapoki") & filters.private)
async def cmd_start(client, message: Message):
    await ensure_user(message.from_user)
    await message.reply(
        "👋 Welcome to PokéExperience!\n\n"
        "Commands (groups):\n"
        "/spawn (admin) - spawn a wild Pokémon now\n"
        "/catch - attempt to catch the active wild Pokémon\n"
        "/profile - view your trainer profile and Pokémon\n"
        "/pokedex - show species list\n"
        "/battle @opponent <your_poke_id> - challenge a trainer\n        (opponent must accept with /acceptbattle ID)\n"
        "/trade @user offer_poke_id for_poke_id - propose trade\n"
    )

@app.on_message(filters.command("pokedex") & (filters.private | filters.group))
async def cmd_pokedex(client, message: Message):
    text = "📘 Pokedex (sample):\n"
    for name, info in POKEDEX.items():
        evolves = info.get("evolves_to", "—")
        evo_lvl = info.get("evolve_lvl", "—")
        text += f"- {name}: HP {info['base_hp']} ATK {info['base_atk']} -> {evolves} @Lv{evo_lvl}\n"
    await message.reply(text)

@app.on_message(filters.command("spawn_poki") & filters.group)
async def cmd_spawn(client, message: Message):
    # require admin to spawn manually
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply("Only group admins can use /spawn.")
    except Exception:
        return await message.reply("Cannot verify admin status.")
    existing = await get_active_spawn(message.chat.id)
    if existing:
        return await message.reply(f"A wild {existing['species']} is already here! Use /catch.")
    spawn = await spawn_wild(message.chat.id)
    await message.reply(f"🦊 A wild *{spawn['species']}* (Lv {spawn['level']}) appeared! Use /catch to try and capture it.", parse_mode="markdown")

@app.on_message(filters.command("catch_poki") & filters.group)
async def cmd_catch(client, message: Message):
    # Attempt to catch active spawn
    spawn = await get_active_spawn(message.chat.id)
    if not spawn:
        return await message.reply("No wild Pokémon is available right now.")
    # Simple catch chance: base 50% + (player_luck) - (level_penalty)
    player = await ensure_user(message.from_user)
    # compute chance
    base_chance = 50
    level_penalty = spawn["level"] * 2
    # limited "luck" from trainer level
    trainer_level = player.get("trainer_level", 1)
    luck = min(20, trainer_level)  # max +20%
    catch_chance = max(5, base_chance + luck - level_penalty)
    roll = random.randint(1, 100)
    if roll <= catch_chance:
        # success
        new_poke = await create_pokemon(message.from_user.id, spawn["species"], spawn["level"])
        await spawns_col.delete_one({"_id": spawn["_id"]})
        # give trainer some xp
        await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"trainer_xp": 10}})
        # maybe level up trainer
        await maybe_trainer_levelup(message.from_user.id)
        await message.reply(f"🎉 Congratulations! {message.from_user.mention} caught a *{spawn['species']}* (Lv {spawn['level']})!\n\n{format_pokemon_doc(new_poke)}", parse_mode="markdown")
    else:
        # fail - decrease spawn time or escape chance
        # 30% chance it runs away immediately
        if random.random() < 0.3:
            await spawns_col.delete_one({"_id": spawn["_id"]})
            await message.reply(f"Oh no! The wild *{spawn['species']}* escaped...", parse_mode="markdown")
        else:
            await message.reply(f"😅 {message.from_user.mention} failed to catch the wild *{spawn['species']}* (rolled {roll} vs {catch_chance}). Try again!")

@app.on_message(filters.command("profile_poki") & (filters.group | filters.private))
async def cmd_profile(client, message: Message):
    user = message.from_user
    await ensure_user(user)
    trainer = await users_col.find_one({"user_id": user.id})
    text = f"🎒 Trainer: {trainer.get('username')} (Lv {trainer.get('trainer_level')})\nXP: {trainer.get('trainer_xp')}\n\nYour Pokémon:\n"
    cursor = pokemons_col.find({"owner_id": user.id})
    found = False
    async for p in cursor:
        found = True
        text += f"- ID: {p['_id']} | {p['nickname']} ({p['species']}) Lv {p['level']} XP {p['xp']}\n"
    if not found:
        text += "You have no Pokémon yet. Catch some with /catch!"
    await message.reply(text)

# ----------------- Leveling / Evolving -----------------
async def maybe_trainer_levelup(user_id: int):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return
    xp = user.get("trainer_xp", 0)
    lvl = user.get("trainer_level", 1)
    # simple leveling: level up when xp >= xp_for_level(lvl+1)
    next_req = xp_for_level(lvl + 1)
    if xp >= next_req:
        await users_col.update_one({"user_id": user_id}, {"$inc": {"trainer_level": 1}})
        # notify user by sending a private message if possible
        try:
            await app.send_message(user_id, f"✨ Congrats! Your trainer level increased to {lvl+1}!")
        except Exception:
            pass

async def maybe_pokemon_levelup_and_evolve(poke: dict):
    # level based on xp. If xp >= xp_for_level(level+1) increase level
    leveled = False
    while poke.get("xp", 0) >= xp_for_level(poke["level"] + 1):
        poke["level"] += 1
        leveled = True
        # increase stats mildly
        poke["hp"] += 3
        poke["atk"] += 2
    # update DB
    await pokemons_col.update_one({"_id": poke["_id"]}, {"$set": {"level": poke["level"], "hp": poke["hp"], "atk": poke["atk"], "xp": poke["xp"]}})
    # check evolution
    species = poke["species"]
    info = POKEDEX.get(species)
    if info and "evolves_to" in info and "evolve_lvl" in info:
        if poke["level"] >= info["evolve_lvl"]:
            new_species = info["evolves_to"]
            # evolve
            poke["species"] = new_species
            poke["nickname"] = new_species
            base = POKEDEX.get(new_species, {})
            poke["hp"] += base.get("base_hp", 5)
            poke["atk"] += base.get("base_atk", 2)
            await pokemons_col.update_one({"_id": poke["_id"]}, {"$set": {"species": poke["species"], "nickname": poke["nickname"], "hp": poke["hp"], "atk": poke["atk"]}})
            # notify owner
            try:
                await app.send_message(poke["owner_id"], f"✨ Your {species} evolved into {new_species}!")
            except Exception:
                pass

# ----------------- Battles -----------------
@app.on_message(filters.command("battle_poki") & filters.group)
async def cmd_battle(client, message: Message):
    # Usage: /battle @target <your_poke_id>
    if len(message.command) < 3:
        return await message.reply("Usage: /battle @opponent <your_poke_id>")
    if not message.entities:
        return await message.reply("Please mention an opponent to battle.")
    # find mentioned user
    mentioned = None
    for ent in message.entities:
        if ent.type == "mention":
            # text mention like @username; resolve?
            username = message.text[ent.offset:ent.offset+ent.length].lstrip("@")
            try:
                usr = await client.get_users(username)
                mentioned = usr
                break
            except Exception:
                pass
        elif ent.type == "text_mention":
            mentioned = ent.user
            break
    if not mentioned:
        return await message.reply("Could not find the opponent mention.")
    if mentioned.id == message.from_user.id:
        return await message.reply("You cannot battle yourself.")
    your_poke_id = message.command[2]
    # fetch your pokemon
    try:
        from bson import ObjectId
        poke_doc = await pokemons_col.find_one({"_id": ObjectId(your_poke_id), "owner_id": message.from_user.id})
        if not poke_doc:
            return await message.reply("Your Pokémon not found. Provide valid ID.")
    except Exception:
        return await message.reply("Invalid Pokémon ID format.")
    # create battle request record
    battle = {
        "challenger_id": message.from_user.id,
        "opponent_id": mentioned.id,
        "challenger_poke": poke_doc["_id"],
        "opponent_poke": None,
        "chat_id": message.chat.id,
        "status": "pending",  # pending, accepted, finished
        "created_at": datetime.utcnow(),
    }
    res = await battles_col.insert_one(battle)
    battle_id = res.inserted_id
    await message.reply(f"{mentioned.mention}, you have a battle request from {message.from_user.mention}! Accept with /acceptbattle {battle_id}")

@app.on_message(filters.command("acceptbattle") & filters.group)
async def cmd_acceptbattle(client, message: Message):
    # Usage: /acceptbattle <battle_id> <your_poke_id>
    if len(message.command) < 3:
        return await message.reply("Usage: /acceptbattle <battle_id> <your_poke_id>")
    battle_id = message.command[1]
    your_poke_id = message.command[2]
    try:
        from bson import ObjectId
        battle = await battles_col.find_one({"_id": ObjectId(battle_id)})
        if not battle:
            return await message.reply("Battle request not found.")
        if battle["opponent_id"] != message.from_user.id:
            return await message.reply("You are not the intended opponent for this battle.")
        # fetch opponent pokemon
        opp_poke = await pokemons_col.find_one({"_id": ObjectId(your_poke_id), "owner_id": message.from_user.id})
        if not opp_poke:
            return await message.reply("Your Pokémon not found.")
        # update battle and run fight
        await battles_col.update_one({"_id": battle["_id"]}, {"$set": {"opponent_poke": opp_poke["_id"], "status": "accepted"}})
        # load challenger poke
        ch_poke = await pokemons_col.find_one({"_id": battle["challenger_poke"]})
        # Simple battle logic: compare level + atk + random
        ch_power = ch_poke["level"] * 5 + ch_poke["atk"] + random.randint(0, 10)
        op_power = opp_poke["level"] * 5 + opp_poke["atk"] + random.randint(0, 10)
        winner_id = battle["challenger_id"] if ch_power >= op_power else battle["opponent_id"]
        loser_id = battle["opponent_id"] if winner_id == battle["challenger_id"] else battle["challenger_id"]
        # award XP to winner's pokemon
        winner_poke_id = battle["challenger_poke"] if winner_id == battle["challenger_id"] else opp_poke["_id"]
        await pokemons_col.update_one({"_id": winner_poke_id}, {"$inc": {"xp": 15}})
        # maybe level and evolve
        winner_poke_doc = await pokemons_col.find_one({"_id": winner_poke_id})
        await maybe_pokemon_levelup_and_evolve(winner_poke_doc)
        # update trainer xp
        await users_col.update_one({"user_id": winner_id}, {"$inc": {"trainer_xp": 20}})
        await maybe_trainer_levelup(winner_id)
        # finalize
        await battles_col.update_one({"_id": battle["_id"]}, {"$set": {"status": "finished", "winner": winner_id}})
        await client.send_message(battle["chat_id"], f"⚔️ Battle finished!\nWinner: <a href='tg://user?id={winner_id}'>player</a>\nChallenge power: {ch_power}\nOpponent power: {op_power}", parse_mode="html")
    except Exception as e:
        await message.reply(f"Error handling battle: {e}")

# ----------------- Trading -----------------
@app.on_message(filters.command("trade_poki") & filters.group)
async def cmd_trade(client, message: Message):
    # /trade @user offer_poke_id for_poke_id
    if len(message.command) < 4:
        return await message.reply("Usage: /trade @user offer_poke_id for_poke_id")
    # resolve user mention
    mentioned = None
    for ent in message.entities or []:
        if ent.type in ("mention", "text_mention"):
            if ent.type == "mention":
                username = message.text[ent.offset:ent.offset+ent.length].lstrip("@")
                try:
                    mentioned = await client.get_users(username)
                except Exception:
                    pass
            else:
                mentioned = ent.user
            break
    if not mentioned:
        return await message.reply("Could not find mentioned user.")
    if mentioned.id == message.from_user.id:
        return await message.reply("You cannot trade with yourself.")
    offer_id = message.command[2]
    if message.command[3].lower() != "for" or len(message.command) < 5:
        return await message.reply("Usage: /trade @user offer_poke_id for_poke_id")
    want_id = message.command[4]
    from bson import ObjectId
    try:
        offer = await pokemons_col.find_one({"_id": ObjectId(offer_id), "owner_id": message.from_user.id})
        want = await pokemons_col.find_one({"_id": ObjectId(want_id), "owner_id": mentioned.id})
    except Exception:
        return await message.reply("Invalid pokemon IDs.")
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
    await message.reply(f"Trade request sent to {mentioned.mention}. They can accept with /accepttrade {res.inserted_id}")

@app.on_message(filters.command("accepttrade_poki") & filters.group)
async def cmd_accepttrade(client, message: Message):
    # /accepttrade <trade_id>
    if len(message.command) < 2:
        return await message.reply("Usage: /accepttrade <trade_id>")
    trade_id = message.command[1]
    from bson import ObjectId
    try:
        trade = await trades_col.find_one({"_id": ObjectId(trade_id)})
        if not trade:
            return await message.reply("Trade not found.")
        if trade["to_user"] != message.from_user.id:
            return await message.reply("You are not the recipient of this trade.")
        # swap ownership
        await pokemons_col.update_one({"_id": trade["offer_id"]}, {"$set": {"owner_id": trade["to_user"]}})
        await pokemons_col.update_one({"_id": trade["want_id"]}, {"$set": {"owner_id": trade["from_user"]}})
        await trades_col.update_one({"_id": trade["_id"]}, {"$set": {"status": "completed"}})
        await message.reply("✅ Trade completed successfully!")
    except Exception as e:
        await message.reply(f"Error accepting trade: {e}")

# ----------------- Background Spawner -----------------
# Optionally track which groups want auto spawns
AUTO_SPAWN_ENABLED = True
SPAWN_INTERVAL = 180  # seconds

async def group_auto_spawner():
    await app.start()  # ensure client ready
    while True:
        if not AUTO_SPAWN_ENABLED:
            await asyncio.sleep(10)
            continue
        # get list of chats where spawns are enabled. For simplicity, we use all chats that had at least one spawn before,
        # or you can save a setting per group. For now, we query distinct chat ids from spawns collection or just do nothing if empty.
        # Better: get chats from a 'groups' collection with 'auto_spawn': True. We'll spawn in chats that have any members (simpler: spawn in a single admin-defined chat).
        # For demo, spawn in chat IDs in an env var or skip.
        # We'll attempt to spawn in chats saved in a "spawn_targets" collection.
        try:
            spawn_targets = db["spawn_targets"]
            async for doc in spawn_targets.find({}):
                chat_id = doc["chat_id"]
                existing = await get_active_spawn(chat_id)
                if not existing:
                    spawn = await spawn_wild(chat_id)
                    try:
                        await app.send_message(chat_id, f"🦊 A wild *{spawn['species']}* (Lv {spawn['level']}) appeared! Use /catch to try and capture it.", parse_mode="markdown")
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(SPAWN_INTERVAL)

# ----------------- Small Admin Commands for spawn targets -----------------
@app.on_message(filters.command("togglespawn_poki") & filters.group)
async def cmd_togglespawn(client, message: Message):
    # toggles the group in spawn_targets
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply("Only admins can toggle auto-spawn.")
    except Exception:
        return await message.reply("Cannot verify admin status.")
    col = db["spawn_targets"]
    existing = await col.find_one({"chat_id": message.chat.id})
    if existing:
        await col.delete_one({"chat_id": message.chat.id})
        await message.reply("Auto spawn disabled for this group.")
    else:
        await col.insert_one({"chat_id": message.chat.id})
        await message.reply("Auto spawn enabled for this group.")

