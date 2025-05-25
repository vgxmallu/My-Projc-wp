import random
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from wallbot import wbot as word

from wallbot import WORD_SET, MEAN_WORD_SET
from wallbot.database.db import update_stats, get_stats


active_host_games = {}

@word.on_message(filters.command("host") & filters.group)
async def host_game(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id in active_host_games:
        await message.reply("🚨 A host game is already active in this chat!")
        return
    
    current_word = random.choice(list(MEAN_WORD_SET)).capitalize()
    
    active_host_games[chat_id] = {
        "host_id": user_id,
        "current_word": current_word,
        "message_id": None,
        "message": None
    }
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👀 See Word", callback_data="host_see_word")],
        [InlineKeyboardButton("🔄 Next Word", callback_data="host_next_word")]
    ])
    
    host_msg = await message.reply(
        f"🎮 {message.from_user.mention} is hosting a word guess game!\n"
        "Simply type the word you think it is in chat!",
        reply_markup=buttons
    )
    
    active_host_games[chat_id]["message_id"] = host_msg.id
    active_host_games[chat_id]["message"] = host_msg

@word.on_callback_query(filters.regex("^host_"))
async def host_callback_handler(client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    
    if chat_id not in active_host_games:
        await callback_query.answer("Game has ended!", show_alert=True)
        return
    
    game = active_host_games[chat_id]
    
    if user_id != game["host_id"]:
        await callback_query.answer("Only the host can use these buttons!", show_alert=True)
        return
    
    if callback_query.data == "host_see_word":
        await callback_query.answer(f"The word is: {game['current_word']}", show_alert=True)
    elif callback_query.data == "host_next_word":
        new_word = random.choice(list(MEAN_WORD_SET)).capitalize()
        game["current_word"] = new_word
        await callback_query.answer(f"Changed word to: {new_word}", show_alert=True)

@word.on_message(filters.group & filters.text, group=-1)
async def handle_guess(client, message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_host_games:
        return
    
    game = active_host_games[chat_id]
    guesser_id = message.from_user.id
    
    
    if guesser_id == game["host_id"]:
        return
    
    guessed_word = message.text.strip().lower()
    current_word = game["current_word"].lower()
    
    if guessed_word == current_word:
        winner_mention = message.from_user.mention
        host_mention = (await client.get_users(game["host_id"])).mention
        
        
        await game["message"].edit_reply_markup(reply_markup=None)
        
        await message.reply(
            f"🎉 {winner_mention} guessed the word correctly!\n"
            f"🏆 The word was: {game['current_word']}\n"
            f"Hosted by: {host_mention}\n"
            f"Use /host to start a new game!"
        )
        
        await update_stats(message.from_user.id, "host_wins", 1)
        await update_stats(game["host_id"], "hosted_games", 1)
        
        del active_host_games[chat_id]

@word.on_message(filters.command("stopgame") & filters.group)
async def stop_host_game(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in active_host_games:
        await message.reply("No active host game to stop!")
        return
    
    game = active_host_games[chat_id]
    if message.from_user.id != game["host_id"]:
        await message.reply("Only the host can stop the game!")
        return
    
    
    await game["message"].edit_reply_markup(reply_markup=None)
    
    host_mention = (await client.get_users(game["host_id"])).mention
    await message.reply(f"🚫 Host game stopped by {host_mention}")
    del active_host_games[chat_id]
