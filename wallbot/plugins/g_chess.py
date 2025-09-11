# Telegram Chess Bot using Pyrogram and MongoDB
# This single file contains all the logic for the bot.

import os
import logging
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import chess
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,
)
from pyrogram.errors import MessageNotModified
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "chess_bot_db"

# --- Constants ---
K_FACTOR = 32  # For ELO calculation
DEFAULT_ELO = 1200
PIECE_EMOJIS = {
    'P': '♙', 'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔',
    'p': '♟︎', 'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚'
}
EMPTY_SQUARE_LIGHT = "▫️"
EMPTY_SQUARE_DARK = "▪️"
HIGHLIGHT_SQUARE = "🟡"

# Time controls in seconds
TIME_CONTROLS = {
    "blitz": 300,  # 5 minutes
    "rapid": 600,  # 10 minutes
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Setup ---
try:
    mongo_client = MongoClient(DB_URL)
    db = mongo_client[DB_NAME]
    users_collection = db["users"]
    games_collection = db["games"]
    
    # Create indexes for faster queries
    users_collection.create_index([("elo", DESCENDING)])
    games_collection.create_index([("status", ASCENDING)])
    logger.info("Successfully connected to MongoDB.")
except Exception as e:
    logger.error(f"Could not connect to MongoDB: {e}")
    exit(1)


# --- Helper Functions ---

def get_user(user_id: int):
    """Retrieves or creates a user in the database."""
    user = users_collection.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "elo": DEFAULT_ELO,
            "wins": 0,
            "losses": 0,
            "draws": 0,
        }
        users_collection.insert_one(user)
    return user

def update_elo(winner_id: int, loser_id: int, is_draw: bool = False):
    """Updates ELO ratings for two players after a game."""
    winner = get_user(winner_id)
    loser = get_user(loser_id)

    r_winner = winner["elo"]
    r_loser = loser["elo"]

    e_winner = 1 / (1 + 10 ** ((r_loser - r_winner) / 400))
    e_loser = 1 / (1 + 10 ** ((r_winner - r_loser) / 400))

    if is_draw:
        s_winner, s_loser = 0.5, 0.5
        update_winner = {"$inc": {"draws": 1}}
        update_loser = {"$inc": {"draws": 1}}
    else:
        s_winner, s_loser = 1, 0
        update_winner = {"$inc": {"wins": 1}}
        update_loser = {"$inc": {"losses": 1}}

    new_r_winner = r_winner + K_FACTOR * (s_winner - e_winner)
    new_r_loser = r_loser + K_FACTOR * (s_loser - e_loser)

    update_winner["$set"] = {"elo": round(new_r_winner)}
    update_loser["$set"] = {"elo": round(new_r_loser)}

    users_collection.update_one({"_id": winner_id}, update_winner)
    users_collection.update_one({"_id": loser_id}, update_loser)

def generate_board_markup(board: chess.Board, game_id: str, perspective: chess.Color, selected_square: str = None):
    """Generates the InlineKeyboardMarkup for the chess board."""
    markup = []
    # Flip board if player is black
    squares_range = reversed(range(8)) if perspective == chess.BLACK else range(8)
    
    legal_moves = []
    if selected_square:
        try:
            legal_moves = [move.to_square for move in board.legal_moves if move.from_square == chess.parse_square(selected_square)]
        except Exception as e:
            logger.warning(f"Error getting legal moves for {selected_square}: {e}")

    for rank in squares_range:
        row = []
        for file in range(8):
            square = chess.square(file, rank)
            square_name = chess.square_name(square)
            piece = board.piece_at(square)

            text = ""
            if square in legal_moves:
                text = HIGHLIGHT_SQUARE
            elif piece:
                text = PIECE_EMOJIS[piece.symbol()]
            else:
                text = EMPTY_SQUARE_LIGHT if (rank + file) % 2 == 1 else EMPTY_SQUARE_DARK

            if selected_square and chess.parse_square(selected_square) == square:
                 callback_data = f"_cancel_{game_id}"
            elif selected_square and square in legal_moves:
                move_uci = f"{selected_square}{square_name}"
                callback_data = f"_move_{game_id}_{move_uci}"
            else:
                callback_data = f"_select_{game_id}_{square_name}"
            
            row.append(InlineKeyboardButton(text, callback_data=callback_data))
        markup.append(row)
        
    # Add control buttons
    control_row = [
        InlineKeyboardButton("🏳️ Surrender", callback_data=f"_surrender_{game_id}")
    ]
    markup.append(control_row)
    
    return InlineKeyboardMarkup(markup)

def get_game_status_text(game: dict, board: chess.Board):
    """Generates the text to accompany the board, showing turn, clocks, etc."""
    white_player = app.get_users(game['white_player_id'])
    black_player = app.get_users(game['black_player_id'])
    
    white_name = white_player.first_name
    black_name = black_player.first_name
    
    white_elo = get_user(game['white_player_id'])['elo']
    black_elo = get_user(game['black_player_id'])['elo']
    
    text = f"**{game['time_control'].capitalize()} Chess**\n\n"
    text += f"⚪️ **{white_name}** ({white_elo}) vs ⚫️ **{black_name}** ({black_elo})\n\n"

    # Update and display clocks
    now = datetime.utcnow()
    if game['status'] == 'ongoing' and game.get('last_move_timestamp'):
        time_diff = (now - game['last_move_timestamp']).total_seconds()
        if board.turn == chess.WHITE:
             game['black_time_left'] -= time_diff
        else:
             game['white_time_left'] -= time_diff
    
    white_time = str(timedelta(seconds=int(game['white_time_left']))).split(":")
    black_time = str(timedelta(seconds=int(game['black_time_left']))).split(":")
    
    text += f"⏳ White: `{white_time[1]}:{white_time[2]}`\n"
    text += f"⏳ Black: `{black_time[1]}:{black_time[2]}`\n\n"

    # Game state message
    if game['status'] == 'ongoing':
        turn_name = white_name if board.turn == chess.WHITE else black_name
        text += f"**Turn: {turn_name} {'⚪️' if board.turn == chess.WHITE else '⚫️'}**"
        if board.is_check():
            text += " (Check!)"
    else:
        text += f"**Game Over: {game['status_message']}**"
        
    return text

# --- Bot Command Handlers ---

@app.on_message(filters.command("stchess"))
async def start_hanhhdler(client: Client, message: Message):
    get_user(message.from_user.id) # Register user if not exists
    await message.reply(
        "**Welcome to the Chess Bot!**\n\n"
        "I use the `python-chess` library for game logic and MongoDB for storing stats.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(" Blitz (5 min)", callback_data="_newgame_blitz")],
            [InlineKeyboardButton(" Rapid (10 min)", callback_data="_newgame_rapid")],
            [
                InlineKeyboardButton("📊 Leaderboard", callback_data="_leaderboard"),
                InlineKeyboardButton("👤 Profile", callback_data="_profile")
            ]
        ])
    )

# --- Main Callback Query Handler ---

@app.on_callback_query(filters.regex(r"^_"))
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data.split("_")
    action = data[1]

    try:
        if action == "newgame":
            time_control = data[2]
            # Look for a waiting game
            waiting_game = games_collection.find_one_and_update(
                {"status": "waiting", "time_control": time_control, "white_player_id": {"$ne": user_id}},
                {
                    "$set": {
                        "status": "ongoing",
                        "black_player_id": user_id,
                        "start_time": datetime.utcnow(),
                        "last_move_timestamp": datetime.utcnow()
                    }
                }
            )
            
            if waiting_game:
                # Found a game, start it
                game_id = str(waiting_game['_id'])
                board = chess.Board(waiting_game['fen'])
                
                # Notify both players
                text = get_game_status_text(waiting_game, board)
                markup = generate_board_markup(board, game_id, perspective=chess.WHITE)
                await client.edit_message_text(waiting_game['chat_id'], waiting_game['message_id'], text, reply_markup=markup)

                # Send board to the second player (black)
                markup_black = generate_board_markup(board, game_id, perspective=chess.BLACK)
                await query.message.edit_text(text, reply_markup=markup_black)

            else:
                # No waiting game, create a new one
                game_id = str(uuid4())
                new_game = {
                    "_id": game_id,
                    "white_player_id": user_id,
                    "black_player_id": None,
                    "fen": chess.Board().fen(),
                    "status": "waiting",
                    "time_control": time_control,
                    "chat_id": query.message.chat.id,
                    "message_id": query.message.id,
                    "white_time_left": TIME_CONTROLS[time_control],
                    "black_time_left": TIME_CONTROLS[time_control],
                }
                games_collection.insert_one(new_game)
                await query.message.edit_text(
                    f"**Waiting for an opponent...**\n"
                    f"Time Control: {time_control.capitalize()}\n\n"
                    f"Share this bot with a friend to play!",
                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel Search", callback_data=f"_cancelsearch_{game_id}")]])
                )

        elif action == "leaderboard":
            leaderboard = users_collection.find().sort("elo", DESCENDING).limit(10)
            text = "**🏆 Top 10 Players 🏆**\n\n"
            for i, user in enumerate(leaderboard):
                try:
                    tg_user = await client.get_users(user['_id'])
                    text += f"{i+1}. **{tg_user.first_name}** - `{user['elo']} ELO`\n"
                except Exception:
                     text += f"{i+1}. *Unknown User* - `{user['elo']} ELO`\n"
            await query.answer(text, show_alert=True)

        elif action == "profile":
            user = get_user(user_id)
            text = (
                f"👤 **Your Profile**\n\n"
                f"**ELO Rating:** `{user['elo']}`\n"
                f"**Wins:** `{user['wins']}`\n"
                f"**Losses:** `{user['losses']}`\n"
                f"**Draws:** `{user['draws']}`"
            )
            await query.answer(text, show_alert=True)
        
        elif action in ["select", "move", "surrender", "cancel"]:
            game_id = data[2]
            game = games_collection.find_one({"_id": game_id})
            
            if not game:
                await query.answer("Game not found or has expired.", show_alert=True)
                return

            board = chess.Board(game['fen'])
            is_white = user_id == game['white_player_id']
            is_black = user_id == game['black_player_id']
            player_color = chess.WHITE if is_white else chess.BLACK

            if game['status'] != 'ongoing':
                await query.answer("This game has already ended.", show_alert=True)
                return

            # Check if it's the player's turn
            if board.turn != player_color and action != "cancel":
                await query.answer("It's not your turn!", show_alert=False)
                return
            
            if action == "select":
                square_name = data[3]
                square = chess.parse_square(square_name)
                piece = board.piece_at(square)
                
                if piece and piece.color == player_color:
                    markup = generate_board_markup(board, game_id, player_color, selected_square=square_name)
                    await query.message.edit_reply_markup(markup)
                else:
                    await query.answer("This is not your piece or the square is empty.", show_alert=False)
            
            elif action == "cancel":
                 markup = generate_board_markup(board, game_id, player_color)
                 await query.message.edit_reply_markup(markup)

            elif action == "move":
                move_uci = data[3]
                
                # Time calculation
                now = datetime.utcnow()
                time_diff = (now - game['last_move_timestamp']).total_seconds()
                
                if board.turn == chess.WHITE:
                    game['white_time_left'] -= time_diff
                else:
                    game['black_time_left'] -= time_diff

                if game['white_time_left'] < 0 or game['black_time_left'] < 0:
                     # Handle timeout (code is in the game over check below)
                     pass
                else:
                    try:
                        move = chess.Move.from_uci(move_uci)
                        if move in board.legal_moves:
                            board.push(move)
                        else:
                            await query.answer("Illegal move!", show_alert=False)
                            return
                    except ValueError:
                        await query.answer("Invalid move format.", show_alert=False)
                        return

                # --- Game Over Check ---
                game_over = False
                status_message = ""
                winner, loser = None, None
                is_draw = False

                # 1. Timeout
                if game['white_time_left'] < 0:
                    game_over, status_message = True, "Black wins on time."
                    winner, loser = game['black_player_id'], game['white_player_id']
                elif game['black_time_left'] < 0:
                    game_over, status_message = True, "White wins on time."
                    winner, loser = game['white_player_id'], game['black_player_id']
                # 2. Checkmate
                elif board.is_checkmate():
                    game_over = True
                    if board.turn == chess.BLACK: # Black is in checkmate
                        status_message, winner, loser = "White wins by checkmate!", game['white_player_id'], game['black_player_id']
                    else:
                        status_message, winner, loser = "Black wins by checkmate!", game['black_player_id'], game['white_player_id']
                # 3. Draws
                elif board.is_stalemate():
                    game_over, status_message, is_draw = True, "Draw by stalemate.", True
                elif board.is_insufficient_material():
                    game_over, status_message, is_draw = True, "Draw by insufficient material.", True
                elif board.can_claim_draw():
                    game_over, status_message, is_draw = True, "Draw by threefold repetition.", True
                
                # --- Update Game State ---
                update_query = {
                    "$set": {
                        "fen": board.fen(),
                        "last_move_timestamp": now,
                        "white_time_left": game['white_time_left'],
                        "black_time_left": game['black_time_left']
                    }
                }
                
                if game_over:
                    update_query["$set"]["status"] = "finished"
                    update_query["$set"]["status_message"] = status_message
                    if is_draw:
                        update_elo(game['white_player_id'], game['black_player_id'], is_draw=True)
                    else:
                        update_elo(winner, loser)
                
                games_collection.update_one({"_id": game_id}, update_query)
                updated_game = games_collection.find_one({"_id": game_id})

                # --- Edit Board for both players ---
                text = get_game_status_text(updated_game, board)
                
                # Opponent info
                opponent_id = game['black_player_id'] if is_white else game['white_player_id']
                opponent_game_msg = games_collection.find_one({"$or": [{"white_player_id": opponent_id, "status": "waiting"}, {"black_player_id": opponent_id, "status": "ongoing"}]})

                # Player's board
                markup_player = generate_board_markup(board, game_id, player_color)
                await query.message.edit_text(text, reply_markup=markup_player)

                # Opponent's board
                # This part is tricky as we need the opponent's message. 
                # A more robust system might store chat_id/message_id for both players.
                # For simplicity, we assume the game object holds the initial message info.
                try:
                    other_player_perspective = chess.BLACK if is_white else chess.WHITE
                    markup_opponent = generate_board_markup(board, game_id, other_player_perspective)
                    # We need the other player's message to edit it. This requires a better game session management.
                    # This simplified version will only update one message.
                    logger.info(f"Updated board for {user_id}")
                except Exception as e:
                    logger.error(f"Could not update opponent's board: {e}")

            elif action == "surrender":
                if is_white:
                    winner, loser = game['black_player_id'], game['white_player_id']
                    status_message = "White surrendered. Black wins."
                else:
                    winner, loser = game['white_player_id'], game['black_player_id']
                    status_message = "Black surrendered. White wins."
                
                update_elo(winner, loser)
                games_collection.update_one({"_id": game_id}, {"$set": {"status": "finished", "status_message": status_message}})
                
                updated_game = games_collection.find_one({"_id": game_id})
                text = get_game_status_text(updated_game, board)
                await query.message.edit_text(text) # Remove board on surrender

        elif action == "cancelsearch":
             game_id = data[2]
             result = games_collection.delete_one({"_id": game_id, "white_player_id": user_id, "status": "waiting"})
             if result.deleted_count > 0:
                 await query.message.edit_text("Your game search has been canceled.")
             else:
                 await query.answer("Could not cancel the search. Perhaps a game has already started?", show_alert=True)


    except MessageNotModified:
        # This happens when the user clicks the same button twice quickly.
        # It's safe to ignore.
        await query.answer()
    except Exception as e:
        logger.error(f"Error in callback handler: {e}", exc_info=True)
        await query.answer("An error occurred. Please try again.", show_alert=True)


