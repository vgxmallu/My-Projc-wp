
import random
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app
mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["secret_santa"]
events = db["events"]
leaderboard = db["leaderboard"]

# ============== HELPERS ===================
async def get_event(chat_id: int):
    event = await events.find_one({"chat_id": chat_id})
    if not event:
        event = {"chat_id": chat_id, "participants": [], "active": False}
        await events.insert_one(event)
    return event

async def save_event(event: dict):
    await events.update_one({"chat_id": event["chat_id"]}, {"$set": event}, upsert=True)

async def add_to_leaderboard(user_id: int, username: str):
    user = await leaderboard.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "username": username, "participations": 0}
    user["participations"] += 1
    await leaderboard.update_one({"user_id": user_id}, {"$set": user}, upsert=True)

# ============== COMMANDS =================
@app.on_message(filters.command("startsanta"))
async def start(_, message: Message):
    await message.reply(
        "🎅 *Welcome to Secret Santa Bot!*\n\n"
        "Commands:\n"
        "- /createevent – Create a Secret Santa round\n"
        "- /join – Join the current event\n"
        "- /startevent – Assign gifters (admins only)\n"
        "- /leaderboard – Show top participants"
    )

@app.on_message(filters.command("create_santaevent"))
async def createwd_event(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user

    if not user: 
        return
    
    event = await get_event(chat_id)
    event["participants"] = []
    event["active"] = True
    await save_event(event)

    await message.reply("🎁 A new *Secret Santa* round has been created!\nType `/join` to participate!")

@app.on_message(filters.command("joinsanta"))
async def joing_event(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    event = await get_event(chat_id)
    if not event["active"]:
        return await message.reply("❌ No active Secret Santa event here. Ask an admin to use /createevent.")

    if user.id not in [p["user_id"] for p in event["participants"]]:
        event["participants"].append({"user_id": user.id, "username": user.username or user.first_name})
        await save_event(event)
        await message.reply(f"✅ {user.mention} joined the Secret Santa!")
    else:
        await message.reply("⚠️ You already joined this event!")

@app.on_message(filters.command("startsantaevent"))
async def stargt_event(_, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    # Only admins can start
    member = await app.get_chat_member(chat_id, user.id)
    if not member.privileges or not member.privileges.can_manage_chat:
        return await message.reply("❌ Only group admins can start the event.")

    event = await get_event(chat_id)
    participants = event["participants"]

    if len(participants) < 3:
        return await message.reply("⚠️ Need at least 3 participants for Secret Santa!")

    random.shuffle(participants)
    assignments = {}
    for i, giver in enumerate(participants):
        receiver = participants[(i + 1) % len(participants)]
        assignments[giver["user_id"]] = receiver

    # Send DMs privately
    for giver_id, receiver in assignments.items():
        try:
            await app.send_message(
                giver_id,
                f"🎅 *Secret Santa Assignment!*\n\nYou are the Secret Santa for 👉 {receiver['username']}!"
            )
            await add_to_leaderboard(giver_id, receiver["username"])
        except Exception:
            pass  # Ignore if user has no PM enabled

    event["active"] = False
    await save_event(event)
    await message.reply("🎄 Secret Santa assignments have been sent privately! Check your DMs 🎁")

@app.on_message(filters.command("santaleaderboard"))
async def show_lgheaderboard(_, message: Message):
    top = leaderboard.find().sort("participations", -1).limit(10)
    text = "🏆 *Secret Santa Leaderboard* 🎁\n\n"
    i = 1
    async for user in top:
        text += f"{i}. {user['username']} – {user['participations']} times\n"
        i += 1
    await message.reply(text if i > 1 else "No leaderboard data yet!")

