import os
import random
import logging
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import DB_URL
from wallbot import wbot as app


mongo_client = MongoClient(DB_URL)
db = mongo_client.RPSBot
users_collection = db.users


# --- Game Logic & Constants ---
CHOICES = ["rock", "paper", "scissors"]
EMOJI = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
WINNING_COMBINATIONS = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper"
}

# --- Helper Functions ---
async def get_or_create_user(user_id: int, first_name: str, username: str):
    """
    Retrieves a user from the database or creates a new entry if they don't exist.
    """
    user = users_collection.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "first_name": first_name,
            "username": username,
            "wins": 0,
            "losses": 0,
            "ties": 0
        }
        users_collection.insert_one(user)
    return user

def update_stats(user_id: int, result: str):
    """
    Updates the win/loss/tie statistics for a user.
    """
    if result == "win":
        users_collection.update_one({"_id": user_id}, {"$inc": {"wins": 1}})
    elif result == "loss":
        users_collection.update_one({"_id": user_id}, {"$inc": {"losses": 1}})
    elif result == "tie":
        users_collection.update_one({"_id": user_id}, {"$inc": {"ties": 1}})

def determine_winner(player1_choice: str, player2_choice: str):
    """
    Determines the winner of the game.
    Returns: "player1", "player2", or "tie".
    """
    if player1_choice == player2_choice:
        return "tie"
    if WINNING_COMBINATIONS[player1_choice] == player2_choice:
        return "player1"
    return "player2"

# --- Bot Command Handlers ---

@app.on_message(filters.command("rpsstart") & filters.private)
async def starthh_command_private(_, message: Message):
    """Handles the /start command in private chat."""
    await get_or_create_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    start_text = (
        "**Welcome to the Advanced Rock, Paper, Scissors Bot!**\n\n"
        "You can play against me or challenge members in a group.\n\n"
        "**How to play:**\n"
        "1. Add me to your group.\n"
        "2. Use the `/rps` command to start a new game.\n"
        "3. Other members can join, or you can play against the bot directly.\n\n"
        "**Available Commands:**\n"
        "- `/rps` - Start a game in a group.\n"
        "- `/profile` - View your game statistics.\n"
        "- `/leaderboard` - See the top players."
    )
    await message.reply_text(start_text)

@app.on_message(filters.command("rps"))
async def rps_command(_, message: Message):
    """Handles the /rps command to start a game."""
    if message.chat.type == "private":
        await message.reply_text("This command is for groups! Add me to a group and try again.")
        return

    player1 = message.from_user
    await get_or_create_user(player1.id, player1.first_name, player1.username)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Game 🤝", callback_data=f"rps_join_{player1.id}")],
        [InlineKeyboardButton("Play with Bot 🤖", callback_data=f"rps_bot_{player1.id}")]
    ])
    await message.reply_text(
        f"**Rock, Paper, Scissors!**\n\n{player1.mention} has started a game. Who wants to challenge?",
        reply_markup=keyboard
    )

@app.on_message(filters.command("rpsprofile"))
async def profhdile_command(_, message: Message):
    """Handles the /profile command to show user stats."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    user_data = await get_or_create_user(user_id, first_name, username)

    total_games = user_data['wins'] + user_data['losses'] + user_data['ties']
    win_rate = (user_data['wins'] / total_games * 100) if total_games > 0 else 0

    # Find user's rank
    pipeline = [
        {"$sort": {"wins": -1}},
        {"$group": {"_id": None, "users": {"$push": "$_id"}}},
        {"$unwind": {"path": "$users", "includeArrayIndex": "rank"}},
        {"$match": {"users": user_id}}
    ]
    rank_cursor = users_collection.aggregate(pipeline)
    rank_info = next(rank_cursor, None)
    rank = rank_info['rank'] + 1 if rank_info else "N/A"


    profile_text = (
        f"**📊 Player Profile: {first_name}**\n\n"
        f"🏆 **Rank:** {rank}\n"
        f"✅ **Wins:** {user_data['wins']}\n"
        f"❌ **Losses:** {user_data['losses']}\n"
        f"🤝 **Ties:** {user_data['ties']}\n"
        f"🎮 **Total Games:** {total_games}\n"
        f"📈 **Win Rate:** {win_rate:.2f}%"
    )
    await message.reply_text(profile_text)

@app.on_message(filters.command("rpsleaderboard"))
async def leaderjdjfboard_command(_, message: Message):
    """Handles the /leaderboard command to show top players."""
    leaderboard = users_collection.find().sort("wins", -1).limit(10)
    
    text = "**🏆 Leaderboard - Top 10 Players 🏆**\n\n"
    rank = 1
    for user in leaderboard:
        try:
            # Fetch user to ensure the name is up-to-date
            user_info = await app.get_users(user['_id'])
            name = user_info.first_name
        except Exception:
            name = user.get('first_name', 'Unknown User')

        text += f"**{rank}.** {name} - **{user['wins']}** Wins\n"
        rank += 1
    
    if rank == 1:
        text += "No games have been played yet. Be the first!"
        
    await message.reply_text(text)


# --- Callback Query Handler ---

@app.on_callback_query(filters.regex("^rps_"))
async def rps_callback_handler(_, query):
    """Handles all callback queries related to the RPS game."""
    data = query.data.split("_")
    action = data[1]

    original_player_id = int(data[2])
    user = query.from_user

    # --- Game Join Logic ---
    if action == "join":
        player2 = user
        await get_or_create_user(player2.id, player2.first_name, player2.username)

        # Create the keyboard for players to make their choice
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{EMOJI['rock']} Rock", callback_data=f"rps_choice_rock_{original_player_id}_{player2.id}"),
                InlineKeyboardButton(f"{EMOJI['paper']} Paper", callback_data=f"rps_choice_paper_{original_player_id}_{player2.id}"),
                InlineKeyboardButton(f"{EMOJI['scissors']} Scissors", callback_data=f"rps_choice_scissors_{original_player_id}_{player2.id}")
            ]
        ])
        
        original_player = await app.get_users(original_player_id)
        
        await query.message.edit_text(
            f"**Game Started!**\n\n"
            f"Player 1: {original_player.mention}\n"
            f"Player 2: {player2.mention}\n\n"
            "Make your move!",
            reply_markup=keyboard
        )
        return

    # --- Play with Bot Logic ---
    if action == "bot":
        if user.id != original_player_id:
            await query.answer("This is not your game to control!", show_alert=True)
            return
        
        player1 = user
        bot_choice = random.choice(CHOICES)
        
        # Create keyboard for the player vs bot
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{EMOJI['rock']} Rock", callback_data=f"rps_botplay_rock_{player1.id}_{bot_choice}"),
                InlineKeyboardButton(f"{EMOJI['paper']} Paper", callback_data=f"rps_botplay_paper_{player1.id}_{bot_choice}"),
                InlineKeyboardButton(f"{EMOJI['scissors']} Scissors", callback_data=f"rps_botplay_scissors_{player1.id}_{bot_choice}")
            ]
        ])
        
        await query.message.edit_text(
            f"**You are playing against the Bot!**\n\n"
            f"Player: {player1.mention}\n"
            "Opponent: 🤖 Bot\n\n"
            "Choose your weapon!",
            reply_markup=keyboard
        )
        return

    # --- Bot Game Result Logic ---
    if action == "botplay":
        player1_choice = data[2]
        player1_id = int(data[3])
        bot_choice = data[4]

        if user.id != player1_id:
            await query.answer("It's not your turn!", show_alert=True)
            return
            
        player1 = user
        winner = determine_winner(player1_choice, bot_choice)

        result_text = f"**Game Over!**\n\n" \
                      f"{player1.mention} chose: {EMOJI[player1_choice]}\n" \
                      f"🤖 Bot chose: {EMOJI[bot_choice]}\n\n"

        if winner == "player1":
            result_text += f"🎉 **{player1.mention} wins!**"
            update_stats(player1_id, "win")
        elif winner == "player2": # In this case, player2 is the bot
            result_text += f"😞 **The Bot wins!**"
            update_stats(player1_id, "loss")
        else:
            result_text += f"🤝 **It's a tie!**"
            update_stats(player1_id, "tie")
            
        await query.message.edit_text(result_text)

    # --- Player vs Player Choice Logic ---
    if action == "choice":
        player1_id = int(data[3])
        player2_id = int(data[4])

        if user.id not in [player1_id, player2_id]:
            await query.answer("This is not your game!", show_alert=True)
            return

        # Simple in-memory storage for choices for this message.
        # A more robust solution for very high traffic might use the DB.
        if not hasattr(query.message, 'game_choices'):
            query.message.game_choices = {}

        player_key = "player1" if user.id == player1_id else "player2"
        
        if player_key in query.message.game_choices:
            await query.answer("You have already made your choice!", show_alert=True)
            return

        query.message.game_choices[player_key] = {"id": user.id, "choice": data[2]}
        await query.answer(f"You chose {data[2]}!")

        # Check if both players have made their choice
        if 'player1' in query.message.game_choices and 'player2' in query.message.game_choices:
            p1_data = query.message.game_choices['player1']
            p2_data = query.message.game_choices['player2']

            p1 = await app.get_users(p1_data['id'])
            p2 = await app.get_users(p2_data['id'])
            
            winner = determine_winner(p1_data['choice'], p2_data['choice'])
            
            result_text = f"**Game Over!**\n\n" \
                          f"{p1.mention} chose: {EMOJI[p1_data['choice']]}\n" \
                          f"{p2.mention} chose: {EMOJI[p2_data['choice']]}\n\n"

            if winner == "player1":
                result_text += f"🎉 **{p1.mention} wins!**"
                update_stats(p1.id, "win")
                update_stats(p2.id, "loss")
            elif winner == "player2":
                result_text += f"🎉 **{p2.mention} wins!**"
                update_stats(p2.id, "win")
                update_stats(p1.id, "loss")
            else:
                result_text += f"🤝 **It's a tie!**"
                update_stats(p1.id, "tie")
                update_stats(p2.id, "tie")
            
            await query.message.edit_text(result_text)
        else:
            # Update the message to show who is waiting
            waiting_on = "Player 1" if 'player2' in query.message.game_choices else "Player 2"
            p1 = await app.get_users(player1_id)
            p2 = await app.get_users(player2_id)
            await query.message.edit_text(
                f"**Game in progress...**\n\n"
                f"Player 1: {p1.mention}\n"
                f"Player 2: {p2.mention}\n\n"
                f"Waiting for {waiting_on} to make a move..."
            )
