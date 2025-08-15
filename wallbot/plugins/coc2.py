import asyncio
import aiohttp
from pyrogram import Client, filters
from cachetools import TTLCache
from wallbot import wbot as bot

COC_API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6ImM1OTYyNzYyLTNiMWQtNDI5Yi1hYzRmLWNmY2MwMTExOTk2NSIsImlhdCI6MTc1NTI2MTE3Miwic3ViIjoiZGV2ZWxvcGVyL2RhNDhmM2Q2LTBlYTItYzQxYy01ZWFlLWJmNDRhY2YzMDRjZCIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjE1Ny40Ni4yLjEzNiJdLCJ0eXBlIjoiY2xpZW50In1dfQ.LV0wmiBs4K2Ylct7HV3nD0OCtKfT7WlC4_Egyl4ou_iP8NttOFkU8a3X04LJGdXhWguL6WNmMVYj5T5Z7gZaEg"


COC_BASE_URL = "https://api.clashofclans.com/v1"
HEADERS = {"Authorization": f"Bearer {COC_API_TOKEN}"}
PLAYER_CACHE = TTLCache(maxsize=500, ttl=300)  # 5 mins
CLAN_CACHE = TTLCache(maxsize=200, ttl=300)

async def fetch_coc_api(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 404:
                return None
            else:
                text = await resp.text()
                raise Exception(f"Error {resp.status}: {text}")

async def get_player_details(player_tag):
    player_tag = player_tag.strip().upper().replace("#", "")
    if player_tag in PLAYER_CACHE:
        return PLAYER_CACHE[player_tag]
    data = await fetch_coc_api(f"{COC_BASE_URL}/players/%23{player_tag}")
    if data:
        PLAYER_CACHE[player_tag] = data
    return data

async def get_clan_details(clan_tag):
    clan_tag = clan_tag.strip().upper().replace("#", "")
    if clan_tag in CLAN_CACHE:
        return CLAN_CACHE[clan_tag]
    data = await fetch_coc_api(f"{COC_BASE_URL}/clans/%23{clan_tag}")
    if data:
        CLAN_CACHE[clan_tag] = data
    return data

def format_player(data):
    if not data:
        return "❌ Player not found."
    txt = (
        f"👤 <b>{data['name']} ({data['tag']})</b>\n"
        f"🏆 Trophies: {data['trophies']}\n"
        f"🏅 Exp Level: {data['expLevel']}\n"
        f"🏰 Town Hall: {data.get('townHallLevel','N/A')}\n"
        f"🎖 War Stars: {data.get('warStars','N/A')}\n"
        f"🛡 Clan: {data['clan']['name']} ({data['clan']['tag']})" if data.get('clan') else "Not in clan"
    )
    txt += (
        f"\n\n<code>Last fetched from Clash of Clans official API</code>"
    )
    return txt

def format_clan(data):
    if not data:
        return "❌ Clan not found."
    txt = (
        f"🏰 <b>{data['name']} ({data['tag']})</b>\n"
        f"🌟 Level: {data['clanLevel']}\n"
        f"👥 Members: {data['members']}/50\n"
        f"🏆 Points: {data['clanPoints']}\n"
        f"🏆 Versus Points: {data.get('clanVersusPoints', 'N/A')}\n"
        f"📝 Description: {data.get('description', '')[:200]}"
    )
    txt += (
        f"\n\n<code>Last fetched from Clash of Clans official API</code>"
    )
    return txt


@bot.on_message(filters.command("player1") & filters.private)
async def player_handler2(client, message):
    if len(message.command) < 2:
        await message.reply("Please provide a player tag, e.g. /player #YOURTAG")
        return
    tag = message.command[1]
    try:
        data = await get_player_details(tag)
        await message.reply(format_player(data), parse_mode="html")
    except Exception as e:
        await message.reply(f"API error: {str(e)}")

@bot.on_message(filters.command("clan2") & filters.private)
async def clan_handler2(client, message):
    if len(message.command) < 2:
        await message.reply("Please provide a clan tag, e.g. /clan #CLANTAG")
        return
    tag = message.command
    try:
        data = await get_clan_details(tag)
        await message.reply(format_clan(data), parse_mode="html")
    except Exception as e:
        await message.reply(f"API error: {str(e)}")
