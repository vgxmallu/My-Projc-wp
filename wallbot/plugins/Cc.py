from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio
from wallbot import wbot as app

# Game state
games = {}

# Create empty board
def create_board():
    return [' '] * 9

# Render board
def render(board):
    return (f"\n"
            f"{board[0]} | {board[1]} | {board[2]}\n"
            f"--+---+--\n"
            f"{board[3]} | {board[4]} | {board[5]}\n"
            f"--+---+--\n"
            f"{board[6]} | {board[7]} | {board[8]}\n")

# Check win
def check_win(board, symbol):
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    return any(board[a] == board[b] == board[c] == symbol for a, b, c in wins)

# Start command
@app.on_message(filters.command("xoxo"))
async def xoxo(_, message: Message):
    await message.reply("🎮 Welcome to XOXO Game!\nUse /newgame to start a new game.")

# New game
@app.on_message(filters.command("xonewgame"))
async def xnewgame(_, message: Message):
    chat_id = message.chat.id
    games[chat_id] = {
        "board": create_board(),
        "players": [message.from_user.id],
        "symbols": {},
        "turn": 0
    }
    await message.reply("Game created! Another player, type /join to join the game.")

# Join game
@app.on_message(filters.command("xojoin"))
async def xjoin(_, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)

    if not game:
        await message.reply("No game available. Use /newgame to create one.")
        return

    if len(game["players"]) >= 2:
        await message.reply("Game already has two players.")
        return

    game["players"].append(user_id)
    game["symbols"] = {
        game["players"][0]: "❌",
        game["players"][1]: "⭕"
    }
    await message.reply("Game started!\n" + render(game["board"]) + f"\nPlayer 1: ❌\nPlayer 2: ⭕\n\nType /move 1-9 to play.")

# Move command
@app.on_message(filters.command("xomove"))
async def move(_, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)

    if not game or user_id not in game["players"]:
        await message.reply("You're not in a game. Use /newgame or /join.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("Usage: /move 1-9")
        return

    pos = int(args[1]) - 1
    if pos < 0 or pos > 8:
        await message.reply("Position must be between 1 and 9.")
        return

    if game["board"][pos] != ' ':
        await message.reply("This cell is already taken.")
        return

    current_player = game["players"][game["turn"] % 2]
    if user_id != current_player:
        await message.reply("It's not your turn!")
        return

    symbol = game["symbols"][user_id]
    game["board"][pos] = symbol

    if check_win(game["board"], symbol):
        await message.reply(render(game["board"]) + f"\n🎉 Player {symbol} wins!")
        del games[chat_id]
    elif ' ' not in game["board"]:
        await message.reply(render(game["board"]) + "\n🤝 It's a draw!")
        del games[chat_id]
    else:
        game["turn"] += 1
        await message.reply(render(game["board"]) + "\nNext player's turn.")
