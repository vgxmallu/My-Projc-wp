import json
import requests
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from config import OPENROUTER_API_KEY
from main import wbot as app


SITE_URL = "https://t.me/XBOTS_X"      # Optional
SITE_NAME = "Gomez Games"    # Optional
MODEL = "deepseek/deepseek-r1:free"


# ========== /ask COMMAND ==========
@app.on_message(filters.command("depask"))
async def ask_deepaik(_, message):
    user_text = " ".join(message.command[1:])
    if not user_text:
        return await message.reply_text("⚠️ Please provide a question after `/ask`.")

    temp_msg = await message.reply_text("⚡ Asking AI... ⏳")

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": SITE_URL,
                "X-Title": SITE_NAME,
            },
            data=json.dumps({
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": user_text}
                ],
            }),
            timeout=30
        )

        data = response.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ No response from AI.")
        await temp_msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await temp_msg.edit_text(f"⚠️ Error: {e}")

