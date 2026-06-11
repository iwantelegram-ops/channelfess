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

@app.on_message()
async def _dummy(_c, _m):
    # Placeholder — tidak pernah dipanggil, hanya untuk trigger import plugins
    pass


async def _on_start():
    """Dipanggil setelah bot connect ke Telegram. Jalankan scheduler."""
    from plugins.repost import start_owner_name_scheduler
    await start_owner_name_scheduler(app)
    log.info("✅ Owner name scheduler started.")


# FIX: Daftarkan on_start handler untuk jalankan scheduler saat bot ready
app.on_message()(lambda *_: None)  # dummy agar plugins ter-load
_original_start = app.start

async def _patched_start(*args, **kwargs):
    result = await _original_start(*args, **kwargs)
    try:
        from plugins.repost import start_owner_name_scheduler
        import asyncio
        asyncio.ensure_future(start_owner_name_scheduler(app))
    except Exception as e:
        log.warning(f"Scheduler start failed: {e}")
    return result

app.start = _patched_start


if __name__ == "__main__":
    log.info("🤖 FessBot v2 starting...")
    app.run()
    log.info("🤖 FessBot v2 stopped.")
