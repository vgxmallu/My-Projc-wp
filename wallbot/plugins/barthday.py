import asyncio
from datetime import datetime
from pyrogram import Client, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app
# ========================
# DATABASE
# ========================
mongo = MongoClient(DB_URL)
db = mongo["birthday_bot"]
birthdays = db["birthdays"]
scheduler = AsyncIOScheduler()

# Save birthday command
@app.on_message(filters.command("mybirthday") & filters.group)
async def set_bifgrthday(client, message):
    try:
        if len(message.command) < 2:
            return await message.reply("❌ Usage: `/mybirthday dd.mm.yyyy`", quote=True)
        
        bday_str = message.command[1]
        try:
            bday = datetime.strptime(bday_str, "%d.%m.%Y")
        except ValueError:
            return await message.reply("⚠️ Please use format: `dd.mm.yyyy`", quote=True)

        user_id = message.from_user.id
        chat_id = message.chat.id

        birthdays.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"birthday": bday_str, "name": message.from_user.first_name}},
            upsert=True
        )
        await message.reply(f"✅ Birthday saved for {message.from_user.first_name}: 🎂 {bday_str}")
    except Exception as e:
        await message.reply(f"Error: {e}")

# Daily check for birthdays
async def check_birthdays():
    today = datetime.now().strftime("%d.%m")
    for record in birthdays.find():
        bday = record["birthday"]
        if bday[:5] == today:  # match day + month only
            chat_id = record["chat_id"]
            name = record["name"]
            try:
                await app.send_message(chat_id, f"🎉 Happy Birthday, {name}! 🎂🎈🥳")
            except Exception as e:
                print(f"Error sending message: {e}")

# Start scheduler
scheduler.add_job(lambda: asyncio.create_task(check_birthdays()), "cron", hour=0, minute=0)
scheduler.start()


