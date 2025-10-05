import requests
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from wallbot import wbot as app
from config import GROQ_API_KEY

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
TEXT_MODEL = "deepseek-r1-distill-llama-70b" #"llama3-8b-8192"  # Example model




# ====== /dep COMMAND ======
@app.on_message(filters.command("dep"))
async def dep(_, message):
    user_text = " ".join(message.command[1:])
    if not user_text:
        return await message.reply_text(
            "⚠️ Please provide some text after `/dep`.\nExample: `/dep Tell me a joke`"
        )

    msg = await message.reply_text("⚡ Generating response... ⏳")

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": TEXT_MODEL,
                "messages": [
                    {"role": "system", "content": "Reply in the same language as the user, briefly."},
                    {"role": "user", "content": user_text},
                ],
            },
            timeout=30
        )

        data = response.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ No response from AI.")

        await msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"⚠️ Error: {e}")

