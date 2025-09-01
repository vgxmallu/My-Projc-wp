import pymongo
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import uuid
from config import DB_URL
from wallbot import wbot as app


load_dotenv()

# Singleton MongoDB client
_mongo_client = MongoClient(os.getenv('DB_URL'))
_db = _mongo_client['gomoku']

class GomokuGame:
    def __init__(self, board_size=15):
        self.board_size = board_size
        self.board = [[' ' for _ in range(board_size)] for _ in range(board_size)]
        self.current_player = 'X'
        self.game_id = None
        self.chat_id = None
        self.player_x = None
        self.player_o = None
        self.status = 'waiting'  # waiting, playing, finished
        self.winner = None
        self.games = _db['games']

    def save_game(self):
        """Save or update game state in MongoDB."""
        game_data = {
            'game_id': self.game_id,
            'chat_id': self.chat_id,
            'board': self.board,
            'current_player': self.current_player,
            'player_x': self.player_x,
            'player_o': self.player_o,
            'status': self.status,
            'winner': self.winner
        }
        self.games.update_one(
            {'game_id': self.game_id, 'chat_id': self.chat_id},
            {'$set': game_data},
            upsert=True
        )

    def load_game(self, game_id, chat_id):
        """Load game state from MongoDB."""
        game_data = self.games.find_one({'game_id': game_id, 'chat_id': chat_id})
        if game_data:
            self.game_id = game_data['game_id']
            self.chat_id = game_data['chat_id']
            self.board = game_data['board']
            self.current_player = game_data['current_player']
            self.player_x = game_data['player_x']
            self.player_o = game_data['player_o']
            self.status = game_data['status']
            self.winner = game_data['winner']
            return True
        return False

    def make_move(self, row, col, player_id):
        """Make a move on the board."""
        if self.status != 'playing':
            return False, "Game is not in progress."
        if (self.current_player == 'X' and player_id != self.player_x) or \
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

    def check_win(self, row, col):
        """Check if the last move resulted in a win."""
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        symbol = self.board[row][col]
        
        for dr, dc in directions:
            count = 1
            r, c = row + dr, col + dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == symbol:
                count += 1
                r += dr
                c += dc
            r, c = row - dr, col - dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == symbol:
                count += 1
                r -= dr
                c -= dc
            if count >= 5:
                return True
        return False

    def check_draw(self):
        """Check if the game is a draw."""
        return all(self.board[row][col] != ' ' for row in range(self.board_size) for col in range(self.board_size))

    def get_board_display(self):
        """Generate a string representation of the board with emojis."""
        display = []
        for row in range(self.board_size):
            row_display = [f"{row:2} "]
            for col in range(self.board_size):
                if self.board[row][col] == 'X':
                    row_display.append('🔴')
                elif self.board[row][col] == 'O':
                    row_display.append('⚫')
                else:
                    row_display.append('⬜')
            display.append(' '.join(row_display))
        header = '   ' + ' '.join(f"{i:2}" for i in range(self.board_size))
        return '```\n' + header + '\n' + '\n'.join(display) + '\n```'

    def start_game(self, game_id, chat_id, player_x):
        """Start a new game."""
        self.game_id = game_id
        self.chat_id = chat_id
        self.player_x = player_x
        self.status = 'waiting'
        self.save_game()

class UserStats:
    def __init__(self):
        self.users = _db['users']
        self.global_stats = _db['global_stats']
        self.ensure_indexes()

    def ensure_indexes(self):
        self.users.create_index([('user_id', pymongo.ASCENDING), ('chat_id', pymongo.ASCENDING)], unique=True)

    def get_user_stats(self, user_id, chat_id):
        user = self.users.find_one({'user_id': user_id, 'chat_id': chat_id})
        if not user:
            return None
        user['win_rate'] = user['wins'] / user['games_played'] if user['games_played'] > 0 else 0
        return user

    def update_user_stats(self, user_id, chat_id, username, win=0, loss=0, draw=0):
        username = username or f"User{user_id}"  # Fallback if username is None
        self.users.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {
                '$set': {'username': username},
                '$inc': {'wins': win, 'losses': loss, 'draws': draw, 'games_played': 1}
            },
            upsert=True
        )

    def get_leaderboard(self, chat_id):
        return list(self.users.find({'chat_id': chat_id}).sort('wins', -1).limit(10))

    def get_global_stats(self, chat_id):
        stats = self.global_stats.find_one({'chat_id': chat_id}) or {
            'chat_id': chat_id,
            'total_games': 0,
            'wins_x': 0,
            'wins_o': 0,
            'draws': 0
        }
        return stats

    def update_global_stats(self, chat_id, winner):
        inc = {'total_games': 1}
        if winner == 'X':
            inc['wins_x'] = 1
        elif winner == 'O':
            inc['wins_o'] = 1
        elif winner == 'Draw':
            inc['draws'] = 1
        self.global_stats.update_one(
            {'chat_id': chat_id},
            {'$inc': inc},
            upsert=True
        )

    def update_stats_after_game(self, game, username_x, username_o):
        if game.winner == 'Draw':
            self.update_user_stats(game.player_x, game.chat_id, username_x, draw=1)
            self.update_user_stats(game.player_o, game.chat_id, username_o, draw=1)
        else:
            winner_id = game.player_x if game.winner == 'X' else game.player_o
            loser_id = game.player_o if game.winner == 'X' else game.player_x
            winner_username = username_x if game.winner == 'X' else username_o
            loser_username = username_o if game.winner == 'X' else username_x
            self.update_user_stats(winner_id, game.chat_id, winner_username, win=1)
            self.update_user_stats(loser_id, game.chat_id, loser_username, loss=1)
        self.update_global_stats(game.chat_id, game.winner)


# Store active games: {chat_id: {game_id: GomokuGame}}
active_games = {}

def is_player_in_game(chat_id, user_id):
    """Check if a user is already in an active game in the group."""
    if chat_id not in active_games:
        return False
    for game_id, game in active_games[chat_id].items():
        if game.status in ('waiting', 'playing') and user_id in (game.player_x, game.player_o):
            return True
    return False

def create_board_buttons(chat_id, game_id, page=0):
    """Create inline buttons for a paginated section of the board."""
    game = active_games[chat_id][game_id]
    buttons = []
    page_size = 8  # 8x8 section per page
    start_row = page * page_size
    end_row = min(start_row + page_size, game.board_size)
    for row in range(start_row, end_row):
        row_buttons = []
        for col in range(page_size):  # First 8 columns
            symbol = '🔴' if game.board[row][col] == 'X' else '⚫' if game.board[row][col] == 'O' else '⬜'
            row_buttons.append(InlineKeyboardButton(
                symbol, callback_data=f"move_{chat_id}_{game_id}_{row}_{col}"
            ))
        buttons.append(row_buttons)
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{chat_id}_{game_id}_{page-1}"))
    if end_row < game.board_size:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{chat_id}_{game_id}_{page+1}"))
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("Show Full Board", callback_data=f"show_{chat_id}_{game_id}")])
    buttons.append([InlineKeyboardButton("Resign", callback_data=f"resign_{chat_id}_{game_id}")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("gort") & filters.group)
async def starnd(client, message):
    await message.reply_text(
        "Welcome to Gomoku in this group! Commands:\n"
        "/newgame - Start a new PvP game\n"
        "/joingame <game_id> - Join a game\n"
        "/profile - View your profile\n"
        "/leaderboard - View group leaderboard\n"
        "/stats - View group statistics"
    )

@app.on_message(filters.command("gnewgame") & filters.group)
async def newgogame(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if is_player_in_game(chat_id, user_id):
        await message.reply_text("You are already in an active game in this group.")
        return
    if chat_id not in active_games:
        active_games[chat_id] = {}
    
    # Check for existing waiting games in this chat
    for game_id, game in active_games[chat_id].items():
        if game.status == 'waiting':
            await message.reply_text(f"A game is waiting for an opponent. Join it with /joingame {game_id}.")
            return

    game_id = str(uuid.uuid4())
    game = GomokuGame()
    game.start_game(game_id, chat_id, user_id)
    active_games[chat_id][game_id] = game
    buttons = [
        [InlineKeyboardButton("Join Game", callback_data=f"join_{chat_id}_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await message.reply_text(
        f"New Gomoku game created by {message.from_user.first_name}! Game ID: {game_id}\nWaiting for an opponent...",
        reply_markup=reply_markup
    )

@app.on_message(filters.command("joingogame") & filters.group)
async def joingogame(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if is_player_in_game(chat_id, user_id):
        await message.reply_text("You are already in an active game in this group.")
        return
    try:
        _, game_id = message.text.split()
        if chat_id not in active_games or game_id not in active_games[chat_id]:
            await message.reply_text("Game ID not found in this group.")
            return
        game = active_games[chat_id][game_id]
        if game.status != 'waiting':
            await message.reply_text("Game has already started or is finished.")
            return
        if user_id == game.player_x:
            await message.reply_text("You cannot join your own game.")
            return
        game.player_o = user_id
        game.status = 'playing'
        game.save_game()
        await message.reply_text(
            f"{message.from_user.first_name} joined game {game_id} as Player O!\n{game.get_board_display()}",
            reply_markup=create_board_buttons(chat_id, game_id)
        )
    except ValueError:
        await message.reply_text("Please provide a valid game ID: /joingame <game_id>")

@app.on_message(filters.command("goprofile") & filters.group)
async def profgogoile(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    stats = UserStats().get_user_stats(user_id, chat_id)
    if not stats:
        await message.reply_text("No profile found in this group. Play some games to create one!")
        return
    profile_text = (
        f"Profile for {message.from_user.first_name} in this group:\n"
        f"Games Played: {stats['games_played']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Draws: {stats['draws']}\n"
        f"Win Rate: {stats['win_rate']:.2%}"
    )
    await message.reply_text(profile_text)

@app.on_message(filters.command("goleaderboard") & filters.group)
async def leadegogggrboard(client, message):
    chat_id = message.chat.id
    top_users = UserStats().get_leaderboard(chat_id)
    if not top_users:
        await message.reply_text("No players in this group yet!")
        return
    lb_text = "Leaderboard (Top 10 by Wins in this group):\n"
    for i, user in enumerate(top_users, 1):
        lb_text += f"{i}. {user['username']} - Wins: {user['wins']}, Win Rate: {user['win_rate']}\n"
    await message.reply_text(lb_text)

@app.on_message(filters.command("sgots") & filters.group)
async def global_stats(client, message):
    chat_id = message.chat.id
    stats = UserStats().get_global_stats(chat_id)
    stats_text = (
        f"Group Statistics:\n"
        f"Total Games: {stats['total_games']}\n"
        f"Total Wins (X): {stats['wins_x']}\n"
        f"Total Wins (O): {stats['wins_o']}\n"
        f"Total Draws: {stats['draws']}"
    )
    await message.reply_text(stats_text)

@app.on_callback_query(filters.regex(r"^move_"))
async def handle_move(client, callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    if len(parts) != 5:
        await callback_query.answer("Invalid move data.", show_alert=True)
        return
    _, chat_id, game_id, row, col = parts
    chat_id = int(chat_id)
    row, col = int(row), int(col)
    if chat_id not in active_games or game_id not in active_games[chat_id]:
        await callback_query.message.edit_text("Game not found.")
        return
    game = active_games[chat_id][game_id]
    success, msg = game.make_move(row, col, callback_query.from_user.id)
    if not success:
        await callback_query.answer(msg, show_alert=True)
        return
    if game.status == 'finished':
        await handle_game_end(client, callback_query, game, msg)
    else:
        await update_board(client, callback_query, game)

async def update_board(client, callback_query, game):
    board_msg = f"Current player: {game.current_player}\n{game.get_board_display()}"
    await callback_query.message.edit_text(
        board_msg,
        reply_markup=create_board_buttons(game.chat_id, game.game_id)
    )
    await callback_query.answer()

async def handle_game_end(client, callback_query, game, msg):
    username_x = (await client.get_users(game.player_x)).first_name or f"User{game.player_x}"
    username_o = (await client.get_users(game.player_o)).first_name or f"User{game.player_o}"
    board_msg = f"{game.get_board_display()}\n{msg}"
    await callback_query.message.edit_text(board_msg, reply_markup=None)
    UserStats().update_stats_after_game(game, username_x, username_o)
    del active_games[game.chat_id][game.game_id]
    if not active_games[game.chat_id]:
        del active_games[game.chat_id]
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^join_"))
async def handle_join(client, callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    if len(parts) != 3:
        await callback_query.answer("Invalid join data.", show_alert=True)
        return
    _, chat_id, game_id = parts
    chat_id = int(chat_id)
    user_id = callback_query.from_user.id
    if is_player_in_game(chat_id, user_id):
        await callback_query.answer("You are already in an active game in this group.", show_alert=True)
        return
    if chat_id not in active_games or game_id not in active_games[chat_id]:
        await callback_query.message.edit_text("Game is no longer available.")
        return
    game = active_games[chat_id][game_id]
    if game.status != 'waiting':
        await callback_query.message.edit_text("Game has already started.")
        return
    if user_id == game.player_x:
        await callback_query.answer("You cannot join your own game.", show_alert=True)
        return
    game.player_o = user_id
    game.status = 'playing'
    game.save_game()
    board_msg = f"{callback_query.from_user.first_name} joined game {game_id} as Player O!\n{game.get_board_display()}"
    await callback_query.message.edit_text(
        board_msg,
        reply_markup=create_board_buttons(chat_id, game_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^page_"))
async def handle_page(client, callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    if len(parts) != 4:
        await callback_query.answer("Invalid page data.", show_alert=True)
        return
    _, chat_id, game_id, page = parts
    chat_id = int(chat_id)
    page = int(page)
    if chat_id not in active_games or game_id not in active_games[chat_id]:
        await callback_query.message.edit_text("Game not found.")
        return
    game = active_games[chat_id][game_id]
    await callback_query.message.edit_text(
        f"Current player: {game.current_player}\n{game.get_board_display()}",
        reply_markup=create_board_buttons(chat_id, game_id, page)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^show_"))
async def show_board(client, callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    if len(parts) != 3:
        await callback_query.answer("Invalid show data.", show_alert=True)
        return
    _, chat_id, game_id = parts
    chat_id = int(chat_id)
    if chat_id not in active_games or game_id not in active_games[chat_id]:
        await callback_query.message.edit_text("Game not found.")
        return
    game = active_games[chat_id][game_id]
    await callback_query.message.edit_text(
        f"Current player: {game.current_player}\n{game.get_board_display()}",
        reply_markup=create_board_buttons(chat_id, game_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^resign_"))
async def resign(client, callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    if len(parts) != 3:
        await callback_query.answer("Invalid resign data.", show_alert=True)
        return
    _, chat_id, game_id = parts
    chat_id = int(chat_id)
    if chat_id not in active_games or game_id not in active_games[chat_id]:
        await callback_query.message.edit_text("Game not found.")
        return
    game = active_games[chat_id][game_id]
    resigner = callback_query.from_user.id
    if resigner not in (game.player_x, game.player_o):
        await callback_query.answer("You are not a player in this game.", show_alert=True)
        return
    winner = 'O' if resigner == game.player_x else 'X'
    game.status = 'finished'
    game.winner = winner
    game.save_game()
    username_x = (await client.get_users(game.player_x)).first_name or f"User{game.player_x}"
    username_o = (await client.get_users(game.player_o)).first_name or f"User{game.player_o}"
    msg = f"Player {'X' if resigner == game.player_x else 'O'} ({callback_query.from_user.first_name}) resigned. Player {winner} wins!"
    await handle_game_end(client, callback_query, game, msg)
    await callback_query.answer()

