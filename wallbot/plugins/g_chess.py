"""
Advanced Button-only Chess Bot
- All game button callbacks begin with '_' and are handled by the single regex callback handler:
  @app.on_callback_query(filters.regex(r"^_"))
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import motor.motor_asyncio
from bson import ObjectId
import chess
from config import DB_URL
from wallbot import wbot as app


load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chessbot")


DB_NAME = "chess_bot_db"

mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]
users_col = db["users"]

FILES = "abcdefgh"
RANKS = "87654321"
PIECE_EMOJI = {
    'P': "♙", 'N': "♘", 'B': "♗", 'R': "♖", 'Q': "♕", 'K': "♔",
    'p': "♟︎", 'n': "♞", 'b': "♝", 'r': "♜", 'q': "♛", 'k': "♚",
    '.': "·"
}

# Time controls (name: seconds, inc)
TIME_CONTROLS = {
    "blitz_3+2": {"name": "3+2 Blitz", "white": 3*60, "black": 3*60, "inc": 2},
    "blitz_5+0": {"name": "5|0 Blitz", "white": 5*60, "black": 5*60, "inc": 0},
    "rapid_10+5": {"name": "10+5 Rapid", "white": 10*60, "black": 10*60, "inc": 5},
    "rapid_15+10": {"name": "15+10 Rapid", "white": 15*60, "black": 15*60, "inc": 10},
}
K_FACTOR = 32

# in-memory clock tasks
clock_tasks: Dict[str, asyncio.Task] = {}

# ----------------- helpers -----------------
def board_to_matrix(board: chess.Board) -> List[List[str]]:
    mat = []
    for r in range(7, -1, -1):
        row = []
        for f in range(8):
            sq = chess.square(f, r)
            piece = board.piece_at(sq)
            row.append(piece.symbol() if piece else '.')
        mat.append(row)
    return mat

def seconds_to_clock(s: int) -> str:
    if s < 0: s = 0
    m = s // 60
    sec = s % 60
    return f"{m}:{sec:02d}"

def render_board_text(board: chess.Board, white_time: int, black_time: int, control_name: str) -> str:
    lines = []
    for r in range(7, -1, -1):
        row = []
        for f in range(8):
            sq = chess.square(f, r)
            piece = board.piece_at(sq)
            row.append(PIECE_EMOJI[piece.symbol()] if piece else "·")
        lines.append(f"{r+1} " + " ".join(row))
    lines.append("   a b c d e f g h")
    turn = "White" if board.turn == chess.WHITE else "Black"
    wt = seconds_to_clock(white_time)
    bt = seconds_to_clock(black_time)
    status = ""
    if board.is_checkmate():
        status = " — CHECKMATE"
    elif board.is_stalemate():
        status = " — STALEMATE"
    elif board.is_check():
        status = " — CHECK"
    return f"⏱ {control_name} | White: {wt} — Black: {bt}\nTurn: {turn}{status}\n\n" + "\n".join(lines)

def legal_moves_map(board: chess.Board) -> Dict[str, List[str]]:
    m = {}
    for mv in board.legal_moves:
        u = mv.uci()
        frm = u[:2]; to = u[2:4]
        m.setdefault(frm, []).append(to)
    return m

async def ensure_user_doc(user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    u = await users_col.find_one({"user_id": user_id})
    if not u:
        u = {"user_id": user_id, "username": username or f"user{user_id}", "elo": 1200, "wins": 0, "losses": 0, "draws": 0, "games": 0}
        await users_col.insert_one(u)
    return u

def elo_expected(a_rating: int, b_rating: int) -> float:
    return 1.0 / (1.0 + 10 ** ((b_rating - a_rating) / 400.0))

def elo_update(a_rating: int, b_rating: int, score_a: float, k: int = K_FACTOR) -> int:
    exp = elo_expected(a_rating, b_rating)
    return int(round(a_rating + k * (score_a - exp)))

# ----------------- keyboard builder -----------------
def make_board_keyboard(gid: str, board: chess.Board, selected: Optional[str], legal_moves: Optional[Dict[str, List[str]]], show_suggestions: bool) -> InlineKeyboardMarkup:
    mat = board_to_matrix(board)
    kb_rows: List[List[InlineKeyboardButton]] = []
    for r_idx, rank in enumerate(RANKS):
        row: List[InlineKeyboardButton] = []
        for f_idx, file in enumerate(FILES):
            sq = f"{file}{rank}"
            piece = mat[r_idx][f_idx]
            label = PIECE_EMOJI.get(piece, "·")
            cb = f"_select|{gid}|{sq}"
            highlight = False
            if selected and legal_moves:
                dests = legal_moves.get(selected, [])
                if sq in dests:
                    highlight = True
                    cb = f"_move|{gid}|{selected}{sq}"
            if selected == sq:
                display = f"🔘{label}"
            elif highlight:
                display = f"🔷{label}"
            else:
                display = label
            row.append(InlineKeyboardButton(display, callback_data=cb))
        kb_rows.append(row)
    ctrl = [
        InlineKeyboardButton("Surrender", callback_data=f"_resign|{gid}"),
        InlineKeyboardButton("Refresh", callback_data=f"_refresh|{gid}"),
        InlineKeyboardButton("New Game", callback_data=f"_newgame|{gid}")
    ]
    ctrl2 = [
        InlineKeyboardButton("Suggest: On" if show_suggestions else "Suggest: Off", callback_data=f"_suggest_toggle|{gid}"),
        InlineKeyboardButton("Time", callback_data=f"_timechoose|{gid}")
    ]
    kb_rows.append(ctrl)
    kb_rows.append(ctrl2)
    return InlineKeyboardMarkup(kb_rows)

# ----------------- clock worker -----------------
async def clock_worker(gid: str):
    log.info("clock_worker start %s", gid)
    try:
        while True:
            game = await games_col.find_one({"_id": ObjectId(gid)})
            if not game:
                log.info("game removed %s", gid); return
            if not game.get("started"):
                await asyncio.sleep(1.0); continue
            board = chess.Board(game["fen"])
            control = game.get("time_control", "blitz_5+0")
            cfg = TIME_CONTROLS.get(control, TIME_CONTROLS["blitz_5+0"])
            white_time = int(game.get("white_time", cfg["white"]))
            black_time = int(game.get("black_time", cfg["black"]))
            last_ts = game.get("last_move_ts") or datetime.utcnow().timestamp()
            now_ts = datetime.utcnow().timestamp()
            elapsed = int(now_ts - last_ts)
            if board.turn == chess.WHITE:
                white_time -= elapsed
            else:
                black_time -= elapsed
            if white_time <= 0 or black_time <= 0:
                if white_time <= 0 and black_time <= 0:
                    result = "draw"
                elif white_time <= 0:
                    result = "black"
                else:
                    result = "white"
                await finalize_game_on_timeout(ObjectId(gid), result)
                return
            await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"white_time": white_time, "black_time": black_time, "last_move_ts": now_ts}})
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        log.info("clock_worker cancelled %s", gid)
    except Exception:
        log.exception("clock_worker error %s", gid)

async def start_clock_task(gid: str):
    if gid in clock_tasks:
        clock_tasks[gid].cancel()
    clock_tasks[gid] = asyncio.create_task(clock_worker(gid))

async def stop_clock_task(gid: str):
    t = clock_tasks.pop(gid, None)
    if t:
        t.cancel()

# ----------------- finalize on timeout -----------------
async def finalize_game_on_timeout(game_oid: ObjectId, result: str):
    game = await games_col.find_one({"_id": game_oid})
    if not game: return
    white = game.get("white_id")
    black = game.get("black_id")
    chat_id = game.get("chat_id")
    await games_col.delete_one({"_id": game_oid})
    await stop_clock_task(str(game_oid))
    if result == "draw":
        await users_col.update_one({"user_id": white}, {"$inc": {"draws": 1, "games": 1}}, upsert=True)
        if black:
            await users_col.update_one({"user_id": black}, {"$inc": {"draws": 1, "games": 1}}, upsert=True)
        await app.send_message(chat_id, "🟰 Both players timed out. Draw.")
        return
    if result == "white":
        winner = white; loser = black
    else:
        winner = black; loser = white
    w_doc = await ensure_user_doc(winner)
    l_doc = await ensure_user_doc(loser)
    w_old = w_doc.get("elo", 1200); l_old = l_doc.get("elo", 1200)
    w_new = elo_update(w_old, l_old, 1.0); l_new = elo_update(l_old, w_old, 0.0)
    await users_col.update_one({"user_id": winner}, {"$set": {"elo": w_new}, "$inc": {"wins": 1, "games": 1}}, upsert=True)
    await users_col.update_one({"user_id": loser}, {"$set": {"elo": l_new}, "$inc": {"losses": 1, "games": 1}}, upsert=True)
    await app.send_message(chat_id, f"⏳ Time out! Winner by clock: [user](tg://user?id={winner})")

# ----------------- message commands (minimal) -----------------
@app.on_message(filters.command("sch"))
async def cmd_stcfgart(_, m: Message):
    await ensure_user_doc(m.from_user.id, m.from_user.username or m.from_user.first_name)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("♟ New Game (open lobby)", callback_data=f"_newgame|open")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data=f"_leaderboard|0")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"_profile|{m.from_user.id}")]
    ])
    await m.reply("♟ Button Chess — use the buttons to play. Create a game or view leaderboard.", reply_markup=kb)

@app.on_message(filters.command("chprofile"))
async def cmd_profbvvile_msg(_, m: Message):
    target = m.from_user.id
    if len(m.command) > 1:
        try: target = int(m.command[1])
        except: target = target
    u = await users_col.find_one({"user_id": target})
    if not u: return await m.reply("No profile found.")
    await m.reply_text(f"👤 {u.get('username')}\nELO: {u.get('elo',1200)}\nG:{u.get('games',0)} W:{u.get('wins',0)} L:{u.get('losses',0)} D:{u.get('draws',0)}")

# ----------------- central callback handler (regex starts with '_') -----------------
@app.on_callback_query(filters.regex(r"^_"))
async def cb_hachndler(_, cq: CallbackQuery):
    data = (cq.data or "")[1:]  # remove leading underscore
    parts = data.split("|")
    if not parts:
        return await cq.answer("Invalid callback", show_alert=True)
    action = parts[0]
    # open-lobby newgame: _newgame|open  or _newgame|<opponent_id>
    if action == "newgame":
        # either open lobby or challenge specific user id
        arg = parts[1] if len(parts) > 1 else "open"
        author = cq.from_user
        board = chess.Board()
        control = "blitz_5+0"
        cfg = TIME_CONTROLS[control]
        doc = {
            "chat_id": cq.message.chat.id,
            "creator_id": author.id,
            "white_id": author.id,
            "white_name": author.first_name or author.username,
            "black_id": None if arg == "open" else int(arg),
            "black_name": None,
            "fen": board.fen(),
            "moves": [],
            "started": False if arg == "open" else True,
            "created_at": datetime.utcnow(),
            "message_id": None,
            "selected_square": None,
            "suggestions": True,
            "time_control": control,
            "white_time": cfg["white"],
            "black_time": cfg["black"],
            "inc": cfg["inc"],
            "last_move_ts": datetime.utcnow().timestamp() if arg != "open" else None
        }
        res = await games_col.insert_one(doc)
        gid = str(res.inserted_id)
        kb = make_board_keyboard(gid, board, None, {}, show_suggestions=True)
        if arg == "open":
            join_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Join as Black", callback_data=f"_join|{gid}")]])
            sent = await cq.message.reply_text(f"♟ Open lobby by {author.first_name}\nGame ID: {gid}\nAnyone can join as Black.", reply_markup=join_kb)
            await games_col.update_one({"_id": res.inserted_id}, {"$set": {"message_id": sent.id}})
            return await cq.answer("Lobby created.")
        else:
            # started game with specified opponent id (if present)
            sent = await cq.message.reply_text(f"♟ Game started!\n{render_board_text(board, doc['white_time'], doc['black_time'], cfg['name'])}", reply_markup=kb)
            await games_col.update_one({"_id": res.inserted_id}, {"$set": {"message_id": sent.id, "started": True}})
            await ensure_user_doc(author.id, author.first_name)
            await ensure_user_doc(doc["black_id"], None)
            await start_clock_task(gid)
            return await cq.answer("Game created and started.")

    # join: _join|<gid>
    if action == "join":
        if len(parts) < 2: return await cq.answer("Missing game id", show_alert=True)
        gid = parts[1]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except Exception:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game:
            return await cq.answer("Game not found", show_alert=True)
        if game.get("started"):
            return await cq.answer("Game already started", show_alert=True)
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"black_id": cq.from_user.id, "black_name": cq.from_user.first_name or cq.from_user.username, "started": True, "last_move_ts": datetime.utcnow().timestamp()}})
        game = await games_col.find_one({"_id": ObjectId(gid)})
        board = chess.Board(game["fen"])
        kb = make_board_keyboard(gid, board, None, legal_moves_map(board), show_suggestions=bool(game.get("suggestions", True)))
        try:
            await app.edit_message_text(game["chat_id"], game["message_id"], text=f"♟️ Game started!\n{render_board_text(board, game['white_time'], game['black_time'], TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except Exception:
            sent = await app.send_message(game["chat_id"], f"♟️ Game started!\n{render_board_text(board, game['white_time'], game['black_time'], TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
            await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"message_id": sent.id}})
        await ensure_user_doc(cq.from_user.id, cq.from_user.first_name)
        await ensure_user_doc(game["white_id"], game.get("white_name"))
        await start_clock_task(gid)
        return await cq.answer("You joined as Black. Game started!")

    # refresh: _refresh|<gid>
    if action == "refresh":
        if len(parts) < 2: return await cq.answer("Missing gid", show_alert=True)
        gid = parts[1]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game: return await cq.answer("Game not found", show_alert=True)
        board = chess.Board(game["fen"])
        kb = make_board_keyboard(gid, board, game.get("selected_square"), legal_moves_map(board), show_suggestions=bool(game.get("suggestions", True)))
        try:
            await cq.message.edit_text(f"♟️ Game\n{render_board_text(board, game['white_time'], game['black_time'], TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except:
            pass
        return await cq.answer()

    # toggle suggestions: _suggest_toggle|<gid>
    if action == "suggest_toggle":
        if len(parts) < 2: return await cq.answer("Missing gid", show_alert=True)
        gid = parts[1]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game: return await cq.answer("Game not found", show_alert=True)
        new = not bool(game.get("suggestions", True))
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"suggestions": new}})
        board = chess.Board(game["fen"])
        kb = make_board_keyboard(gid, board, game.get("selected_square"), legal_moves_map(board), show_suggestions=new)
        try:
            await cq.message.edit_text(f"♟️ Game\n{render_board_text(board, game['white_time'], game['black_time'], TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except:
            pass
        return await cq.answer(f"Suggestions {'enabled' if new else 'disabled'}")

    # timechoose: _timechoose|<gid> (rotate preset if not started)
    if action == "timechoose":
        if len(parts) < 2: return await cq.answer("Missing gid", show_alert=True)
        gid = parts[1]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game: return await cq.answer("Game not found", show_alert=True)
        if game.get("started"):
            return await cq.answer("Cannot change time after start", show_alert=True)
        keys = list(TIME_CONTROLS.keys())
        cur = game.get("time_control", keys[0])
        idx = keys.index(cur) if cur in keys else 0
        nxt = keys[(idx + 1) % len(keys)]
        cfg = TIME_CONTROLS[nxt]
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"time_control": nxt, "white_time": cfg["white"], "black_time": cfg["black"], "inc": cfg["inc"]}})
        try:
            await cq.message.edit_text(f"♟️ Lobby updated. Time: {cfg['name']}\nGame ID: {gid}")
        except:
            pass
        return await cq.answer(f"Time set to {cfg['name']}")

    # select: _select|<gid>|<sq>
    if action == "select":
        if len(parts) < 3: return await cq.answer("Missing args", show_alert=True)
        gid = parts[1]; sq = parts[2]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game or not game.get("started"): return await cq.answer("Game not active", show_alert=True)
        board = chess.Board(game["fen"])
        # check turn ownership
        player_id = cq.from_user.id
        side_to_move = chess.WHITE if board.turn == chess.WHITE else chess.BLACK
        expected = game.get("white_id") if side_to_move == chess.WHITE else game.get("black_id")
        if player_id != expected:
            return await cq.answer("Not your turn", show_alert=True)
        # verify piece exists and belongs to player
        try:
            sq_idx = chess.parse_square(sq)
        except:
            return await cq.answer("Invalid square", show_alert=True)
        piece = board.piece_at(sq_idx)
        if not piece or piece.color != board.turn:
            return await cq.answer("Select your own piece", show_alert=True)
        # store selected square and show legal moves highlight
        legal_map = legal_moves_map(board)
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"selected_square": sq}})
        kb = make_board_keyboard(gid, board, sq, legal_map, show_suggestions=bool(game.get("suggestions", True)))
        try:
            await cq.message.edit_text(f"♟️ {cq.from_user.first_name} selected {sq}\n{render_board_text(board, game['white_time'], game['black_time'], TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except:
            pass
        return await cq.answer(f"Selected {sq}")

    # move: _move|<gid>|<from><to> (e2e4)
    if action == "move":
        if len(parts) < 3: return await cq.answer("Missing move", show_alert=True)
        gid = parts[1]; uci = parts[2]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game or not game.get("started"): return await cq.answer("Game not active", show_alert=True)
        board = chess.Board(game["fen"])
        player_id = cq.from_user.id
        side_to_move = chess.WHITE if board.turn == chess.WHITE else chess.BLACK
        expected = game.get("white_id") if side_to_move == chess.WHITE else game.get("black_id")
        if player_id != expected:
            return await cq.answer("Not your turn", show_alert=True)
        # handle promotion choice
        from_sq = uci[:2]; to_sq = uci[2:4]
        try:
            mv = chess.Move.from_uci(uci)
        except:
            # check for promotion (missing piece)
            from_idx = chess.parse_square(from_sq); to_idx = chess.parse_square(to_sq)
            p = board.piece_at(from_idx)
            if p and p.piece_type == chess.PAWN and (chess.square_rank(to_idx) in (0,7)):
                prom_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Queen", callback_data=f"_promote|{gid}|{from_sq}{to_sq}|q"),
                     InlineKeyboardButton("Rook", callback_data=f"_promote|{gid}|{from_sq}{to_sq}|r")],
                    [InlineKeyboardButton("Bishop", callback_data=f"_promote|{gid}|{from_sq}{to_sq}|b"),
                     InlineKeyboardButton("Knight", callback_data=f"_promote|{gid}|{from_sq}{to_sq}|n")]
                ])
                await cq.message.reply_text("Choose promotion:", reply_markup=prom_kb)
                return await cq.answer()
            return await cq.answer("Invalid move", show_alert=True)
        if mv not in board.legal_moves:
            return await cq.answer("Illegal move", show_alert=True)
        # compute elapsed for clocks
        last_ts = game.get("last_move_ts", datetime.utcnow().timestamp())
        now_ts = datetime.utcnow().timestamp()
        elapsed = int(now_ts - last_ts)
        white_time = int(game.get("white_time", TIME_CONTROLS[game.get("time_control")]["white"]))
        black_time = int(game.get("black_time", TIME_CONTROLS[game.get("time_control")]["black"]))
        if board.turn == chess.WHITE:
            white_time = max(0, white_time - elapsed)
        else:
            black_time = max(0, black_time - elapsed)
        # push move, SAN
        board.push(mv)
        try:
            san = board.peek().san()
        except Exception:
            san = mv.uci()
        moves = game.get("moves", []); moves.append(san)
        # add increment to mover
        inc = int(game.get("inc", 0))
        if board.turn == chess.WHITE:
            # previous was black
            black_time += inc
        else:
            white_time += inc
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"fen": board.fen(), "moves": moves, "selected_square": None, "white_time": white_time, "black_time": black_time, "last_move_ts": now_ts}})
        # check end conditions
        outcome_msg = None
        if board.is_checkmate():
            winner_id = player_id
            loser_id = game.get("white_id") if winner_id == game.get("black_id") else game.get("black_id")
            wdoc = await ensure_user_doc(winner_id); ldoc = await ensure_user_doc(loser_id)
            w_new = elo_update(wdoc.get("elo",1200), ldoc.get("elo",1200), 1.0)
            l_new = elo_update(ldoc.get("elo",1200), wdoc.get("elo",1200), 0.0)
            await users_col.update_one({"user_id": winner_id}, {"$set": {"elo": w_new}, "$inc": {"wins":1,"games":1}}, upsert=True)
            await users_col.update_one({"user_id": loser_id}, {"$set": {"elo": l_new}, "$inc": {"losses":1,"games":1}}, upsert=True)
            outcome_msg = f"🏁 Checkmate! Winner: [user](tg://user?id={winner_id})"
        elif board.is_stalemate() or board.is_insufficient_material() or board.can_claim_threefold_repetition():
            await users_col.update_one({"user_id": game.get("white_id")}, {"$inc": {"draws":1,"games":1}}, upsert=True)
            if game.get("black_id"):
                await users_col.update_one({"user_id": game.get("black_id")}, {"$inc": {"draws":1,"games":1}}, upsert=True)
            outcome_msg = "🟰 Draw!"
        kb = make_board_keyboard(gid, board, None, legal_moves_map(board), show_suggestions=bool(game.get("suggestions", True)))
        try:
            await cq.message.edit_text(f"♟️ Move: {san}\n{render_board_text(board, white_time, black_time, TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except:
            pass
        if outcome_msg:
            await app.send_message(game["chat_id"], outcome_msg)
            await games_col.delete_one({"_id": ObjectId(gid)})
            await stop_clock_task(gid)
        else:
            await start_clock_task(gid)
        return await cq.answer("Move played.")

    # promote: _promote|<gid>|<from><to>|<piece>
    if action == "promote":
        if len(parts) < 4: return await cq.answer("Missing promotion", show_alert=True)
        gid = parts[1]; uci_move = parts[2]; prom = parts[3]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game: return await cq.answer("Game not found", show_alert=True)
        board = chess.Board(game["fen"])
        try:
            mv = chess.Move.from_uci(uci_move + prom)
        except:
            return await cq.answer("Invalid promotion", show_alert=True)
        if mv not in board.legal_moves:
            return await cq.answer("Illegal promotion", show_alert=True)
        board.push(mv)
        try:
            san = board.peek().san()
        except:
            san = mv.uci()
        moves = game.get("moves", []); moves.append(san)
        # clocks: similar handling as move (simple update)
        last_ts = game.get("last_move_ts", datetime.utcnow().timestamp())
        now_ts = datetime.utcnow().timestamp()
        elapsed = int(now_ts - last_ts)
        white_time = int(game.get("white_time")); black_time = int(game.get("black_time"))
        prev_mover_was_white = not board.turn
        inc = int(game.get("inc", 0))
        if prev_mover_was_white:
            white_time = max(0, white_time - elapsed) + inc
        else:
            black_time = max(0, black_time - elapsed) + inc
        await games_col.update_one({"_id": ObjectId(gid)}, {"$set": {"fen": board.fen(), "moves": moves, "selected_square": None, "white_time": white_time, "black_time": black_time, "last_move_ts": now_ts}})
        kb = make_board_keyboard(gid, board, None, legal_moves_map(board), show_suggestions=bool(game.get("suggestions", True)))
        try:
            await cq.message.edit_text(f"♟️ Promotion: {san}\n{render_board_text(board, white_time, black_time, TIME_CONTROLS[game['time_control']]['name'])}", reply_markup=kb)
        except:
            pass
        if board.is_checkmate():
            winner_id = cq.from_user.id
            loser_id = game.get("white_id") if winner_id == game.get("black_id") else game.get("black_id")
            wdoc = await ensure_user_doc(winner_id); ldoc = await ensure_user_doc(loser_id)
            w_new = elo_update(wdoc.get("elo",1200), ldoc.get("elo",1200), 1.0)
            l_new = elo_update(ldoc.get("elo",1200), wdoc.get("elo",1200), 0.0)
            await users_col.update_one({"user_id": winner_id}, {"$set": {"elo": w_new}, "$inc": {"wins":1,"games":1}}, upsert=True)
            await users_col.update_one({"user_id": loser_id}, {"$set": {"elo": l_new}, "$inc": {"losses":1,"games":1}}, upsert=True)
            await app.send_message(game["chat_id"], f"🏁 Checkmate! Winner: [user](tg://user?id={winner_id})")
            await games_col.delete_one({"_id": ObjectId(gid)}); await stop_clock_task(gid)
        else:
            await start_clock_task(gid)
        return await cq.answer("Promotion played.")

    # resign: _resign|<gid>
    if action == "resign":
        if len(parts) < 2: return await cq.answer("Missing gid", show_alert=True)
        gid = parts[1]
        try:
            game = await games_col.find_one({"_id": ObjectId(gid)})
        except:
            return await cq.answer("Invalid gid", show_alert=True)
        if not game: return await cq.answer("Game not found", show_alert=True)
        uid = cq.from_user.id
        if uid not in (game.get("white_id"), game.get("black_id")):
            return await cq.answer("Only a player may resign", show_alert=True)
        winner = game.get("black_id") if uid == game.get("white_id") else game.get("white_id")
        # elo update and stats
        wdoc = await ensure_user_doc(winner); ldoc = await ensure_user_doc(uid)
        w_new = elo_update(wdoc.get("elo",1200), ldoc.get("elo",1200), 1.0)
        l_new = elo_update(ldoc.get("elo",1200), wdoc.get("elo",1200), 0.0)
        await users_col.update_one({"user_id": winner}, {"$set": {"elo": w_new}, "$inc": {"wins":1,"games":1}}, upsert=True)
        await users_col.update_one({"user_id": uid}, {"$set": {"elo": l_new}, "$inc": {"losses":1,"games":1}}, upsert=True)
        await app.send_message(game["chat_id"], f"🏳️ {cq.from_user.first_name} resigned. Winner: [user](tg://user?id={winner})")
        await games_col.delete_one({"_id": ObjectId(gid)}); await stop_clock_task(gid)
        try: await cq.message.edit_text("Game ended by resignation.")
        except: pass
        return await cq.answer("You resigned.")

    # leaderboard: _leaderboard|0
    if action == "leaderboard":
        cursor = users_col.find().sort("elo", -1).limit(15)
        text = "🏆 Leaderboard (by ELO)\n"
        i = 1
        async for u in cursor:
            text += f"{i}. {u.get('username','user')} — {u.get('elo',1200)} (G:{u.get('games',0)})\n"
            i += 1
        try: await cq.message.edit_text(text)
        except: pass
        return await cq.answer()

    # profile: _profile|<user_id>
    if action == "profile":
        if len(parts) < 2: return await cq.answer("Missing user id", show_alert=True)
        try:
            uid = int(parts[1])
        except:
            return await cq.answer("Invalid user id", show_alert=True)
        u = await users_col.find_one({"user_id": uid})
        if not u: return await cq.answer("Profile not found", show_alert=True)
        text = f"👤 {u.get('username')}\nELO: {u.get('elo',1200)}\nG:{u.get('games',0)} W:{u.get('wins',0)} L:{u.get('losses',0)} D:{u.get('draws',0)}"
        return await cq.answer(text, show_alert=True)

    return await cq.answer("Unknown action", show_alert=True)

# ----------------- resume clocks on startup -----------------
async def resume_active_games():
    async for g in games_col.find({"started": True}):
        gid = str(g["_id"])
        await start_clock_task(gid)
    log.info("Resumed active game clocks.")
