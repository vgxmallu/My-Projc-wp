import os
import re
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import chess
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message
)
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from config import DB_URL
from wallbot import wbot as app
# Initialize MongoDB
mongo_client = MongoClient(DB_URL)
db = mongo_client.telegram_chess_bot

# Collections
users_collection = db.users
games_collection = db.games
leaderboard_collection = db.leaderboard

# Game states and management
active_games: Dict[str, Dict] = {}
game_timers: Dict[str, asyncio.Task] = {}

# ELO configuration
INITIAL_ELO = 1000
K_FACTOR = 32

class ChessGame:
    def __init__(self, game_id: str, white_id: int, black_id: int, time_control: int = 600):
        self.game_id = game_id
        self.white_id = white_id
        self.black_id = black_id
        self.board = chess.Board()
        self.start_time = datetime.now()
        self.time_control = time_control  # in seconds
        self.white_time = time_control
        self.black_time = time_control
        self.last_update = time.time()
        self.move_count = 0
        
    def current_player_id(self) -> int:
        return self.white_id if self.board.turn == chess.WHITE else self.black_id
    
    def get_time_left(self, user_id: int) -> float:
        current_time = time.time()
        elapsed = current_time - self.last_update
        
        if self.board.turn == chess.WHITE:
            self.white_time -= elapsed
        else:
            self.black_time -= elapsed
            
        self.last_update = current_time
        
        if user_id == self.white_id:
            return self.white_time
        else:
            return self.black_time
    
    def format_time(self, seconds: float) -> str:
        if seconds <= 0:
            return "0:00"
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"
    
    def make_move(self, move: str) -> bool:
        try:
            chess_move = self.board.parse_san(move)
            if chess_move in self.board.legal_moves:
                self.board.push(chess_move)
                self.move_count += 1
                return True
        except:
            try:
                # Try UCI format
                chess_move = chess.Move.from_uci(move)
                if chess_move in self.board.legal_moves:
                    self.board.push(chess_move)
                    self.move_count += 1
                    return True
            except:
                pass
        return False
    
    def is_game_over(self) -> bool:
        return self.board.is_game_over()
    
    def get_result(self) -> str:
        if self.board.is_checkmate():
            return "checkmate"
        elif self.board.is_stalemate():
            return "stalemate"
        elif self.board.is_insufficient_material():
            return "insufficient material"
        elif self.board.is_seventyfive_moves():
            return "75-move rule"
        elif self.board.is_fivefold_repetition():
            return "fivefold repetition"
        elif self.board.can_claim_draw():
            return "draw claimed"
        return "unknown"
    
    def get_winner(self) -> Optional[int]:
        if self.board.is_checkmate():
            return self.black_id if self.board.turn == chess.WHITE else self.white_id
        return None

async def get_user(user_id: int) -> Dict:
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "elo": INITIAL_ELO,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "created_at": datetime.now()
        }
        await users_collection.insert_one(user)
    return user

async def update_elo(winner_id: int, loser_id: int, draw: bool = False):
    winner = await get_user(winner_id)
    loser = await get_user(loser_id)
    
    if draw:
        # Draw - both players get partial points based on rating difference
        expected_win = 1 / (1 + 10 ** ((loser["elo"] - winner["elo"]) / 400))
        winner_change = K_FACTOR * (0.5 - expected_win)
        loser_change = K_FACTOR * (0.5 - (1 - expected_win))
    else:
        # Calculate ELO changes
        expected_win = 1 / (1 + 10 ** ((loser["elo"] - winner["elo"]) / 400))
        winner_change = K_FACTOR * (1 - expected_win)
        loser_change = K_FACTOR * (0 - (1 - expected_win))
    
    # Update winner
    await users_collection.update_one(
        {"_id": winner_id},
        {
            "$inc": {
                "elo": winner_change,
                "games_played": 1,
                "wins": 0 if draw else 1,
                "draws": 1 if draw else 0
            }
        }
    )
    
    # Update loser
    await users_collection.update_one(
        {"_id": loser_id},
        {
            "$inc": {
                "elo": loser_change,
                "games_played": 1,
                "losses": 0 if draw else 1,
                "draws": 1 if draw else 0
            }
        }
    )
    
    # Update leaderboard
    await update_leaderboard(winner_id, winner["elo"] + winner_change)
    await update_leaderboard(loser_id, loser["elo"] + loser_change)

async def update_leaderboard(user_id: int, elo: float):
    await leaderboard_collection.update_one(
        {"user_id": user_id},
        {"$set": {"elo": elo}},
        upsert=True
    )

async def get_leaderboard(limit: int = 10) -> List[Dict]:
    return await leaderboard_collection.find().sort("elo", DESCENDING).limit(limit).to_list(length=limit)

def create_board_keyboard(board: chess.Board, selected_square: Optional[str] = None) -> InlineKeyboardMarkup:
    keyboard = []
    legal_moves = []
    
    if selected_square:
        try:
            square_index = chess.parse_square(selected_square)
            piece = board.piece_at(square_index)
            if piece and piece.color == board.turn:
                for move in board.legal_moves:
                    if move.from_square == square_index:
                        legal_moves.append(chess.square_name(move.to_square))
        except:
            selected_square = None
    
    # Create board UI
    for row in range(7, -1, -1):
        row_buttons = []
        for col in range(8):
            square_index = row * 8 + col
            square_name = chess.square_name(square_index)
            piece = board.piece_at(square_index)
            
            symbol = "·"
            if piece:
                symbol = piece.symbol()
                if piece.color == chess.WHITE:
                    symbol = symbol.upper()
                else:
                    symbol = symbol.lower()
            
            # Highlight legal moves and selected piece
            callback_data = f"_select_{square_name}"
            if selected_square == square_name:
                callback_data = f"_deselect"
            elif square_name in legal_moves:
                callback_data = f"_move_{selected_square}_{square_name}"
            
            row_buttons.append(InlineKeyboardButton(symbol, callback_data=callback_data))
        keyboard.append(row_buttons)
    
    # Add control buttons
    control_row = [
        InlineKeyboardButton("Resign", callback_data="_resign"),
        InlineKeyboardButton("Draw", callback_data="_offer_draw"),
        InlineKeyboardButton("Refresh", callback_data="_refresh")
    ]
    keyboard.append(control_row)
    
    return InlineKeyboardMarkup(keyboard)

async def update_game_message(game: ChessGame, chat_id: int, message_id: int, selected_square: Optional[str] = None):
    time_left_white = game.format_time(game.get_time_left(game.white_id))
    time_left_black = game.format_time(game.get_time_left(game.black_id))
    
    status = "White to move" if game.board.turn == chess.WHITE else "Black to move"
    if game.is_game_over():
        status = f"Game Over - {game.get_result()}"
        winner = game.get_winner()
        if winner:
            status += f" - {'White' if winner == game.white_id else 'Black'} wins!"
    
    caption = (
        f"♟️ Chess Game\n"
        f"⚪ White: {game.white_id} ({time_left_white})\n"
        f"⚫ Black: {game.black_id} ({time_left_black})\n"
        f"**{status}**\n"
        f"Move: {game.move_count + 1}"
    )
    
    keyboard = create_board_keyboard(game.board, selected_square)
    
    try:
        await app.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=caption,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except:
        pass  # Message might not be modified if content is the same

async def game_timer(game_id: str, chat_id: int, message_id: int):
    try:
        while game_id in active_games:
            game = active_games[game_id]
            
            # Check if time ran out
            white_time = game.get_time_left(game.white_id)
            black_time = game.get_time_left(game.black_id)
            
            if white_time <= 0:
                await end_game(game_id, game.black_id, "timeout")
                break
            elif black_time <= 0:
                await end_game(game_id, game.white_id, "timeout")
                break
            
            # Update the message every 10 seconds
            await update_game_message(game, chat_id, message_id)
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass  # Timer was cancelled

async def end_game(game_id: str, winner_id: Optional[int] = None, reason: str = "resignation"):
    if game_id not in active_games:
        return
    
    game = active_games[game_id]
    white_id, black_id = game.white_id, game.black_id
    
    # Cancel timer
    if game_id in game_timers:
        game_timers[game_id].cancel()
        del game_timers[game_id]
    
    # Update user stats
    if winner_id:
        loser_id = black_id if winner_id == white_id else white_id
        await update_elo(winner_id, loser_id)
    else:
        # Draw
        await update_elo(white_id, black_id, draw=True)
    
    # Save game to database
    await games_collection.insert_one({
        "game_id": game_id,
        "white_id": white_id,
        "black_id": black_id,
        "winner_id": winner_id,
        "moves": [move.uci() for move in game.board.move_stack],
        "result": reason,
        "ended_at": datetime.now(),
        "move_count": game.move_count
    })
    
    # Remove from active games
    del active_games[game_id]

@app.on_message(filters.command("chestart"))
async def start_comfffmand(client: Client, message: Message):
    user_id = message.from_user.id
    await get_user(user_id)  # Ensure user exists
    
    welcome_text = (
        "♟️ Welcome to Chess Bot!\n\n"
        "Available commands:\n"
        "/start - Show this help\n"
        "/play @username - Challenge a user to a game\n"
        "/profile - Show your stats and rating\n"
        "/leaderboard - Show top players\n"
        "/cancel - Cancel your active game"
    )
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command("playchess"))
async def play_cejcommand(client: Client, message: Message):
    user_id = message.from_user.id
    opponent_username = message.command[1] if len(message.command) > 1 else None
    
    if not opponent_username:
        await message.reply_text("Please specify an opponent: /play @username")
        return
    
    # Remove @ if present
    opponent_username = opponent_username.lstrip('@')
    
    # Check if user is trying to play themselves
    if message.from_user.username and opponent_username.lower() == message.from_user.username.lower():
        await message.reply_text("You can't play against yourself!")
        return
    
    # In a real implementation, you would resolve the username to a user ID
    # For this example, we'll assume the opponent is the next available user
    opponent_id = user_id + 1  # This is just a placeholder
    
    # Create game ID
    game_id = f"{min(user_id, opponent_id)}_{max(user_id, opponent_id)}"
    
    # Check if there's already an active game
    if game_id in active_games:
        await message.reply_text("You already have an active game with this user!")
        return
    
    # Create new game
    game = ChessGame(game_id, user_id, opponent_id)
    active_games[game_id] = game
    
    # Send game message
    keyboard = create_board_keyboard(game.board)
    msg = await message.reply_text(
        f"♟️ Chess Game\n"
        f"⚪ White: {user_id}\n"
        f"⚫ Black: {opponent_id}\n"
        f"**White to move**\n"
        f"Move: 1",
        reply_markup=keyboard
    )
    
    # Start timer
    game_timers[game_id] = asyncio.create_task(game_timer(game_id, msg.chat.id, msg.id))

@app.on_message(filters.command("cheprofile"))
async def profilecff_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    profile_text = (
        f"👤 Profile for {message.from_user.first_name}\n\n"
        f"📊 ELO Rating: {user['elo']:.0f}\n"
        f"🎮 Games Played: {user['games_played']}\n"
        f"✅ Wins: {user['wins']}\n"
        f"❌ Losses: {user['losses']}\n"
        f"🤝 Draws: {user['draws']}\n"
        f"📈 Win Rate: {(user['wins'] / user['games_played'] * 100) if user['games_played'] > 0 else 0:.1f}%"
    )
    
    await message.reply_text(profile_text)

@app.on_message(filters.command("cheleaderboard"))
async def leaderbchhoard_command(client: Client, message: Message):
    leaders = await get_leaderboard(10)
    
    if not leaders:
        await message.reply_text("No players on the leaderboard yet!")
        return
    
    leaderboard_text = "🏆 Top Players\n\n"
    for i, player in enumerate(leaders, 1):
        # In a real implementation, you would get the username from user ID
        leaderboard_text += f"{i}. User {player['user_id']} - {player['elo']:.0f} ELO\n"
    
    await message.reply_text(leaderboard_text)

@app.on_callback_query(filters.regex(r"^_select_"))
async def select_piece(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    square = data.replace("_select_", "")
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    game = active_games[game_id]
    
    # Check if it's the user's turn
    if user_id != game.current_player_id():
        await callback_query.answer("It's not your turn!")
        return
    
    # Update message with selected piece highlighted
    await update_game_message(game, callback_query.message.chat.id, callback_query.message.id, square)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^_deselect"))
async def deselect_piece(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    game = active_games[game_id]
    
    # Update message without selection
    await update_game_message(game, callback_query.message.chat.id, callback_query.message.id)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^_move_"))
async def make_moveg(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    parts = data.split("_")
    from_square = parts[2]
    to_square = parts[3]
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    game = active_games[game_id]
    
    # Check if it's the user's turn
    if user_id != game.current_player_id():
        await callback_query.answer("It's not your turn!")
        return
    
    # Make the move
    move_uci = f"{from_square}{to_square}"
    success = game.make_move(move_uci)
    
    if not success:
        await callback_query.answer("Invalid move!")
        return
    
    # Update the board
    await update_game_message(game, callback_query.message.chat.id, callback_query.message.id)
    await callback_query.answer()
    
    # Check if game is over
    if game.is_game_over():
        winner = game.get_winner()
        await end_game(game_id, winner, "checkmate" if winner else "draw")

@app.on_callback_query(filters.regex(r"^_resign"))
async def resign_game(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    game = active_games[game_id]
    winner_id = game.black_id if user_id == game.white_id else game.white_id
    
    await end_game(game_id, winner_id, "resignation")
    await callback_query.answer("You resigned from the game")
    
    # Update message
    await update_game_message(game, callback_query.message.chat.id, callback_query.message.id)
    await callback_query.message.edit_text(
        f"{callback_query.message.text}\n\n{callback_query.from_user.first_name} resigned!",
        reply_markup=callback_query.message.reply_markup
    )

@app.on_callback_query(filters.regex(r"^_offer_draw"))
async def offer_draw(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    # In a real implementation, you would send a draw offer to the opponent
    # For simplicity, we'll just end the game as a draw
    await end_game(game_id, None, "draw agreed")
    await callback_query.answer("Draw offered")
    
    # Update message
    game = active_games.get(game_id)
    if game:
        await update_game_message(game, callback_query.message.chat.id, callback_query.message.id)
        await callback_query.message.edit_text(
            f"{callback_query.message.text}\n\nDraw agreed!",
            reply_markup=callback_query.message.reply_markup
        )

@app.on_callback_query(filters.regex(r"^_refresh"))
async def refresh_board(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Find active game for this user
    game_id = None
    for gid, game in active_games.items():
        if user_id in [game.white_id, game.black_id]:
            game_id = gid
            break
    
    if not game_id:
        await callback_query.answer("You don't have an active game!")
        return
    
    game = active_games[game_id]
    await update_game_message(game, callback_query.message.chat.id, callback_query.message.id)
    await callback_query.answer("Board refreshed")
