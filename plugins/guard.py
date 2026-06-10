"""
Guard — blokir akses user saat maintenance mode aktif.
Hanya intercept non-start commands agar /start tetap jalan normal.
"""
from pyrogram import Client, filters, StopPropagation
from pyrogram.types import Message
from config import OWNER_ID
from db.helpers import get_maintenance

# Semua command KECUALI /start — /start punya logic maintenance sendiri
GUARDED_COMMANDS = [
    "stats", "pause", "run", "listpartner", "daftarkan",
    "broadcast", "broadcastpartner", "maintenance", "unmaintenance",
    "addbl", "rmbl", "listbl"
]

@Client.on_message(filters.command(GUARDED_COMMANDS) & filters.private)
async def guard_maintenance(client: Client, message: Message):
    if message.from_user.id == OWNER_ID:
        return  # Owner selalu bisa akses

    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(f"🔧 **Bot sedang maintenance**\n\n_{reason}_\n\nCoba lagi nanti! 🙏")
        raise StopPropagation
