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


# Session disimpan di MongoDB — persisten di semua device/HP
_storage = MongoStorage(
    name               = "fessbot_session",
    collection_session = sessions_col,
    collection_peers   = peers_col,
)

app = Client(
    _storage,
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    plugins  = dict(root="plugins"),
)


if __name__ == "__main__":
    log.info("🤖 FessBot v2 starting...")
    app.run()
    log.info("🤖 FessBot v2 stopped.")
