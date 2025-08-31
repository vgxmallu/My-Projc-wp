import pymongo
from pymongo import MongoClient
import os
from config import DB_URL

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import uuid
import random  # For simple AI
from wallbot import wbot as app


class GomokuGame:
    def __init__(self, board_size=15):
        self.board_size = board_size
        self.board = [[' ' for _ in range(board_size)] for _ in range(board_size)]
        self.current_player = 'X'
        self.game_id = None
        self.player_x = None
        self.player_o = None
        self.status = 'waiting'  # waiting, playing, finished
        self.winner = None

        # MongoDB setup
        client = MongoClient(os.getenv('DB_URL'))
        self.db = client['gomoku']
        self.games = self.db['games']

    # ... (rest of the methods same as before)

    def make_move(self, row, col, player_id):
        if self.status != 'playing':
            return False, "Game is not in progress."
        if player_id == 'AI':
            if self.player_o != 'AI' or self.current_player != 'O':
                return False, "Invalid AI move."
        elif (self.current_player == 'X' and player_id != self.player_x) or \
             (self.current_player == 'O' and player_id != self.player_o):
            return False, "Not your turn or you are not a player in this game."
        if row < 0 or row >= self.board_size or col < 0 or col >= self.board_size:
            return False, "Invalid move: out of bounds."
        if self.board[row][col] != ' ':
            return False, "Cell already occupied."
        
        self.board[row][col] = self.current_player
        if self.check_win(row, col):
            self.status = 'finished'
            self.winner = self.current_player
            self.save_game()
            return True, f"Player {self.current_player} wins!"
        if self.check_draw():
            self.status = 'finished'
            self.winner = 'Draw'
            self.save_game()
            return True, "Game is a draw!"
        
        self.current_player = 'O' if self.current_player == 'X' else 'X'
        self.save_game()
        return True, "Move successful."

    # ... (other methods)

class UserStats:
    def __init__(self):
        client = MongoClient(os.getenv('DB_URL'))
        self.db = client['gomoku']
        self.users = self.db['users']
        self.global_stats = self.db['global_stats']
        self.ensure_indexes()

    def ensure_indexes(self):
        self.users.create_index('user_id', unique=True)

    def get_user_stats(self, user_id):
        user = self.users.find_one({'user_id': user_id})
        if not user:
            return None
        user['win_rate'] = user['wins'] / user['games_played'] if user['games_played'] > 0 else 0
        return user

    def update_user_stats(self, user_id, win=0, loss=0, draw=0):
        self.users.update_one(
            {'user_id': user_id},
            {'$inc': {'wins': win, 'losses': loss, 'draws': draw, 'games_played': 1}},
            upsert=True
        )

    def get_leaderboard(self):
        return list(self.users.find().sort('wins', -1).limit(10))

    def get_global_stats(self):
        stats = self.global_stats.find_one() or {
            'total_games': 0,
            'wins_x': 0,
            'wins_o': 0,
            'draws': 0
        }
        return stats

    def update_global_stats(self, winner):
        inc = {'total_games': 1}
        if winner == 'X':
            inc['wins_x'] = 1
        elif winner == 'O':
            inc['wins_o'] = 1
        elif winner == 'Draw':
            inc['draws'] = 1
        self.global_stats.update_one({}, {'$inc': inc}, upsert=True)

    def update_stats_after_game(self, game):
        if game.winner == 'Draw':
            if game.player_x != 'AI':
                self.update_user_stats(game.player_x, draw=1)
            if game.player_o != 'AI':
                self.update_user_stats(game.player_o, draw=1)
        else:
            winner_id = game.player_x if game.winner == 'X' else game.player_o
            loser_id = game.player_o if game.winner == 'X' else game.player_x
            if winner_id != 'AI':
                self.update_user_stats(winner_id, win=1)
            if loser_id != 'AI':
                self.update_user_stats(loser_id, loss=1)
        self.update_global_stats(game.winner)

# Store active games
active_games = {}

@app.on_message(filters.command("gost"))
async def start_command(client, message):
    await message.reply_text(
        "Welcome to Advanced Gomoku! Commands:\n"
        "/newgame [ai] - Start a new game (optional: vs AI)\n"
        "/joingame <game_id> - Join a multiplayer game\n"
        "/profile - View your profile\n"
        "/leaderboard - View top players\n"
        "/stats - View global statistics"
    )

@app.on_message(filters.command("gonewgame"))
async def negow_game(client, message):
    args = message.text.split()
    vs_ai = len(args) > 1 and args[1].lower() == 'ai'
    game_id = str(uuid.uuid4())
    game = GomokuGame()
    game.start_game(game_id, message.from_user.id, 'AI' if vs_ai else None)
    active_games[game_id] = game
    if vs_ai:
        await message.reply_text(
            f"New Gomoku game vs AI created! Game ID: {game_id}\nYou are X, AI is O.\n{game.get_board_display()}",
            reply_markup=create_board_buttons(game_id)
        )
    else:
        buttons = [
            [InlineKeyboardButton("Join Game", callback_data=f"join_{game_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_text(
            f"New Gomoku game created! Game ID: {game_id}\nWaiting for an opponent...",
            reply_markup=reply_markup
        )

@app.on_message(filters.command("gojoingame"))
async def joingi_game(client, message):
    try:
        _, game_id = message.text.split()
        if game_id not in active_games:
            await message.reply_text("Game ID not found or game has already started.")
            return
        game = active_games[game_id]
        if game.status != 'waiting':
            await message.reply_text("Game has already started or is finished.")
            return
        if game.player_o is not None:
            await message.reply_text("Game already has two players.")
            return
        game.player_o = message.from_user.id
        game.status = 'playing'
        game.save_game()
        await message.reply_text(
            f"You joined game {game_id} as Player O!\n{game.get_board_display()}",
            reply_markup=create_board_buttons(game_id)
        )
        await client.send_message(
            game.player_x,
            f"Opponent joined! You are Player X.\n{game.get_board_display()}",
            reply_markup=create_board_buttons(game_id)
        )
    except ValueError:
        await message.reply_text("Please provide a valid game ID: /joingame <game_id>")

@app.on_message(filters.command("goprofile"))
async def progofile(client, message):
    user_id = message.from_user.id
    stats = UserStats().get_user_stats(user_id)
    if not stats:
        await message.reply_text("No profile found. Play some games to create one!")
        return
    profile_text = (
        f"Profile for {message.from_user.first_name}:\n"
        f"Games Played: {stats['games_played']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Draws: {stats['draws']}\n"
        f"Win Rate: {stats['win_rate']:.2%}"
    )
    await message.reply_text(profile_text)

@app.on_message(filters.command("goleaderboard"))
async def leaderbgomoard(client, message):
    top_users = UserStats().get_leaderboard()
    if not top_users:
        await message.reply_text("No players yet!")
        return
    lb_text = "Leaderboard (Top 10 by Wins):\n"
    for i, user in enumerate(top_users, 1):
        lb_text += f"{i}. {user['username']} - Wins: {user['wins']}, Win Rate: {user['win_rate']:.2%}\n"
    await message.reply_text(lb_text)

@app.on_message(filters.command("gostats"))
async def global_stgoats(client, message):
    stats = UserStats().get_global_stats()
    stats_text = (
        f"Global Statistics:\n"
        f"Total Games: {stats['total_games']}\n"
        f"Total Wins (X): {stats['wins_x']}\n"
        f"Total Wins (O): {stats['wins_o']}\n"
        f"Total Draws: {stats['draws']}"
    )
    await message.reply_text(stats_text)

def create_board_buttons(game_id):
    """Create inline buttons for the game board."""
    buttons = []
    for row in range(15):
        row_buttons = []
        for col in range(15):  # Full 15x15, but note Telegram limit ~100 buttons; for production, paginate
            symbol = '❌' if active_games[game_id].board[row][col] == 'X' else '⭕' if active_games[game_id].board[row][col] == 'O' else '⬜'
            row_buttons.append(InlineKeyboardButton(
                symbol, callback_data=f"move_{game_id}_{row}_{col}"
            ))
        buttons.append(row_buttons)
    buttons = buttons[:8]  # Limit to first 8 rows to avoid button limit; add pagination if needed
    buttons.append([InlineKeyboardButton("Show Full Board", callback_data=f"show_{game_id}")])
    buttons.append([InlineKeyboardButton("Resign", callback_data=f"resign_{game_id}")])
    return InlineKeyboardMarkup(buttons)

@app.on_callback_query(filters.regex(r"^move_"))
async def handle_move(client, callback_query: CallbackQuery):
    _, game_id, row, col = callback_query.data.split('_')
    row, col = int(row), int(col)
    game = active_games.get(game_id)
    if not game:
        await callback_query.message.edit_text("Game not found.")
        return
    success, msg = game.make_move(row, col, callback_query.from_user.id)
    if not success:
        await callback_query.answer(msg, show_alert=True)
        return
    if game.status == 'finished':
        await handle_game_end(client, callback_query, game, msg)
    else:
        if game.player_o == 'AI' and game.current_player == 'O':
            await ai_move(client, callback_query, game)
        else:
            await update_board(client, callback_query, game)

async def ai_move(client, callback_query, game):
    # Simple AI: Random move; for advanced, implement heuristic
    empty_cells = [(r, c) for r in range(game.board_size) for c in range(game.board_size) if game.board[r][c] == ' ']
    if empty_cells:
        row, col = random.choice(empty_cells)
        success, msg = game.make_move(row, col, 'AI')
        if success and game.status == 'finished':
            await handle_game_end(client, callback_query, game, msg)
            return
    await update_board(client, callback_query, game)

async def update_board(client, callback_query, game):
    board_msg = f"Current player: {game.current_player}\n{game.get_board_display()}"
    await callback_query.message.edit_text(
        board_msg,
        reply_markup=create_board_buttons(game.game_id)
    )
    opponent = game.player_x if game.current_player == 'O' else game.player_o
    if opponent != 'AI':
        await client.send_message(
            opponent,
            board_msg,
            reply_markup=create_board_buttons(game.game_id)
        )
    await callback_query.answer()

async def handle_game_end(client, callback_query, game, msg):
    board_msg = f"{game.get_board_display()}\n{msg}"
    await callback_query.message.edit_text(board_msg, reply_markup=None)
    opponent = game.player_x if game.player_o == callback_query.from_user.id else game.player_o
    if opponent != 'AI':
        await client.send_message(opponent, board_msg, reply_markup=None)
    # Update stats
    UserStats().update_stats_after_game(game)
    del active_games[game.game_id]

@app.on_callback_query(filters.regex(r"^join_"))
async def handle_join(client, callback_query: CallbackQuery):
    _, game_id = callback_query.data.split('_')
    game = active_games.get(game_id)
    if not game or game.status != 'waiting':
        await callback_query.message.edit_text("Game is no longer available.")
        return
    game.player_o = callback_query.from_user.id
    game.status = 'playing'
    game.save_game()
    board_msg = f"You joined game {game_id} as Player O!\n{game.get_board_display()}"
    await callback_query.message.edit_text(
        board_msg,
        reply_markup=create_board_buttons(game_id)
    )
    await client.send_message(
        game.player_x,
        f"Opponent joined! You are Player X.\n{game.get_board_display()}",
        reply_markup=create_board_buttons(game_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^show_"))
async def show_board(client, callback_query: CallbackQuery):
    _, game_id = callback_query.data.split('_')
    game = active_games.get(game_id)
    if not game:
        await callback_query.message.edit_text("Game not found.")
        return
    await callback_query.message.edit_text(
        f"Current player: {game.current_player}\n{game.get_board_display()}",
        reply_markup=create_board_buttons(game_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^resign_"))
async def resign(client, callback_query: CallbackQuery):
    _, game_id = callback_query.data.split('_')
    game = active_games.get(game_id)
    if not game:
        await callback_query.message.edit_text("Game not found.")
        return
    resigner = callback_query.from_user.id
    if resigner not in (game.player_x, game.player_o):
        await callback_query.answer("You are not a player in this game.", show_alert=True)
        return
    winner = 'O' if resigner == game.player_x else 'X'
    game.status = 'finished'
    game.winner = winner
    game.save_game()
    msg = f"Player {'X' if resigner == game.player_x else 'O'} resigned. Player {winner} wins!"
    await handle_game_end(client, callback_query, game, msg)
    await callback_query.answer()

