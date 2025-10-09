#!/usr/bin/env python3
"""
Chess Inline Bot (Pyrogram + MongoDB + python-chess)

Controls: Only InlineKeyboardMarkup buttons for all in-game actions:
- /chess_create  -> create lobby with Join button
- Join button -> add player to lobby; first two players auto-start game
- Board displayed as 8x8 inline keyboard; tap source square then destination square
- Promotion handled via inline promotion buttons
- Resign/Offer Draw buttons as inline
- /profile and /leaderboard commands (text replies)
- All games persisted in MongoDB

Author: ChatGPT (generated)
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorClient
import chess
from config import DB_URL
from wallbot import wbot as app

load_dotenv()
logging.basicConfig(level=logging.INFO)

DB_NAME = os.getenv("DB_NAME", "chess_bot_db")
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]

# Collections
users_col = db["users"]
lobbies_col = db["lobbies"]
games_col = db["games"]

# Settings
LOBBY_TIMEOUT = 300  # seconds
XP_WIN = 200
XP_DRAW = 100
XP_LOSE = 50

RANKS = [(0, "Novice"), (500, "Apprentice"), (1500, "Warrior"), (3500, "Champion"), (8000, "Legend")]

# Unicode pieces mapping for white and black
UNICODE_PIECES = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

# helpers
def rank_from_xp(xp: int) -> str:
    r = "Novice"
    for threshold, name in RANKS:
        if xp >= threshold:
            r = name
    return r

async def ensure_user(user_id: int, name: str) -> Dict[str, Any]:
    u = await users_col.find_one({"user_id": user_id})
    if not u:
        u = {"user_id": user_id, "name": name, "xp": 0, "wins": 0, "losses": 0, "draws": 0, "created_at": datetime.utcnow()}
        await users_col.insert_one(u)
    return u

async def add_result(user_id: int, xp: int=0, win: int=0, loss: int=0, draw:int=0):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"xp": xp, "wins": win, "losses": loss, "draws": draw}}, upsert=True)

# board helpers
def square_index_to_alg(idx: int) -> str:
    # idx 0..63 where 0 = a8, 63 = h1 if we display top-to-bottom
    row = 8 - (idx // 8)
    col = idx % 8
    file_letter = "abcdefgh"[col]
    return f"{file_letter}{row}"

def make_board_buttons(fen: str, selectable_from: Optional[str]=None, highlight_squares: Optional[List[str]]=None, player_allowed: Optional[int]=None, game_id: Optional[str]=None, actor_id: Optional[int]=None):
    """
    Build 8x8 inline keyboard representing board.
    We will produce 8 rows of 8 buttons each.
    callback_data format:
     chess_sq|<game_id>|<alg>|<actor_id>
    For promotion, there will be a special callback path.
    The board string fen is used to render pieces; squares without piece show '·' or blank.
    selectable_from: algebraic string of selected source square to mark.
    highlight_squares: list of algebraic squares to highlight (legal moves).
    """
    board = chess.Board(fen)
    # we'll build rows from rank 8 downto 1, files a..h
    kb = []
    for rank in range(8, 0, -1):
        row = []
        for file_i, file_c in enumerate("abcdefgh"):
            sq = f"{file_c}{rank}"
            piece = board.piece_at(chess.parse_square(sq))
            label = UNICODE_PIECES.get(piece.symbol(), "·") if piece else "·"
            # visual markers
            if selectable_from == sq:
                label = f"🔵{label}"
            elif highlight_squares and sq in highlight_squares:
                label = f"🟢{label}"
            # callback data
            if game_id:
                cb = f"chess_sq|{game_id}|{sq}|{actor_id}"
            else:
                cb = "noop"
            row.append(InlineKeyboardButton(label, callback_data=cb))
        kb.append(row)
    # bottom action row: resign / offer draw / refresh
    action_row = [
        InlineKeyboardButton("🚪 Resign", callback_data=f"chess_resign|{game_id}|{actor_id}"),
        InlineKeyboardButton("🤝 Offer Draw", callback_data=f"chess_offer_draw|{game_id}|{actor_id}"),
        InlineKeyboardButton("🔄 Refresh", callback_data=f"chess_refresh|{game_id}|{actor_id}")
    ]
    kb.append(action_row)
    return InlineKeyboardMarkup(kb)

# Lobby keyboard
def lobby_keyboard(chat_id:int, message_id:int):
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Join", callback_data=f"chess_join|{chat_id}|{message_id}")],
                                 [InlineKeyboardButton("❌ Cancel", callback_data=f"chess_cancel_lobby|{chat_id}|{message_id}")]])

# Promotion keyboard
def promotion_keyboard(game_id:str, from_sq:str, to_sq:str, actor_id:int):
    # options: q,r,b,n
    options = [("q","Queen"),("r","Rook"),("b","Bishop"),("n","Knight")]
    kb = [[InlineKeyboardButton(f"Promote to {name}", callback_data=f"chess_promote|{game_id}|{from_sq}|{to_sq}|{letter}|{actor_id}")] for letter,name in options]
    return InlineKeyboardMarkup(kb)

# DB helpers for lobby/game
async def create_lobby_doc(chat_id:int, message_id:int):
    doc = {"chat_id": chat_id, "message_id": message_id, "players": [], "created_at": datetime.utcnow(), "expires_at": datetime.utcnow()+timedelta(seconds=LOBBY_TIMEOUT)}
    await lobbies_col.insert_one(doc)
    return doc

async def add_player_to_lobby(chat_id:int, message_id:int, user_id:int, name:str):
    doc = await lobbies_col.find_one({"chat_id": chat_id, "message_id": message_id})
    if not doc: return None
    if any(p["user_id"]==user_id for p in doc["players"]): return doc
    doc["players"].append({"user_id":user_id, "name":name})
    await lobbies_col.update_one({"chat_id":chat_id, "message_id":message_id}, {"$set":{"players":doc["players"]}})
    return doc

async def remove_lobby(chat_id:int, message_id:int):
    await lobbies_col.delete_one({"chat_id":chat_id, "message_id":message_id})

async def start_game_from_lobby(chat_id:int, message_id:int):
    lobby = await lobbies_col.find_one({"chat_id":chat_id, "message_id":message_id})
    if not lobby: return None
    players = lobby["players"]
    if len(players)<2: return None
    # pick first two
    p1 = players[0]
    p2 = players[1]
    import random
    if random.choice([True, False]):
        white = p1; black = p2
    else:
        white = p2; black = p1
    game = {
        "chat_id": chat_id,
        "white_id": white["user_id"],
        "white_name": white["name"],
        "black_id": black["user_id"],
        "black_name": black["name"],
        "fen": chess.Board().fen(),
        "turn": "white",
        "selected": None,   # algebraic source if a player selected a piece
        "selected_by": None,
        "moves": [],
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "finished": False,
        "result": None
    }
    res = await games_col.insert_one(game)
    game["_id"] = res.inserted_id
    # remove lobby
    await remove_lobby(chat_id, message_id)
    return game

async def get_active_game(chat_id:int):
    return await games_col.find_one({"chat_id":chat_id, "finished":False})

async def update_game(game_id, patch:Dict[str,Any]):
    await games_col.update_one({"_id":game_id}, {"$set":patch})

async def finish_game_and_award(game, result:str, winner_id:Optional[int]=None):
    # set finished and result and award xp
    await games_col.update_one({"_id":game["_id"]}, {"$set":{"finished":True, "result":result, "last_activity":datetime.utcnow()}})
    # ensure profiles
    await ensure_user(game["white_id"], game["white_name"])
    await ensure_user(game["black_id"], game["black_name"])
    if result == "1-0":
        # white won
        await add_result(game["white_id"], xp=XP_WIN, win=1)
        await add_result(game["black_id"], xp=XP_LOSE, loss=1)
    elif result == "0-1":
        await add_result(game["black_id"], xp=XP_WIN, win=1)
        await add_result(game["white_id"], xp=XP_LOSE, loss=1)
    else:
        await add_result(game["white_id"], xp=XP_DRAW, draw=1)
        await add_result(game["black_id"], xp=XP_DRAW, draw=1)

# ---------- Commands ----------
@app.on_message(filters.command("chessstart"))
async def cmd_xhestart(client, message:Message):
    await message.reply_text("♟️ Chess Inline Bot — use /chess_create in group to create a lobby. All controls are inline buttons.")

@app.on_message(filters.command("chess_create") & filters.group)
async def cmd_chess_create(client, message:Message):
    chat_id = message.chat.id
    m_id = message.id
    # check active game
    active = await get_active_game(chat_id)
    if active:
        return await message.reply_text("A game is already active in this chat. Use /board to view it.")
    sent = await message.reply_text("♟️ Chess lobby created! Click Join to enter the queue (first two players will start).", reply_markup=lobby_keyboard(chat_id, m_id))
    await create_lobby_doc(chat_id, m_id)

@app.on_message(filters.command("chessprofile") & (filters.group | filters.private))
async def cmdches_profile(client, message:Message):
    uid = message.from_user.id
    u = await ensure_user(uid, message.from_user.first_name or message.from_user.username or str(uid))
    xp = u.get("xp",0); wins = u.get("wins",0); losses = u.get("losses",0); draws = u.get("draws",0)
    rank = rank_from_xp(xp)
    await message.reply_text(f"👤 {u.get('name')}\nRank: {rank}\nXP: {xp}\nWins: {wins} | Losses: {losses} | Draws: {draws}")

@app.on_message(filters.command("chessleaderboard") & (filters.group | filters.private))
async def cmd_lechessaderboard(client, message:Message):
    top = await users_col.find().sort("xp",-1).limit(10).to_list(length=10)
    text = "🏆 Leaderboard (by XP)\n\n"
    i = 1
    for u in top:
        text += f"{i}. {u.get('name','User')} — XP {u.get('xp',0)}\n"; i+=1
    await message.reply_text(text)

# ---------- Callback handlers ----------
@app.on_callback_query(filters.regex(r"^chess_join\|"))
async def cb_join(client, cq:CallbackQuery):
    try:
        _, chat_id_s, msg_id_s = cq.data.split("|")
        chat_id=int(chat_id_s); msg_id=int(msg_id_s)
    except:
        return await cq.answer("Invalid data", show_alert=True)
    user = cq.from_user
    await ensure_user(user.id, user.first_name or user.username or str(user.id))
    lobby = await add_player_to_lobby(chat_id, msg_id, user.id, user.first_name or user.username or str(user.id))
    if not lobby:
        return await cq.answer("Lobby no longer exists.", show_alert=True)
    await cq.answer("You joined the lobby ✅")
    # edit lobby message if possible
    players_text = "\n".join([f"- {p['name']}" for p in lobby["players"]])
    try:
        await client.edit_message_text(chat_id, msg_id, f"♟️ Chess Lobby\nPlayers:\n{players_text}", reply_markup=lobby_keyboard(chat_id,msg_id))
    except:
        pass
    # if at least 2 players start game
    if len(lobby["players"])>=2:
        game = await start_game_from_lobby(chat_id, msg_id)
        if not game:
            return
        # build board and message
        fen = game["fen"]
        desc = f"♟️ Game started!\nWhite: [{game['white_name']}](tg://user?id={game['white_id']})\nBlack: [{game['black_name']}](tg://user?id={game['black_id']})\nTurn: White"
        kb = make_board_buttons(fen, selectable_from=None, highlight_squares=None, player_allowed=None, game_id=str(game["_id"]), actor_id=0)
        await client.send_message(chat_id, desc + "\n\nTap your piece, then destination.", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^chess_cancel_lobby\|"))
async def cb_cancel_lobby(client, cq:CallbackQuery):
    try:
        _, chat_id_s, msg_id_s = cq.data.split("|")
        chat_id=int(chat_id_s); msg_id=int(msg_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    # only admin can cancel lobby
    member = await client.get_chat_member(chat_id, cq.from_user.id)
    if member.status not in ("administrator","creator"):
        return await cq.answer("Only admins can cancel lobby.", show_alert=True)
    await remove_lobby(chat_id, msg_id)
    await cq.answer("Lobby cancelled ✅")
    try:
        await client.edit_message_text(chat_id, msg_id, "♟️ Lobby cancelled by admin.")
    except:
        pass

@app.on_callback_query(filters.regex(r"^chess_sq\|"))
async def cb_square(client, cq:CallbackQuery):
    """
    Callback data: chess_sq|<game_id>|<sq>|<actor_id>
    actor_id in callback is the user id allowed when keyboard built; we will still enforce actual cq.from_user id.
    Flow:
      - If no selection in game: user selects a source square
      - If selection exists by same user: treat as destination and attempt move
      - If selection exists by other user: override (not allowed)
    """
    parts = cq.data.split("|")
    if len(parts) < 4:
        return await cq.answer("Invalid", show_alert=True)
    _, game_id, sq, actor_id_s = parts
    actor_id = int(actor_id_s) if actor_id_s.isdigit() else 0
    user = cq.from_user
    game = await games_col.find_one({"_id": chess.polyglot.zobrist_hash.__self__})  # placeholder to satisfy type; will replace below

    # find game by id
    try:
        from bson import ObjectId
        gid = ObjectId(game_id)
    except Exception:
        return await cq.answer("Invalid game", show_alert=True)
    game = await games_col.find_one({"_id": gid})
    if not game:
        return await cq.answer("Game not found or finished.", show_alert=True)

    if game.get("finished"):
        return await cq.answer("Game finished.", show_alert=True)

    # only players can press (we allow both players)
    if user.id not in (game["white_id"], game["black_id"]):
        return await cq.answer("Only players can control this game.", show_alert=True)

    board = chess.Board(game["fen"])

    # if no selected source -> treat this as selecting source
    sel = game.get("selected")
    sel_by = game.get("selected_by")
    # if no selection -> user tries to choose source
    if not sel:
        # check that the square has a piece and it belongs to this user (color)
        piece = board.piece_at(chess.parse_square(sq))
        if not piece:
            return await cq.answer("No piece on that square.", show_alert=True)
        is_white_piece = piece.color == chess.WHITE
        user_is_white = (user.id == game["white_id"])
        if is_white_piece != user_is_white:
            return await cq.answer("You cannot select opponent's piece.", show_alert=True)
        # also must be player's turn
        if (board.turn == chess.WHITE and user.id != game["white_id"]) or (board.turn == chess.BLACK and user.id != game["black_id"]):
            return await cq.answer("It's not your turn.", show_alert=True)
        # compute legal moves from this square for highlighting
        legal = [move for move in board.legal_moves if chess.square_name(move.from_square) == sq]
        highlight = [chess.square_name(m.to_square) for m in legal]
        # store selection in DB
        await games_col.update_one({"_id": gid}, {"$set":{"selected":sq, "selected_by":user.id}})
        kb = make_board_buttons(game["fen"], selectable_from=sq, highlight_squares=highlight, game_id=game_id, actor_id=user.id)
        await cq.answer("Selected. Tap destination square.", show_alert=False)
        try:
            await cq.message.edit_reply_markup(kb)
        except:
            pass
        return

    # if selection exists -> check if selection by same user
    if sel_by != user.id:
        # another player had selected; disallow
        await cq.answer("Selection belongs to the other player. Wait or clear selection.", show_alert=True)
        return

    # Attempt to move from sel -> sq
    from_sq = sel
    to_sq = sq
    uci = f"{from_sq}{to_sq}"
    move_obj = None
    try:
        move_obj = chess.Move.from_uci(uci)
    except Exception:
        move_obj = None

    # handle promotions: if pawn move to last rank and no promotion letter provided yet, ask promotion
    # determine if move is a legal promotion candidate
    promotion_required = False
    try:
        if move_obj is None:
            # maybe UCI with promotion (like e7e8q) - but user didn't provide promotion letter
            # check if there is any legal move from from_sq to to_sq with promotion options
            for m in board.legal_moves:
                if chess.square_name(m.from_square) == from_sq and chess.square_name(m.to_square) == to_sq:
                    if m.promotion:
                        promotion_required = True
                        break
        else:
            if move_obj not in board.legal_moves:
                # maybe promotion required
                for m in board.legal_moves:
                    if chess.square_name(m.from_square)==from_sq and chess.square_name(m.to_square)==to_sq and m.promotion:
                        promotion_required = True
                        break
                    # else illegal
    except Exception:
        promotion_required = False

    if promotion_required:
        # ask user to pick promotion piece via inline buttons
        kb = promotion_keyboard(game_id, from_sq, to_sq, user.id)
        await cq.answer("Choose promotion piece", show_alert=False)
        try:
            await cq.message.reply_text("Choose promotion piece:", reply_markup=kb)
        except:
            pass
        # clear selection in DB (we will handle move when promotion callback arrives)
        await games_col.update_one({"_id":gid}, {"$set":{"selected":None,"selected_by":None}})
        return

    # If no promotion required, validate move
    if move_obj is None or move_obj not in board.legal_moves:
        await cq.answer("Illegal move.", show_alert=True)
        # clear selection
        await games_col.update_one({"_id":gid}, {"$set":{"selected":None,"selected_by":None}})
        # refresh keyboard
        kb = make_board_buttons(game["fen"], selectable_from=None, game_id=game_id, actor_id=0)
        try:
            await cq.message.edit_reply_markup(kb)
        except:
            pass
        return

    # Make move
    board.push(move_obj)
    san = board.peek().uci() if hasattr(board, "peek") else move_obj.uci()
    # update DB: fen, moves, clear selected
    await games_col.update_one({"_id":gid}, {"$set":{"fen":board.fen(), "last_activity":datetime.utcnow(), "selected":None, "selected_by":None}})
    await games_col.update_one({"_id":gid}, {"$push":{"moves": move_obj.uci()}})
    # check game end
    if board.is_checkmate():
        # the side who just moved delivered mate; determine winner
        # after push, board.turn is flipped; so the player who moved is opposite of board.turn
        mover_color = not board.turn  # True if white moved
        if mover_color == chess.WHITE:
            result = "1-0"; winner = game["white_id"]
        else:
            result = "0-1"; winner = game["black_id"]
        await finish_game_and_award(game, result, winner)
        # send final board message
        final = f"♟️ Checkmate!\nResult: {result}\n\n{board_to_text(board)}"
        try:
            await cq.message.reply_text(final)
        except:
            pass
        await cq.answer("Checkmate!", show_alert=True)
        return

    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_fifty_moves() or board.can_claim_threefold_repetition():
        result = "1/2-1/2"
        await finish_game_and_award(game, result, None)
        final = f"♟️ Draw!\nResult: {result}\n\n{board_to_text(board)}"
        try:
            await cq.message.reply_text(final)
        except:
            pass
        await cq.answer("Draw", show_alert=True)
        return

    # otherwise continue - update board message keyboard with new fen, no selected
    kb = make_board_buttons(board.fen(), selectable_from=None, highlight_squares=None, game_id=game_id, actor_id=0)
    try:
        await cq.message.edit_reply_markup(kb)
    except:
        pass
    await cq.answer("Move played", show_alert=False)

# small helper to show unicode board in messages
def board_to_text(board: chess.Board) -> str:
    # python-chess provides board.unicode()
    return board.unicode(borders=True)

@app.on_callback_query(filters.regex(r"^chess_promote\|"))
async def cb_promote(client, cq:CallbackQuery):
    # data: chess_promote|<game_id>|<from>|<to>|<piece_letter>|<actor_id>
    try:
        _, game_id, from_sq, to_sq, p_letter, actor_id_s = cq.data.split("|")
        actor_id = int(actor_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    try:
        from bson import ObjectId
        gid = ObjectId(game_id)
    except:
        return await cq.answer("Invalid game", show_alert=True)
    game = await games_col.find_one({"_id":gid})
    if not game:
        return await cq.answer("Game not found", show_alert=True)
    if cq.from_user.id != actor_id:
        return await cq.answer("Only the player who selected can pick promotion.", show_alert=True)
    board = chess.Board(game["fen"])
    # build move with promotion
    uci = f"{from_sq}{to_sq}{p_letter}"
    try:
        mv = chess.Move.from_uci(uci)
    except:
        return await cq.answer("Invalid promotion", show_alert=True)
    if mv not in board.legal_moves:
        return await cq.answer("Illegal promotion", show_alert=True)
    board.push(mv)
    await games_col.update_one({"_id":gid}, {"$set":{"fen":board.fen(), "last_activity":datetime.utcnow(), "selected":None, "selected_by":None}})
    await games_col.update_one({"_id":gid}, {"$push":{"moves": mv.uci()}})
    # check end conditions similar to above
    if board.is_checkmate():
        mover_color = not board.turn
        if mover_color == chess.WHITE:
            result="1-0"; winner=game["white_id"]
        else:
            result="0-1"; winner=game["black_id"]
        await finish_game_and_award(game, result, winner)
        await cq.message.reply_text(f"♟️ Checkmate! Result: {result}\n\n{board_to_text(board)}")
        return await cq.answer("Promotion and mate!", show_alert=True)
    # else update board keyboard
    kb = make_board_buttons(board.fen(), game_id=game_id, actor_id=0)
    try:
        await cq.message.edit_reply_markup(kb)
    except:
        pass
    await cq.answer("Promoted!", show_alert=False)

@app.on_callback_query(filters.regex(r"^chess_resign\|"))
async def cb_resign(client, cq:CallbackQuery):
    # data: chess_resign|<game_id>|<actor_id>
    try:
        _, game_id, actor_id_s = cq.data.split("|")
        actor_id=int(actor_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    from bson import ObjectId
    try:
        gid = ObjectId(game_id)
    except:
        return await cq.answer("Invalid", show_alert=True)
    game = await games_col.find_one({"_id":gid})
    if not game: return await cq.answer("Game not found", show_alert=True)
    # only player may resign
    if cq.from_user.id not in (game["white_id"], game["black_id"]):
        return await cq.answer("Only players can resign.", show_alert=True)
    # determine winner
    if cq.from_user.id == game["white_id"]:
        result="0-1"; winner=game["black_id"]
    else:
        result="1-0"; winner=game["white_id"]
    await finish_game_and_award(game, result, winner)
    await cq.answer("You resigned.", show_alert=True)
    try:
        await cq.message.reply_text(f"♟️ {cq.from_user.mention} resigned. Result: {result}")
    except:
        pass

@app.on_callback_query(filters.regex(r"^chess_offer_draw\|"))
async def cb_offer_draw(client, cq:CallbackQuery):
    # chess_offer_draw|<game_id>|<actor_id>
    try:
        _, game_id, actor_id_s = cq.data.split("|")
        actor_id=int(actor_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    from bson import ObjectId
    try:
        gid = ObjectId(game_id)
    except:
        return await cq.answer("Invalid", show_alert=True)
    game = await games_col.find_one({"_id":gid})
    if not game: return await cq.answer("Game not found", show_alert=True)
    if cq.from_user.id not in (game["white_id"], game["black_id"]):
        return await cq.answer("Only players can offer draw.", show_alert=True)
    # mark draw offer in DB and notify opponent via message with accept/decline inline
    opponent = game["black_id"] if cq.from_user.id==game["white_id"] else game["white_id"]
    await games_col.update_one({"_id":gid}, {"$set":{"draw_offer_by":cq.from_user.id}})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"chess_accept_draw|{game_id}|{opponent}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"chess_decline_draw|{game_id}|{opponent}")]
    ])
    await cq.message.reply_text(f"{cq.from_user.mention} offered a draw. {('Opponent', 'Player')} choose:", reply_markup=kb)
    await cq.answer("Draw offered", show_alert=True)

@app.on_callback_query(filters.regex(r"^chess_accept_draw\|"))
async def cb_accept_draw(client, cq:CallbackQuery):
    # chess_accept_draw|<game_id>|<actor_id>
    try:
        _, game_id, actor_id_s = cq.data.split("|")
        actor_id=int(actor_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    from bson import ObjectId
    gid = ObjectId(game_id)
    game = await games_col.find_one({"_id":gid})
    if not game: return await cq.answer("Game not found", show_alert=True)
    if cq.from_user.id != actor_id:
        return await cq.answer("Only the challenged opponent can accept.", show_alert=True)
    # finish as draw
    await finish_game_and_award(game, "1/2-1/2", None)
    await cq.answer("Draw accepted", show_alert=True)
    try:
        await cq.message.reply_text("♟️ Draw accepted. Game ended 1/2-1/2.")
    except:
        pass

@app.on_callback_query(filters.regex(r"^chess_decline_draw\|"))
async def cb_decline_draw(client, cq:CallbackQuery):
    try:
        _, game_id, actor_id_s = cq.data.split("|")
        actor_id=int(actor_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    from bson import ObjectId
    gid = ObjectId(game_id)
    game = await games_col.find_one({"_id":gid})
    if not game: return await cq.answer("Game not found", show_alert=True)
    if cq.from_user.id != actor_id:
        return await cq.answer("Only the opponent can decline.", show_alert=True)
    await games_col.update_one({"_id":gid}, {"$unset":{"draw_offer_by":""}})
    await cq.answer("Draw declined", show_alert=True)
    try:
        await cq.message.reply_text("♟️ Draw offer declined.")
    except:
        pass

@app.on_callback_query(filters.regex(r"^chess_refresh\|"))
async def cb_refresh(client, cq:CallbackQuery):
    # refresh keyboard to latest fen
    try:
        _, game_id, actor_id_s = cq.data.split("|")
        from bson import ObjectId
        gid = ObjectId(game_id)
    except:
        return await cq.answer("Invalid", show_alert=True)
    game = await games_col.find_one({"_id":gid})
    if not game:
        return await cq.answer("Game not found", show_alert=True)
    kb = make_board_buttons(game["fen"], game_id=game_id, actor_id=0)
    try:
        await cq.message.edit_reply_markup(kb)
    except:
        pass
    await cq.answer("Refreshed", show_alert=False)

