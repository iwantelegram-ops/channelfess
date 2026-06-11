import asyncio
import logging
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from db.mongo import sessions_col, peers_col
from db.mongo_storage import MongoStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fessbot")
logging.getLogger("fessbot.repost").setLevel(logging.DEBUG)

SESSION_NAME = "fessbot_session"

app = Client(
    SESSION_NAME,
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    plugins  = dict(root="plugins", exclude=["guard"),
)

app.storage = MongoStorage(
    name               = SESSION_NAME,
    collection_session = sessions_col,
    collection_peers   = peers_col,
)

if __name__ == "__main__":
    log.info("🤖 FessBot v3 starting...")
    app.run()
    log.info("🤖 FessBot v3 stopped.")
