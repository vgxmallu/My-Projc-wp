

import os
import asyncio
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pymongo import MongoClient
from pymongo.collection import Collection

import uuid
from config import DB_URL
from wallbot import wbot as app

DB_NAME = os.environ.get("DB_NAME", "gomoku2_bot")


# --- DB setup
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users_col: Collection = db.users
games_col: Collection = db.games

# --- Constants
EMPTY = 0
BLACK = 1
WHITE = 2
WIN_COUNT = 5

@dataclass
class PlayerRef:
    user_id: int
    username: Optional[str] = None

@dataclass
class GameState:
    game_id: str
    board: List[List[int]]
    size: int
    turn: int
    player_black: Optional[PlayerRef] = None
    player_white: Optional[PlayerRef] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_move_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    winner: Optional[int] = None
    move_count: int = 0

    def to_dict(self):
        return {
            'game_id': self.game_id,
            'board': self.board,
            'size': self.size,
            'turn': self.turn,
            'player_black': self.player_black.__dict__ if self.player_black else None,
            'player_white': self.player_white.__dict__ if self.player_white else None,
            'created_at': self.created_at,
            'last_move_at': self.last_move_at,
            'is_active': self.is_active,
            'winner': self.winner,
            'move_count': self.move_count,
        }

# --- Utility functions

def new_game_doc(creator: PlayerRef, vs_bot: bool = False, size: int = 15) -> GameState:
    board = [[EMPTY for _ in range(size)] for __ in range(size)]
    game_id = str(uuid.uuid4())[:8]
    black = creator
    white = PlayerRef(user_id=0, username='BOT') if vs_bot else None
    gs = GameState(game_id=game_id, board=board, size=size, turn=BLACK, player_black=black, player_white=white)
    return gs

def save_game(gs: GameState):
    games_col.replace_one({'game_id': gs.game_id}, gs.to_dict(), upsert=True)

def load_game(game_id: str) -> Optional[GameState]:
    doc = games_col.find_one({'game_id': game_id})
    if not doc:
        return None
    return GameState(
        game_id=doc['game_id'],
        board=doc['board'],
        size=doc['size'],
        turn=doc['turn'],
        player_black=PlayerRef(**doc['player_black']) if doc.get('player_black') else None,
        player_white=PlayerRef(**doc['player_white']) if doc.get('player_white') else None,
        created_at=doc.get('created_at', datetime.utcnow()),
        last_move_at=doc.get('last_move_at', datetime.utcnow()),
        is_active=doc.get('is_active', True),
        winner=doc.get('winner'),
        move_count=doc.get('move_count', 0),
    )

def user_upsert(user_id: int, username: Optional[str]):
    users_col.update_one({'user_id': user_id}, {'$set': {'username': username, 'last_seen': datetime.utcnow()}}, upsert=True)

def record_result(winner_user_id: Optional[int], loser_user_id: Optional[int], draw: bool=False):
    if draw:
        if winner_user_id:
            users_col.update_one({'user_id': winner_user_id}, {'$inc': {'draws': 1}}, upsert=True)
        return
    if winner_user_id:
        users_col.update_one({'user_id': winner_user_id}, {'$inc': {'wins': 1}}, upsert=True)
    if loser_user_id:
        users_col.update_one({'user_id': loser_user_id}, {'$inc': {'losses': 1}}, upsert=True)

# --- Game logic

def in_bounds(x:int,y:int,size:int):
    return 0<=x<size and 0<=y<size

def check_five(board: List[List[int]], size:int, x:int, y:int, player:int) -> bool:
    directions = [(1,0),(0,1),(1,1),(1,-1)]
    for dx,dy in directions:
        count = 1
        nx,ny = x+dx,y+dy
        while in_bounds(nx,ny,size) and board[ny][nx]==player:
            count+=1; nx+=dx; ny+=dy
        nx,ny = x-dx,y-dy
        while in_bounds(nx,ny,size) and board[ny][nx]==player:
            count+=1; nx-=dx; ny-=dy
        if count>=WIN_COUNT: return True
    return False

def game_winner_after_move(gs: GameState, x:int, y:int, player:int) -> bool:
    return check_five(gs.board, gs.size, x, y, player)

def ai_find_move(gs: GameState) -> Tuple[int,int]:
    size = gs.size
    board = gs.board
    for y in range(size):
        for x in range(size):
            if board[y][x]!=EMPTY: continue
            board[y][x]=WHITE
            if check_five(board,size,x,y,WHITE): board[y][x]=EMPTY; return x,y
            board[y][x]=EMPTY
    for y in range(size):
        for x in range(size):
            if board[y][x]!=EMPTY: continue
            board[y][x]=BLACK
            if check_five(board,size,x,y,BLACK): board[y][x]=EMPTY; return x,y
            board[y][x]=EMPTY
    best_score=-1; best_move=None
    for y in range(size):
        for x in range(size):
            if board[y][x]!=EMPTY: continue
            score=0; cx,cy=size//2,size//2
            score-=(abs(x-cx)+abs(y-cy))
            for dx in [-1,0,1]:
                for dy in [-1,0,1]:
                    nx,ny=x+dx,y+dy
                    if in_bounds(nx,ny,size):
                        if board[ny][nx]==WHITE: score+=3
                        elif board[ny][nx]==BLACK: score+=1
            if score>best_score: best_score=score; best_move=(x,y)
    return best_move or (0,0)

# --- Rendering

def render_board_as_text(board: List[List[int]]) -> str:
    size=len(board)
    rows=["   "+" ".join([f"{i:2d}" for i in range(size)])]
    for y in range(size):
        row=f"{y:2d} ";
        for x in range(size):
            v=board[y][x]
            row+= ' .' if v==EMPTY else (' X' if v==BLACK else ' O')
        rows.append(row)
    return "\n".join(rows)

def board_to_inline_keyboard(gs: GameState) -> InlineKeyboardMarkup:
    kb=[]
    for y in range(gs.size):
        row=[]
        for x in range(gs.size):
            val=gs.board[y][x]
            text='▫️' if val==EMPTY else ('⚫' if val==BLACK else '⚪')
            row.append(InlineKeyboardButton(text, callback_data=f"move|{gs.game_id}|{x}|{y}"))
        kb.append(row)
    kb.append([
        InlineKeyboardButton('Resign', callback_data=f"resign|{gs.game_id}"),
        InlineKeyboardButton('Show Text', callback_data=f"showtext|{gs.game_id}")
    ])
    return InlineKeyboardMarkup(kb)



# --- Helpers
async def ensure_user_in_db(user_id:int, username:Optional[str]):
    user_upsert(user_id, username)

async def send_game_message(chat_id:int, gs: GameState):
    text=f"Gomoku — Game {gs.game_id}\nSize: {gs.size}x{gs.size}\nTurn: {'Black (X)' if gs.turn==BLACK else 'White (O)'}\n"
    if gs.player_black: text+=f"Black: @{gs.player_black.username}\n"
    if gs.player_white: text+=f"White: @{gs.player_white.username}\n"
    text+='\nUse the buttons to play.\n'
    await app.send_message(chat_id, text, reply_markup=board_to_inline_keyboard(gs))

# --- Commands
@app.on_message(filters.command("gom"))
async def startrcmd(client, message: Message):
    await ensure_user_in_db(message.from_user.id, message.from_user.username)
    text=("Welcome to Gomoku Bot!\n\n"
          "/new - Create a new game\n"
          "/profile - Show profile\n"
          "/leaderboard - Top players\n")
    keyboard=InlineKeyboardMarkup([
        [InlineKeyboardButton('New PvP', callback_data="create|pvp"), InlineKeyboardButton('New vs Bot', callback_data="create|bot")],
        [InlineKeyboardButton('Profile', callback_data=f"profile|{message.from_user.id}"), InlineKeyboardButton('Leaderboard', callback_data="leaderboard")]
    ])
    await message.reply_text(text, reply_markup=keyboard)

@app.on_message(filters.command(['profilegom']))
async def profihfhfle_cmd(client, message: Message):
    doc=users_col.find_one({'user_id': message.from_user.id}) or {}
    wins,losses,draws=doc.get('wins',0),doc.get('losses',0),doc.get('draws',0)
    await message.reply_text(f"Profile @{message.from_user.username}\nWins:{wins}\nLosses:{losses}\nDraws:{draws}")

@app.on_message(filters.command(['gomleaderboard']))
async def leaderbobdfard_cmd(client, message: Message):
    top=users_col.find().sort('wins',-1).limit(10)
    rows=[f"{i+1}. @{u.get('username','unknown')} — {u.get('wins',0)} wins" for i,u in enumerate(top)]
    await message.reply_text("Leaderboard:\n"+"\n".join(rows) if rows else "No players yet.")

# --- Regex-based callbacks
@app.on_callback_query(filters.regex(r"^create\|(pvp|bot)$"))
async def create_game_cb(client, cq: CallbackQuery):
    mode=cq.data.split('|')[1]
    creator=PlayerRef(user_id=cq.from_user.id, username=cq.from_user.username)
    gs=new_game_doc(creator, vs_bot=(mode=="bot"), size=15)
    save_game(gs)
    await send_game_message(cq.message.chat.id, gs)
    await cq.answer("Game created")

@app.on_callback_query(filters.regex(r"^move\|"))
async def move_cb(client, cq: CallbackQuery):
    _,gid,x,y=cq.data.split('|')
    x,y=int(x),int(y)
    gs=load_game(gid)
    if not gs or not gs.is_active: await cq.answer('Invalid game', show_alert=True); return
    uid=cq.from_user.id
    if gs.player_black and gs.player_black.user_id==uid: color=BLACK
    elif gs.player_white and gs.player_white.user_id==uid: color=WHITE
    elif not gs.player_white or gs.player_white.user_id==0:
        gs.player_white=PlayerRef(user_id=uid, username=cq.from_user.username)
        color=WHITE
    else:
        await cq.answer('Not your game', show_alert=True); return
    if gs.turn!=color: await cq.answer('Not your turn', show_alert=True); return
    if gs.board[y][x]!=EMPTY: await cq.answer('Cell not empty', show_alert=True); return
    gs.board[y][x]=color; gs.move_count+=1; gs.last_move_at=datetime.utcnow()
    if game_winner_after_move(gs,x,y,color):
        gs.is_active=False; gs.winner=color; save_game(gs)
        winner_id=gs.player_black.user_id if color==BLACK else gs.player_white.user_id
        loser_id=gs.player_white.user_id if color==BLACK else gs.player_black.user_id
        record_result(winner_id if winner_id!=0 else None, loser_id if loser_id!=0 else None)
        await cq.message.reply_text(f"Game {gid} finished. Winner: {'Black' if color==BLACK else 'White'}")
        await cq.answer('You win!'); return
    if all(all(c!=EMPTY for c in row) for row in gs.board):
        gs.is_active=False; gs.winner=None; save_game(gs); record_result(None,None,draw=True)
        await cq.message.reply_text(f"Game {gid} is a draw"); await cq.answer('Draw'); return
    gs.turn=WHITE if gs.turn==BLACK else BLACK; save_game(gs)
    await send_game_message(cq.message.chat.id, gs)
    await cq.answer('Move accepted')

@app.on_callback_query(filters.regex(r"^resign\|"))
async def resign_cb(client, cq: CallbackQuery):
    _,gid=cq.data.split('|')
    gs=load_game(gid)
    if not gs: await cq.answer('Game not found', show_alert=True); return
    uid=cq.from_user.id
    if not (gs.player_black and gs.player_black.user_id==uid) and not (gs.player_white and gs.player_white.user_id==uid):
        await cq.answer('Not a player', show_alert=True); return
    gs.is_active=False
    winner=gs.player_white.user_id if gs.player_black and gs.player_black.user_id==uid else gs.player_black.user_id
    loser=uid
    save_game(gs)
    record_result(winner if winner!=0 else None, loser if loser!=0 else None)
    await cq.message.reply_text(f"@{cq.from_user.username} resigned. Game {gid} finished.")
    await cq.answer('Resigned')

@app.on_callback_query(filters.regex(r"^showtext\|"))
async def showtext_cb(client, cq: CallbackQuery):
    _,gid=cq.data.split('|')
    gs=load_game(gid)
    if not gs: await cq.answer('Game not found', show_alert=True); return
    txt=render_board_as_text(gs.board)
    await cq.message.reply_text(f"Game {gid} — Text view:\n```\n{txt}\n```")
    await cq.answer()

@app.on_callback_query(filters.regex(r"^profile\|"))
async def profile_cb(client, cq: CallbackQuery):
    _,uid=cq.data.split('|')
    uid=int(uid)
    doc=users_col.find_one({'user_id': uid}) or {}
    wins,losses,draws=doc.get('wins',0),doc.get('losses',0),doc.get('draws',0)
    await cq.message.reply_text(f"Profile @{cq.from_user.username}\nWins:{wins}\nLosses:{losses}\nDraws:{draws}")
    await cq.answer()

@app.on_callback_query(filters.regex(r"^leaderboard$"))
async def leaderboard_cb(client, cq: CallbackQuery):
    top=users_col.find().sort('wins',-1).limit(10)
    rows=[f"{i+1}. @{u.get('username','unknown')} — {u.get('wins',0)} wins" for i,u in enumerate(top)]
    await cq.message.reply_text("Leaderboard:\n"+"\n".join(rows) if rows else "No results")
