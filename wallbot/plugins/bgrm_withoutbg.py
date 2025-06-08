import os
import requests
from pyrogram import Client, filters


WITHOUTBG_API_KEY = "key-mdr7UmnpgH5ELRoz"  # Replace with your withoutbg.com API Key


def remove_bg(input_file):
    url = "https://api.withoutbg.com/v1.0/removebg"
    with open(input_file, "rb") as image_file:
        response = requests.post(
            url,
            files={"image_file": image_file},
            headers={"X-Api-Key": WITHOUTBG_API_KEY},
            data={"format": "png"}
        )
    if response.status_code == 200:
        return response.content
    else:
        return None

@app.on_message(filters.photo)
def photo_handler(client, message):
    msg = message.reply("Processing your image, please wait...")
    photo = message.photo[-1]  # Get the highest resolution photo
    file_path = app.download_media(photo, file_name="input.jpg")
    output = remove_bg(file_path)
    if output:
        out_path = "no_bg.png"
        with open(out_path, "wb") as f:
            f.write(output)
        message.reply_document(out_path, caption="Here is your image without background!")
        os.remove(out_path)
    else:
        message.reply("Failed to remove background. Please try again later.")
    os.remove(file_path)
    msg.delete()
