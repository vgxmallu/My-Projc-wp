import requests
from pyrogram import Client, filters
from wallbot import wbot
# Replace with your credentials
COC_API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjllMDg3YjNjLTI4YzgtNGQzNy05ZjZlLTBmNWFjNmUyMDMyZCIsImlhdCI6MTc0ODc3NzU5Miwic3ViIjoiZGV2ZWxvcGVyL2RhNDhmM2Q2LTBlYTItYzQxYy01ZWFlLWJmNDRhY2YzMDRjZCIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjE0NS4xMjcuMjI4LjI5IiwiMTQ1LjEyNy4yMjguMjkiXSwidHlwZSI6ImNsaWVudCJ9XX0.XJ4fpd0N9q_D2pXnOcL2k3KOmHjnaDvcMsGn5LsjFYu3v9dCS5_KRqMCfy20CtTXpieDa94LLQB8_-KfWS4pTQ"

# Clash of Clans API base URL
COC_API_URL = "https://api.clashofclans.com/v1/players/{}"
COC_HEADERS = {"Authorization": f"Bearer {COC_API_TOKEN}"}


def get_player_info(tag):
    tag = tag.replace("#", "%23")
    url = COC_API_URL.format(tag)
    resp = requests.get(url, headers=COC_HEADERS)
    if resp.status_code == 200:
        data = resp.json()
        name = data.get("name")
        level = data.get("expLevel")
        trophies = data.get("trophies")
        clan = data.get("clan", {}).get("name", "No Clan")
        return f"👤 **Player:** {name}\n📊 **Level:** {level}\n🏆 **Trophies:** {trophies}\n🛡️ **Clan:** {clan}"
    else:
        return "Player not found or API error."

# Command example: /player #TAG
@wbot.on_message(filters.command("player"))
async def player_command(client, message):
    if len(message.command) < 2:
        await message.reply("Usage: /player #TAG")
        return
    tag = await message.command[1]
    await message.reply("Fetching player info...")
    info = get_player_info(tag)
    await message.reply(info)
