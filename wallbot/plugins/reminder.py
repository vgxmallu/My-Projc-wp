import os
import asyncio
from datetime import datetime, timedelta
import pytz
import uuid

from pyrogram import Client, filters, idle
from pyrogram.types import Message
import motor.motor_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import DB_URL
from wallbot import wbot as app
DB_NAME = os.getenv("DB_NAME", "reminder_db")

mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
reminders_col = db["reminders"]
settings_col = db["settings"]

scheduler = AsyncIOScheduler(timezone="UTC")
scheduler.start()

# ---------------- HELPERS ----------------
async def get_timezone(chat_id: int):
    s = await settings_col.find_one({"chat_id": chat_id})
    return s["timezone"] if s and "timezone" in s else "UTC"

async def add_reminder(chat_id, user_id, text, remind_time, repeat=None):
    reminder_id = str(uuid.uuid4())[:8]
    doc = {
        "reminder_id": reminder_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "time": remind_time,
        "repeat": repeat,
        "created_at": datetime.utcnow()
    }
    await reminders_col.insert_one(doc)

    # Schedule job
    scheduler.add_job(
        send_reminder,
        "date" if not repeat else "interval",
        run_date=remind_time if not repeat else None,
        minutes=repeat if repeat else None,
        args=[doc],
        id=reminder_id,
        replace_existing=True
    )
    return reminder_id

async def send_reminder(doc):
    try:
        await app.send_message(
            doc["chat_id"],
            f"⏰ Reminder ({doc['reminder_id']}):\n{doc['text']}"
        )
        if not doc["repeat"]:
            await reminders_col.delete_one({"reminder_id": doc["reminder_id"]})
    except Exception as e:
        print(f"Error sending reminder: {e}")

# ---------------- COMMANDS ----------------
@app.on_message(filters.command("reminderx"))
async def reminffder_handler(_, m: Message):
    args = m.text.split()
    if len(args) < 2:
        return await m.reply("Usage: `/reminder [add/remove/list/edit]`")

    cmd = args[1].lower()

    if cmd == "add":
        if len(args) < 4:
            return await m.reply("Usage: `/reminder add [minutes_from_now] [text]`")
        minutes = int(args[2])
        text = " ".join(args[3:])
        remind_time = datetime.utcnow() + timedelta(minutes=minutes)
        rid = await add_reminder(m.chat.id, m.from_user.id, text, remind_time)
        await m.reply(f"✅ Reminder added with ID `{rid}` at {remind_time} UTC.")

    elif cmd == "list":
        cursor = reminders_col.find({"chat_id": m.chat.id})
        text = "📋 Active Reminders:\n"
        i = 0
        async for r in cursor:
            tz = await get_timezone(m.chat.id)
            local_time = pytz.utc.localize(r['time']).astimezone(pytz.timezone(tz))
            text += f"- ID: `{r['reminder_id']}` | {local_time} | {r['text']}\n"
            i += 1
        if i == 0:
            text = "No active reminders."
        await m.reply(text)

    elif cmd == "remove":
        if len(args) < 3:
            return await m.reply("Usage: `/reminder remove [reminder_id]`")
        rid = args[2]
        res = await reminders_col.delete_one({"reminder_id": rid})
        scheduler.remove_job(rid) if rid in scheduler.get_jobs() else None
        await m.reply("🗑️ Reminder removed." if res.deleted_count else "❌ Reminder not found.")

    elif cmd == "edit":
        await m.reply("✍️ Edit feature not implemented yet (can be added).")

    elif cmd == "customize":
        await m.reply("✨ Customization coming soon (avatars, colors, etc.).")

@app.on_message(filters.command("resettings"))
async def settffings_handler(_, m: Message):
    args = m.text.split()
    if len(args) < 2:
        return await m.reply("Usage: `/settings timezone [set/view]`")

    sub = args[1].lower()
    if sub == "timezone":
        if len(args) < 3:
            return await m.reply("Usage: `/settings timezone [set/view]`")

        action = args[2].lower()
        if action == "set":
            if len(args) < 4:
                return await m.reply("Usage: `/settings timezone set [Timezone]`\nExample: `/settings timezone set Asia/Kolkata`")
            tz = args[3]
            if tz not in pytz.all_timezones:
                return await m.reply("❌ Invalid timezone. See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
            await settings_col.update_one({"chat_id": m.chat.id}, {"$set": {"timezone": tz}}, upsert=True)
            await m.reply(f"✅ Timezone set to `{tz}`")
        elif action == "view":
            tz = await get_timezone(m.chat.id)
            await m.reply(f"🌍 Current timezone: `{tz}`")

# ---------------- RUN ----------------
