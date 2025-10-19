#!/usr/bin/env python3
"""
Daily Quotes Bot — Advanced Version
Auto background task (scheduler) runs inside bot.start()
No need to add anything in main.py or __init__.py
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, enums 
from pyrogram.types import Message
#from enums import ParseMode
from wallbot import wbot as bot, subs



load_dotenv()

ZENQUOTES_API = os.getenv("ZENQUOTES_API", "https://zenquotes.io/api/random")
DEFAULT_TIME_UTC = os.getenv("DEFAULT_TIME_UTC", "08:00")



# ---------------- UTILITIES ----------------
def now_utc():
    return datetime.now(timezone.utc)

def normalize_time_str(t: str) -> Optional[str]:
    try:
        hh, mm = map(int, t.split(":"))
        if 0 <= hh < 24 and 0 <= mm < 60:
            return f"{hh:02d}:{mm:02d}"
    except Exception:
        pass
    return None

async def fetch_quote() -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(ZENQUOTES_API, timeout=15) as r:
                data = await r.json()
                if isinstance(data, list):
                    data = data[0]
                text = data.get("q") or data.get("quote")
                author = data.get("a") or data.get("author", "Unknown")
                return {"text": text, "author": author}
    except Exception as e:
        LOG.warning(f"Fetch quote failed: {e}")
        return None

def build_quote(q: dict) -> str:
    return f"💬 <b>{q['text']}</b>\n\n— <i>{q['author']}</i>"


@bot.on_message(filters.command("qtstart"))
async def startgg_cmd(_, m: Message):
    await m.reply_text(
        "👋 <b>Welcome to Daily Quotes Bot!</b>\n\n"
        "📅 Get daily motivational quotes automatically.\n\n"
        "Commands:\n"
        "/subscribe - Subscribe to daily quotes (default 08:00 UTC)\n"
        "/unsubscribe - Stop receiving quotes\n"
        "/settime HH:MM - Set delivery time (UTC)\n"
        "/quote - Get a random quote now",
    )
#parse_mode=ParseMode.MARKDOWN.value
@bot.on_message(filters.command("quote"))
async def quote_cmd(_, m: Message):
    q = await fetch_quote()
    if not q:
        return await m.reply_text("❌ Couldn't fetch a quote.")
    await m.reply_text(build_quote(q), parse_mode=enums.ParseMode.MARKDOWN)

@bot.on_message(filters.command("qtsubscribe"))
async def subscribxxe_cmd(client, m: Message):
    time = DEFAULT_TIME_UTC
    if len(m.command) >= 2:
        t = normalize_time_str(m.command[1])
        if not t:
            return await m.reply_text("❌ Invalid time. Use HH:MM (UTC)")
        time = t
    await client.subs.update_one(
        {"chat_id": m.chat.id},
        {"$set": {"chat_id": m.chat.id, "enabled": True, "send_time": time, "chat_type": m.chat.type}},
        upsert=True
    )
    await m.reply_text(f"✅ Subscribed! Daily quote at <b>{time} UTC</b>.", parse_mode=enums.ParseMode.MARKDOWN)

@bot.on_message(filters.command("qtunsubscribe"))
async def unsubxxscribe_cmd(client, m: Message):
    res = await client.subs.delete_one({"chat_id": m.chat.id})
    if res.deleted_count:
        await m.reply_text("✅ Unsubscribed from daily quotes.")
    else:
        await m.reply_text("ℹ️ You were not subscribed.")

@bot.on_message(filters.command("qtsettime"))
async def sgsettime_cmd(client, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /settime HH:MM (UTC)")
    t = normalize_time_str(m.command[1])
    if not t:
        return await m.reply_text("❌ Invalid format. Use HH:MM (UTC)")
    await client.subs.update_one({"chat_id": m.chat.id}, {"$set": {"send_time": t}}, upsert=True)
    await m.reply_text(f"🕒 Time updated to <b>{t} UTC</b>.", parse_mode=enums.ParseMode.MARKDOWN)

# ---------------- RUN ----------------
