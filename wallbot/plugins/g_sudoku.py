import os
import random
import asyncio
from datetime import datetime

from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import motor.motor_asyncio
from config import DB_URL
from wallbot import wbot as app

DB_NAME = os.getenv("DB_NAME", "sudoku_db")

mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]
games_col = db["games"]

# ---------------- HELPERS ----------------
async def ensure_user(user) -> dict:
    """Ensure player exists in DB."""
    doc = await users_col.find_one({"user_id": user.id})
    if not doc:
        doc = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "games_played": 0,
            "games_won": 0,
            "best_time": None,
            "created_at": datetime.utcnow(),
        }
        await users_col.insert_one(doc)
    return doc

def make_sudoku():
    """Generate a random Sudoku puzzle (basic, 9x9)."""
    # Pre-filled puzzle templates (for simplicity). Replace with real generator for production
    puzzles = [
        "53..7....6..195....98....6.8...6...34..8..6..6...2...6..6....28....419..5....8..79",
        "6..8..2..3.9..1....2..3..89..7...4..1..6..9..4...3..6..83..2....4..6.1..9..5..3..",
    ]
    puzzle = random.choice(puzzles)
    solution = puzzle.replace(".", "1")  # dummy solution, replace with solver
    return puzzle, solution

def board_to_markup(puzzle: str):
    """Convert Sudoku string to inline keyboard UI."""
    buttons = []
    for r in range(9):
        row = []
        for c in range(9):
            cell = puzzle[r*9 + c]
            text = cell if cell != "." else "⬜"
            row.append(InlineKeyboardButton(text, callback_data=f"cell_{r}_{c}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✅ Submit", callback_data="submit")])
    return InlineKeyboardMarkup(buttons)

async def start_game(user_id: int):
    puzzle, solution = make_sudoku()
    game = {
        "user_id": user_id,
        "puzzle": puzzle,
        "solution": solution,
        "start_time": datetime.utcnow(),
        "moves": [],
    }
    await games_col.update_one({"user_id": user_id}, {"$set": game}, upsert=True)
    return puzzle


@app.on_message(filters.command("sudoplay"))
async def sufhplay(_, m: Message):
    await ensure_user(m.from_user)
    puzzle = await start_game(m.from_user.id)
    await m.reply("🎮 Your Sudoku Puzzle:", reply_markup=board_to_markup(puzzle))

@app.on_message(filters.command("suprofile"))
async def psyrofile(_, m: Message):
    u = await ensure_user(m.from_user)
    text = (
        f"👤 {u['username']}\n"
        f"Games Played: {u['games_played']}\n"
        f"Games Won: {u['games_won']}\n"
        f"Best Time: {u['best_time'] if u['best_time'] else 'N/A'}"
    )
    await m.reply(text)

@app.on_message(filters.command("sutop"))
async def tsuop(_, m: Message):
    cursor = users_col.find().sort("games_won", -1).limit(10)
    text = "🏆 Top Sudoku Players:\n"
    i = 1
    async for u in cursor:
        text += f"{i}. {u['username']} — Wins {u['games_won']}\n"
        i += 1
    await m.reply(text)

# ---------------- CALLBACK HANDLERS ----------------
@app.on_callback_query(filters.regex(r"^cell_"))
async def select_cell(_, cq: CallbackQuery):
    r, c = map(int, cq.data.split("_")[1:])
    await cq.message.reply(f"📍 You clicked cell ({r+1},{c+1}). Feature coming soon.")
    await cq.answer()

@app.on_callback_query(filters.regex("^submit$"))
async def subhmit(_, cq: CallbackQuery):
    game = await games_col.find_one({"user_id": cq.from_user.id})
    if not game:
        return await cq.answer("No game in progress.", show_alert=True)

    # Validate puzzle
    solved = game["puzzle"].replace(".", "1") == game["solution"]  # dummy check
    await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {"games_played": 1}})
    if solved:
        await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {"games_won": 1}})
        await cq.message.reply("🎉 Congrats! You solved the Sudoku!")
    else:
        await cq.message.reply("❌ Incorrect solution. Try again!")

    await games_col.delete_one({"user_id": cq.from_user.id})
    await cq.answer()

