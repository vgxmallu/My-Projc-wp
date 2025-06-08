import aiohttp
import os
from pyrogram import Client, filters
from wallbot import wbot as app


PHOTOROOM_API_KEY = "key-mdr7UmnpgH5ELRoz"


async def remove_background(file_path):
    url = "https://sdk.photoroom.com/v1/segment"
    headers = {
        "x-api-key": PHOTOROOM_API_KEY
    }
    with open(file_path, "rb") as image_file:
        data = {"image_file": image_file}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    return None

@app.on_message(filters.command("bgrm2") & filters.private)
async def bgrm_c2ommand(client, message):
    target = message.reply_to_message

    if not target or not target.photo:
        await message.reply("❗ Please reply to a photo with /bgrm")
        return

    msg = await message.reply("🛠 Removing background...")

    file_path = await target.download()
    output = await remove_background(file_path)

    if output:
        out_file = file_path.replace(".jpg", "_no_bg.png")
        with open(out_file, "wb") as f:
            f.write(output)

        await message.reply_document(out_file, caption="✅ Background removed!")
        os.remove(out_file)
    else:
        await msg.edit("❌ Failed to process the image.")

    os.remove(file_path)
    await msg.delete()

