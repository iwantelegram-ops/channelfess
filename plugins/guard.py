"""
Guard — tolak akses saat maintenance, tangkap perintah tidak dikenal.
"""
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from db.helpers import get_maintenance

KNOWN_COMMANDS = {
    "start", "stats", "pause", "run", "listpartner", "daftarkan",
    "broadcast", "broadcastpartner", "maintenance", "unmaintenance",
    "addbl", "rmbl", "listbl"
}

@Client.on_message(filters.command(list(KNOWN_COMMANDS), prefixes="/") & filters.private)
async def guard_maintenance(client: Client, message: Message):
    if message.from_user.id == OWNER_ID:
        return  # Owner selalu bisa akses

    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(f"🔧 **Bot sedang maintenance**\n\n_{reason}_\n\nCoba lagi nanti! 🙏")
        raise StopPropagation
