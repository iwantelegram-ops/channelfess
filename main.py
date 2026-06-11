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
    plugins  = dict(root="plugins"),
)

app.storage = MongoStorage(
    name               = SESSION_NAME,
    collection_session = sessions_col,
    collection_peers   = peers_col,
)


async def main():
    await app.start()
    log.info("🤖 FessBot v2 started.")

    # Jalankan scheduler setelah bot connect
    try:
        from plugins.repost import start_owner_name_scheduler
        await start_owner_name_scheduler(app)
    except Exception as e:
        log.warning(f"Scheduler start failed: {e}")

    await asyncio.Event().wait()  # block selamanya sampai Ctrl+C


if __name__ == "__main__":
    log.info("🤖 FessBot v2 starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    log.info("🤖 FessBot v2 stopped.")
