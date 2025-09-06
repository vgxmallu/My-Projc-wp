"""
football_bot.py
Pyrogram + Motor (MongoDB) Football bot:
- Predictions
- Live score subscriptions for groups
- Matches listing
- FIFA-like player cards (text-based or image stub)
- Leaderboard & user stats

Configure via environment variables:
API_ID, API_HASH, BOT_TOKEN, MONGO_URI, FOOTBALL_API_KEY, FOOTBALL_API_BASE (optional)
"""
import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import aiohttp
from pyrogram import Client, filters, idle
from pyrogram.types import Message
import motor.motor_asyncio
from PIL import Image, ImageDraw, ImageFont
from config import DB_URL
from wallbot import wbot as app

# ---------- Config ----------

FOOTBALL_API_KEY = "8f130bb08f7741a98e068b4163cc6cca"
FOOTBALL_API_BASE = os.getenv("FOOTBALL_API_BASE", "https://api.football-data.org/v2")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # seconds


# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("football-bot")

# ---------- App & DB ----------
mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo["football_bot_db"]
preds_col = db["predictions"]         # predictions: {match_id, user_id, pick, created_at, resolved, points}
subs_col = db["subscriptions"]        # group subscriptions: {chat_id, match_ids: []}
matches_col = db["matches_cache"]     # cached match info from API
users_col = db["users_stats"]         # leaderboard: {user_id, username, points, correct, wrong}

# ---------- HTTP Session ----------
session: Optional[aiohttp.ClientSession] = None

# ---------- Helpers: Football API ----------
async def fetch_json(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generic fetch from FOOTBALL_API_BASE. Many football APIs differ. Adjust headers/paths per provider.
    This example uses football-data.org style (X-Auth-Token header).
    """
    global session
    if session is None:
        session = aiohttp.ClientSession()
    url = endpoint if endpoint.startswith("http") else f"{FOOTBALL_API_BASE}{endpoint}"
    headers = {}
    if FOOTBALL_API_KEY:
        headers["X-Auth-Token"] = FOOTBALL_API_KEY
    async with session.get(url, params=params or {}, headers=headers, timeout=20) as resp:
        if resp.status != 200:
            text = await resp.text()
            log.warning("API non-200: %s %s %s", resp.status, url, text)
            return {}
        return await resp.json()

async def get_upcoming_matches(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch upcoming matches from API. Adjust endpoint depending on your provider.
    For football-data.org: /matches?status=SCHEDULED
    """
    data = await fetch_json("/matches", params={"status": "SCHEDULED", "limit": limit})
    if not data:
        return []
    # structure differs per API; normalize to list of matches with id, utcDate, homeTeam, awayTeam, competition
    raw = data.get("matches") or data.get("events") or []
    matches = []
    for m in raw[:limit]:
        match_id = m.get("id") or m.get("match_id") or m.get("event_id")
        utc = m.get("utcDate") or m.get("date") or m.get("start_time")
        home = (m.get("homeTeam") or m.get("team1") or {}).get("name") or (m.get("home") or {}).get("name")
        away = (m.get("awayTeam") or m.get("team2") or {}).get("name") or (m.get("away") or {}).get("name")
        comp = (m.get("competition") or {}).get("name") or m.get("league")
        matches.append({
            "match_id": str(match_id),
            "utcDate": utc,
            "home": home,
            "away": away,
            "competition": comp
        })
    return matches

async def get_live_matches() -> List[Dict[str, Any]]:
    """
    Fetch live matches (IN_PLAY). Adjust based on API
    """
    data = await fetch_json("/matches", params={"status": "LIVE"})
    raw = data.get("matches") or []
    matches = []
    for m in raw:
        match_id = m.get("id")
        utc = m.get("utcDate")
        home = (m.get("homeTeam") or {}).get("name")
        away = (m.get("awayTeam") or {}).get("name")
        score = m.get("score") or {}
        full = score.get("fullTime") or {}
        matches.append({
            "match_id": str(match_id),
            "utcDate": utc,
            "home": home,
            "away": away,
            "score": full,
            "status": m.get("status")
        })
    return matches

async def get_match_details(match_id: str) -> Dict[str, Any]:
    data = await fetch_json(f"/matches/{match_id}")
    if not data:
        return {}
    m = data.get("match") or data.get("event") or {}
    return m

# ---------- Prediction logic ----------
def normalize_pick(pick: str) -> Optional[str]:
    pick = pick.lower().strip()
    if pick in ("home", "h", "1"):
        return "home"
    if pick in ("away", "a", "2"):
        return "away"
    if pick in ("draw", "d", "x"):
        return "draw"
    return None

async def submit_prediction(chat_id: int, user_id: int, username: str, match_id: str, pick: str) -> str:
    pick_norm = normalize_pick(pick)
    if pick_norm is None:
        return "Invalid pick. Choose home/away/draw."

    # check match exists in cache or API
    cached = await matches_col.find_one({"match_id": match_id})
    if not cached:
        # try to fetch details
        m = await get_match_details(match_id)
        if not m:
            return "Match not found (invalid match_id). Use /matches to list upcoming matches."
        # cache minimum
        cached = {"match_id": match_id, "data": m}
        await matches_col.insert_one(cached)
    # check if already started
    utc = cached.get("data", {}).get("utcDate") or cached.get("data", {}).get("date")
    if utc:
        try:
            match_time = datetime.fromisoformat(utc.replace("Z","+00:00"))
            if datetime.now(timezone.utc) >= match_time:
                return "Match already started. Predictions closed."
        except Exception:
            pass

    existing = await preds_col.find_one({"match_id": match_id, "user_id": user_id})
    if existing:
        return "You already predicted this match. Use /mypredictions to view."
    doc = {
        "match_id": match_id,
        "user_id": user_id,
        "username": username,
        "pick": pick_norm,
        "created_at": datetime.utcnow(),
        "resolved": False,
        "points": 0
    }
    await preds_col.insert_one(doc)
    # ensure user exists in users_col
    await users_col.update_one({"user_id": user_id}, {"$setOnInsert": {"username": username, "points": 0, "correct": 0, "wrong": 0}}, upsert=True)
    return f"Prediction recorded: {pick_norm} for match {match_id}."

async def resolve_match_predictions(match_id: str, result: str):
    """
    result: 'home'/'away'/'draw'
    Award points: exact winner = 10 points. (Can extend to scoreline exact)
    """
    cursor = preds_col.find({"match_id": match_id, "resolved": False})
    async for p in cursor:
        user_id = p["user_id"]
        correct = (p["pick"] == result)
        pts = 10 if correct else 0
        await preds_col.update_one({"_id": p["_id"]}, {"$set": {"resolved": True, "points": pts}})
        if correct:
            await users_col.update_one({"user_id": user_id}, {"$inc": {"points": pts, "correct": 1}})
        else:
            await users_col.update_one({"user_id": user_id}, {"$inc": {"wrong": 1}})

# ---------- Live subscriptions & poller ----------
async def poll_live_and_announce():
    """
    Background task: poll live matches periodically, store state, and announce updates to subscribed chats.
    Also detect finished matches and trigger prediction resolution.
    """
    log.info("Starting live poller loop (interval %s seconds)", POLL_INTERVAL)
    while True:
        try:
            # fetch live matches
            live = await get_live_matches()
            live_ids = [m["match_id"] for m in live]
            # update cache
            for m in live:
                await matches_col.update_one({"match_id": m["match_id"]}, {"$set": {"data": m, "last_seen": datetime.utcnow()}}, upsert=True)
            # announce to subscribed chats
            async for sub in subs_col.find({}):
                chat_id = sub["chat_id"]
                # if sub has specific match_ids subscribed, only announce those; otherwise announce all
                subscribed_matches = sub.get("match_ids") or []
                for m in live:
                    if subscribed_matches and m["match_id"] not in subscribed_matches:
                        continue
                    text = f"🔴 Live: {m.get('home')} {m.get('score',{}).get('homeTeam', '')} - {m.get('score',{}).get('awayTeam','')} {m.get('away')}\nStatus: {m.get('status')}"
                    await safe_send(chat_id, text)
            # detect matches that finished since last poll -> check status from cache for transitions
            # We'll fetch matches currently in cache with status not finished and see if now finished
            async for cached in matches_col.find({"data.status": {"$in": ["LIVE","IN_PLAY","IN_PROGRESS"]}}):
                mid = cached["match_id"]
                # fetch latest details
                details = await get_match_details(mid)
                status = (details.get("status") if isinstance(details, dict) else None) or (details.get("match",{}).get("status") if isinstance(details, dict) else None)
                # Some APIs use "FINISHED" or "IN_PLAY". Normalize:
                new_status = status or details.get("status")
                if new_status and new_status.upper() in ("FINISHED","POSTPONED","SCHEDULED","CANCELED") and new_status.upper() != cached["data"].get("status","").upper():
                    # match ended -> resolve predictions if FINISHED
                    if new_status.upper() == "FINISHED":
                        # attempt to deduce result
                        # For simplicity, re-fetch and determine winner
                        final = details.get("match") or details
                        score = (final.get("score") or {}).get("fullTime") or final.get("score") or {}
                        home_goals = score.get("homeTeam") or score.get("home") or 0
                        away_goals = score.get("awayTeam") or score.get("away") or 0
                        if home_goals > away_goals:
                            result = "home"
                        elif away_goals > home_goals:
                            result = "away"
                        else:
                            result = "draw"
                        await resolve_match_predictions(mid, result)
                        await safe_send(cached.get("chat_announce") or cached.get("last_announce_chat") or cached.get("announce_chat") or 0,
                                        f"🏁 Match {mid} finished: {final.get('homeTeam', {}).get('name','')} {home_goals} - {away_goals} {final.get('awayTeam', {}).get('name','')}\nPredictions resolved.")
                    # update cache status
                    await matches_col.update_one({"match_id": mid}, {"$set": {"data.status": new_status}})
        except Exception as e:
            log.exception("Error in poller: %s", e)
        await asyncio.sleep(POLL_INTERVAL)

# ---------- Safe send helper ----------
async def safe_send(chat_id: int, text: str):
    try:
        if not chat_id or chat_id == 0:
            return
        await app.send_message(chat_id, text)
    except Exception as e:
        log.warning("Failed to send to %s: %s", chat_id, e)

# ---------- Commands ----------
@app.on_message(filters.command("matches") & (filters.private | filters.group))
async def cmd_smatches(_, m: Message):
    matches = await get_upcoming_matches(limit=10)
    if not matches:
        return await m.reply("No upcoming matches found (API limit/response).")
    text = "Upcoming matches:\n"
    for mm in matches:
        utc = mm.get("utcDate")
        tstr = utc if not utc else utc
        text += f"ID: {mm['match_id']} — {mm.get('home')} vs {mm.get('away')} — {tstr}\n"
    await m.reply(text)

@app.on_message(filters.command("smatch") & (filters.private | filters.group))
async def cmd_smatch(_, m: Message):
    if len(m.command) < 2:
        return await m.reply("Usage: /match <match_id>")
    match_id = m.command[1]
    details = await get_match_details(match_id)
    if not details:
        return await m.reply("Match not found or API error.")
    # normalize alarm
    home = (details.get("homeTeam") or {}).get("name") or details.get("home")
    away = (details.get("awayTeam") or {}).get("name") or details.get("away")
    utc = details.get("utcDate") or details.get("date")
    score = (details.get("score") or {}).get("fullTime") or {}
    text = f"Match {match_id}\n{home} vs {away}\nTime: {utc}\nScore: {score}\nStatus: {details.get('status')}"
    await m.reply(text)

@app.on_message(filters.command("spredict") & (filters.private | filters.group))
async def cmd_spredict(_, m: Message):
    # /predict <match_id> <home/away/draw>
    if len(m.command) < 3:
        return await m.reply("Usage: /predict <match_id> <home/away/draw>")
    match_id = m.command[1]
    pick = m.command[2]
    res = await submit_prediction(m.chat.id, m.from_user.id, m.from_user.username or m.from_user.first_name, match_id, pick)
    await m.reply(res)

@app.on_message(filters.command("mypredictions") & (filters.private | filters.group))
async def cmd_my_predictions(_, m: Message):
    cursor = preds_col.find({"user_id": m.from_user.id}).sort("created_at", -1)
    text = "Your predictions:\n"
    found = False
    async for p in cursor:
        found = True
        status = "✅" if p.get("resolved") and p.get("points",0)>0 else ("❌" if p.get("resolved") else "⏳")
        text += f"Match {p['match_id']}: {p['pick']} — {status}\n"
    if not found:
        text = "You have no predictions yet."
    await m.reply(text)

@app.on_message(filters.command("sleaderboard") & (filters.private | filters.group))
async def cmd_scrleaderboard(_, m: Message):
    cursor = users_col.find({}).sort("points", -1).limit(10)
    text = "🏆 Prediction Leaderboard:\n"
    i = 1
    async for doc in cursor:
        text += f"{i}. {doc.get('username')} — {doc.get('points',0)} pts (✔{doc.get('correct',0)} ✖{doc.get('wrong',0)})\n"
        i += 1
    await m.reply(text)

@app.on_message(filters.command("subscribe_live") & filters.group)
async def cmd_skubscribe_live(_, m: Message):
    # /subscribe_live  OR /subscribe_live <match_id> (optional)
    chat_id = m.chat.id
    match_id = m.command[1] if len(m.command) > 1 else None
    doc = await subs_col.find_one({"chat_id": chat_id})
    if not doc:
        doc = {"chat_id": chat_id, "match_ids": []}
        await subs_col.insert_one(doc)
    if match_id:
        if match_id in doc.get("match_ids", []):
            return await m.reply("Already subscribed to that match.")
        doc["match_ids"].append(match_id)
        await subs_col.update_one({"chat_id": chat_id}, {"$set": {"match_ids": doc["match_ids"]}})
        await m.reply(f"Subscribed to live updates for match {match_id}.")
    else:
        await subs_col.update_one({"chat_id": chat_id}, {"$set": {"match_ids": []}}, upsert=True)
        await m.reply("Subscribed to all live match updates in this group.")

@app.on_message(filters.command("unsubscribe_live") & filters.group)
async def cmd_uhnsub_live(_, m: Message):
    chat_id = m.chat.id
    doc = await subs_col.find_one({"chat_id": chat_id})
    if not doc:
        return await m.reply("This group was not subscribed.")
    await subs_col.delete_one({"chat_id": chat_id})
    await m.reply("Unsubscribed from live updates.")

# ---------- FIFA card generation (simple image stub) ----------
async def generate_fifa_card(player_name: str, team: Optional[str] = None, rating: int = 75) -> str:
    """
    Generate a simple FIFA-like card image and save locally; return filepath.
    This uses Pillow. For real images use player photo APIs.
    """
    width, height = 512, 768
    img = Image.new("RGB", (width, height), color=(20, 20, 60))
    draw = ImageDraw.Draw(img)
    # title
    try:
        fnt = ImageFont.truetype("arial.ttf", 36)
    except:
        fnt = ImageFont.load_default()
    draw.text((20, 20), player_name, font=fnt, fill=(255, 255, 255))
    draw.text((20, 70), f"Team: {team or '—'}", font=fnt, fill=(200,200,200))
    draw.text((20, 120), f"Rating: {rating}", font=fnt, fill=(255,255,0))
    # big circle for image
    draw.ellipse((150, 170, 362, 382), outline=(255,255,255), width=4)
    # simple stats
    stats = ["PAC 75", "SHO 70", "PAS 72", "DRI 74", "DEF 60", "PHY 68"]
    y = 420
    for s in stats:
        draw.text((40, y), s, font=fnt, fill=(240,240,240))
        y += 40
    # save
    filename = f"fifacard_{player_name.replace(' ','_')}_{int(datetime.utcnow().timestamp())}.png"
    img.save(filename)
    return filename

@app.on_message(filters.command("fifacard") & (filters.private | filters.group))
async def cmd_fifhacard(_, m: Message):
    if len(m.command) < 2:
        return await m.reply("Usage: /fifacard <player name>")
    player_name = " ".join(m.command[1:])
    # For real app, call an API to fetch player rating/team
    #rating = random.randint(60, 92)
    team = None
    # generate image
    fp = await generate_fifa_card(player_name, team)
    try:
        await app.send_photo(m.chat.id, fp, caption=f"{player_name} — Rating {rating}")
    except Exception:
        await m.reply(f"{player_name} — Rating {rating}")
    finally:
        try:
            os.remove(fp)
        except:
            pass

# ---------- Startup / Shutdown ----------
async def start_pollers():
    # start live poller background task
    asyncio.create_task(poll_live_and_announce())

@app.on_message(filters.command("socerhelp") & (filters.private | filters.group))
async def cmd_hejglp(_, m: Message):
    text = (
        "⚽ Football Bot commands:\n"
        "/smatches — list upcoming matches\n"
        "/smatch <match_id> — show match details\n"
        "/spredict <match_id> <home/away/draw> — place a prediction\n"
        "/mypredictions — your predictions\n"
        "/sleaderboard — top predictors\n"
        "/subscribe_live [match_id] — subscribe group to live updates\n"
        "/unsubscribe_live — stop live updates\n"
        "/fifacard <player name> — generate a FIFA style card\n"
    )
    await m.reply(text)

