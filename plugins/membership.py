"""
Callback: recheck join & notif user baru join channel utama.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import upsert_user, is_joined
from utils import check_membership
from datetime import datetime

USER_JOINED_NOTIF = """
🎉 **Welcome to the fam, {name}!**

Sekarang kamu bisa tautkan channelmu ke **FessBot** dan jangkau lebih banyak audiens. 🚀

**Cara mulai:**
`1.` Tambahkan bot sebagai **Admin** di channelmu
`2.` Channel otomatis terdaftar sebagai partner
`3.` Setiap foto/video di-repost ke channel utama secara real-time

Tap tombol di bawah untuk langsung mulai 👇
"""

@Client.on_callback_query(filters.regex("^recheck_join$"))
async def recheck_join(client: Client, cb: CallbackQuery):
    user_id   = cb.from_user.id
    user_name = cb.from_user.first_name or "Pengguna"
    joined    = await check_membership(client, user_id)

    if joined:
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Tambah Bot sebagai Admin",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users")]
        ])
        await cb.message.edit_text(USER_JOINED_NOTIF.format(name=user_name), reply_markup=btn)
        await cb.answer("✅ Verified!", show_alert=False)
    else:
        await cb.answer("Belum join nih. Join dulu terus cek ulang ya!", show_alert=True)

@Client.on_chat_member_updated(filters.chat(MAIN_CHANNEL_ID))
async def on_new_member(client: Client, update: ChatMemberUpdated):
    if not update.new_chat_member:
        return
    new_status = update.new_chat_member.status.value
    old_status = update.old_chat_member.status.value if update.old_chat_member else "left"

    if old_status in ("left", "kicked", "restricted") and new_status == "member":
        user    = update.new_chat_member.user
        user_id = user.id
        name    = user.first_name or "Pengguna"

        if is_joined(user_id):
            return

        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Tambah Bot sebagai Admin",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users")]
        ])
        try:
            await client.send_message(
                user_id,
                USER_JOINED_NOTIF.format(name=name),
                reply_markup=btn
            )
        except Exception:
            pass
