#!/usr/bin/env python3
"""
Telegram Flight Price Tracker Bot ✈️
------------------------------------
Track flight prices by route & date.
Uses MongoDB for persistence and Pyrogram for Telegram interaction.

Features:
- /track origin destination date  (e.g. /track DEL BOM 2025-10-22)
- /myflights  - view all tracked routes
- /remove <flight_id>  - remove a tracked flight
- Periodic background check for price drops (mocked random data)
- Data persisted in MongoDB
"""

import os
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
from config import DB_URL
from wallbot import wbot as app
# ---------------- Config ----------------
load_dotenv()

DB_NAME = os.getenv("DB_NAME", "flight_tracker")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FlightTracker")

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

users_col = db["users"]
flights_col = db["flights"]

# ---------------- Utils ----------------
async def ensure_user(uid: int, name: str):
    """Ensure a user exists in DB."""
    user = await users_col.find_one({"user_id": uid})
    if not user:
        await users_col.insert_one({"user_id": uid, "name": name, "created_at": datetime.utcnow()})
    return user

async def fetch_flight_price(origin: str, dest: str, date: str) -> float:
    """
    Simulated flight price fetcher.
    Replace this with real API calls (e.g., Skyscanner, Amadeus, etc.)
    """
    await asyncio.sleep(0.2)
    return round(random.uniform(50, 500), 2)  # random USD price

async def notify_user(user_id: int, text: str):
    try:
        await app.send_message(user_id, text)
    except Exception as e:
        logger.warning(f"Failed to notify {user_id}: {e}")

# ---------------- Commands ----------------
#@app.on_message(filters.command("start"))
async def cmdd_start(_, m: Message):
    await ensure_user(m.from_user.id, m.from_user.first_name)
    await m.reply_text(
        "✈️ *Welcome to Flight Price Tracker!*\n\n"
        "Use `/track DEL BOM 2025-12-20` to track a flight.\n"
        "Commands:\n"
        "• `/track ORG DST YYYY-MM-DD` — Add a flight to track\n"
        "• `/myflights` — View your tracked flights\n"
        "• `/remove <flight_id>` — Stop tracking a flight\n"
        "• `/help` — Show help\n\n"
        "_The bot will notify you if the price drops!_",
        parse_mode="markdown"
    )

#@app.on_message(filters.command("help"))
async def cmdjjhelp(_, m: Message):
    await m.reply_text(
        "📘 *Flight Tracker Help*\n\n"
        "`/track ORG DST YYYY-MM-DD` — Track a flight route (e.g. /track DEL BOM 2025-12-20)\n"
        "`/myflights` — Show your tracked flights\n"
        "`/remove <flight_id>` — Remove a flight from tracking\n"
        "You'll automatically be notified of price drops!",
        parse_mode="markdown"
    )

@app.on_message(filters.command("track_f"))
async def cmd_track(_, m: Message):
    args = m.text.split()
    if len(args) != 4:
        return await m.reply_text("Usage: `/track_f ORG DST YYYY-MM-DD`")
    origin, dest, date = args[1].upper(), args[2].upper(), args[3]
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return await m.reply_text("❌ Invalid date format. Use YYYY-MM-DD.")

    await ensure_user(m.from_user.id, m.from_user.first_name)
    current_price = await fetch_flight_price(origin, dest, date)
    flight_doc = {
        "user_id": m.from_user.id,
        "origin": origin,
        "destination": dest,
        "date": date,
        "last_price": current_price,
        "tracked_since": datetime.utcnow(),
        "last_checked": datetime.utcnow(),
    }
    res = await flights_col.insert_one(flight_doc)
    await m.reply_text(
        f"🛫 Tracking flight *{origin} → {dest}* on *{date}*\n",
        f"Current price: `${current_price}`\n",
        f"Flight ID: `{res.inserted_id}`"
    )

@app.on_message(filters.command("myflights"))
async def cmd_myflights(_, m: Message):
    await ensure_user(m.from_user.id, m.from_user.first_name)
    flights = await flights_col.find({"user_id": m.from_user.id}).to_list(length=50)
    if not flights:
        return await m.reply_text("You’re not tracking any flights yet. Use /track to add one.")
    text = "✈️ *Your Tracked Flights:*\n\n"
    for f in flights:
        text += (
            f"`{f['_id']}` — {f['origin']} → {f['destination']} on {f['date']}\n"
            f"Last price: ${f['last_price']} (checked {f['last_checked'].strftime('%Y-%m-%d %H:%M')})\n\n"
        )
    await m.reply_text(text)

@app.on_message(filters.command("remove_f"))
async def cmd_remove(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: `/remove_f <flight_id>`")
    fid = m.command[1]
    res = await flights_col.delete_one({"_id": {"$eq": m.command[1]}})  # fallback text id
    if res.deleted_count == 0:
        # Try ObjectId
        from bson import ObjectId
        try:
            res = await flights_col.delete_one({"_id": ObjectId(fid)})
        except Exception:
            pass
    if res.deleted_count > 0:
        await m.reply_text("🗑️ Flight tracking removed.")
    else:
        await m.reply_text("❌ Flight ID not found or already removed.")

# ---------------- Background Job ----------------
async def price_checker():
    """Periodically checks prices and notifies users of drops."""
    while True:
        try:
            flights = await flights_col.find().to_list(length=200)
            for f in flights:
                new_price = await fetch_flight_price(f["origin"], f["destination"], f["date"])
                if new_price < f["last_price"] - 10:  # drop > $10
                    diff = f["last_price"] - new_price
                    msg = (
                        f"💸 *Price Drop Alert!*\n"
                        f"{f['origin']} → {f['destination']} on {f['date']}\n"
                        f"Old price: ${f['last_price']}\n"
                        f"New price: *${new_price}*\n"
                        f"Difference: ↓ ${round(diff, 2)}"
                    )
                    await notify_user(f["user_id"], msg)
                # update DB
                await flights_col.update_one(
                    {"_id": f["_id"]},
                    {"$set": {"last_price": new_price, "last_checked": datetime.utcnow()}}
                )
            await asyncio.sleep(300)  # check every 5 minutes
        except Exception as e:
            logger.error(f"Price checker error: {e}")
            await asyncio.sleep(60)

