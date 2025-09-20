from pyrogram import Client, filters
import google.generativeai as genai
import os
from wallbot import wbot as app
from config import BARD_KEY

# Gemini API Key (from Google AI Studio)
GEMINI_API_KEY = BARD_KEY
genai.configure(api_key=GEMINI_API_KEY)

# In-memory conversation history
user_sessions = {}




# Handle text messages with Gemini
@app.on_message(filters.command("aibard"))
async def gemini_chat(client, message):
    user_id = message.from_user.id
    #user_input = message.text
    user_input = message.text.split(' ', 1)[1]
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    # Add user message to history
    user_sessions[user_id].append({"role": "user", "content": user_input})

    try:
        # Generate response using Gemini
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(
            [m["content"] for m in user_sessions[user_id]]
        )

        reply_text = response.text if response.text else "⚠️ No reply."

        # Save Gemini reply into session
        user_sessions[user_id].append({"role": "assistant", "content": reply_text})

        await message.reply_text(reply_text)

    except Exception as e:
        await message.reply_text(f"⚠️ Error: {str(e)}")

