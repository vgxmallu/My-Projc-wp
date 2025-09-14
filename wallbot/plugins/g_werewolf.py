# werewolf_bot.py
"""
Advanced Werewolf Telegram Bot (Pyrogram + Motor)
- Single-file starter/framework implementing many roles and game flow.
- Uses asyncio tasks to advance phases. Persists state to MongoDB.
- Author: ChatGPT (starter). Extend role behavior per comments.
"""

import os
import asyncio
import random
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from pyrogram import Client, filters
from pyrogram.types import Message
import motor.motor_asyncio
from bson import ObjectId
from config import DB_URL
from wallbot import wbot as app

# ----------------- CONFIG -----------------

DB_NAME = os.getenv("DB_NAME", "werewolf_db")


# Game timing (for testing you can shorten durations)
DAY_SECONDS = int(os.getenv("WW_DAY_SECONDS", "180"))   # day length
NIGHT_SECONDS = int(os.getenv("WW_NIGHT_SECONDS", "120"))  # night length
VOTE_TIME_SECONDS = int(os.getenv("WW_VOTE_SECONDS", "90"))

# ----------------- DB -----------------
mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]        # stores game state per chat
players_col = db["players"]    # stores player persistent stats/leaderboard


# ----------------- ROLES -----------------
# Roles implemented with simplified behavior and extensible hooks.
ROLE_DESCRIPTIONS = {
    "alpha": "Alpha Wolf - 20% chance to convert a player bitten at night instead of killing.",
    "wolf": "Werewolf - kills at night as a pack.",
    "villager": "Village simpleton - no night ability.",
    "seer": "Seer - can reveal a player's role at night.",
    "apprentice_seer": "Apprentice Seer - becomes seer if seer dies.",
    "beholder": "Beholder - always knows who the seer is.",
    "blacksmith": "Blacksmith - may use silverdust to block a wolf kill (one-time).",
    "clumsy": "Clumsy Guy - 50% chance to vote random.",
    "cultist_hunter": "Hunts cultists at night.",
    "cupid": "Cupid - links two lovers at start.",
    "cursed": "Cursed - turns into wolf when bitten.",
    "detective": "Detective - investigate players, 40% chance to be detected by wolves.",
    "drunk": "Drunk - special effects on werewolf kills.",
    "fool": "Fool - thinks they're seer but sees random role.",
    "guardian": "Guardian Angel - protect a player at night.",
    "gunner": "Gunner - 2 silver bullets; can shoot by day.",
    "harlot": "Harlot - visits players at night (risk!).",
    "hunter": "Hunter - may take someone down when killed.",
    "mason": "Mason - knows other masons.",
    "mayor": "Mayor - reveal to double votes.",
    "prince": "Prince - first lynch reveals and survives once.",
    "traitor": "Traitor - becomes wolf if all wolves die.",
    "wild_child": "Wild Child - chooses role model, becomes wolf if they die.",
    "wolf_cub": "Wolf Cub - if they die, wolves get double victim? (simplified effect)",
    # add more if desired
}

# default role pool for balanced games (example)
DEFAULT_ROLE_POOL = [
    "alpha", "wolf", "wolf", "seer", "villager", "villager", "villager", "mason", "mason",
    "hunter", "guardian", "prince", "cupid", "blacksmith"
]

# ----------------- UTIL -----------------
def now_ts():
    return datetime.utcnow().isoformat()

def as_short(u):
    return f"{u.get('first_name') or u.get('username') or 'User'}"

# ----------------- GAME MODEL -----------------
# Game document structure (example):
# {
#   chat_id: int,
#   phase: "lobby" | "night" | "day" | "ended",
#   owner_id: int,
#   players: [{user_id, name, role, alive, joined_at, meta: {}}...],
#   day_count: int,
#   night_count: int,
#   votes: {voter_id: target_id},
#   actions: {user_id: {action_type: ..., target_id: ..., extra: ...}},
#   created_at, updated_at, scheduled_task_id
# }

# ----------------- HELPERS: DB access -----------------
async def create_game(chat_id: int, owner_id: int) -> Dict[str, Any]:
    doc = {
        "chat_id": chat_id,
        "owner_id": owner_id,
        "phase": "lobby",
        "players": [],
        "day_count": 0,
        "night_count": 0,
        "votes": {},
        "actions": {},
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "last_tick": now_ts(),
        "roles_revealed": False
    }
    await games_col.update_one({"chat_id": chat_id}, {"$set": doc}, upsert=True)
    return doc

async def get_game(chat_id: int) -> Optional[Dict[str, Any]]:
    return await games_col.find_one({"chat_id": chat_id})

async def save_game(chat_id: int, patch: Dict[str, Any]):
    patch["updated_at"] = now_ts()
    await games_col.update_one({"chat_id": chat_id}, {"$set": patch}, upsert=True)

async def add_player(chat_id: int, user: Dict[str, Any]):
    g = await get_game(chat_id)
    if not g: return None
    if any(p["user_id"] == user["id"] for p in g["players"]):
        return g
    newp = {
        "user_id": user["id"],
        "name": user.get("first_name") or user.get("username"),
        "role": None,
        "alive": True,
        "joined_at": now_ts(),
        "meta": {}  # store per-role flags here (e.g., bullets left)
    }
    g["players"].append(newp)
    await save_game(chat_id, {"players": g["players"]})
    return g

async def remove_player(chat_id: int, user_id: int):
    g = await get_game(chat_id)
    if not g: return None
    g["players"] = [p for p in g["players"] if p["user_id"] != user_id]
    await save_game(chat_id, {"players": g["players"]})
    return g

# ----------------- ROLE ASSIGNMENT -----------------
def weighted_role_pool_for(n_players: int) -> List[str]:
    # Simple heuristic: use default pool trimmed/padded to players count
    pool = DEFAULT_ROLE_POOL.copy()
    # if not enough roles, fill with villagers or wolves depending on balance
    while len(pool) < n_players:
        pool.append("villager")
    # if too many, trim
    return pool[:n_players]

def assign_roles_to_players(players: List[Dict[str, Any]], seed: Optional[int] = None):
    n = len(players)
    pool = weighted_role_pool_for(n)
    if seed is not None:
        random.Random(seed).shuffle(pool)
    else:
        random.shuffle(pool)
    for i, p in enumerate(players):
        p["role"] = pool[i]
        # set default meta per role
        p["meta"] = {
            "silverdust": 1 if p["role"] == "blacksmith" else 0,
            "bullets": 2 if p["role"] == "gunner" else 0,
            "is_mason": p["role"] == "mason",
            "prince_survived": False,
            "marked_for_death": False,
            "protected": False,
            "lover_with": None,
            "converted": False,  # for cursed/converted
        }

# ----------------- UTILITY: player lookups -----------------
def find_player(g: Dict[str, Any], user_id: int) -> Optional[Dict[str, Any]]:
    for p in g.get("players", []):
        if p["user_id"] == user_id:
            return p
    return None

def alive_players(g: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in g.get("players", []) if p.get("alive", False)]

def alive_nonwolves(g: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in alive_players(g) if p["role"] not in ("wolf", "alpha")]

def wolves(g: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in alive_players(g) if p["role"] in ("wolf", "alpha")]

# ----------------- GAME FLOW: phase loop -----------------
async def start_game_loop(chat_id: int, send_fn):
    """
    Main loop per game chat. This is triggered when game starts.
    Uses send_fn(chat_id, text) to send updates into the chat.
    """
    g = await get_game(chat_id)
    if not g:
        return
    # Mark day_count/night_count
    # Starting phase: night 0? We'll start with night to allow seer to act first.
    await save_game(chat_id, {"phase": "night", "night_count": 0, "day_count": 0})
    await send_fn(chat_id, "🔔 Game started! Night falls... Use your night actions by /action <type> <@target> command.")
    while True:
        g = await get_game(chat_id)
        if not g or g.get("phase") == "ended":
            return
        if g["phase"] == "night":
            await send_fn(chat_id, f"🌙 Night {g.get('night_count',0)+1} begins. You have {NIGHT_SECONDS} seconds to submit night actions.")
            # clear previous actions/votes
            await save_game(chat_id, {"votes": {}, "actions": {}})
            # wait night duration
            await asyncio.sleep(NIGHT_SECONDS)
            # reload and process night
            g = await get_game(chat_id)
            await process_night(chat_id, send_fn)
            # set day
            await save_game(chat_id, {"phase": "day", "day_count": g.get("day_count", 0) + 1})
        elif g["phase"] == "day":
            await send_fn(chat_id, f"☀️ Day {g.get('day_count')} begins. Discuss and vote! Voting lasts {VOTE_TIME_SECONDS} seconds.")
            # open votes
            await save_game(chat_id, {"votes": {}})
            await asyncio.sleep(VOTE_TIME_SECONDS)
            await tally_votes_and_lynch(chat_id, send_fn)
            # continue to night if still more than one team alive
            g = await get_game(chat_id)
            if check_win_condition(g):
                # game ended
                winners = determine_winners(g)
                await send_fn(chat_id, f"🏁 Game over! Winners: {', '.join(winners)}")
                await finalize_game(chat_id, send_fn)
                return
            await save_game(chat_id, {"phase": "night", "night_count": g.get("night_count", 0) + 1})
        else:
            return

# ----------------- send helper -----------------
async def safe_send(chat_id: int, text: str):
    try:
        await app.send_message(chat_id, text)
    except Exception as e:
        print("send error:", e)

# ----------------- NIGHT PROCESSING -----------------
async def process_night(chat_id: int, send_fn):
    """
    Resolve night actions in an order:
    - Collect actions from game doc
    - Resolve protections (guardian), blacksmith, cupid, cultist hunter, wolf kill (pack decision),
      harlot visits, hunter, cursed conversions, alpha bite chance conversion logic, etc.
    This simplified resolution tries to preserve reasonable behavior.
    """
    g = await get_game(chat_id)
    if not g: return
    actions = g.get("actions", {})  # {user_id: {action_type, target_id, extra}}
    # Reset per-night marks
    for p in g["players"]:
        p["protected"] = False
        p["marked_for_death"] = False
    # 1) Guardian protections
    for uid, act in actions.items():
        if act.get("action") == "protect":
            target = act.get("target")
            pl = find_player(g, target)
            if pl and pl["alive"]:
                pl["protected"] = True
                await safe_send(chat_id, f"🛡️ A guardian watches over {pl['name']}.")
    # 2) Blacksmith silverdust: players with silverdust can spend to prevent a wolf kill on target
    # handled during kill resolution
    # 3) Cupid linking occurs at start (handled earlier)
    # 4) Cultist hunter hunts: immediate kill if target is cultist (not implemented cultist role in pool)
    # 5) Wolves decide target:
    wolf_targets = {}
    for uid, act in actions.items():
        pl = find_player(g, uid)
        if pl and pl["alive"] and pl["role"] in ("wolf", "alpha"):
            t = act.get("target")
            if t:
                wolf_targets.setdefault(t, 0)
                wolf_targets[t] += 1
    # Choose final wolf target: highest votes by wolves
    wolf_target_id = None
    if wolf_targets:
        wolf_target_id = max(wolf_targets.items(), key=lambda kv: kv[1])[0]
    # 6) Resolve wolf kill:
    if wolf_target_id:
        target_pl = find_player(g, wolf_target_id)
        if target_pl and target_pl["alive"]:
            # if protected -> failed
            if target_pl.get("protected"):
                await safe_send(chat_id, f"🌙 Wolves tried to devour {target_pl['name']}, but they were protected!")
            else:
                # check blacksmith silverdust on target? iterate players for blacksmith uses
                bs_blocked = False
                for p in g["players"]:
                    if p["role"] == "blacksmith" and p["meta"].get("silverdust",0) > 0:
                        # blacksmith can choose to spend via action
                        bs_action = actions.get(str(p["user_id"])) or actions.get(p["user_id"])
                        if bs_action and bs_action.get("action") == "usesilver" and bs_action.get("target") == target_pl["user_id"]:
                            # chance to prevent (we'll make deterministic for chosen)
                            p["meta"]["silverdust"] -= 1
                            await safe_send(chat_id, f"⚒️ Blacksmith used silverdust to protect {target_pl['name']}.")
                            bs_blocked = True
                            break
                if bs_blocked:
                    # no death
                    pass
                else:
                    # Alpha conversion chance
                    if target_pl["role"] == "cursed":
                        # cursed becomes wolf instead of dying
                        target_pl["role"] = "wolf"
                        target_pl["meta"]["converted"] = True
                        await safe_send(chat_id, f"🩸 {target_pl['name']} was bitten and has become a werewolf!")
                    else:
                        # 20% extra effect if any attacker is alpha (convert rather than kill)
                        attackers = [find_player(g, int(uid)) for uid, a in actions.items() if find_player(g, int(uid)) and find_player(g, int(uid))["role"] in ("wolf","alpha") and a.get("target")==wolf_target_id]
                        alpha_present = any(a for a in attackers if a and a["role"]=="alpha")
                        if alpha_present and random.random() < 0.2:
                            # convert
                            target_pl["role"] = "wolf"
                            target_pl["meta"]["converted"] = True
                            await safe_send(chat_id, f"🩸 {target_pl['name']} survived the bite — and joins the pack as a werewolf!")
                        else:
                            # mark for death
                            target_pl["alive"] = False
                            await safe_send(chat_id, f"🩸 {target_pl['name']} was killed by the wolves during the night.")
    # 7) Harlot visits and other visit interactions
    for uid, act in actions.items():
        if act.get("action") == "visit":
            target = act.get("target")
            visitor = find_player(g, int(uid))
            tgt = find_player(g, target)
            if not visitor or not tgt: continue
            # if visiting a wolf, visitor dies
            if tgt["role"] in ("wolf","alpha"):
                visitor["alive"] = False
                await safe_send(chat_id, f"💀 {visitor['name']} visited {tgt['name']} and was killed!")
            else:
                # if target was targeted by wolves to kill, normal rules apply (visitor may get killed if wolves target them)
                await safe_send(chat_id, f"🏠 {visitor['name']} visited {tgt['name']} tonight.")
    # 8) Detective/investigate/seer/fool results
    for uid, act in actions.items():
        if act.get("action") == "investigate":
            target = act.get("target")
            pl_target = find_player(g, target)
            investigator = find_player(g, int(uid))
            if not pl_target or not investigator: continue
            # Detective has 40% chance to be detected - implement as messaging and mark
            if investigator["role"] == "detective":
                # 40% chance wolves detect detective: we will send a "detected" message to wolves (not implemented secure PM)
                if random.random() < 0.4:
                    # we announce to chat (for simplicity) that detective was detected - in more realistic design we'd message wolves privately
                    await safe_send(chat_id, f"⚠️ The wolves sensed activity in the night (a detective may have been investigating).")
                # reveal role to investigator
                await safe_send(chat_id, f"🔎 Detective result: {pl_target['name']} is **{pl_target['role']}**")
            elif investigator["role"] == "seer":
                # seer reveals exact role
                await safe_send(chat_id, f"🔮 Seer result: {pl_target['name']} is **{pl_target['role']}**")
            elif investigator["role"] == "fool":
                # fool sees random role
                random_role = random.choice(list(ROLE_DESCRIPTIONS.keys()))
                await safe_send(chat_id, f"🔮 Fool result: {pl_target['name']} is **{random_role}** (not a real result).")
    # 9) Cultist hunter effect (simplified: if they hunted a cultist role, kill)
    for uid, act in actions.items():
        if act.get("action") == "hunt":
            target = act.get("target")
            hunter = find_player(g, int(uid))
            tgt = find_player(g, target)
            if hunter and tgt:
                if tgt.get("role") == "cultist":
                    tgt["alive"] = False
                    await safe_send(chat_id, f"🏹 Cultist Hunter killed {tgt['name']} (they were cult).")
                else:
                    await safe_send(chat_id, f"🏹 Cultist Hunter hunted {tgt['name']}, but they were not a cultist.")
    # 10) Gunner/daily/day shots handled via actions (if action == shoot)
    for uid, act in actions.items():
        if act.get("action") == "shoot":
            shooter = find_player(g, int(uid))
            target = find_player(g, act.get("target"))
            if shooter and target and shooter["meta"].get("bullets",0)>0:
                shooter["meta"]["bullets"] -= 1
                # immediate kill
                if target["protected"]:
                    await safe_send(chat_id, f"🔫 {shooter['name']} shot {target['name']}, but they were protected!")
                else:
                    target["alive"] = False
                    await safe_send(chat_id, f"🔫 {shooter['name']} shot and killed {target['name']}!")
    # 11) After resolving, persist player states
    await save_game(chat_id, {"players": g["players"]})
    # check win condition
    if check_win_condition(g):
        winners = determine_winners(g)
        await send_fn(chat_id, f"🏁 Game over! Winners: {', '.join(winners)}")
        await finalize_game(chat_id, send_fn)
        return

# ----------------- VOTING / LYNCH -----------------
async def tally_votes_and_lynch(chat_id: int, send_fn):
    g = await get_game(chat_id)
    if not g: return
    votes = g.get("votes", {})  # voter_id -> target_id
    # count votes among alive players only
    tally = {}
    for voter_str, target in votes.items():
        try:
            voter_id = int(voter_str)
        except:
            voter_id = voter_str
        voter = find_player(g, voter_id)
        if not voter or not voter.get("alive"): continue
        if target is None: continue
        tally.setdefault(target,0)
        # mayor may have double vote if revealed (we haven't implemented reveal action; simplified)
        # clumsy may vote random - handled client-side on vote submission
        tally[target] += 1
    if not tally:
        await send_fn(chat_id, "No votes were cast today.")
        return
    # find highest
    target_id, count = max(tally.items(), key=lambda kv: kv[1])
    target_pl = find_player(g, target_id)
    if not target_pl:
        await send_fn(chat_id, "Vote target not found.")
        return
    # Prince survives once: if prince and hasn't survived before => reveal and survive
    if target_pl["role"] == "prince" and not target_pl["meta"].get("prince_survived", False):
        target_pl["meta"]["prince_survived"] = True
        await save_game(chat_id, {"players": g["players"]})
        await send_fn(chat_id, f"👑 The village tried to lynch {target_pl['name']} (Prince)! They survived but their role is revealed.")
        return
    # kill target
    target_pl["alive"] = False
    await save_game(chat_id, {"players": g["players"]})
    await send_fn(chat_id, f"⚖️ {target_pl['name']} was lynched by the village. They were a **{target_pl['role']}**.")
    # if seer died and an apprentice seer exists, promote them
    if target_pl["role"] == "seer":
        for p in g["players"]:
            if p["role"] == "apprentice_seer" and p["alive"]:
                p["role"] = "seer"
                await save_game(chat_id, {"players": g["players"]})
                await send_fn(chat_id, f"🔮 {p['name']} is now the Seer (apprentice promoted).")
    # check win
    if check_win_condition(g):
        winners = determine_winners(g)
        await send_fn(chat_id, f"🏁 Game over! Winners: {', '.join(winners)}")
        await finalize_game(chat_id, send_fn)
        return

# ----------------- WIN CONDITIONS -----------------
def check_win_condition(g: Dict[str, Any]) -> bool:
    """
    Return True if either wolves or villagers (or lovers) win.
    Simplified:
    - Villagers win if no wolves alive
    - Wolves win if wolves >= non-wolves
    - Lovers win if both lovers alive and everyone else dead (or at least one lover on winning team)
    """
    if not g:
        return True
    alive = alive_players(g)
    wolves_alive = [p for p in alive if p["role"] in ("wolf","alpha")]
    nonwolves_alive = [p for p in alive if p["role"] not in ("wolf","alpha")]
    # lovers scenario
    lovers = [p for p in alive if p.get("lover_with")]
    if len(lovers) == 2 and len(alive) == 2:
        return True
    if len(wolves_alive) == 0 and len(nonwolves_alive) > 0:
        return True
    if len(wolves_alive) >= len(nonwolves_alive) and len(wolves_alive) > 0:
        return True
    return False

def determine_winners(g: Dict[str, Any]) -> List[str]:
    alive = alive_players(g)
    wolves_alive = [p for p in alive if p["role"] in ("wolf","alpha")]
    nonwolves_alive = [p for p in alive if p["role"] not in ("wolf","alpha")]
    winners = []
    lovers = [p for p in alive if p.get("lover_with")]
    if len(lovers) == 2 and len(alive) == 2:
        return [lovers[0]["name"], lovers[1]["name"]]
    if len(wolves_alive) == 0:
        winners = [p["name"] for p in alive if p["role"] not in ("wolf","alpha")]
    elif len(wolves_alive) >= len(nonwolves_alive):
        winners = [p["name"] for p in alive if p["role"] in ("wolf","alpha")]
    else:
        winners = [p["name"] for p in alive if p["role"] not in ("wolf","alpha")]
    return winners

# ----------------- FINALIZE: award leaderboard -----------------
async def finalize_game(chat_id: int, send_fn):
    g = await get_game(chat_id)
    if not g: return
    winners = determine_winners(g)
    # update players_col leaderboard: +1 win for winners, +1 loss for losers
    for p in g["players"]:
        existing = await players_col.find_one({"user_id": p["user_id"]})
        if not existing:
            await players_col.insert_one({"user_id": p["user_id"], "name": p["name"], "wins": 0, "losses": 0})
            existing = await players_col.find_one({"user_id": p["user_id"]})
        if p["name"] in winners:
            await players_col.update_one({"user_id": p["user_id"]}, {"$inc": {"wins": 1}})
        else:
            await players_col.update_one({"user_id": p["user_id"]}, {"$inc": {"losses": 1}})
    # reveal final roles
    role_text = "Final roles:\n"
    for p in g["players"]:
        role_text += f"- {p['name']}: {p['role']} ({'alive' if p['alive'] else 'dead'})\n"
    await send_fn(chat_id, role_text)
    # end game
    await save_game(chat_id, {"phase": "ended"})
    # archive or delete game as desired
    return

# ----------------- COMMAND HANDLERS -----------------
@app.on_message(filters.command("create_werewolf") & filters.group)
async def cmd_create(_, m: Message):
    # Create a game lobby in the group
    chat_id = m.chat.id
    owner = m.from_user.id
    existing = await get_game(chat_id)
    if existing and existing.get("phase") != "ended":
        return await m.reply("A game is already active or in lobby in this chat.", quote=True)
    await create_game(chat_id, owner)
    await m.reply("🟢 Werewolf game lobby created! Type `!join` to join. Owner can `!start` to start the game.", quote=True)

@app.on_message(filters.regex(r"^!join$") & filters.group)
async def cmd_join(_, m: Message):
    chat_id = m.chat.id
    user = m.from_user
    g = await get_game(chat_id)
    if not g:
        return await m.reply("No game lobby in this chat. Owner can create with /create.", quote=True)
    if g["phase"] != "lobby":
        return await m.reply("Game already started. Wait for next one.", quote=True)
    await add_player(chat_id, {"id": user.id, "first_name": user.first_name, "username": user.username})
    await m.reply(f"✅ {user.first_name} joined the lobby. Current players: {len(g['players'])+1}", quote=True)

@app.on_message(filters.regex(r"^!leave$") & filters.group)
async def cmd_leave(_, m: Message):
    chat_id = m.chat.id
    user_id = m.from_user.id
    g = await get_game(chat_id)
    if not g:
        return await m.reply("No game here.", quote=True)
    await remove_player(chat_id, user_id)
    await m.reply("You left the game lobby.", quote=True)

@app.on_message(filters.regex(r"^!players$") & filters.group)
async def cmd_players(_, m: Message):
    g = await get_game(m.chat.id)
    if not g:
        return await m.reply("No game lobby.", quote=True)
    text = f"Players ({len(g.get('players',[]))}):\n"
    for p in g.get("players", []):
        text += f"- {p['name']} ({'alive' if p.get('alive',True) else 'dead'})\n"
    await m.reply(text, quote=True)

@app.on_message(filters.regex(r"^!start$") & filters.group)
async def cmd_start(_, m: Message):
    chat_id = m.chat.id
    g = await get_game(chat_id)
    if not g:
        return await m.reply("No game lobby here. Create with /create", quote=True)
    if len(g.get("players", [])) < 4:
        return await m.reply("Need at least 4 players to start.", quote=True)
    if m.from_user.id != g.get("owner_id"):
        return await m.reply("Only the lobby owner can start the game.", quote=True)
    # Assign roles
    assign_roles_to_players(g["players"])
    # Special handling: cupid choose lovers immediately if cupid exists. We'll assign and notify privately (simplified: announce in chat)
    lovers = []
    for p in g["players"]:
        if p["role"] == "cupid":
            # pick two random others
            others = [x for x in g["players"] if x["user_id"] != p["user_id"]]
            if len(others) >= 2:
                a,b = random.sample(others,2)
                a["lover_with"] = b["user_id"]
                b["lover_with"] = a["user_id"]
                lovers = [a,b]
    await save_game(chat_id, {"players": g["players"], "phase": "night", "day_count": 0, "night_count": 0})
    # announce roles privately (in production do via pm)
    role_list = "Roles assigned:\n"
    roles_text = "\n".join(role_list) if isinstance(role_list, list) else str(role_list)
    for p in g["players"]:
        role_list += f"- {p['name']}: {p['role']}\n"
    await app.send_message(chat_id, "🔐 Roles assigned. Night begins. (For demo we announce roles publicly — remove in production)\n\n" + role_list)
    # start main loop
    asyncio.create_task(start_game_loop(chat_id, safe_send))

# Action command for night/day abilities
@app.on_message(filters.command("waction") & filters.group)
async def cmd_awction(_, m: Message):
    """
    Usage (examples):
    /action kill @target   (wolf)
    /action protect @target  (guardian)
    /action investigate @target  (seer/detective)
    /action visit @target  (harlot)
    /action shoot @target  (gunner)
    /action usesilver @target (blacksmith)
    /action hunt @target (cultist hunter)
    """
    chat_id = m.chat.id
    user = m.from_user
    g = await get_game(chat_id)
    if not g:
        return await m.reply("No active game.", quote=True)
    if g.get("phase") != "night":
        return await m.reply("Actions are only allowed during night.", quote=True)
    # parse
    if len(m.command) < 3:
        return await m.reply("Usage: /waction [type] @target", quote=True)
    act = m.command[1].lower()
    # resolve mention
    target_user = None
    if m.entities:
        for ent in m.entities:
            if ent.type in ("mention","text_mention"):
                if ent.type == "text_mention":
                    target_user = ent.user
                else:
                    username = m.text[ent.offset+1: ent.offset+ent.length]  # drop '@'
                    try:
                        target_user = await app.get_users(username)
                    except Exception:
                        target_user = None
                break
    if not target_user:
        return await m.reply("Could not resolve target user. Mention them.", quote=True)
    target_id = target_user.id
    # store action
    actions = g.get("actions", {})
    actions[str(user.id)] = {"action": act, "target": target_id}
    await save_game(chat_id, {"actions": actions})
    await m.reply(f"Action recorded: {act} -> {target_user.first_name}", quote=True)

# Vote command during day
@app.on_message(filters.command("wvote") & filters.group)
async def cmd_vowte(_, m: Message):
    chat_id = m.chat.id
    g = await get_game(chat_id)
    if not g or g.get("phase") != "day":
        return await m.reply("Voting is only allowed during the day phase.", quote=True)
    if len(m.command) < 2:
        return await m.reply("Usage: /vote @target", quote=True)
    # resolve target
    target_user = None
    if m.reply_to_message:
        target_user = m.reply_to_message.from_user
    else:
        # check mention
        if m.entities:
            for ent in m.entities:
                if ent.type in ("mention","text_mention"):
                    if ent.type == "text_mention":
                        target_user = ent.user
                    else:
                        username = m.text[ent.offset+1: ent.offset+ent.length]
                        try:
                            target_user = await app.get_users(username)
                        except:
                            target_user = None
                    break
    if not target_user:
        return await m.reply("Could not resolve target. Reply or mention a user.", quote=True)
    votes = g.get("votes", {})
    # clumsy chance: if voter is clumsy, 50% chance random vote
    voter = find_player(g, m.from_user.id)
    target_id = target_user.id
    if voter and voter.get("role") == "clumsy" and random.random() < 0.5:
        # pick random alive target
        alive = [p for p in g["players"] if p["alive"] and p["user_id"] != m.from_user.id]
        if alive:
            chosen = random.choice(alive)
            target_id = chosen["user_id"]
            await m.reply(f"😵 The clumsy vote misfires and votes for {chosen['name']} instead.", quote=True)
    votes[str(m.from_user.id)] = target_id
    await save_game(chat_id, {"votes": votes})
    await m.reply(f"Vote recorded against {target_user.first_name}.", quote=True)

# Leaderboard commands
@app.on_message(filters.command("wrank"))
async def cmdw_rank(_, m: Message):
    user = m.from_user
    p = await players_col.find_one({"user_id": user.id})
    if not p:
        return await m.reply("No stats for you yet. Play some games!", quote=True)
    await m.reply(f"{user.first_name}'s stats — Wins: {p.get('wins',0)}, Losses: {p.get('losses',0)}", quote=True)

@app.on_message(filters.command("wtop"))
async def cmdw_top(_, m: Message):
    cursor = players_col.find({}).sort("wins",-1).limit(10)
    text = "🏆 Top players by wins:\n"
    i = 1
    async for doc in cursor:
        text += f"{i}. {doc.get('name')} — {doc.get('wins',0)} wins\n"
        i += 1
    await m.reply(text, quote=True)

@app.on_message(filters.command("wstatus"))
async def cmd_wstatus(_, m: Message):
    g = await get_game(m.chat.id)
    if not g:
        return await m.reply("No active game in this chat.", quote=True)
    text = f"Game phase: {g.get('phase')}\nPlayers: {len(g.get('players',[]))}\nDay: {g.get('day_count')} Night: {g.get('night_count')}"
    await m.reply(text, quote=True)

# ----------------- STARTUP -----------------
@app.on_message(filters.command("helw"))
async def cmd_help(_, m: Message):
    text = (
        "📜 Werewolf Bot Help\n"
        "Group commands:\n"
        "/create — create a game lobby\n"
        "!join — join lobby\n"
        "!leave — leave\n"
        "/start (owner) — start game\n"
        "/players — list players\n\n"
        "Night actions (use during night):\n"
        "/action protect @user (guardian)\n"
        "/action kill @user (wolf)\n"
        "/action investigate @user (seer/detective)\n"
        "/action visit @user (harlot)\n"
        "/action shoot @user (gunner)\n"
        "/action usesilver @user (blacksmith)\n"
        "/action hunt @user (cultist hunter)\n\n"
        "Day:\n"
        "/vote @user — vote to lynch\n\n"
        "Leaderboard: /rank /top\n"
    )
    await m.reply(text, quote=True)

