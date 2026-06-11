"""
Guard — blokir akses saat maintenance, kecuali owner.
group=0 agar dieksekusi SEBELUM handler lain.
"""
import logging
from pyrogram import Client, filters, StopPropagation
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from config import OWNER_ID
from db.helpers import get_maintenance

log = logging.getLogger("fessbot.guard")

GUARDED_COMMANDS = [
    "stats", "pause", "run", "listpartner", "daftarkan",
    "addbl", "rmbl", "listbl", "maintenance", "unmaintenance",
]

PM = ParseMode.HTML


@Client.on_message(filters.command(GUARDED_COMMANDS) & filters.private, group=0)
async def guard_maintenance(client: Client, message: Message):
    if message.from_user.id == OWNER_ID:
        return

    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(
            f"🔧 <b>Bot sedang maintenance</b>\n\n"
            f"<i>{reason}</i>\n\n"
            f"Coba lagi nanti! 🙏",
            parse_mode=PM,
        )
        raise StopPropagation


@Client.on_message(filters.text & filters.private, group=0)
async def guard_text_maintenance(client: Client, message: Message):
    """Guard untuk tombol reply keyboard saat maintenance."""
    if message.from_user.id == OWNER_ID:
        return

    BUTTON_TEXTS = [
        "📂 My Channel", "ℹ️ Info Bot", "📊 Statistik Saya",
        "🔔 Notifikasi", "❓ Bantuan",
    ]
    if message.text not in BUTTON_TEXTS:
        return

    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(
            f"🔧 <b>Bot sedang maintenance</b>\n\n"
            f"<i>{reason}</i>\n\n"
            f"Coba lagi nanti! 🙏",
            parse_mode=PM,
        )
        raise StopPropagation
