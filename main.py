import asyncio
import logging
from pyrogram import Client, idle
from config import API_ID, API_HASH, BOT_TOKEN
from db.mongo import sessions_col, peers_col
from db.mongo_storage import MongoStorage
from plugins.repost import start_owner_name_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fessbot")
# Set DEBUG untuk modul repost agar bisa diagnosa delete tracking
logging.getLogger("fessbot.repost").setLevel(logging.DEBUG)

SESSION_NAME = "fessbot_session"

app = Client(
    SESSION_NAME,
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    plugins  = dict(root="plugins"),
)

# Ganti FileStorage bawaan Pyrogram dengan MongoStorage
# sebelum app.run() agar sesi disimpan di MongoDB, bukan file .session
app.storage = MongoStorage(
    name               = SESSION_NAME,
    collection_session = sessions_col,
    collection_peers   = peers_col,
)

if __name__ == "__main__":
    log.info("🤖 FessBot v2 starting...")

    async def _main():
        await app.start()
        await start_owner_name_scheduler(app)
        await idle()
        await app.stop()

    asyncio.run(_main())
    log.info("🤖 FessBot v2 stopped.")
