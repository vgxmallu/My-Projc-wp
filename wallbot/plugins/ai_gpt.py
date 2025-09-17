from pyrogram import Client, filters
import openai
import asyncio
from config import OPENAI_KEY
from wallbot import wbot as app


# OpenAI API key (get it from https://platform.openai.com)
openai.api_key = OPENAI_KEY

# In-memory conversation history per user
user_sessions = {}




# Handle AI chat (remembers context per user)
@app.on_message(filters.command("oai"))
async def chatgpt_reply(client, message):
    user_id = message.from_user.id
    user_input = message.text
    message.text.split(" ", 1)[1]
    # Create session if not exists
    if user_id not in user_sessions:
        user_sessions[user_id] = [
            {"role": "system", "content": "You are a helpful AI assistant."}
        ]

    # Append user message
    user_sessions[user_id].append({"role": "user", "content": user_input})

    try:
        # Generate response from OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Or "gpt-4"
            messages=user_sessions[user_id]
        )

        reply_text = response["choices"][0]["message"]["content"].strip()

        # Append assistant reply to session
        user_sessions[user_id].append({"role": "assistant", "content": reply_text})

        # Reply in Telegram
        await message.reply_text(reply_text)

    except Exception as e:
        await message.reply_text(f"⚠️ Error: {str(e)}")


# Image generation command
@app.on_message(filters.command("image"))
async def generate_image(client, message):
    try:
        prompt = message.text.split(" ", 1)[1]
    except IndexError:
        await message.reply_text("❌ Usage: `/image a cute cat in space`")
        return

    try:
        # Call OpenAI Image API (DALL·E)
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        image_url = response["data"][0]["url"]

        # Send image to Telegram
        await message.reply_photo(image_url, caption=f"🖼 Prompt: {prompt}")

    except Exception as e:
        await message.reply_text(f"⚠️ Error generating image: {str(e)}")
