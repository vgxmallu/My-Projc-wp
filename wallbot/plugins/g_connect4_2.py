import os
import random
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.errors import DuplicateKeyError
from config import DB_URL
from wallbot import wbot as app

# Initialize MongoDB

mongo_client = MongoClient(DB_URL)
db = mongo_client.connect4_bot

# Collections
games_col = db.games
users_col = db.users
tournaments_col = db.tournaments
leaderboard_col = db.leaderboard

# Create indexes
games_col.create_index([("status", 1), ("created_at", 1)])
games_col.create_index("players")
users_col.create_index("user_id", unique=True)
tournaments_col.create_index([("status", 1), ("start_date", 1)])
leaderboard_col.create_index("user_id", unique=True)

# Initialize Pyrogram Client

# Game constants
ROWS = 6
COLS = 7
EMPTY = "⚪"
PLAYER1 = "🔴"
PLAYER2 = "🟡"
BOT = "🤖"
WINNING_LENGTH = 4

# Game difficulty levels
class Difficulty(Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3

# Game status
class GameStatus(Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

# Tournament status
class TournamentStatus(Enum):
    REGISTERING = "registering"
    ACTIVE = "active"
    COMPLETED = "completed"

# Database models
async def get_or_create_user(user_id: int, username: str = "", first_name: str = ""):
    """Get user from DB or create if not exists"""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.now(),
            "games_played": 0,
            "games_won": 0,
            "games_lost": 0,
            "tournaments_won": 0,
            "rating": 1000  # Elo rating
        }
        users_col.insert_one(user)
        # Add to leaderboard
        leaderboard_col.insert_one({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "rating": 1000,
            "games_played": 0,
            "games_won": 0,
            "last_updated": datetime.now()
        })
    return user

async def update_user_stats(user_id: int, won: bool = None):
    """Update user statistics"""
    update_data = {"$inc": {"games_played": 1}}
    
    if won is True:
        update_data["$inc"]["games_won"] = 1
        update_data["$inc"]["rating"] = 20  # Increase rating for win
    elif won is False:
        update_data["$inc"]["games_lost"] = 1
        update_data["$inc"]["rating"] = -15  # Decrease rating for loss
    
    users_col.update_one({"user_id": user_id}, update_data)
    
    # Update leaderboard
    user = users_col.find_one({"user_id": user_id})
    leaderboard_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "rating": user["rating"],
                "games_played": user["games_played"],
                "games_won": user["games_won"],
                "last_updated": datetime.now()
            }
        }
    )

async def create_game(player1_id: int, player2_id: int = None, is_bot: bool = False, 
                     difficulty: Difficulty = Difficulty.MEDIUM, tournament_id: str = None):
    """Create a new game"""
    board = [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]
    
    game = {
        "player1_id": player1_id,
        "player2_id": player2_id if not is_bot else None,
        "is_bot": is_bot,
        "bot_difficulty": difficulty.value if is_bot else None,
        "current_player": player1_id,
        "board": board,
        "status": GameStatus.ACTIVE.value,
        "moves": [],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "tournament_id": tournament_id
    }
    
    result = games_col.insert_one(game)
    return str(result.inserted_id)

async def get_game(game_id: str):
    """Get a game by ID"""
    return games_col.find_one({"_id": game_id})

async def update_game(game_id: str, update_data: dict):
    """Update game data"""
    update_data["updated_at"] = datetime.now()
    games_col.update_one({"_id": game_id}, {"$set": update_data})

async def abandon_game(game_id: str, user_id: int):
    """Mark a game as abandoned"""
    game = await get_game(game_id)
    if not game:
        return False
    
    # Determine winner (the player who didn't abandon)
    winner_id = game["player1_id"] if game["player1_id"] != user_id else game["player2_id"]
    
    await update_game(game_id, {
        "status": GameStatus.ABANDONED.value,
        "winner_id": winner_id
    })
    
    # Update stats
    await update_user_stats(winner_id, True)
    await update_user_stats(user_id, False)
    
    return True

async def cleanup_old_games():
    """Clean up games older than 24 hours"""
    cutoff = datetime.now() - timedelta(hours=24)
    result = games_col.delete_many({
        "created_at": {"$lt": cutoff},
        "status": {"$ne": GameStatus.COMPLETED.value}
    })
    return result.deleted_count

async def get_leaderboard(limit: int = 10):
    """Get top players from leaderboard"""
    return list(leaderboard_col.find().sort("rating", DESCENDING).limit(limit))

async def create_tournament(name: str, created_by: int, max_players: int = 8):
    """Create a new tournament"""
    tournament = {
        "name": name,
        "created_by": created_by,
        "max_players": max_players,
        "players": [],
        "status": TournamentStatus.REGISTERING.value,
        "start_date": None,
        "end_date": None,
        "winner_id": None,
        "bracket": {},
        "current_round": 0,
        "created_at": datetime.now()
    }
    
    result = tournaments_col.insert_one(tournament)
    return str(result.inserted_id)

async def join_tournament(tournament_id: str, user_id: int):
    """Add a player to a tournament"""
    tournament = tournaments_col.find_one({"_id": tournament_id})
    if not tournament:
        return False, "Tournament not found"
    
    if tournament["status"] != TournamentStatus.REGISTERING.value:
        return False, "Tournament registration is closed"
    
    if len(tournament["players"]) >= tournament["max_players"]:
        return False, "Tournament is full"
    
    if user_id in tournament["players"]:
        return False, "Already joined this tournament"
    
    tournaments_col.update_one(
        {"_id": tournament_id},
        {"$push": {"players": user_id}}
    )
    
    return True, "Joined tournament successfully"

# Game logic
def is_valid_move(board: List[List[str]], col: int) -> bool:
    """Check if a move is valid"""
    return 0 <= col < COLS and board[0][col] == EMPTY

def make_move(board: List[List[str]], col: int, player: str) -> Tuple[bool, List[List[str]]]:
    """Make a move on the board"""
    if not is_valid_move(board, col):
        return False, board
    
    # Find the lowest empty row in the column
    for row in range(ROWS-1, -1, -1):
        if board[row][col] == EMPTY:
            board[row][col] = player
            return True, board
    
    return False, board

def check_winner(board: List[List[str]], player: str) -> bool:
    """Check if a player has won"""
    # Check horizontal
    for row in range(ROWS):
        for col in range(COLS - WINNING_LENGTH + 1):
            if all(board[row][col+i] == player for i in range(WINNING_LENGTH)):
                return True
    
    # Check vertical
    for row in range(ROWS - WINNING_LENGTH + 1):
        for col in range(COLS):
            if all(board[row+i][col] == player for i in range(WINNING_LENGTH)):
                return True
    
    # Check diagonal (top-left to bottom-right)
    for row in range(ROWS - WINNING_LENGTH + 1):
        for col in range(COLS - WINNING_LENGTH + 1):
            if all(board[row+i][col+i] == player for i in range(WINNING_LENGTH)):
                return True
    
    # Check diagonal (bottom-left to top-right)
    for row in range(WINNING_LENGTH - 1, ROWS):
        for col in range(COLS - WINNING_LENGTH + 1):
            if all(board[row-i][col+i] == player for i in range(WINNING_LENGTH)):
                return True
    
    return False

def is_board_full(board: List[List[str]]) -> bool:
    """Check if the board is full"""
    return all(cell != EMPTY for row in board for cell in row)

def board_to_string(board: List[List[str]]) -> str:
    """Convert board to string representation"""
    # Add column numbers
    board_str = "".join(f"{i+1}️⃣" for i in range(COLS)) + "\n"
    
    # Add board rows
    for row in board:
        board_str += "".join(cell for cell in row) + "\n"
    
    return board_str

def get_bot_move(board: List[List[str]], difficulty: Difficulty) -> int:
    """Get a move for the bot based on difficulty"""
    # Easy: Random move
    if difficulty == Difficulty.EASY:
        valid_moves = [col for col in range(COLS) if is_valid_move(board, col)]
        return random.choice(valid_moves) if valid_moves else -1
    
    # Medium: Try to win or block opponent, otherwise random
    if difficulty == Difficulty.MEDIUM:
        # Check if bot can win
        for col in range(COLS):
            if is_valid_move(board, col):
                test_board = [row[:] for row in board]  # Copy board
                _, new_board = make_move(test_board, col, PLAYER2)
                if check_winner(new_board, PLAYER2):
                    return col
        
        # Check if need to block player
        for col in range(COLS):
            if is_valid_move(board, col):
                test_board = [row[:] for row in board]  # Copy board
                _, new_board = make_move(test_board, col, PLAYER1)
                if check_winner(new_board, PLAYER1):
                    return col
        
        # Otherwise random
        valid_moves = [col for col in range(COLS) if is_valid_move(board, col)]
        return random.choice(valid_moves) if valid_moves else -1
    
    # Hard: Minimax algorithm (simplified)
    if difficulty == Difficulty.HARD:
        # This is a simplified version - a full minimax would be better
        best_score = float('-inf')
        best_move = -1
        
        for col in range(COLS):
            if is_valid_move(board, col):
                test_board = [row[:] for row in board]  # Copy board
                _, new_board = make_move(test_board, col, PLAYER2)
                
                # Simple evaluation function
                score = evaluate_board(new_board, PLAYER2)
                
                if score > best_score:
                    best_score = score
                    best_move = col
        
        return best_move if best_move != -1 else random.choice([col for col in range(COLS) if is_valid_move(board, col)])

def evaluate_board(board: List[List[str]], player: str) -> int:
    """Evaluate the board for a player (simplified)"""
    opponent = PLAYER1 if player == PLAYER2 else PLAYER2
    score = 0
    
    # Center preference
    center_col = COLS // 2
    for row in range(ROWS):
        if board[row][center_col] == player:
            score += 3
    
    # Check for potential wins
    for row in range(ROWS):
        for col in range(COLS):
            if board[row][col] == player:
                # Horizontal
                if col <= COLS - WINNING_LENGTH:
                    window = [board[row][col+i] for i in range(WINNING_LENGTH)]
                    score += evaluate_window(window, player, opponent)
                
                # Vertical
                if row <= ROWS - WINNING_LENGTH:
                    window = [board[row+i][col] for i in range(WINNING_LENGTH)]
                    score += evaluate_window(window, player, opponent)
                
                # Diagonal (positive slope)
                if row <= ROWS - WINNING_LENGTH and col <= COLS - WINNING_LENGTH:
                    window = [board[row+i][col+i] for i in range(WINNING_LENGTH)]
                    score += evaluate_window(window, player, opponent)
                
                # Diagonal (negative slope)
                if row >= WINNING_LENGTH - 1 and col <= COLS - WINNING_LENGTH:
                    window = [board[row-i][col+i] for i in range(WINNING_LENGTH)]
                    score += evaluate_window(window, player, opponent)
    
    return score

def evaluate_window(window: List[str], player: str, opponent: str) -> int:
    """Evaluate a window of 4 consecutive cells"""
    score = 0
    
    if window.count(player) == 4:
        score += 100
    elif window.count(player) == 3 and window.count(EMPTY) == 1:
        score += 5
    elif window.count(player) == 2 and window.count(EMPTY) == 2:
        score += 2
    
    if window.count(opponent) == 3 and window.count(EMPTY) == 1:
        score -= 4
    
    return score

# Handlers
@app.on_message(filters.command("sttc4"))
async def starthhdhd_command(client, message: Message):
    """Handle/start command"""
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    welcome_text = (
        "🎮 *Connect 4 Bot* 🎮\n\n"
        "Play Connect 4 against friends or the bot!\n\n"
        "**Available Commands:**\n"
        "/play - Start a new game\n"
        "/leaderboard - View top players\n"
        "/stats - Your game statistics\n"
        "/tournament - Tournament management\n\n"
        "**Game Features:**\n"
        "• Player vs Player\n"
        "• Player vs Bot (3 difficulty levels)\n"
        "• Tournament mode\n"
        "• Leaderboard system\n"
        "• Auto game cleanup\n\n"
        "Use /help for detailed instructions."
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Play vs Friend", callback_data="play_pvp"),
            InlineKeyboardButton("🤖 Play vs Bot", callback_data="play_bot")
        ],
        [
            InlineKeyboardButton("📊 Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton("📈 My Stats", callback_data="stats")
        ]
    ])
    
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("playc4"))
async def play_command(client, message: Message):
    """Handle /play command"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Play vs Friend", callback_data="play_pvp"),
            InlineKeyboardButton("🤖 Play vs Bot", callback_data="play_bot")
        ]
    ])
    
    await message.reply_text(
        "Choose your game mode:",
        reply_markup=keyboard
    )

@app.on_message(filters.command("cleaderboard4"))
async def leaderbo4cdkard_command(client, message: Message):
    """Handle /leaderboard command"""
    leaderboard = await get_leaderboard(10)
    
    if not leaderboard:
        await message.reply_text("No players on the leaderboard yet!")
        return
    
    response = "🏆 *Top Players* 🏆\n\n"
    
    for i, player in enumerate(leaderboard):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
        response += f"{medal} {player.get('first_name', 'Unknown')} - {player['rating']} pts\n"
    
    await message.reply_text(response)

@app.on_message(filters.command("statc4"))
async def statscrr_command(client, message: Message):
    """Handle /stats command"""
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    win_rate = (user["games_won"] / user["games_played"] * 100) if user["games_played"] > 0 else 0
    
    response = (
        f"📊 *Stats for {user['first_name']}* 📊\n\n"
        f"• Rating: {user['rating']}\n"
        f"• Games Played: {user['games_played']}\n"
        f"• Games Won: {user['games_won']}\n"
        f"• Win Rate: {win_rate:.1f}%\n"
        f"• Tournaments Won: {user['tournaments_won']}\n"
    )
    
    await message.reply_text(response)

@app.on_callback_query(filters.regex("^play_"))
async def play_callback(client, callback_query: CallbackQuery):
    """Handle play callback"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "play_pvp":
        # Create a PvP game
        game_id = await create_game(user_id)
        game = await get_game(game_id)
        
        # Send game invite
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎮 Join Game", callback_data=f"join_{game_id}")
        ]])
        
        await callback_query.message.edit_text(
            f"🎮 {callback_query.from_user.first_name} started a new game!\n\n"
            "Click the button below to join:",
            reply_markup=keyboard
        )
    
    elif data == "play_bot":
        # Show bot difficulty options
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("😊 Easy", callback_data="bot_easy"),
                InlineKeyboardButton("😐 Medium", callback_data="bot_medium")
            ],[
                InlineKeyboardButton("😈 Hard", callback_data="bot_hard")
            ]
        ])
        
        await callback_query.message.edit_text(
            "Choose bot difficulty:",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^bot_"))
async def bot_difficulty_callback(client, callback_query: CallbackQuery):
    """Handle bot difficulty selection"""
    difficulty_map = {
        "bot_easy": Difficulty.EASY,
        "bot_medium": Difficulty.MEDIUM,
        "bot_hard": Difficulty.HARD
    }
    
    difficulty = difficulty_map.get(callback_query.data)
    if not difficulty:
        await callback_query.answer("Invalid difficulty")
        return
    
    # Create a bot game
    game_id = await create_game(callback_query.from_user.id, is_bot=True, difficulty=difficulty)
    game = await get_game(game_id)
    
    # Send game board
    board_text = board_to_string(game["board"])
    keyboard = create_game_keyboard(game_id, game["board"])
    
    await callback_query.message.edit_text(
        f"🎮 Game Started!\n\n{callback_query.from_user.first_name} vs {BOT} Bot\n\n{board_text}",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^join_"))
async def join_game_callback(client, callback_query: CallbackQuery):
    """Handle join game callback"""
    game_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    game = await get_game(game_id)
    if not game:
        await callback_query.answer("Game not found")
        return
    
    if game["status"] != GameStatus.ACTIVE.value:
        await callback_query.answer("Game is no longer available")
        return
    
    if game["player2_id"] is not None:
        await callback_query.answer("Game is already full")
        return
    
    # Join the game
    await update_game(game_id, {
        "player2_id": user_id,
        "current_player": game["player1_id"]  # Player 1 starts
    })
    
    # Send game board
    game = await get_game(game_id)
    board_text = board_to_string(game["board"])
    keyboard = create_game_keyboard(game_id, game["board"])
    
    player1 = await get_or_create_user(game["player1_id"])
    player2 = await get_or_create_user(game["player2_id"])
    
    await callback_query.message.edit_text(
        f"🎮 Game Started!\n\n{player1['first_name']} {PLAYER1} vs {PLAYER2} {player2['first_name']}\n\n{board_text}",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^move_"))
async def move_callback(client, callback_query: CallbackQuery):
    """Handle move callback"""
    data_parts = callback_query.data.split("_")
    game_id = data_parts[1]
    col = int(data_parts[2]) - 1  # Convert to 0-based index
    
    user_id = callback_query.from_user.id
    game = await get_game(game_id)
    
    if not game:
        await callback_query.answer("Game not found")
        return
    
    if game["status"] != GameStatus.ACTIVE.value:
        await callback_query.answer("Game is not active")
        return
    
    if game["current_player"] != user_id:
        await callback_query.answer("It's not your turn")
        return
    
    # Make the move
    success, new_board = make_move(game["board"], col, PLAYER1 if user_id == game["player1_id"] else PLAYER2)
    if not success:
        await callback_query.answer("Invalid move")
        return
    
    # Update the game
    await update_game(game_id, {
        "board": new_board,
        "moves": game["moves"] + [{"player": user_id, "col": col}]
    })
    
    # Check for winner
    player_symbol = PLAYER1 if user_id == game["player1_id"] else PLAYER2
    if check_winner(new_board, player_symbol):
        await update_game(game_id, {
            "status": GameStatus.COMPLETED.value,
            "winner_id": user_id
        })
        
        # Update stats
        await update_user_stats(user_id, True)
        if game["is_bot"]:
            await update_user_stats(0, False)  # Bot has user_id 0
        else:
            opponent_id = game["player1_id"] if user_id == game["player2_id"] else game["player2_id"]
            await update_user_stats(opponent_id, False)
        
        # Send win message
        board_text = board_to_string(new_board)
        await callback_query.message.edit_text(
            f"🎉 {callback_query.from_user.first_name} wins!\n\n{board_text}"
        )
        await callback_query.answer()
        return
    
    # Check for draw
    if is_board_full(new_board):
        await update_game(game_id, {
            "status": GameStatus.COMPLETED.value,
            "winner_id": None  # Draw
        })
        
        # Update stats (both players get a draw)
        await update_user_stats(game["player1_id"], None)
        if not game["is_bot"]:
            await update_user_stats(game["player2_id"], None)
        
        # Send draw message
        board_text = board_to_string(new_board)
        await callback_query.message.edit_text(
            f"🤝 It's a draw!\n\n{board_text}"
        )
        await callback_query.answer()
        return
    
    # Switch player
    if game["is_bot"]:
        # Bot's turn
        bot_difficulty = Difficulty(game["bot_difficulty"])
        bot_move = get_bot_move(new_board, bot_difficulty)
        
        if bot_move != -1:
            # Make bot move
            success, new_board = make_move(new_board, bot_move, PLAYER2)
            await update_game(game_id, {
                "board": new_board,
                "moves": game["moves"] + [{"player": 0, "col": bot_move}]  # Bot has user_id 0
            })
            
            # Check if bot wins
            if check_winner(new_board, PLAYER2):
                await update_game(game_id, {
                    "status": GameStatus.COMPLETED.value,
                    "winner_id": 0  # Bot wins
                })
                
                # Update stats
                await update_user_stats(user_id, False)
                await update_user_stats(0, True)  # Bot has user_id 0
                
                # Send win message
                board_text = board_to_string(new_board)
                await callback_query.message.edit_text(
                    f"🤖 Bot wins!\n\n{board_text}"
                )
                await callback_query.answer()
                return
            
            # Check for draw
            if is_board_full(new_board):
                await update_game(game_id, {
                    "status": GameStatus.COMPLETED.value,
                    "winner_id": None  # Draw
                })
                
                # Update stats
                await update_user_stats(user_id, None)
                await update_user_stats(0, None)  # Bot has user_id 0
                
                # Send draw message
                board_text = board_to_string(new_board)
                await callback_query.message.edit_text(
                    f"🤝 It's a draw!\n\n{board_text}"
                )
                await callback_query.answer()
                return
            
            # Switch back to player
            await update_game(game_id, {
                "current_player": user_id
            })
            
            # Update board display
            board_text = board_to_string(new_board)
            keyboard = create_game_keyboard(game_id, new_board)
            
            await callback_query.message.edit_text(
                f"🎮 Your Turn!\n\n{board_text}",
                reply_markup=keyboard
            )
    else:
        # Switch to other player
        next_player = game["player1_id"] if user_id == game["player2_id"] else game["player2_id"]
        await update_game(game_id, {
            "current_player": next_player
        })
        
        # Update board display
        board_text = board_to_string(new_board)
        keyboard = create_game_keyboard(game_id, new_board)
        
        next_player_user = await get_or_create_user(next_player)
        await callback_query.message.edit_text(
            f"🎮 {next_player_user['first_name']}'s Turn!\n\n{board_text}",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

def create_game_keyboard(game_id: str, board: List[List[str]]) -> InlineKeyboardMarkup:
    """Create game keyboard with column buttons"""
    keyboard = []
    
    # Add column buttons
    row_buttons = []
    for col in range(COLS):
        # Check if column is full
        if board[0][col] == EMPTY:
            row_buttons.append(InlineKeyboardButton(f"{col+1}", callback_data=f"move_{game_id}_{col+1}"))
        else:
            row_buttons.append(InlineKeyboardButton("❌", callback_data="full_column"))
    
    # Split into two rows if too many buttons
    if len(row_buttons) > 5:
        mid = len(row_buttons) // 2
        keyboard.append(row_buttons[:mid])
        keyboard.append(row_buttons[mid:])
    else:
        keyboard.append(row_buttons)
    
    # Add abandon button
    keyboard.append([InlineKeyboardButton("🚫 Abandon Game", callback_data=f"abandon_{game_id}")])
    
    return InlineKeyboardMarkup(keyboard)

@app.on_callback_query(filters.regex("^abandon_"))
async def abandon_callback(client, callback_query: CallbackQuery):
    """Handle abandon game callback"""
    game_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    success = await abandon_game(game_id, user_id)
    if success:
        await callback_query.message.edit_text(
            f"🚫 {callback_query.from_user.first_name} abandoned the game."
        )
    else:
        await callback_query.answer("Failed to abandon game")
    
    await callback_query.answer()

# Background tasks
async def cleanup_task():
    """Background task to clean up old games"""
    while True:
        try:
            deleted_count = await cleanup_old_games()
            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} old games")
        except Exception as e:
            print(f"Error in cleanup task: {e}")
        
        await asyncio.sleep(3600)  # Run every hour

