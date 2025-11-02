#!/usr/bin/env python3
"""
Sports Manager Bot (Pyrogram + Motor)

Features:
- /start
- /create_league <name> <slots>  -> create a league with N teams (slots)
- /join_league <league_id>       -> join as manager (creates team)
- /league <league_id>            -> show league info
- /draft <league_id>             -> start draft UI (creator only)
- Draft uses inline buttons to pick from player pool. Turn-based pick order.
- /team                          -> show your team roster and stats
- /simulate_now <league_id>      -> simulate one matchday immediately (admin or leader)
- Automatic simulation in background every SIM_INTERVAL_SECONDS
- /standings <league_id>         -> show standings (points)
- MongoDB collections: leagues, teams, players, matches, users
"""

import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from config import DB_URL
from wallbot import wbot as app
load_dotenv()

DB_NAME = os.getenv("DB_NAME", "sports_manager_db")
SIM_INTERVAL = int(os.getenv("SIM_INTERVAL_SECONDS", "86400"))  # default daily
DEFAULT_PLAYERS_PER_TEAM = 11

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

leagues_col = db["leagues"]
teams_col = db["teams"]
players_col = db["players"]
matches_col = db["matches"]
users_col = db["users"]

# ------------- Helpers & Data Models -------------

def now_iso():
    return datetime.utcnow().isoformat()

def mkshort(oid):
    return str(oid)[-6:]

async def ensure_user(user_id: int, username: Optional[str]):
    u = await users_col.find_one({"user_id": user_id})
    if not u:
        u = {
            "user_id": user_id,
            "username": username or "",
            "created_at": now_iso(),
            "total_managed": 0,
        }
        await users_col.insert_one(u)
    return u

def generate_player_template(name: str) -> Dict[str, Any]:
    """Create a random player with rating and positions. Ratings 40-99."""
    rating = random.randint(60, 95)
    pos_choices = ["GK", "DEF", "MID", "FWD"]
    # choose primary position weighted by probability
    pos = random.choices(pos_choices, weights=[0.1, 0.35, 0.4, 0.15], k=1)[0]
    player = {
        "name": name,
        "rating": rating,
        "position": pos,
        "goals": 0,
        "assists": 0,
        "appearances": 0,
        "created_at": now_iso(),
    }
    return player

def sample_player_names(n=1):
    """Return n human-readable random player names."""
    first = ["Alex", "Kai", "Luca", "Noah", "Leo", "Sam", "Jordan", "Maya", "Riley", "Ava", "Evan", "Mia", "Zoe", "Max"]
    last = ["Smith","Johnson","Garcia","Brown","Martinez","Davis","Miller","Wilson","Anderson","Taylor","Thomas","Moore"]
    out=[]
    for _ in range(n):
        out.append(f"{random.choice(first)} {random.choice(last)}")
    return out

async def create_player_pool(n=200):
    """Generate a pool of players if players collection is empty."""
    count = await players_col.count_documents({})
    if count >= n:
        return
    LOG.info("Generating player pool (%s players)...", n)
    for _ in range(n):
        name = sample_player_names(1)[0]
        player = generate_player_template(name)
        await players_col.insert_one(player)
    LOG.info("Player pool ready.")

# ------------- League APIs -------------

#@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await ensure_user(m.from_user.id, m.from_user.username)
    text = (
        "🏟️ Welcome to Sports Manager!\n\n"
        "Commands:\n"
        "/create_league <name> <slots> - create a new league (slots = number of teams)\n"
        "/join_league <league_id> - join a league as manager (creates a team)\n"
        "/league <league_id> - show league info\n"
        "/draft <league_id> - start draft (league creator only)\n"
        "/team - show your team\n"
        "/simulate_now <league_id> - run immediate simulation (admins)\n"
        "/standings <league_id> - view standings\n"
    )
    await m.reply_text(text)

@app.on_message(filters.command("create_league"))
async def cmd_create_league(_, m: Message):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /create_league <name> <slots>\nExample: /create_league FunLeague 6")
    _, name, slots = m.command[0], m.command[1], None
    try:
        # allow space in name
        parts = m.text.split(maxsplit=2)
        name = parts[1] if len(parts) >= 2 else "League"
        slots = int(parts[2]) if len(parts) == 3 else 6
    except Exception:
        return await m.reply_text("Invalid usage. Example: /create_league FunLeague 6")
    # create league doc
    creator = m.from_user
    await ensure_user(creator.id, creator.username)
    league = {
        "name": name,
        "creator_id": creator.id,
        "slots": slots,
        "created_at": now_iso(),
        "status": "waiting",  # waiting, drafting, active
        "teams": [],  # team ids
        "draft_order": [],
        "draft_index": 0,
        "player_pool_size": slots * DEFAULT_PLAYERS_PER_TEAM * 2,
        "matchday": 0,
        "standings": {},  # team_id -> points
    }
    res = await leagues_col.insert_one(league)
    lid = str(res.inserted_id)
    # ensure player pool exists
    await create_player_pool(500)
    await m.reply_text(f"✅ League created: {name}\nLeague ID: `{lid}`\nSlots: {slots}\nUse /join_league {lid} to create your team.", parse_mode=enums.ParseMode.MONO)
    LOG.info("League %s created by %s", lid, creator.id)

@app.on_message(filters.command("join_league"))
async def cmd_join_league(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /join_league <league_id>")
    lid = m.command[1]
    try:
        league = await leagues_col.find_one({"_id": ObjectId(lid)})
    except Exception:
        return await m.reply_text("Invalid league id.")
    if not league:
        return await m.reply_text("League not found.")

    # check slots
    if len(league["teams"]) >= league["slots"]:
        return await m.reply_text("League is full.")

    # check if user already has team in league
    existing = await teams_col.find_one({"league_id": lid, "manager_id": m.from_user.id})
    if existing:
        return await m.reply_text("You already have a team in this league.")

    # create team doc
    team_name = f"{m.from_user.first_name}'s Team"
    team = {
        "name": team_name,
        "manager_id": m.from_user.id,
        "league_id": lid,
        "created_at": now_iso(),
        "players": [],  # player ids
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
    }
    r = await teams_col.insert_one(team)
    team_id = str(r.inserted_id)
    # add to league
    await leagues_col.update_one({"_id": ObjectId(lid)}, {"$push": {"teams": team_id}})
    await ensure_user(m.from_user.id, m.from_user.username)
    await users_col.update_one({"user_id": m.from_user.id}, {"$inc": {"total_managed": 1}})
    await m.reply_text(f"✅ You joined league `{lid}` as team `{team_name}`\nTeam ID: `{team_id}`", parse_mode=enums.ParseMode.MONO)
    LOG.info("User %s joined league %s as team %s", m.from_user.id, lid, team_id)

@app.on_message(filters.command("league"))
async def cmd_show_league(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /league <league_id>")
    lid = m.command[1]
    league = await leagues_col.find_one({"_id": ObjectId(lid)})
    if not league:
        return await m.reply_text("League not found.")
    teams = []
    for tid in league.get("teams", []):
        t = await teams_col.find_one({"_id": ObjectId(tid)})
        if t:
            manager = await users_col.find_one({"user_id": t["manager_id"]})
            teams.append(f"{t['name']} (mgr: @{manager.get('username','-')})")
    text = (
        f"🏆 League: {league['name']}\n"
        f"League ID: `{lid}`\n"
        f"Status: {league['status']}\n"
        f"Slots: {league['slots']}\n"
        f"Teams ({len(teams)}/{league['slots']}):\n" + ("\n".join(teams) if teams else "No teams yet.") + "\n\n"
    )
    if league.get("status") == "waiting":
        text += "When all teams joined, the league creator can start the draft with /draft <league_id>."
    await m.reply_text(text, parse_mode=enums.ParseMode.MONO)

# ------------- Draft logic (inline) -------------

def build_draft_pool_kb(player_docs: List[Dict[str, Any]], league_id: str):
    # show up to 8 options
    rows = []
    for p in player_docs[:8]:
        rows.append([InlineKeyboardButton(f"{p['name']} ({p['position']}/{p['rating']})", callback_data=f"pick|{league_id}|{str(p['_id'])}")])
    # add refresh button
    rows.append([InlineKeyboardButton("🔄 Refresh pool", callback_data=f"refresh|{league_id}")])
    return InlineKeyboardMarkup(rows)

@app.on_message(filters.command("draft"))
async def cmd_start_draft(_, m: Message):
    # only league creator can start draft
    if len(m.command) < 2:
        return await m.reply_text("Usage: /draft <league_id>")
    lid = m.command[1]
    league = await leagues_col.find_one({"_id": ObjectId(lid)})
    if not league:
        return await m.reply_text("League not found.")
    if m.from_user.id != league.get("creator_id"):
        return await m.reply_text("Only the league creator can start the draft.")
    # check teams count
    if len(league.get("teams", [])) < league["slots"]:
        return await m.reply_text("Not all slots filled. Wait until all teams join.")
    # prepare draft order (randomized list of team ids)
    teams = league["teams"]
    order = teams.copy()
    random.shuffle(order)
    await leagues_col.update_one({"_id": ObjectId(lid)}, {"$set": {"status": "drafting", "draft_order": order, "draft_index": 0}})
    # show draft UI with options to pick
    # pick some random players from pool
    pool_cursor = players_col.aggregate([{"$sample": {"size": 20}}])
    pool = await pool_cursor.to_list(length=20)
    await m.reply_text(f"📝 Draft started for league `{lid}`!\nDraft order randomized. First pick: team {order[0]}", parse_mode=enums.ParseMode.MONO)
    # send a message to the chat with the draft pool (creator's chat)
    kb = build_draft_pool_kb(pool, lid)
    sent = await m.reply_text("Select a player to pick (buttons):", reply_markup=kb)
    # store last draft message id in league for editing later
    await leagues_col.update_one({"_id": ObjectId(lid)}, {"$set": {"draft_message_id": sent.message_id}})
    LOG.info("Draft started for league %s", lid)

@app.on_callback_query(filters.regex(r"^refresh\|"))
async def cb_refresh_pool(_, cq: CallbackQuery):
    try:
        _, lid = cq.data.split("|",1)
        league = await leagues_col.find_one({"_id": ObjectId(lid)})
        if not league:
            return await cq.answer("League not found.", show_alert=True)
        pool = await players_col.aggregate([{"$sample": {"size": 20}}]).to_list(length=20)
        kb = build_draft_pool_kb(pool, lid)
        try:
            await cq.message.edit_reply_markup(kb)
        except:
            pass
        await cq.answer("Pool refreshed.")
    except Exception as e:
        LOG.exception("refresh pool error")
        await cq.answer("Error refreshing pool.", show_alert=True)

@app.on_callback_query(filters.regex(r"^pick\|"))
async def cb_pick_player(_, cq: CallbackQuery):
    # pick|<league_id>|<player_oid>
    try:
        _, lid, pid = cq.data.split("|",2)
        league = await leagues_col.find_one({"_id": ObjectId(lid)})
        if not league or league.get("status") != "drafting":
            return await cq.answer("Draft not active.", show_alert=True)
        # find whose turn
        idx = int(league.get("draft_index",0))
        order = league.get("draft_order",[])
        if idx >= len(order):
            return await cq.answer("Draft completed.", show_alert=True)
        current_team_id = order[idx]
        # only manager of current_team should pick (enforced by checking cq.from_user)
        team = await teams_col.find_one({"_id": ObjectId(current_team_id)})
        if not team:
            return await cq.answer("Team not found.", show_alert=True)
        if cq.from_user.id != team["manager_id"]:
            return await cq.answer("It's not your team's turn to pick.", show_alert=True)

        # check player exists and not already taken
        player = await players_col.find_one({"_id": ObjectId(pid)})
        if not player:
            return await cq.answer("Player not found.", show_alert=True)
        # ensure not already in any team
        owned = await teams_col.find_one({"players": pid})
        if owned:
            return await cq.answer("Player already taken.", show_alert=True)

        # add to team
        await teams_col.update_one({"_id": ObjectId(current_team_id)}, {"$push": {"players": pid}})
        # increment draft index
        await leagues_col.update_one({"_id": ObjectId(lid)}, {"$inc": {"draft_index": 1}})
        # if reached end of order, wrap around (snake draft could be implemented)
        league = await leagues_col.find_one({"_id": ObjectId(lid)})
        if league.get("draft_index") >= len(order)*DEFAULT_PLAYERS_PER_TEAM:
            # finished draft
            await leagues_col.update_one({"_id": ObjectId(lid)}, {"$set": {"status": "active", "draft_index": 0}})
            await cq.message.edit_text("✅ Draft complete! League active.")
            await cq.answer("You picked the player. Draft complete!")
            LOG.info("Draft complete for league %s", lid)
            return
        else:
            # notify and update message
            next_idx = league.get("draft_index")
            next_team_id = order[next_idx % len(order)]
            next_team = await teams_col.find_one({"_id": ObjectId(next_team_id)})
            try:
                await cq.message.edit_text(f"Pick registered. Next turn: {next_team['name']} (manager @{(await users_col.find_one({'user_id': next_team['manager_id']})).get('username','-')})")
            except:
                pass
            await cq.answer("You picked the player!")
            LOG.info("Team %s picked player %s in league %s", current_team_id, pid, lid)
    except Exception as e:
        LOG.exception("draft pick error")
        await cq.answer("Error processing pick.", show_alert=True)

# ------------- Team & roster commands -------------

@app.on_message(filters.command("team"))
async def cmd_team(_, m: Message):
    # show user's team(s)
    teams = await teams_col.find({"manager_id": m.from_user.id}).to_list(length=50)
    if not teams:
        return await m.reply_text("You don't manage any team. Join a league with /join_league <league_id>.")
    out=[]
    for t in teams:
        lines=[f"🏷 Team: {t['name']}  (ID: `{str(t['_id'])[-6:]}`)"]
        players = []
        for pid in t.get("players", []):
            p = await players_col.find_one({"_id": ObjectId(pid)})
            if p:
                players.append(f"{p['name']} ({p['position']}/{p['rating']})")
        lines.append("Players:")
        lines.extend(players if players else ["No players yet."])
        lines.append(f"Points: {t.get('points',0)}, GF: {t.get('goals_for',0)}, GA: {t.get('goals_against',0)}")
        out.append("\n".join(lines))
    await m.reply_text("\n\n".join(out), parse_mode=enums.ParseMode.MONO)

# ------------- Standings & simulation -------------

@app.on_message(filters.command("standings"))
async def cmd_standings(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /standings <league_id>")
    lid = m.command[1]
    league = await leagues_col.find_one({"_id": ObjectId(lid)})
    if not league:
        return await m.reply_text("League not found.")
    # gather teams and points
    table = []
    for tid in league.get("teams", []):
        t = await teams_col.find_one({"_id": ObjectId(tid)})
        if t:
            table.append((t.get("points",0), t.get("name"), tid))
    table.sort(reverse=True)
    lines=["🏆 Standings:"]
    for i,(pts,name,tid) in enumerate(table, start=1):
        lines.append(f"{i}. {name} — {pts} pts")
    await m.reply_text("\n".join(lines))

def simulate_one_match(team_a: Dict[str, Any], team_b: Dict[str, Any]) -> Dict[str,int]:
    """Simple simulation: use average player rating as strength, random variance."""
    def team_strength(team):
        ratings=[]
        for pid in team.get("players", []):
            p = asyncio.get_event_loop().run_until_complete(players_col.find_one({"_id": ObjectId(pid)})) if False else None
        # we cannot run DB calls here because this function can be called in sync context;
        # We'll compute strength outside where we have async access.
        return 0
    # placeholder: shouldn't be used
    return {"a_goals":0,"b_goals":0}

async def compute_team_strength(team_doc):
    """Compute numeric strength from players' ratings and items (simple average)."""
    rsum=0; cnt=0
    for pid in team_doc.get("players", []):
        p = await players_col.find_one({"_id": ObjectId(pid)})
        if p:
            rsum += p.get("rating",70)
            cnt += 1
    if cnt==0:
        return 30  # weak
    # average scaled
    avg = rsum/cnt
    # applying small random form factor
    form = random.uniform(0.9, 1.15)
    return avg * form

async def simulate_match_async(team_a_doc, team_b_doc, league_id:str):
    """Simulate a match asynchronously, update DB."""
    strength_a = await compute_team_strength(team_a_doc)
    strength_b = await compute_team_strength(team_b_doc)
    # Poisson-like scoring using strength ratio
    base_a = max(0.5, strength_a/50.0)
    base_b = max(0.5, strength_b/50.0)
    # expected goals
    exp_a = base_a * random.uniform(0.5,1.8)
    exp_b = base_b * random.uniform(0.5,1.8)
    # sample goals with small randomness
    goals_a = int(random.gauss(exp_a, 1) + abs(random.randint(-1,2)))
    goals_b = int(random.gauss(exp_b, 1) + abs(random.randint(-1,2)))
    goals_a = max(0, goals_a)
    goals_b = max(0, goals_b)

    # update team stats
    await teams_col.update_one({"_id": team_a_doc["_id"]}, {"$inc": {"goals_for": goals_a, "goals_against": goals_b}})
    await teams_col.update_one({"_id": team_b_doc["_id"]}, {"$inc": {"goals_for": goals_b, "goals_against": goals_a}})
    # points
    if goals_a > goals_b:
        await teams_col.update_one({"_id": team_a_doc["_id"]}, {"$inc": {"points": 3}})
        result = f"{team_a_doc['name']} {goals_a} - {goals_b} {team_b_doc['name']}  (win {team_a_doc['name']})"
    elif goals_b > goals_a:
        await teams_col.update_one({"_id": team_b_doc["_id"]}, {"$inc": {"points": 3}})
        result = f"{team_a_doc['name']} {goals_a} - {goals_b} {team_b_doc['name']}  (win {team_b_doc['name']})"
    else:
        # draw
        await teams_col.update_one({"_id": team_a_doc["_id"]}, {"$inc": {"points": 1}})
        await teams_col.update_one({"_id": team_b_doc["_id"]}, {"$inc": {"points": 1}})
        result = f"{team_a_doc['name']} {goals_a} - {goals_b} {team_b_doc['name']}  (draw)"

    # store match
    match = {
        "league_id": league_id,
        "team_a": str(team_a_doc["_id"]),
        "team_b": str(team_b_doc["_id"]),
        "score_a": goals_a,
        "score_b": goals_b,
        "played_at": now_iso(),
    }
    await matches_col.insert_one(match)
    LOG.info("Simulated match: %s", result)
    return result

async def simulate_matchday(league_id: str):
    league = await leagues_col.find_one({"_id": ObjectId(league_id)})
    if not league:
        return
    teams = league.get("teams", [])
    if len(teams) < 2:
        return
    # shuffle and pair up (simple round-robin step)
    shuffled = teams.copy()
    random.shuffle(shuffled)
    pairings=[]
    for i in range(0, len(shuffled)-1, 2):
        pairings.append((shuffled[i], shuffled[i+1]))
    # if odd, last team gets bye (no match)
    results=[]
    for a,b in pairings:
        team_a = await teams_col.find_one({"_id": ObjectId(a)})
        team_b = await teams_col.find_one({"_id": ObjectId(b)})
        res = await simulate_match_async(team_a, team_b, league_id)
        results.append(res)
    # increment matchday
    await leagues_col.update_one({"_id": ObjectId(league_id)}, {"$inc": {"matchday": 1}})
    # send summary to league creator via DM (or skip if fail)
    try:
        creator = league.get("creator_id")
        await app.send_message(creator, f"⚽ League `{league['name']}` matchday {league.get('matchday')+1} results:\n" + "\n".join(results))
    except Exception:
        pass
    return results

# ------------- Manual simulate command -------------

@app.on_message(filters.command("simulate_now"))
async def cmd_simulate_now(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /simulate_now <league_id>")
    lid = m.command[1]
    league = await leagues_col.find_one({"_id": ObjectId(lid)})
    if not league:
        return await m.reply_text("League not found.")
    # only creator or admin allowed
    if m.from_user.id != league.get("creator_id"):
        return await m.reply_text("Only the league creator can trigger simulation.")
    await m.reply_text("Simulating matchday...")
    results = await simulate_matchday(lid)
    await m.reply_text("Simulation results:\n" + "\n".join(results))

# ------------- Background simulation loop -------------

async def background_simulator():
    LOG.info("Background simulator started (interval %s seconds).", SIM_INTERVAL)
    while True:
        try:
            # run simulation for all active leagues
            active = await leagues_col.find({"status": "active"}).to_list(length=200)
            for league in active:
                await simulate_matchday(str(league["_id"]))
        except Exception:
            LOG.exception("Error in background simulator")
        await asyncio.sleep(SIM_INTERVAL)

