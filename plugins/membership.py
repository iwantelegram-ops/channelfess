"""
Callback recheck join + notif user baru join channel utama.
"""
import asyncio
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.errors import MessageNotModified
from pyrogram.enums import ParseMode

from config import MAIN_CHANNEL_ID, BOT_USERNAME, BOT_NAME, MAIN_CHANNEL_USERNAME
from db.helpers import upsert_user, is_joined, get_bot_setting, set_bot_setting
from utils import check_membership, safe_send, safe_delete, safe_edit, answer_cb

log = logging.getLogger("fessbot.membership")
PM  = ParseMode.HTML
SEP = "─" * 30


CHANNEL_WELCOME_TEXT = (
    "✅ Hai selamat bergabung 👋, postingan di channel kamu juga bisa "
    "tampil di sini loh, klik tombol di bawah untuk tutorial."
)
CHANNEL_WELCOME_TTL = 60
WELCOME_SETTING_KEY = "channel_welcome_msg"
_welcome_lock = asyncio.Lock()


def _channel_welcome_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📖 Tutorial / Mulai Bot", url=f"https://t.me/{BOT_USERNAME}?start=true")
    ]])


async def _send_channel_welcome(client: Client):
    sent = None
    async with _welcome_lock:
        existing = get_bot_setting(WELCOME_SETTING_KEY)
        if existing and existing.get("msg_id"):
            log.debug("[channel_welcome] Welcome lama masih aktif, skip.")
            return
        sent = await safe_send(client.send_message(
            MAIN_CHANNEL_ID,
            CHANNEL_WELCOME_TEXT,
            reply_markup=_channel_welcome_markup(),
        ))
        if not sent:
            return
        set_bot_setting(WELCOME_SETTING_KEY, {
            "msg_id":  sent.id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

    asyncio.create_task(_expire_channel_welcome(client, sent.id))


async def _expire_channel_welcome(client: Client, msg_id: int):
    await asyncio.sleep(CHANNEL_WELCOME_TTL)
    async with _welcome_lock:
        await safe_delete(client, MAIN_CHANNEL_ID, msg_id)
        current = get_bot_setting(WELCOME_SETTING_KEY)
        if current and current.get("msg_id") == msg_id:
            set_bot_setting(WELCOME_SETTING_KEY, {"msg_id": None, "sent_at": None})


WELCOME_TEXT = (
    "🎉 <b>Verifikasi berhasil!</b>\n\n"
    "Selamat datang, <b>{name}</b>! 👋\n\n"
    "Kamu sekarang bisa menghubungkan channelmu ke <b>{bot_name}</b> dan "
    "foto/video di channelmu akan otomatis di-repost ke channel utama.\n\n"
    "<b>Cara mulai:</b>\n"
    "1️⃣ Tambahkan bot sebagai <b>Admin</b> di channelmu\n"
    "2️⃣ Channel otomatis terdaftar\n"
    "3️⃣ Konten di-repost real-time ✅\n\n"
    "Ketuk tombol di bawah untuk mulai."
)

def user_main_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 My Channel",     callback_data="user_channels_0"),
            InlineKeyboardButton("📊 Statistik",      callback_data="user_stats"),
        ],
        [
            InlineKeyboardButton("🔔 Notifikasi",     callback_data="user_notif"),
            InlineKeyboardButton("ℹ️ Info Bot",        callback_data="user_info"),
        ],
        [
            InlineKeyboardButton("📖 Tutorial",       callback_data="user_tutorial"),
            InlineKeyboardButton("➕ Tambah Channel", url=(
                f"https://t.me/{BOT_USERNAME}?startchannel=true"
                f"&admin=post_messages+edit_messages+delete_messages+invite_users"
            )),
        ],
    ])


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
                WELCOME_TEXT.format(name=user_name, bot_name=BOT_NAME),
                reply_markup=user_main_markup(),
                parse_mode=PM,
            )
        except (MessageNotModified, Exception):
            pass
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

        asyncio.create_task(_send_channel_welcome(client))

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
                WELCOME_TEXT.format(name=name, bot_name=BOT_NAME),
                reply_markup=user_main_markup(),
                parse_mode=PM,
            )
        except Exception as e:
            log.warning(f"[on_new_member] Gagal kirim ke {user_id}: {e}")
