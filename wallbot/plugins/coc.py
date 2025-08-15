from pyrogram import Client, filters
#from coc_async_api import ClashOfClansAPI, CoCAPIError
from wallbot import wbot as app
import httpx
import asyncio
from typing import Optional, Dict

class CoCAPIError(Exception):
    """Base exception for Clash of Clans API wrapper."""

class CoCRateLimitError(CoCAPIError):
    """Exception for rate limit errors."""

class ClashOfClansAPI:
    BASE_URL = "https://api.clashofclans.com/v1"

    def __init__(self, api_token: str, timeout: int = 10):
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json"
        }
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = await self.client.get(url, headers=self.headers, params=params)
            if response.status_code == 429:
                raise CoCRateLimitError("Clash of Clans API rate limit exceeded.")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise CoCAPIError(f"HTTP error: {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise CoCAPIError(f"Error: {str(e)}")

    async def get_player(self, tag: str):
        tag = tag.replace("#", "%23")
        return await self._get(f"/players/{tag}")

    async def get_clan(self, tag: str):
        tag = tag.replace("#", "%23")
        return await self._get(f"/clans/{tag}")

    async def get_clan_members(self, tag: str):
        tag = tag.replace("#", "%23")
        data = await self.get_clan(tag)
        return data.get("memberList", [])

    async def get_clan_warlog(self, tag: str, limit: int = 5):
        tag = tag.replace("#", "%23")
        return await self._get(f"/clans/{tag}/warlog", params={"limit": limit})

    async def get_current_war(self, tag: str):
        tag = tag.replace("#", "%23")
        return await self._get(f"/clans/{tag}/currentwar")

    async def search_clans(self, name: str, limit: int = 5):
        return await self._get("/clans", params={"name": name, "limit": limit})

    async def get_location(self, location_id: int):
        return await self._get(f"/locations/{location_id}")

    async def close(self):
        await self.client.aclose()



API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjAwZTFmMWNhLTljMWYtNGJhYS1iMTAxLTRiMjY4NWNiMmIyMSIsImlhdCI6MTc0ODc5OTIxMSwic3ViIjoiZGV2ZWxvcGVyL2RhNDhmM2Q2LTBlYTItYzQxYy01ZWFlLWJmNDRhY2YzMDRjZCIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjExNS4yNDAuOTAuMTYzIl0sInR5cGUiOiJjbGllbnQifV19.00bWfRMp43JtbvXk9ahC6vSJ68EST0Xh-JMKwwZKTvBCP0_7kUtqO39P67NofVYIpkB_l8HyhqVIIoTUM1sN6w"
coc = ClashOfClansAPI(API_TOKEN)



@app.on_message(filters.command("player"))
async def player_handler(client, message):
    try:
        tag = message.text.split(maxsplit=1)[1]
        data = await coc.get_player(tag)
        msg = (
            f"🏆 Player: {data['name']} ({data['tag']})\n"
            f"Town Hall: {data['townHallLevel']}\n"
            f"Exp Level: {data['expLevel']}\n"
            f"Trophies: {data['trophies']}\n"
            f"Clan: {data.get('clan', {}).get('name', 'No Clan')}"
        )
    except Exception as e:
        msg = f"Error: {e}"
    await message.reply(msg)

@app.on_message(filters.command("clan"))
async def clan_handler(client, message):
    try:
        tag = message.text.split(maxsplit=1)[1]
        data = await coc.get_clan(tag)
        msg = (
            f"🛡 Clan: {data['name']} ({data['tag']})\n"
            f"Level: {data['clanLevel']}\n"
            f"Members: {data['members']}\n"
            f"Description: {data['description']}"
        )
    except Exception as e:
        msg = f"Error: {e}"
    await message.reply(msg)

@app.on_message(filters.command("warlog"))
async def warlog_handler(client, message):
    try:
        tag = message.text.split(maxsplit=1)[1]
        warlog = await coc.get_clan_warlog(tag, limit=3)
        msg = "🏅 Recent Wars:\n"
        for war in warlog.get("items", []):
            msg += (
                f"- Result: {war['result']}, "
                f"Team Stars: {war['teamStars']}, "
                f"Opponent: {war['opponent']['name']}\n"
            )
        if not warlog.get("items"):
            msg += "No wars found."
    except Exception as e:
        msg = f"Error: {e}"
    await message.reply(msg)

@app.on_message(filters.command("close"))
async def close_handler(client, message):
    await coc.close()
    await message.reply("API client closed.")

