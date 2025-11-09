"""
OwO-Style Telegram Bot (Pyrogram + Motor)
Features implemented:
- Economy: /cowoncy, /daily, /give
- Animals: /hunt, /zoo, /autohunt, /owodex, /pets
- Gambling: /slots, /coinflip, /lottery, /blackjack
- Fun: /8b
- Rankings: /top, /my
- Social: /cookie
- Actions: /hug, /kiss, /pat, /slap
- Shop & selling: /shop, /buy, /sell, /equip
- Battle: reply-to-user /battle to challenge (simple)
- MongoDB persistence (MONGO_URI)
Usage:
- Set environment variables: API_ID, API_HASH, BOT_TOKEN, MONGO_URI
- Run: python owobot_full.py
"""

import os
import random
import asyncio
import datetime
from typing import Dict, Any
from pyrogram import Client, filters, idle
from pyrogram.types import Message
import motor.motor_asyncio
from config import DB_URL
from main import wbot as app

DB_NAME = "owo_db"


mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

users_col = db["users"]      # one doc per user: economy, inventory, pets, meta
groups_col = db["groups"]    # group settings if needed
# Optional: other collections for lotteries, ledger etc.

# ---------------- DATA ----------------
#ANIMALS = ["Dog", "Cat", "Rabbit", "Panda", "Tiger", "Monkey", "Penguin", "Rabbit", "Lion"]
#ANIMAL_EMOJI = {
#    "Dog": "🐶", "Cat": "🐱", "Fox": "🦊", "Panda": "🐼", "Tiger": "🐯",
#    "Monkey": "🐵", "Penguin": "🐧", "Rabbit": "🐰", "Lion": "🦁"
#}

ANIMALS = [
    # Common
    "Dog", "Cat", "Rabbit", "Fox", "Mouse", "Horse", "Sheep", "Cow", "Pig", "Chicken",
    # Wild
    "Wolf", "Bear", "Tiger", "Lion", "Elephant", "Giraffe", "Kangaroo", "Panda", "Monkey", "Deer", "Camel",
    # Birds
    "Owl", "Eagle", "Penguin", "Duck", "Peacock", "Parrot", "Turkey", "Swan", "Flamingo",
    # Aquatic
    "Dolphin", "Shark", "Whale", "Seal", "Octopus", "Crab", "Lobster", "Turtle", "Frog", "Fish", "Blowfish",
    # Rare / Mythical
    "Dragon", "Unicorn", "Phoenix", "Griffin", "Kraken", "Cerberus"
]

ANIMAL_EMOJI = {
    # Common
    "Dog": "🐶", "Cat": "🐱", "Rabbit": "🐰", "Fox": "🦊", "Mouse": "🐭",
    "Horse": "🐴", "Sheep": "🐑", "Cow": "🐮", "Pig": "🐷", "Chicken": "🐔",
    # Wild
    "Wolf": "🐺", "Bear": "🐻", "Tiger": "🐯", "Lion": "🦁", "Elephant": "🐘",
    "Giraffe": "🦒", "Kangaroo": "🦘", "Panda": "🐼", "Monkey": "🐵", "Deer": "🦌", "Camel": "🐫",
    # Birds
    "Owl": "🦉", "Eagle": "🦅", "Penguin": "🐧", "Duck": "🦆", "Peacock": "🦚",
    "Parrot": "🦜", "Turkey": "🦃", "Swan": "🦢", "Flamingo": "🦩",
    # Aquatic
    "Dolphin": "🐬", "Shark": "🦈", "Whale": "🐋", "Seal": "🦭",
    "Octopus": "🐙", "Crab": "🦀", "Lobster": "🦞", "Turtle": "🐢",
    "Frog": "🐸", "Fish": "🐟", "Blowfish": "🐡",
    # Rare / Mythical
    "Dragon": "🐉", "Unicorn": "🦄", "Phoenix": "🔥", "Griffin": "🪽",
    "Kraken": "🌊", "Cerberus": "👹"
}



SHOP = {
    "pokeball": {"name": "Poké Ball", "price": 50, "type": "item"},
    "greatball": {"name": "Great Ball", "price": 150, "type": "item"},
    "ultraball": {"name": "Ultra Ball", "price": 450, "type": "item"},
    "auto_hunter": {"name": "Auto Hunter (30m)", "price": 500, "type": "service"},
    "pet_collar": {"name": "Pet Collar (equip)", "price": 200, "type": "equip"},
}

EIGHTBALL = ["Yes", "No", "Maybe", "Ask later", "Absolutely!", "Nope", "Certainly", "Not sure"]

# ---------------- HELPERS ----------------
async def ensure_user(user) -> Dict[str, Any]:
    """Ensure user document exists and return it."""
    doc = await users_col.find_one({"user_id": user.id})
    if not doc:
        doc = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "cowoncy": 200,
            "inventory": {},        # e.g. {"pokeball": 3, "Dog": 1}
            "pets": {},             # pet_name -> count or list of pet dicts
            "equipped": None,       # equipped pet key (string)
            "daily_claimed": None,  # iso date string
            "created_at": datetime.datetime.utcnow(),
            "last_hunt": None,
            "last_autohunt": None,
            "stats": {"hunts": 0, "wins": 0, "losses": 0}
        }
        await users_col.insert_one(doc)
    return doc

async def update_user(user_id, update: Dict):
    await users_col.update_one({"user_id": user_id}, {"$set": update}, upsert=True)

async def inc_user(user_id, field: str, amount: int = 1):
    await users_col.update_one({"user_id": user_id}, {"$inc": {field: amount}}, upsert=True)

def today_iso():
    return datetime.date.today().isoformat()

def parse_amount(s: str):
    try:
        return int(s)
    except Exception:
        return None

# ---------------- ECONOMY ----------------
@app.on_message(filters.command("cowoncy"))
async def cmd_coowwoncy(_, m: Message):
    u = await ensure_user(m.from_user)
    await m.reply(f"💰 You have **{u['cowoncy']}** cowoncy.", quote=True)

@app.on_message(filters.command("daily_owo"))
async def cmd_dowaily(_, m: Message):
    u = await ensure_user(m.from_user)
    today = today_iso()
    if u.get("daily_claimed") == today:
        return await m.reply("❌ You already claimed your daily reward today.", quote=True)
    reward = random.randint(50, 150)
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": reward}, "$set": {"daily_claimed": today}})
    await m.reply(f"✅ You claimed daily reward: **{reward}** cowoncy.", quote=True)

@app.on_message(filters.command("give_owo"))
async def cmd_gwowive(_, m: Message):
    # usage: reply to user with /give <amount>
    if not m.reply_to_message:
        return await m.reply("Reply to a user's message and use `/giveowo [amount]`", quote=True)
    if len(m.command) < 2:
        return await m.reply("Usage: `/giveowo [amount]`", quote=True)
    amt = parse_amount(m.command[1])
    if amt is None or amt <= 0:
        return await m.reply("Invalid amount.", quote=True)
    giver = await ensure_user(m.from_user)
    if giver["cowoncy"] < amt:
        return await m.reply("You don't have enough cowoncy.", quote=True)
    receiver = await ensure_user(m.reply_to_message.from_user)
    await users_col.update_one({"user_id": giver["user_id"]}, {"$inc": {"cowoncy": -amt}})
    await users_col.update_one({"user_id": receiver["user_id"]}, {"$inc": {"cowoncy": amt}})
    await m.reply(f"🎁 {m.from_user.first_name} gave **{amt}** cowoncy to {m.reply_to_message.from_user.first_name}!", quote=True)

# ---------------- ANIMALS ----------------
@app.on_message(filters.command("hunt_owo"))
async def cmd_howunt(_, m: Message):
    u = await ensure_user(m.from_user)
    # basic cooldown: 10s
    now = datetime.datetime.utcnow()
    if u.get("last_hunt"):
        last = u["last_hunt"]
        if (now - last).total_seconds() < 8:
            return await m.reply("⏳ You're hunting too fast — wait a few seconds.", quote=True)
    animal = random.choice(ANIMALS)
    emoji = ANIMAL_EMOJI.get(animal, "")
    # update inventory and stats
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {f"inventory.{animal}": 1, "stats.hunts": 1}, "$set": {"last_hunt": now}})
    await m.reply(f"🌲 You hunted and found **{animal}** {emoji}!", quote=True)

@app.on_message(filters.command("zoo_owo"))
async def cmd_owzoo(_, m: Message):
    u = await ensure_user(m.from_user)
    inv = u.get("inventory", {}) or {}
    text = "🦁 **Your Zoo**\n\n"
    if not inv:
        text += "Your zoo is empty. Try `/hunt_owo` to find animals."
        return await m.reply(text, quote=True)
    for a, qty in inv.items():
        if qty and qty > 0:
            emoji = ANIMAL_EMOJI.get(a, "")
            text += f"{emoji} {a} × {qty}\n"
    await m.reply(text, quote=True)

@app.on_message(filters.command("owodex"))
async def cmd_owodex(_, m: Message):
    text = "📖 **Owodex** — available animals:\n\n"
    for a in ANIMALS:
        text += f"{ANIMAL_EMOJI.get(a,'')} {a}\n"
    await m.reply(text, quote=True)

@app.on_message(filters.command("autohunt"))
async def cmd_autwohunt(_, m: Message):
    # rapid multiple hunts: 2-6 animals
    u = await ensure_user(m.from_user)
    # check coins cost or cooldown: we'll charge a small fee for auto
    cost = 20
    if u["cowoncy"] < cost:
        return await m.reply(f"Auto-hunt costs {cost} cowoncy. You have {u['cowoncy']}.", quote=True)
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -cost}})
    count = random.randint(2, 6)
    found = {}
    for _ in range(count):
        a = random.choice(ANIMALS)
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {f"inventory.{a}": 1, "stats.hunts": 1}})
        found[a] = found.get(a, 0) + 1
    text = "🤖 **Autohunt Results**\n"
    for k, v in found.items():
        text += f"{ANIMAL_EMOJI.get(k,'')} {k} × {v}\n"
    await m.reply(text, quote=True)

@app.on_message(filters.command("pets_owo"))
async def cmdhr_pets(_, m: Message):
    u = await ensure_user(m.from_user)
    equipped = u.get("equipped")
    text = "🐾 **Pets & Equipped**\n\n"
    if equipped:
        text += f"Equipped: {ANIMAL_EMOJI.get(equipped,'')} {equipped}\n\n"
    inv = u.get("inventory", {}) or {}
    if not inv:
        text += "You have no animals. Use `/hunt_owo`."
    else:
        text += "Inventory:\n"
        for a, qty in inv.items():
            if qty and qty > 0:
                text += f"{ANIMAL_EMOJI.get(a,'')} {a} × {qty}\n"
    await m.reply(text, quote=True)

# ---------------- SHOP / BUY / SELL / EQUIP ----------------
@app.on_message(filters.command("shop_owo"))
async def cmd_owshop(_, m: Message):
    text = "🛒 **Shop**\n\n"
    for key, info in SHOP.items():
        text += f"`{key}` — {info['name']} — {info['price']} cowoncy\n"
    text += "\nBuy with `/buy_owo [item_key] [qty]`"
    await m.reply(text, quote=True)

@app.on_message(filters.command("buy_owo"))
async def cmdow_buy(_, m: Message):
    if len(m.command) < 2:
        return await m.reply("Usage: `/buy_owo [item_key] [qty]`", quote=True)
    key = m.command[1].lower()
    qty = int(m.command[2]) if len(m.command) > 2 and m.command[2].isdigit() else 1
    if key not in SHOP:
        return await m.reply("Item not found in the shop.", quote=True)
    total = SHOP[key]["price"] * qty
    u = await ensure_user(m.from_user)
    if u["cowoncy"] < total:
        return await m.reply(f"You don't have enough cowoncy. Need {total}.", quote=True)
    # deduct coins and add to inventory (or apply service)
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -total, f"inventory.{key}": qty}})
    await m.reply(f"✅ You bought {qty} x {SHOP[key]['name']} for {total} cowoncy.", quote=True)

@app.on_message(filters.command("sell_owo"))
async def cmhdd_seloel(_, m: Message):
    # /sell <animal> <qty>
    if len(m.command) < 3:
        return await m.reply("Usage: `/sell_owo [animal] [qty[` (animal name exactly as in /owodex)", quote=True)
    animal = m.command[1]
    qty = parse_amount(m.command[2])
    if qty is None or qty <= 0:
        return await m.reply("Invalid quantity.", quote=True)
    u = await ensure_user(m.from_user)
    inv = u.get("inventory", {})
    have = inv.get(animal, 0)
    if have < qty:
        return await m.reply(f"You only have {have} {animal}.", quote=True)
    price_per = 25
    total = price_per * qty
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": total, f"inventory.{animal}": -qty}})
    await m.reply(f"💰 Sold {qty} {animal} for {total} cowoncy.", quote=True)

@app.on_message(filters.command("equip_owo"))
async def cmdje_equip(_, m: Message):
    # /equip <animal> will set it as active pet if you own it
    if len(m.command) < 2:
        return await m.reply("Usage: `/equip_owo [animal]`", quote=True)
    animal = m.command[1]
    u = await ensure_user(m.from_user)
    inv = u.get("inventory", {})
    if inv.get(animal, 0) <= 0:
        return await m.reply(f"You don't own any {animal}.", quote=True)
    await users_col.update_one({"user_id": u["user_id"]}, {"$set": {"equipped": animal}})
    await m.reply(f"✅ Equipped {ANIMAL_EMOJI.get(animal,'')} {animal} as your active pet.", quote=True)

# ---------------- BATTLE ----------------
@app.on_message(filters.command("battle_owo"))
async def cmdbr_battle(_, m: Message):
    # reply-to-user to battle them using equipped pet (simple)
    if not m.reply_to_message:
        return await m.reply("Reply to a user's message to battle them. Usage: reply with /battle_owo", quote=True)
    challenger = await ensure_user(m.from_user)
    opponent_user = m.reply_to_message.from_user
    opponent = await ensure_user(opponent_user)
    ch_pet = challenger.get("equipped")
    op_pet = opponent.get("equipped")
    if not ch_pet:
        return await m.reply("You have no equipped pet. Use `/equip_owo <animal>`.", quote=True)
    if not op_pet:
        return await m.reply(f"{opponent_user.first_name} has no equipped pet.", quote=True)
    # Compute simple power = random + pet_count + small advantage for equipped
    ch_count = challenger.get("inventory", {}).get(ch_pet, 0)
    op_count = opponent.get("inventory", {}).get(op_pet, 0)
    ch_power = ch_count * random.randint(1, 6) + random.randint(1, 10)
    op_power = op_count * random.randint(1, 6) + random.randint(1, 10)
    if ch_power == op_power:
        result = f"⚔️ It's a tie! Both fought bravely. ({ch_power} vs {op_power})"
    elif ch_power > op_power:
        result = f"🏆 {m.from_user.first_name}'s {ch_pet} defeated {opponent_user.first_name}'s {op_pet}! ({ch_power} vs {op_power})"
        await users_col.update_one({"user_id": m.from_user.id}, {"$inc": {"stats.wins": 1, "cowoncy": 20}})
        await users_col.update_one({"user_id": opponent_user.id}, {"$inc": {"stats.losses": 1}})
    else:
        result = f"🏆 {opponent_user.first_name}'s {op_pet} defeated {m.from_user.first_name}'s {ch_pet}! ({op_power} vs {ch_power})"
        await users_col.update_one({"user_id": opponent_user.id}, {"$inc": {"stats.wins": 1, "cowoncy": 20}})
        await users_col.update_one({"user_id": m.from_user.id}, {"$inc": {"stats.losses": 1}})
    await m.reply(result, quote=True)

# ---------------- GAMBLING ----------------
@app.on_message(filters.command("slots_owo"))
async def cmd_dnslots(_, m: Message):
    u = await ensure_user(m.from_user)
    cost = 10
    if u["cowoncy"] < cost:
        return await m.reply("You need at least 10 cowoncy to play slots.", quote=True)
    icons = ["🍒", "🍋", "🍇", "🍉", "⭐", "7️⃣"]
    result = [random.choice(icons) for _ in range(3)]
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -cost}})
    if len(set(result)) == 1:
        win = 100
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": win}})
        await m.reply(f"🎰 {' | '.join(result)}\nJACKPOT! +{win} cowoncy", quote=True)
    elif len(set(result)) == 2:
        win = 20
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": win}})
        await m.reply(f"🎰 {' | '.join(result)}\nNice! +{win} cowoncy", quote=True)
    else:
        await m.reply(f"🎰 {' | '.join(result)}\nBetter luck next time.", quote=True)

@app.on_message(filters.command("coinflip_owo"))
async def cmd_ecoinowflip(_, m: Message):
    if len(m.command) < 3:
        return await m.reply("Usage: `/coinflip_owo [heads/tails] [amount]`", quote=True)
    choice = m.command[1].lower()
    bet = parse_amount(m.command[2])
    if bet is None or bet <= 0:
        return await m.reply("Invalid bet amount.", quote=True)
    u = await ensure_user(m.from_user)
    if u["cowoncy"] < bet:
        return await m.reply("You don't have enough cowoncy.", quote=True)
    outcome = random.choice(["heads", "tails"])
    if choice == outcome:
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": bet}})
        await m.reply(f"🪙 The coin landed on **{outcome}**. You won **{bet}** cowoncy!", quote=True)
    else:
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -bet}})
        await m.reply(f"🪙 The coin landed on **{outcome}**. You lost **{bet}** cowoncy.", quote=True)

@app.on_message(filters.command("blackjack_owo"))
async def cmd_eoblackjack(_, m: Message):
    u = await ensure_user(m.from_user)
    stake = 20
    if u["cowoncy"] < stake:
        return await m.reply("You need at least 20 cowoncy to play blackjack.", quote=True)
    player = random.randint(15, 23)
    dealer = random.randint(16, 23)
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -stake}})
    if player > 21:
        await m.reply(f"🃏 You busted with {player}. Dealer had {dealer}. You lose {stake} cowoncy.", quote=True)
    elif dealer > 21 or player > dealer:
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": stake * 2}})
        await m.reply(f"🃏 You {player} vs Dealer {dealer}. You win {stake*2} cowoncy!", quote=True)
    elif player == dealer:
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": stake}})
        await m.reply(f"🃏 Tie! You both had {player}. Bet refunded.", quote=True)
    else:
        await m.reply(f"🃏 You {player} vs Dealer {dealer}. You lose {stake} cowoncy.", quote=True)

@app.on_message(filters.command("lottery_owo"))
async def cmd_lwoottery(_, m: Message):
    u = await ensure_user(m.from_user)
    ticket_cost = 50
    if u["cowoncy"] < ticket_cost:
        return await m.reply(f"🎟️ Ticket costs {ticket_cost} cowoncy.", quote=True)
    await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": -ticket_cost}})
    roll = random.randint(1, 100)
    if roll == 100:
        prize = 1000
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": prize}})
        await m.reply("🎉 JACKPOT! You won 1000 cowoncy!", quote=True)
    elif roll > 90:
        prize = 200
        await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {"cowoncy": prize}})
        await m.reply("🎉 You won 200 cowoncy!", quote=True)
    else:
        await m.reply("😢 You lost the lottery.", quote=True)

# ---------------- FUN / EIGHTBALL ----------------
@app.on_message(filters.command("8b"))
async def cmd_eightball(_, m: Message):
    await m.reply(f"🎱 {random.choice(EIGHTBALL)}", quote=True)

# ---------------- SOCIAL ----------------
@app.on_message(filters.command("cookie"))
async def cmd_cowokie(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("Reply to someone to give them a cookie. `/cookie`", quote=True)
    giver = m.from_user.first_name
    receiver = m.reply_to_message.from_user.first_name
    await m.reply(f"🍪 {giver} gave a cookie to {receiver}!", quote=True)

# ---------------- ACTIONS ----------------
ACTIONS = ["hug", "kiss", "pat", "slap", "cuddle", "poke"]
@app.on_message(filters.command(ACTIONS))
async def cmd_action(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("Reply to someone to perform this action.", quote=True)
    action = m.command[0]
    a = m.from_user.first_name
    b = m.reply_to_message.from_user.first_name
    await m.reply(f"{a} {action}s {b}! ❤️", quote=True)

# ---------------- RANKINGS ----------------
@app.on_message(filters.command("top_owo"))
async def cmd_toeop(_, m: Message):
    cursor = users_col.find({}).sort("cowoncy", -1).limit(10)
    text = "🏆 Top cowoncy holders:\n\n"
    i = 1
    async for u in cursor:
        name = u.get("username") or f"user{u.get('user_id')}"
        text += f"{i}. {name} — {u.get('cowoncy',0)} cowoncy\n"
        i += 1
    await m.reply(text, quote=True)

@app.on_message(filters.command("my_owo"))
async def cmd_owmy(_, m: Message):
    u = await ensure_user(m.from_user)
    text = f"👤 {m.from_user.first_name}\nCowoncy: {u['cowoncy']}\nStats: {u.get('stats',{})}\nEquipped: {u.get('equipped')}"
    await m.reply(text, quote=True)

