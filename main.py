import asyncio
import logging
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from db.mongo import sessions_col, peers_col, ensure_indexes
from db.mongo_storage import MongoStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fessbot")
logging.getLogger("fessbot.repost").setLevel(logging.DEBUG)

SESSION_NAME = "fessbot_session_baru"

app = Client(
    SESSION_NAME,
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    plugins  = dict(root="plugins"),
)

app.storage = MongoStorage(
    name               = SESSION_NAME,
    collection_session = sessions_col,
    collection_peers   = peers_col,
)

if __name__ == "__main__":
    log.info("🤖 FessBot v3 starting...")
    try:
        ensure_indexes()
        log.info("✅ MongoDB indexes ensured.")
    except Exception as e:
        log.warning(f"⚠️ Gagal membuat indexes: {e}")
    app.run()
    log.info("🤖 FessBot v3 stopped.")
