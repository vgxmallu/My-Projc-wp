import random
from pyrogram import Client, filters
from wallbot import wbot

# Store user game state: {user_id: number_to_guess}
user_games = {}



@app.on_message(filters.command("play"))
def play(client, message):
    num = random.randint(1, 100)
    user_games[message.from_user.id] = num
    message.reply("I'm thinking of a number between 1 and 100. Try to guess it!")

@app.on_message(filters.text & ~filters.command("play"))
def guess(client, message):
    user_id = message.from_user.id
    if user_id not in user_games:
        message.reply("Type /play to start a game first!")
        return

    try:
        guess = int(message.text)
    except ValueError:
        message.reply("Please send a valid number.")
        return

    number = user_games[user_id]
    if guess < number:
        message.reply("Too low! Try again.")
    elif guess > number:
        message.reply("Too high! Try again.")
    else:
        message.reply("🎉 Correct! You guessed the number!")
        del user_games[user_id]

