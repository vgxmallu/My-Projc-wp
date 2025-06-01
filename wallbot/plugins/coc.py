import requests
from pyrogram import Client, filters
from wallbot import wbot
import logging

# Replace with your credentials
COC_API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjllMDg3YjNjLTI4YzgtNGQzNy05ZjZlLTBmNWFjNmUyMDMyZCIsImlhdCI6MTc0ODc3NzU5Miwic3ViIjoiZGV2ZWxvcGVyL2RhNDhmM2Q2LTBlYTItYzQxYy01ZWFlLWJmNDRhY2YzMDRjZCIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjE0NS4xMjcuMjI4LjI5IiwiMTQ1LjEyNy4yMjguMjkiXSwidHlwZSI6ImNsaWVudCJ9XX0.XJ4fpd0N9q_D2pXnOcL2k3KOmHjnaDvcMsGn5LsjFYu3v9dCS5_KRqMCfy20CtTXpieDa94LLQB8_-KfWS4pTQ"

# Clash of Clans API base URL
COC_API_URL = "api.clashofclans.com/v1/players/{}"
COC_HEADERS = {"Authorization": f"Bearer {COC_API_TOKEN}"}

"""
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
        return "Player not found or API error"
"""

def get_player_info(tag):
    """Fetch player info from Clash of Clans API."""
    if not tag.startswith("#") and not tag.startswith("%23"):
        tag = f"#${tag}"  # Ensures proper tag format

    encoded_tag = tag.replace("#", "%23")
    url = COC_API_URL.format(encoded_tag)

    try:
        resp = requests.get(url, headers=COC_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("name")
            level = data.get("expLevel")
            trophies = data.get("trophies")
            clan = data.get("clan", {}).get("name", "No Clan")

            return (
                f"👤 **Player:** {name}\n"
                f"📊 **Level:** {level}\n"
                f"🏆 **Trophies:** {trophies}\n"
                f"🛡️ **Clan:** {clan}"
            )

        elif resp.status_code == 403:
            logging.warning("403 Forbidden - Check API key or IP whitelist.")
            return "🚫 Access denied. Check your API key and whitelisted IP address."
        elif resp.status_code == 404:
            return "❌ Player not found."
        else:
            logging.error(f"Unexpected error: {resp.status_code} - {resp.text}")
            return "⚠️ Unexpected error from Clash of Clans API."

    except requests.exceptions.RequestException as e:
        logging.exception("Network error occurred.")
        return "❗ Network error while connecting to Clash of Clans API."

# Command example: /player #TAG
@wbot.on_message(filters.command("player"))
async def player_command(client, message):
    if len(message.command) < 2:
        await message.reply("Usage: /player #TAG")
        return
    tag = message.command[1]
    await message.reply("Fetching player info...")
    info = get_player_info(tag)
    await message.reply(info)
