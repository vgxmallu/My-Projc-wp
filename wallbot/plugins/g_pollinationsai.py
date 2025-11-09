import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from main import wbot as app

# ==============================
# IMAGE GENERATION
# ==============================
@app.on_message(filters.command("pimage"))
async def geppnerate_image(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide a prompt. Usage: /image <prompt>")

    prompt = " ".join(message.command[1:])
    url = f"https://image.pollinations.ai/prompt/{prompt}"
    await message.reply_photo(url, caption=f"🎨 Generated image for: {prompt}")


# ==============================
# TEXT GENERATION
# ==============================
@app.on_message(filters.command("ptext"))
async def gpenerate_text(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide a prompt. Usage: /text <prompt>")

    prompt = " ".join(message.command[1:])
    url = f"https://text.pollinations.ai/{prompt}"

    try:
        response = requests.get(url)
        result = response.text.strip()
        await message.reply_text(f"🧠 *AI Response:*{result}")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")


# ==============================
# AUDIO GENERATION
# ==============================
@app.on_message(filters.command("pvoice"))
async def genperate_audio(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide text. Usage: /voice <text>")

    text = " ".join(message.command[1:])
    voice = "alloy"
    url = f"https://text.pollinations.ai/{text}?model=openai-audio&voice={voice}"

    await message.reply_audio(url, caption=f"🎤 Generated voice for: {text}")


# ==============================
# MODELS LIST
# ==============================
@app.on_message(filters.command("pmodels"))
async def lipst_models(_, message):
    image_models = requests.get("https://image.pollinations.ai/models").text
    text_models = requests.get("https://text.pollinations.ai/models").text

    await message.reply_text(f"🖼 *Image Models:*\n```{image_models}```\n\n✍️ *Text Models:*\n```{text_models}```")

