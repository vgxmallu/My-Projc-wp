# pvp_shop_bot.py
import uuid
import random
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app


DB_NAME = "pvp_game_shop"
# ----------------------------------------

# ---------- Setup ----------
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games = db["games"]       # active/pending games
players = db["players"]   # player profiles, coins, xp, items
# ---------------------------

# ---------- Shop Catalog ----------
SHOP_CATALOG = {
    "potion": {"price": 30, "desc": "Heals 30 HP when used."},
    "shield": {"price": 50, "desc": "Halves next incoming damage (one use)."},
    "bomb": {"price": 75, "desc": "Deals 40 damage to opponent instantly."},
}
# ----------------------------------

# ---------- Helpers ----------
async def ensure_player(uid: int) -> Dict[str, Any]:
    p = await players.find_one({"_id": uid})
    if not p:
        p = {
            "_id": uid,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "coins": 100,   # starting coins
            "xp": 0,
            "items": {}     # e.g. {"potion": 2, "shield": 1}
        }
        await players.insert_one(p)
    # normalize items dict
    p.setdefault("items", {})
    return p

async def inc_player(uid: int, field: str, amount: int = 1):
    await players.update_one({"_id": uid}, {"$inc": {field: amount}}, upsert=True)

async def add_coins(uid: int, amount: int):
    await players.update_one({"_id": uid}, {"$inc": {"coins": amount}}, upsert=True)

async def grant_xp(uid: int, amount: int):
    await players.update_one({"_id": uid}, {"$inc": {"xp": amount}}, upsert=True)

async def add_item(uid: int, item_key: str, count: int = 1):
    await players.update_one({"_id": uid}, {"$inc": {f"items.{item_key}": count}}, upsert=True)

async def remove_item(uid: int, item_key: str, count: int = 1) -> bool:
    """Remove item if exists. Return True if removed, False if not enough."""
    p = await ensure_player(uid)
    have = p.get("items", {}).get(item_key, 0)
    if have < count:
        return False
    await players.update_one({"_id": uid}, {"$inc": {f"items.{item_key}": -count}})
    return True

def make_action_kb(gid: str, uid: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ Attack", callback_data=f"pvp_attack|{gid}|{uid}"),
            InlineKeyboardButton("💖 Heal", callback_data=f"pvp_heal|{gid}|{uid}")
        ],
        [
            InlineKeyboardButton("🎒 Use Item", callback_data=f"pvp_useitem_menu|{gid}|{uid}"),
            InlineKeyboardButton("🏳️ Resign", callback_data=f"pvp_resign|{gid}|{uid}")
        ]
    ])

def short_mention(user):
    """Not awaited version for formatting when we have user dict or id only."""
    # This helper is used where we later replace IDs with actual mentions for messages.
    return f"<user:{user}>"

async def mention(uid: int) -> str:
    try:
        u = await app.get_users(uid)
        return u.mention
    except:
        return f"User({uid})"

def compute_level(xp: int) -> int:
    # Simple level formula: 100 XP per level
    return xp // 100 + 1

# ---------- Game creation ----------
@app.on_message(filters.command("battle") & filters.group)
async def battle_cmd(_, message: Message):
    """Start a battle by replying to a user's message or /battle <@user>"""
    # Determine opponent
    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
    else:
        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply_text("Reply to someone or use `/battle @user` to challenge.")
        try:
            opponent = await app.get_users(parts[1].strip())
        except:
            return await message.reply_text("Invalid user. Reply to their message or give @username/id.")

    challenger = message.from_user
    if opponent.id == challenger.id:
        return await message.reply_text("You cannot battle yourself.")

    # Ensure players exist
    await ensure_player(challenger.id)
    await ensure_player(opponent.id)

    gid = str(uuid.uuid4())
    # Initial game doc
    game = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [challenger.id, opponent.id],
        "hp": {str(challenger.id): 100, str(opponent.id): 100},
        "turn": challenger.id,
        "status": "pending",
        "mode": "classic",
        "created_at": datetime.utcnow(),
        # buffs e.g. {"shield": {uid_str: True}}
        "buffs": {"shield": {}},
        # optional log
        "log": []
    }
    await games.insert_one(game)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️Accept the Battle⚔️", callback_data=f"pvp_accept|{gid}|{opponent.id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"pvp_decline|{gid}|{opponent.id}")]
    ])

    await message.reply_text(
        f"⚔️ <b>Battle Request</b>\n\n"
        f"{challenger.mention} challenged {opponent.mention}!\n\n"
        "Challenged user: press Accept to start the battle.",
        reply_markup=kb
    )

# ---------- Accept / Decline ----------
@app.on_callback_query(filters.regex(r"^pvp_accept\|"))
async def accept_cb(_, query: CallbackQuery):
    _, gid, expected_uid = query.data.split("|")
    expected_uid = int(expected_uid)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.", show_alert=True)
    if query.from_user.id != expected_uid:
        return await query.answer("Only the challenged user can accept.", show_alert=True)

    # Set active and send initial action message
    await games.update_one({"_id": gid}, {"$set": {"status": "active"}})
    game = await games.find_one({"_id": gid})  # refresh
    p1, p2 = game["players"]
    hp1 = game["hp"][str(p1)]
    hp2 = game["hp"][str(p2)]
    kb = make_action_kb(gid, game["turn"])
    await query.message.edit_text(
        f"⚔️ <b>Battle Started</b>\n\n"
        f"{await mention(p1)} — HP: {hp1}\n"
        f"{await mention(p2)} — HP: {hp2}\n\n"
        f"Turn: {await mention(game['turn'])}",
        reply_markup=kb
    )
    await query.answer("Battle started!")

@app.on_callback_query(filters.regex(r"^pvp_decline\|"))
async def decline_cb(_, query: CallbackQuery):
    _, gid, expected_uid = query.data.split("|")
    expected_uid = int(expected_uid)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game no longer exists.", show_alert=True)
    if query.from_user.id != expected_uid:
        return await query.answer("Only the challenged user can decline.", show_alert=True)

    await games.delete_one({"_id": gid})
    await query.message.edit_text("❌ Battle declined.")
    await query.answer("Declined.")

# ---------- Core Actions: Attack, Heal, Resign ----------
async def resolve_attack(game: Dict[str, Any], attacker_id: int, defender_id: int) -> Dict[str, Any]:
    """Apply attack logic: crit, dodge, shield. Return dict with result text and updated game."""
    buffs = game.get("buffs", {"shield": {}})
    hp = game["hp"]
    # Dodge
    dodge = random.random() < 0.15
    if dodge:
        text = f"😎 {await mention(defender_id)} dodged the attack!"
        dmg = 0
    else:
        dmg = random.randint(15, 25)
        crit = random.random() < 0.20
        if crit:
            dmg *= 2
            text = f"🔥 <b>CRITICAL!</b> {await mention(attacker_id)} dealt {dmg} damage!"
        else:
            text = f"💥 {await mention(attacker_id)} attacked and dealt {dmg} damage!"

        # Apply defender's shield if present
        if str(defender_id) in buffs.get("shield", {}) and buffs["shield"].get(str(defender_id), False):
            reduced = dmg // 2
            text += f"\n🛡️ Shield reduced damage {dmg} → {reduced}."
            dmg = reduced
            # consume shield
            buffs["shield"][str(defender_id)] = False

    hp[str(defender_id)] -= dmg
    # add log entry
    game["log"].append({
        "time": datetime.utcnow(),
        "action": "attack",
        "by": attacker_id,
        "to": defender_id,
        "damage": int(dmg),
        "dodge": dodge
    })
    game["hp"] = hp
    game["buffs"] = buffs
    return {"text": text, "game": game, "dmg": int(dmg)}

@app.on_callback_query(filters.regex(r"^pvp_attack\|"))
async def attack_cb(_, query: CallbackQuery):
    _, gid, uid_s = query.data.split("|")
    uid = int(uid_s)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("This game no longer exists.", show_alert=True)

    if game["status"] != "active":
        return await query.answer("Game is not active.", show_alert=True)

    if uid != query.from_user.id:
        return await query.answer("This button is not for you.", show_alert=True)

    if game["turn"] != uid:
        return await query.answer("Not your turn.", show_alert=True)

    p1, p2 = game["players"]
    attacker = uid
    defender = p1 if p2 == attacker else p2

    # Resolve attack
    res = await resolve_attack(game, attacker, defender)
    game = res["game"]
    dmg = res["dmg"]
    text = res["text"]

    # Check for win
    if game["hp"][str(defender)] <= 0:
        # attacker wins
        await games.delete_one({"_id": gid})
        # stats + rewards
        await inc_player(attacker, "wins")
        await inc_player(defender, "losses")
        await add_coins(attacker, 50)
        await grant_xp(attacker, 20)
        await grant_xp(defender, 5)
        # finalize message
        await query.message.edit_text(
            f"{text}\n\n🏆 {await mention(attacker)} wins!\n"
            f"Rewards: +50💰 +20XP"
        )
        return await query.answer("You won!")
    else:
        # switch turn
        next_turn = defender
        game["turn"] = next_turn
        await games.update_one({"_id": gid}, {"$set": {"hp": game["hp"], "turn": next_turn, "buffs": game["buffs"], "log": game["log"]}})
        kb = make_action_kb(gid, next_turn)
        await query.message.edit_text(
            f"{text}\n\n❤️ HP: {game['hp'][str(p1)]} vs {game['hp'][str(p2)]}\n\n"
            f"Turn: {await mention(next_turn)}",
            reply_markup=kb
        )
        return await query.answer("Attack done.")

@app.on_callback_query(filters.regex(r"^pvp_heal\|"))
async def heal_cb(_, query: CallbackQuery):
    _, gid, uid_s = query.data.split("|")
    uid = int(uid_s)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.", show_alert=True)
    if game["status"] != "active":
        return await query.answer("Game not active.", show_alert=True)
    if uid != query.from_user.id:
        return await query.answer("Button not for you.", show_alert=True)
    if game["turn"] != uid:
        return await query.answer("Not your turn.", show_alert=True)

    heal = random.randint(10, 20)
    game["hp"][str(uid)] = min(100, game["hp"][str(uid)] + heal)
    # log
    game["log"].append({"time": datetime.utcnow(), "action": "heal", "by": uid, "heal": int(heal)})
    # switch turn
    next_turn = game["players"][0] if uid == game["players"][1] else game["players"][1]
    game["turn"] = next_turn
    await games.update_one({"_id": gid}, {"$set": {"hp": game["hp"], "turn": next_turn, "log": game["log"]}})
    kb = make_action_kb(gid, next_turn)
    await query.message.edit_text(
        f"💖 {await mention(uid)} healed +{heal} HP!\n\n❤️ HP: {game['hp'][str(game['players'][0])]} vs {game['hp'][str(game['players'][1])]} \n\nTurn: {await mention(next_turn)}",
        reply_markup=kb
    )
    return await query.answer("Healed.")

@app.on_callback_query(filters.regex(r"^pvp_resign\|"))
async def resign_cb(_, query: CallbackQuery):
    _, gid, uid_s = query.data.split("|")
    uid = int(uid_s)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.")
    if uid != query.from_user.id:
        return await query.answer("Button not for you.")
    # opponent wins
    p1, p2 = game["players"]
    winner = p1 if uid == p2 else p2
    await games.delete_one({"_id": gid})
    await inc_player(winner, "wins")
    await inc_player(uid, "losses")
    await add_coins(winner, 50)
    await grant_xp(winner, 20)
    await query.message.edit_text(
        f"🏳️ {await mention(uid)} resigned.\n\n🏆 Winner: {await mention(winner)} (+50💰 +20XP)"
    )
    return await query.answer("You resigned.")

# ---------- Item Usage Flow ----------
@app.on_callback_query(filters.regex(r"^pvp_useitem_menu\|"))
async def useitem_menu_cb(_, query: CallbackQuery):
    _, gid, uid_s = query.data.split("|")
    uid = int(uid_s)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.", show_alert=True)
    if query.from_user.id != uid:
        return await query.answer("This menu is for the current player only.", show_alert=True)
    if game["turn"] != uid:
        return await query.answer("Not your turn.", show_alert=True)

    # Fetch player's inventory to show available items
    p = await ensure_player(uid)
    items = p.get("items", {})
    buttons = []
    for key, meta in SHOP_CATALOG.items():
        cnt = items.get(key, 0)
        label = f"{key} ({cnt})"
        buttons.append(InlineKeyboardButton(label, callback_data=f"pvp_useitem|{gid}|{uid}|{key}"))
    if not buttons:
        return await query.answer("You have no items.", show_alert=True)

    # create keyboard in rows (one per item)
    kb_rows = [[b] for b in buttons] + [[InlineKeyboardButton("↩️ Back", callback_data=f"pvp_back_action|{gid}|{uid}")]]
    kb = InlineKeyboardMarkup(kb_rows)
    await query.answer()  # remove loading
    await query.message.edit_reply_markup(reply_markup=kb)

@app.on_callback_query(filters.regex(r"^pvp_back_action\|"))
async def back_action_cb(_, query: CallbackQuery):
    _, gid, uid_s = query.data.split("|")
    uid = int(uid_s)
    kb = make_action_kb(gid, uid)
    await query.message.edit_reply_markup(reply_markup=kb)
    await query.answer()

@app.on_callback_query(filters.regex(r"^pvp_useitem\|"))
async def useitem_cb(_, query: CallbackQuery):
    _, gid, uid_s, item_key = query.data.split("|")
    uid = int(uid_s)
    game = await games.find_one({"_id": gid})
    if not game:
        return await query.answer("Game missing.", show_alert=True)
    if query.from_user.id != uid:
        return await query.answer("Button not for you.", show_alert=True)
    if game["turn"] != uid:
        return await query.answer("Not your turn.", show_alert=True)

    # confirm item exists in catalog
    if item_key not in SHOP_CATALOG:
        return await query.answer("Unknown item.", show_alert=True)

    # check inventory and remove
    success = await remove_item(uid, item_key, 1)
    if not success:
        return await query.answer("You don't have that item.", show_alert=True)

    p1, p2 = game["players"]
    owner = uid
    opponent = p1 if p2 == owner else p2

    # apply item effects
    msg = ""
    if item_key == "potion":
        heal = 30
        game["hp"][str(owner)] = min(100, game["hp"][str(owner)] + heal)
        msg = f"💊 {await mention(owner)} used a Potion and recovered +{heal} HP!"
        game["log"].append({"time": datetime.utcnow(), "action": "use_potion", "by": owner, "heal": heal})
    elif item_key == "shield":
        # activate shield buff for owner (halves next incoming damage)
        game.setdefault("buffs", {}).setdefault("shield", {})[str(owner)] = True
        msg = f"🛡️ {await mention(owner)} used a Shield! Next incoming damage will be halved."
        game["log"].append({"time": datetime.utcnow(), "action": "use_shield", "by": owner})
    elif item_key == "bomb":
        dmg = 40
        # bombs can be dodged too by defender (apply dodge)
        dodge = random.random() < 0.15
        if dodge:
            dmg = 0
            msg = f"💣 {await mention(owner)} used a Bomb but {await mention(opponent)} dodged it!"
        else:
            # apply defender shield
            if str(opponent) in game.get("buffs", {}).get("shield", {}) and game["buffs"]["shield"].get(str(opponent), False):
                reduced = dmg // 2
                game["buffs"]["shield"][str(opponent)] = False
                dmg = reduced
                msg = f"💣 Bomb hit but shield reduced damage to {dmg}!"
            else:
                msg = f"💣 {await mention(owner)} used a Bomb and dealt {dmg} damage to {await mention(opponent)}!"
            game["hp"][str(opponent)] -= dmg
        game["log"].append({"time": datetime.utcnow(), "action": "use_bomb", "by": owner, "damage": int(dmg)})
    else:
        msg = f"Used {item_key}"

    # Check if bomb killed opponent
    if game["hp"][str(opponent)] <= 0:
        # owner wins immediately
        await games.delete_one({"_id": gid})
        await inc_player(owner, "wins")
        await inc_player(opponent, "losses")
        await add_coins(owner, 50)
        await grant_xp(owner, 20)
        await query.message.edit_text(f"{msg}\n\n🏆 {await mention(owner)} wins! (+50💰 +20XP)")
        return await query.answer("⚔️You won!")

    # After using an item, switch turn to opponent
    next_turn = opponent
    game["turn"] = next_turn
    await games.update_one({"_id": gid}, {"$set": {"hp": game["hp"], "turn": next_turn, "buffs": game.get("buffs", {}), "log": game["log"]}})
    kb = make_action_kb(gid, next_turn)
    await query.message.edit_text(
        f"{msg}\n\n❤️ HP: {game['hp'][str(p1)]} vs {game['hp'][str(p2)]}\n\nTurn: {await mention(next_turn)}",
        reply_markup=kb
    )
    return await query.answer("Item used.")

# ---------- Shop Commands ----------
@app.on_message(filters.command("shop"))
async def shop_cmd(_, message: Message):
    text = "<b>🛒 Shop</b>\n\n"
    for key, meta in SHOP_CATALOG.items():
        text += f"{key} — {meta['price']}💰 — {meta['desc']}\n"
    text += "\nBuy with: /buy <item_key>\nCheck your inventory: /inventory"
    await message.reply_text(text)

@app.on_message(filters.command("buy"))
async def buy_cmd(_, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /buy <item_key>")
    item = parts[1].strip().lower()
    if item not in SHOP_CATALOG:
        return await message.reply_text("Unknown item key. Use /shop to see items.")
    uid = message.from_user.id
    await ensure_player(uid)
    cost = SHOP_CATALOG[item]["price"]
    p = await players.find_one({"_id": uid})
    if p.get("coins", 0) < cost:
        return await message.reply_text("Not enough coins.")
    # deduct and add item
    await players.update_one({"_id": uid}, {"$inc": {"coins": -cost, f"items.{item}": 1}})
    await message.reply_text(f"✅ Purchased 1 {item} for {cost}💰. Use in-battle with Use Item button.")

@app.on_message(filters.command("inventory"))
async def inventory_cmd(_, message: Message):
    uid = message.from_user.id
    p = await ensure_player(uid)
    items = p.get("items", {})
    if not items:
        return await message.reply_text("Your inventory is empty. Visit /shop to buy items.")
    text = "<b>🎒 Inventory</b>\n\n"
    for k, v in items.items():
        text += f"{k}: {v}\n"
    text += f"\nCoins: {p.get('coins',0)} 💰\nXP: {p.get('xp',0)} (Lvl {compute_level(p.get('xp',0))})"
    await message.reply_text(text)

# ---------- Profile & Leaderboard ----------
@app.on_message(filters.command("b_profile"))
async def profile_bcmd(_, message: Message):
    uid = message.from_user.id
    p = await ensure_player(uid)
    total = p["wins"] + p["losses"] + p["draws"]
    win_rate = round((p["wins"] / total) * 100, 1) if total else 0
    level = compute_level(p.get("xp", 0))
    text = (
        f"👤 <b>{message.from_user.first_name}'s Profile</b>\n\n"
        f"🏆 Wins: {p['wins']}\n❌ Losses: {p['losses']}\n🤝 Draws: {p['draws']}\n"
        f"⚡ Win Rate: {win_rate}%\n✨ XP: {p.get('xp',0)} (Lvl {level})\n💰 Coins: {p.get('coins',0)}\n"
        f"🎒 Items: {', '.join([f'{k}×{v}' for k,v in p.get('items',{}).items()]) if p.get('items') else 'None'}"
    )
    await message.reply_text(text)

@app.on_message(filters.command("b_leaderboard")) # & (filters.group | filters.private)
async def leaderboard_bcmd(_, message: Message):
    # global leaderboard sorted by wins
    cursor = players.find().sort("wins", -1).limit(10)
    text = "🏆 <b>Leaderboard — Top players (by wins)</b>\n\n"
    i = 1
    async for p in cursor:
        try:
            u = await app.get_users(p["_id"])
            name = u.first_name
        except:
            name = f"User({p['_id']})"
        text += f"{i}. {name} — {p.get('wins',0)}W / {p.get('losses',0)}L / {p.get('draws',0)}D — {p.get('coins',0)}💰\n"
        i += 1
    if i == 1:
        text += "No players yet."
    await message.reply_text(text)

# ---------- Admin / Utility: restore lingering games (optional) ----------
# You can implement scheduled cleanup / timeouts for games (auto-forfeit after inactivity).
# For brevity this file does not include scheduler code, but it's straightforward to add.
