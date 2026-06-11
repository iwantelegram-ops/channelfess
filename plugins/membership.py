"""
Callback recheck join + notif saat user baru join channel utama.
"""
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.errors import MessageNotModified
from pyrogram.enums import ParseMode
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import upsert_user, is_joined
from utils import check_membership

log = logging.getLogger("fessbot.membership")
PM  = ParseMode.HTML

WELCOME_TEXT = (
    "🎉 <b>Verifikasi berhasil!</b>\n\n"
    "Selamat datang, <b>{name}</b>! 👋\n\n"
    "Kamu sekarang bisa menghubungkan channel ke <b>FessBot</b> dan "
    "foto/video di channelmu akan otomatis di-repost ke channel utama.\n\n"
    "<b>Cara mulai:</b>\n"
    "1️⃣ Tambahkan bot sebagai <b>Admin</b> di channelmu\n"
    "2️⃣ Channel otomatis terdaftar\n"
    "3️⃣ Konten di-repost real-time ✅\n\n"
    "Ketuk <b>My Channel</b> untuk mulai."
)

def user_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📂 My Channel"), KeyboardButton("📊 Statistik Saya")],
            [KeyboardButton("🔔 Notifikasi"),  KeyboardButton("ℹ️ Info Bot")],
        ],
        resize_keyboard=True,
    )


@Client.on_callback_query(filters.regex("^recheck_join$"))
async def recheck_join(client: Client, cb: CallbackQuery):
    user_id   = cb.from_user.id
    user_name = cb.from_user.first_name or "Pengguna"
    joined    = await check_membership(client, user_id)

    if joined:
        upsert_user(user_id, {
            "joined":    True,
            "joined_at": datetime.now(timezone.utc),
            "username":  cb.from_user.username or "",
            "name":      user_name,
        })
        try:
            await cb.message.edit_text(
                WELCOME_TEXT.format(name=user_name),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "➕ Tambah Bot sebagai Admin",
                        url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                             f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
                    )
                ]]),
                parse_mode=PM,
            )
        except MessageNotModified:
            pass
        await client.send_message(user_id, "Menu kamu:", reply_markup=user_keyboard())
        await cb.answer("✅ Verified!", show_alert=False)
    else:
        await cb.answer(
            "Kamu belum join channel utama nih.\nJoin dulu, lalu cek ulang ya! 😊",
            show_alert=True,
        )


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

        upsert_user(user_id, {
            "joined":    True,
            "joined_at": datetime.now(timezone.utc),
            "username":  user.username or "",
            "name":      name,
        })
        try:
            await client.send_message(
                user_id,
                WELCOME_TEXT.format(name=name),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "➕ Tambah Bot sebagai Admin",
                        url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                             f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
                    )
                ]]),
                parse_mode=PM,
            )
            await client.send_message(user_id, "Menu kamu:", reply_markup=user_keyboard())
        except Exception as e:
            log.warning(f"[on_new_member] Gagal kirim pesan ke {user_id}: {e}")
