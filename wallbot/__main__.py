import asyncio
import logging
from wallbot import wbot

# ---------------- Logging Setup ----------------
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
    level=logging.INFO,
)
LOGGER = logging.getLogger("WallBot")


async def main():
    try:
        await wbot.start()
        me = await wbot.get_me()
        LOGGER.info(f"🤖 Logged in as {me.first_name} (@{me.username}) [ID: {me.id}]")
        LOGGER.info("💫 WallBot is running... Press Ctrl+C to stop.")

        # Keep the bot alive
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        LOGGER.warning("🛑 Keyboard interrupt received. Stopping bot...")

    finally:
        await wbot.stop()
        LOGGER.info("👋 WallBot stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.warning("🛑 Bot exited manually.")
