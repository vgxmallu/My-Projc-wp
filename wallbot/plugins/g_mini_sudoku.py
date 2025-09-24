import asyncio
import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app


mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["sudoku_db"]
users_col = db["users"]

# Store active games
active_games = {}  # {chat_id: {"board": list, "solution": list, "msg_id": int, "scores": dict, "running": bool}}


# ================= FUNCTIONS =================
def generate_sudoku():
    """Generate a 3x3 sudoku puzzle"""
    nums = [1, 2, 3]
    random.shuffle(nums)
    solution = [
        nums,
        nums[1:] + nums[:1],
        nums[2:] + nums[:2],
    ]
    # Copy puzzle with blanks
    puzzle = [row.copy() for row in solution]
    blanks = random.sample(range(9), k=4)  # 4 blanks
    for i in blanks:
        puzzle[i // 3][i % 3] = 0
    return puzzle, solution


def render_board(board):
    """Convert board to InlineKeyboardMarkup"""
    keyboard = []
    for i, row in enumerate(board):
        btns = []
        for j, val in enumerate(row):
            if val == 0:
                btns.append(InlineKeyboardButton("⬜", callback_data=f"move_{i}_{j}"))
            else:
                btns.append(InlineKeyboardButton(str(val), callback_data="noop"))
        keyboard.append(btns)
    return InlineKeyboardMarkup(keyboard)


async def update_user(user_id, name, score):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({"user_id": user_id, "name": name, "score": score})
    else:
        await users_col.update_one(
            {"user_id": user_id}, {"$inc": {"score": score}, "$set": {"name": name}}
        )


async def get_leaderboard():
    cursor = users_col.find().sort("score", -1).limit(10)
    top = await cursor.to_list(length=10)
    text = "🏆 **Global Sudoku Leaderboard** 🏆\n\n"
    for i, user in enumerate(top, 1):
        text += f"{i}. {user['name']} → {user['score']} pts\n"
    return text


# ================= HANDLERS =================
@app.on_message(filters.command("mini_sudoku") & filters.group)
async def start_jdsudoku(_, message):
    chat_id = message.chat.id
    if chat_id in active_games and active_games[chat_id]["running"]:
        return await message.reply_text("⚠️ A Sudoku game is already running here!")

    puzzle, solution = generate_sudoku()

    sent = await message.reply_text(
        "🧩 **Mini Sudoku (3×3)**\nFill the blanks by tapping tiles!",
        reply_markup=render_board(puzzle),
    )

    active_games[chat_id] = {
        "board": puzzle,
        "solution": solution,
        "msg_id": sent.id,
        "scores": {},
        "running": True,
    }


@app.on_callback_query(filters.regex(r"^move_(\d+)_(\d+)$"))
async def handle_move(_, query):
    chat_id = query.message.chat.id
    user = query.from_user
    i, j = map(int, query.data.split("_")[1:])

    session = active_games.get(chat_id)
    if not session or not session["running"]:
        return await query.answer("⚠️ No active game!", show_alert=True)

    # Only blank cells can be filled
    if session["board"][i][j] != 0:
        return await query.answer("❌ Already filled!", show_alert=True)

    # Show number options
    nums = [
        InlineKeyboardButton(str(n), callback_data=f"fill_{i}_{j}_{n}")
        for n in [1, 2, 3]
    ]
    await query.message.reply_text(
        f"🔢 {user.first_name}, choose number for ({i+1},{j+1}):",
        reply_markup=InlineKeyboardMarkup([nums]),
    )
    await query.answer()


@app.on_callback_query(filters.regex(r"^fill_(\d+)_(\d+)_(\d+)$"))
async def handle_fill(_, query):
    chat_id = query.message.chat.id
    user = query.from_user
    i, j, n = map(int, query.data.split("_")[1:])

    session = active_games.get(chat_id)
    if not session or not session["running"]:
        return await query.answer("⚠️ No active game!", show_alert=True)

    # Correct?
    if session["solution"][i][j] == n:
        session["board"][i][j] = n
        session["scores"][user.id] = session["scores"].get(user.id, 0) + 1
        await query.answer("✅ Correct!")
    else:
        session["scores"][user.id] = session["scores"].get(user.id, 0) - 1
        await query.answer("❌ Wrong!", show_alert=True)

    # Update board
    await query.message.edit_text(
        "🧩 **Mini Sudoku (3×3)**",
        reply_markup=render_board(session["board"]),
    )

    # Check if game complete
    if all(all(val != 0 for val in row) for row in session["board"]):
        session["running"] = False
        # Save scores
        for uid, pts in session["scores"].items():
            user_obj = await app.get_users(uid)
            await update_user(uid, user_obj.first_name, pts)

        leaderboard = await get_leaderboard()
        winner_id, max_pts = max(session["scores"].items(), key=lambda x: x[1])
        winner = (await app.get_users(winner_id)).first_name

        await app.send_message(
            chat_id,
            f"🏁 **Sudoku Finished!**\n👑 Winner: {winner} ({max_pts} pts)\n\n{leaderboard}",
        )


@app.on_message(filters.command("leaderboard"))
async def leaderboard(_, message):
    text = await get_leaderboard()
    await message.reply_text(text)
