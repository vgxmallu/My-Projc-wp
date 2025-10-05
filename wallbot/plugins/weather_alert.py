import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import os
from dotenv import load_dotenv
from config import DB_URL
from wallbot import wbot as app
load_dotenv()


# Initialize
mongo = AsyncIOMotorClient(DB_URL)
db = mongo["weather_bot"]
subs = db["subscriptions"]  # { chat_id, location (lat,lon or city), alert_conditions: [...], last_alerted: timestamp }

# Helper: fetch weather from Open-Meteo
async def fetch_weather(lat: float, lon: float):
    # Example: current weather, daily forecast
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&current_weather=true&timezone=auto"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    return None

# Helper: parse conditions e.g., check for “rain” or certain weather codes
def check_alerts(weather_json, alert_conditions: list):
    """
    alert_conditions is list of strings, like ["rain", "snow", "storm"]
    weather_json daily weathercode or current weather etc.
    Return list of conditions triggered.
    """
    triggered = []
    # Open-Meteo uses weather codes: e.g., codes for rain, snow etc.
    # For simplicity check current weather description via mapping or code
    current = weather_json.get("current_weather", {})
    wc = current.get("weathercode")
    # very basic mapping (you may expand)
    code_map = {
        "rain": [61, 63, 65, 80, 81, 82],  # some rain codes
        "snow": [71, 73, 75, 85, 86],
        "clear": [0],
        "cloudy": [2,3,4],
        # add more as needed
    }
    for cond in alert_conditions:
        codes = code_map.get(cond.lower())
        if codes and wc in codes:
            triggered.append(cond)
    return triggered

# Commands

@app.on_message(filters.command("wthstart") & filters.private)
async def start_cjjjmd(_, message: Message):
    await message.reply("🌤️ Weather Alert Bot\n\nCommands:\n"
                        "/subscribe <lat> <lon> <conditions> — Subscribe alerts for conditions (comma-separated)\n"
                        "/unsubscribe — Remove subscription\n"
                        "/weather <lat> <lon> — Get current weather\n"
                        "/myalerts — See your subscription")

@app.on_message(filters.command("weather") & filters.private)
async def weather_cmd(_, message: Message):
    if len(message.command) < 3:
        return await message.reply("Usage: /weather <lat> <lon>")
    try:
        lat = float(message.command[1])
        lon = float(message.command[2])
    except ValueError:
        return await message.reply("Invalid latitude/longitude.")
    data = await fetch_weather(lat, lon)
    if not data:
        return await message.reply("Could not fetch weather.")
    cw = data.get("current_weather", {})
    await message.reply(f"🌍 Current Weather at ({lat},{lon}):\n"
                        f"Temperature: {cw.get('temperature')}°C\n"
                        f"Weather Code: {cw.get('weathercode')}")

@app.on_message(filters.command("wsubscribe") & filters.private)
async def subschribe_cmd(_, message: Message):
    if len(message.command) < 4:
        return await message.reply("Usage: /subscribe <lat> <lon> <cond1,cond2,...>\nE.g. /subscribe 12.34 56.78 rain,storm")
    try:
        lat = float(message.command[1])
        lon = float(message.command[2])
    except ValueError:
        return await message.reply("Invalid latitude/longitude.")
    conds = message.command[3].split(",")
    conds = [c.strip().lower() for c in conds if c.strip()]
    await subs.update_one({"user_id": message.from_user.id}, {"$set": {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "latitude": lat,
        "longitude": lon,
        "alert_conditions": conds,
        "last_alerted": None
    }}, upsert=True)
    await message.reply(f"✅ Subscribed for alerts at ({lat},{lon}) for: {', '.join(conds)}")

@app.on_message(filters.command("wunsubscribe") & filters.private)
async def unsubhscribe_cmd(_, message: Message):
    res = await subs.delete_one({"user_id": message.from_user.id})
    if res.deleted_count:
        await message.reply("✅ Unsubscribed from alerts.")
    else:
        await message.reply("ℹ️ You had no active subscription.")

@app.on_message(filters.command("mywalerts") & filters.private)
async def myalerths_cmd(_, message: Message):
    doc = await subs.find_one({"user_id": message.from_user.id})
    if not doc:
        return await message.reply("You have no subscriptions.")
    await message.reply(f"📌 Your alerts:\nLocation: ({doc['latitude']},{doc['longitude']})\nConditions: {', '.join(doc['alert_conditions'])}")

# Background task to check alerts
async def alert_loop():
    while True:
        async for doc in subs.find({}):
            lat = doc.get("latitude")
            lon = doc.get("longitude")
            conds = doc.get("alert_conditions", [])
            data = await fetch_weather(lat, lon)
            if not data:
                continue
            triggered = check_alerts(data, conds)
            if triggered:
                # optionally check last_alerted to avoid spamming
                last = doc.get("last_alerted")
                # For example, alert once every hour
                now = datetime.datetime.utcnow().timestamp()
                if not last or (now - last > 3600):
                    try:
                        await app.send_message(doc["chat_id"], f"🚨 Weather Alert! Condition(s): {', '.join(triggered)} at your location.")
                        await subs.update_one({"user_id": doc["user_id"]}, {"$set": {"last_alerted": now}})
                    except Exception:
                        pass
        await asyncio.sleep(600)  # check every 10 minutes

