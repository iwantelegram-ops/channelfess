import asyncio
import logging
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fessbot")


app = Client(
    "fessbot_session",
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    plugins  = dict(root="plugins"),
)


if __name__ == "__main__":
    log.info("🤖 FessBot v2 starting...")
    app.run()
    log.info("🤖 FessBot v2 stopped.")
