import random
from pyrogram import Client, filters
from wallbot import wbot

# Store user game state: {user_id: number_to_guess}
user_games = {}



@wbot.on_message(filters.command("gplay"))
async def play(client, message):
    num = random.randint(1, 100)
    user_games[message.from_user.id] = num
    await message.reply("I'm thinking of a number between 1 and 100. Try to guess it!")

@wbot.on_message(filters.text & ~filters.command("gplay"))
async def guess(client, message):
    user_id = message.from_user.id
    if user_id not in user_games:
        await message.reply("Type /play to start a game first!")
        return

    try:
        guess = int(message.text)
    except ValueError:
        await message.reply("Please send a valid number.")
        return

    number = user_games[user_id]
    if guess < number:
        await message.reply("Too low! Try again.")
    elif guess > number:
        await message.reply("Too high! Try again.")
    else:
        await message.reply("🎉 Correct! You guessed the number!")
        del user_games[user_id]

