import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app

mongo = MongoClient(DB_URL)
db = mongo["tictactoe_bot"]
games = db["games"]
stats = db["stats"]



# ─────────────────────────────────────
# GAME HELPERS
# ─────────────────────────────────────
def empty_board():
    return [" "] * 9


def check_winner(board):
    wins = [(0,1,2), (3,4,5), (6,7,8),
            (0,3,6), (1,4,7), (2,5,8),
            (0,4,8), (2,4,6)]
    for a,b,c in wins:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a]
    if " " not in board:
        return "Draw"
    return None


def render_board(board):
    buttons = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            symbol = board[i+j]
            text = symbol if symbol != " " else "⬜"
            row.append(InlineKeyboardButton(text, callback_data=f"move_{i+j}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def ai_move(board, level):
    empty = [i for i, x in enumerate(board) if x == " "]
    if level == "easy":
        return random.choice(empty)
    elif level == "medium":
        # Try to win or block
        for i in empty:
            board[i] = "⭕"
            if check_winner(board) == "O":
                board[i] = " "
                return i
            board[i] = " "
        for i in empty:
            board[i] = "❌"
            if check_winner(board) == "X":
                board[i] = " "
                return i
            board[i] = " "
        return random.choice(empty)
    elif level == "hard":
        # Minimax algorithm (simplified)
        def minimax(is_max):
            winner = check_winner(board)
            if winner == "⭕": return 1
            if winner == "❌": return -1
            if winner == "Draw": return 0

            if is_max:
                best = -10
                for i in empty:
                    if board[i] == " ":
                        board[i] = "⭕"
                        score = minimax(False)
                        board[i] = " "
                        best = max(best, score)
                return best
            else:
                best = 10
                for i in empty:
                    if board[i] == " ":
                        board[i] = "❌"
                        score = minimax(True)
                        board[i] = " "
                        best = min(best, score)
                return best

        best_score, move = -10, None
        for i in empty:
            board[i] = "⭕"
            score = minimax(False)
            board[i] = " "
            if score > best_score:
                best_score = score
                move = i
        return move


def update_stats(user_id, result):
    stats.update_one(
        {"user_id": user_id},
        {"$inc": {result: 1}},
        upsert=True
    )


def leaderboard_text():
    top = stats.find().sort([("wins", -1)]).limit(10)
    text = "🏆 **Leaderboard** 🏆\n\n"
    for i, u in enumerate(top, 1):
        wins = u.get("wins", 0)
        losses = u.get("losses", 0)
        draws = u.get("draws", 0)
        text += f"{i}. {u['first_name']} - `{u['user_id']}` → ✅ {wins} | ❌ {losses} | 🤝 {draws}\n"
    return text


# ─────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────
@app.on_message(filters.command("xoxo"))
async def staxoxoxrt(_, msg: Message):
    await msg.reply("🎮 Welcome to Tic Tac Toe Bot!\n\n"
                    "Commands:\n"
                    "`/pvp_xoxo @username` → Challenge someone\n"
                    "`/pve_xoxo easy|medium|hard` → Play vs Bot\n"
                    "`/xoleaderboard` → Show top players")


@app.on_message(filters.command("pvp_xoxo"))
async def pvp(_, msg: Message):
    if not msg.reply_to_message and len(msg.command) < 2:
        return await msg.reply("Reply to someone or use `/pvp @username`")
    if msg.reply_to_message:
        opponent = msg.reply_to_message.from_user.id
    else:
        try:
            opponent = (await app.get_users(msg.command[1])).id
        except:
            return await msg.reply("Invalid user!")
    challenger = msg.from_user.id

    board = empty_board()
    game_id = f"pvp_{challenger}_{opponent}"
    games.update_one({"_id": game_id}, {"$set": {"board": board, "turn": challenger, "mode": "pvp"}}, upsert=True)

    await msg.reply(f"🎮❌⭕❌⭕ PvP Tic Tac Toe Game is Started!\n\n{msg.from_user.mention} vs <a href='tg://user?id={opponent}'>Opponent</a>",
                    reply_markup=render_board(board))


@app.on_message(filters.command("pve_xoxo"))
async def pve(_, msg: Message):
    if len(msg.command) < 2:
        return await msg.reply("Now play with me not users. \nUsage: `/pve_xoxo easy|medium|hard`")
    level = msg.command[1].lower()
    if level not in ["easy", "medium", "hard"]:
        return await msg.reply("Choose: easy / medium / hard")

    user = msg.from_user.id
    board = empty_board()
    game_id = f"pve_{user}"
    games.update_one({"_id": game_id}, {"$set": {"board": board, "turn": user, "mode": "pve", "level": level}}, upsert=True)

    await msg.reply(f"🎮 ❌⭕❌⭕ Tic Tac Toe PvE Game Started!\nDifficulty: **{level.title()}**",
                    reply_markup=render_board(board))


@app.on_message(filters.command("xoleaderboard"))
async def lshb(_, msg: Message):
    await msg.reply(leaderboard_text())


# ─────────────────────────────────────
# GAME MOVES
# ─────────────────────────────────────
@app.on_callback_query(filters.regex("move_"))
async def moves(_, cq: CallbackQuery):
    move = int(cq.data.split("_")[1])
    game = games.find_one({"_id": {"$regex": f"{cq.from_user.id}"}})
    if not game:
        return await cq.answer("No active game!", show_alert=True)

    board = game["board"]
    if board[move] != " ":
        return await cq.answer("Invalid move!", show_alert=True)

    mode = game["mode"]
    turn = game["turn"]

    if mode == "pvp":
        challenger, opponent = map(int, game["_id"].split("_")[1:])
        if cq.from_user.id != turn:
            return await cq.answer("Not your turn!", show_alert=True)

        board[move] = "X" if turn == challenger else "O"
        winner = check_winner(board)

        if winner:
            if winner == "Draw":
                update_stats(challenger, "draws")
                update_stats(opponent, "draws")
                text = "🤝 It's a draw!"
            else:
                win_id = challenger if winner == "X" else opponent
                lose_id = opponent if win_id == challenger else challenger
                update_stats(win_id, "wins")
                update_stats(lose_id, "losses")
                text = f"🏆 <a href='tg://user?id={win_id}'>Winner!</a>"

            games.delete_one({"_id": game["_id"]})
            return await cq.message.edit(text, reply_markup=render_board(board))

        next_turn = opponent if turn == challenger else challenger
        games.update_one({"_id": game["_id"]}, {"$set": {"board": board, "turn": next_turn}})
        await cq.message.edit(f"🎮❌⭕❌⭕ PvP Game\nNext turn: <a href='tg://user?id={next_turn}'>Player</a>",
                              reply_markup=render_board(board))

    elif mode == "pve":
        if cq.from_user.id != turn:
            return await cq.answer("Not your turn!", show_alert=True)

        board[move] = "❌"
        winner = check_winner(board)
        if winner:
            if winner == "Draw":
                update_stats(cq.from_user.id, "draws")
                text = "🤝 It's a draw!"
            elif winner == "❌":
                update_stats(cq.from_user.id, "wins")
                text = "🏆 You won!"
            else:
                update_stats(cq.from_user.id, "losses")
                text = "😢 You lost! Try next time ;)"
            games.delete_one({"_id": game["_id"]})
            return await cq.message.edit(text, reply_markup=render_board(board))

        # Bot move
        level = game["level"]
        bot_move = ai_move(board, level)
        board[bot_move] = "⭕"
        winner = check_winner(board)

        if winner:
            if winner == "Draw":
                update_stats(cq.from_user.id, "draws")
                text = "🤝 It's a draw!"
            elif winner == "❌":
                update_stats(cq.from_user.id, "wins")
                text = "🏆 You won!"
            else:
                update_stats(cq.from_user.id, "losses")
                text = "😢 You lost! try next time ;)"
            games.delete_one({"_id": game["_id"]})
            return await cq.message.edit(text, reply_markup=render_board(board))

        games.update_one({"_id": game["_id"]}, {"$set": {"board": board}})
        await cq.message.edit("🎮❌⭕❌⭕ PvE Game\nYour turn!", reply_markup=render_board(board))


