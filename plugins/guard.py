"""
Guard — blokir semua perintah untuk user yang belum join channel utama.
(kecuali /start dan callback recheck_join)
"""
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID, MAIN_CHANNEL_USERNAME
from db.helpers import is_joined
from utils import check_membership

ALLOWED_COMMANDS = {"start"}

@Client.on_message(filters.private & filters.command(list(
    # Blokir semua command kecuali start
    ["pause", "run", "stats", "listpartner"]
)), group=-1)
async def guard_commands(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id == OWNER_ID:
        return  # owner bebas

    # Cek DB dulu (cepat), lalu verifikasi ke Telegram jika perlu
    if not is_joined(user_id):
        live_check = await check_membership(client, user_id)
        if not live_check:
            await message.reply(
                "🔒 Fitur ini hanya untuk anggota channel utama.\nJoin dulu untuk melanjutkan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel Utama",
                     url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
                    [InlineKeyboardButton("✅ Sudah Join", callback_data="recheck_join")]
                ])
            )
            message.stop_propagation()
