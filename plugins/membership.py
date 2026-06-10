"""
Callback: recheck join, deteksi user baru join channel utama.
Bot harus di-invite ke channel utama sebagai admin agar bisa dengar chat_member updates.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import MAIN_CHANNEL_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import upsert_user, is_joined
from utils import check_membership
from datetime import datetime

USER_JOINED_NOTIF = """
🎉 **Selamat, {name}! Kamu sudah bergabung.**

Sekarang kamu bisa menautkan channel kamu ke FessBot dan mulai mendapat eksposur lebih luas di channel utama kami.

━━━━━━━━━━━━━━━━━━━━━━━
**Cara Menautkan Channel:**
1. Tambahkan bot sebagai admin di channel kamu
2. Channel otomatis terdaftar sebagai **partner**
3. Setiap foto/video yang kamu post akan diteruskan ke channel utama

Klik tombol di bawah untuk langsung jadikan bot admin di channelmu:
"""

@Client.on_callback_query(filters.regex("^recheck_join$"))
async def recheck_join(client: Client, cb: CallbackQuery):
    user_id   = cb.from_user.id
    user_name = cb.from_user.first_name or "Pengguna"
    joined    = await check_membership(client, user_id)

    if joined:
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Jadikan Bot Admin di Channelku",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=link&admin=post_messages+edit_messages+delete_messages")]
        ])
        await cb.message.edit_text(USER_JOINED_NOTIF.format(name=user_name), reply_markup=btn)
    else:
        await cb.answer("⚠️ Kamu belum join channel utama. Coba lagi setelah join.", show_alert=True)

@Client.on_chat_member_updated(filters.chat(MAIN_CHANNEL_ID))
async def on_new_member(client: Client, update: ChatMemberUpdated):
    """Kirim notif DM saat user baru join channel utama."""
    if not update.new_chat_member:
        return
    new_status = update.new_chat_member.status.value
    old_status = update.old_chat_member.status.value if update.old_chat_member else "left"

    # Hanya proses kalau ini join baru (left/banned → member)
    if old_status in ("left", "kicked", "restricted") and new_status == "member":
        user    = update.new_chat_member.user
        user_id = user.id
        name    = user.first_name or "Pengguna"

        if is_joined(user_id):
            return  # sudah pernah dapat notif

        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Jadikan Bot Admin di Channelku",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=link&admin=post_messages+edit_messages+delete_messages")]
        ])
        try:
            await client.send_message(
                user_id,
                USER_JOINED_NOTIF.format(name=name),
                reply_markup=btn
            )
        except Exception:
            pass  # User mungkin blokir bot
