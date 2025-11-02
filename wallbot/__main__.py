from os import mkdir, path

from wallbot import wbot

import asyncio
import logging
from pyrogram import idle


from pyrogram import Client
from wallbot.plugins.g_daily_brain import run_background_tasks
from wallbot.plugins.s_sports_mana import create_player_pool, background_simulator, db


leagues_col = db["leagues"]
teams_col = db["teams"]
players_col = db["players"]
matches_col = db["matches"]
users_col = db["users"]


async def spon_start(client):
    try:
        await leagues_col.create_index("creator_id")
        await teams_col.create_index("manager_id")
        await players_col.create_index("name")
        await teams_col.create_index("league_id")
        await matches_col.create_index("league_id")
    except Exception:
        pass
    # ensure player pool
    await create_player_pool(500)
    # spawn background simulator
    asyncio.create_task(background_simulator())
    print("Sports Manager ready.")

#======{{{{{{{{{
async def loop_bc(client):
    client.loop.create_task(run_background_tasks())
    print("✅ Background task started automatically when bot runs.")
    

if __name__ == "__main__":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
    asyncio.get_event_loop().run_until_complete(main())
