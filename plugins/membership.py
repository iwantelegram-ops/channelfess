"""
Callback recheck join + notif saat user baru join channel utama.
"""
import asyncio
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
from db.helpers import upsert_user, is_joined, get_bot_setting, set_bot_setting
from utils import check_membership, safe_send, safe_delete

log = logging.getLogger("fessbot.membership")
PM  = ParseMode.HTML

# ═══════════════════════════════════════════════════════════
#  WELCOME ANNOUNCEMENT — di channel utama
# ═══════════════════════════════════════════════════════════

CHANNEL_WELCOME_TEXT = (
    "✅ Hai selamat bergabung 👋, postingan di channel kamu juga bisa "
    "tampil di sini loh, klik tombol di bawah untuk tutorial."
)
CHANNEL_WELCOME_TTL = 60   # detik — durasi pesan welcome sebelum dihapus
WELCOME_SETTING_KEY = "channel_welcome_msg"

# Lock supaya cek "ada welcome aktif?" + kirim baru tidak race condition
_welcome_lock = asyncio.Lock()


def _channel_welcome_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📖 Tutorial / Mulai Bot", url=f"https://t.me/{BOT_USERNAME}?start=true")
    ]])


async def _send_channel_welcome(client: Client):
    """
    Kirim pesan sambutan ke channel utama untuk user baru.
    - Tidak dikirim jika welcome sebelumnya masih ada (belum dihapus).
    - Pesan otomatis dihapus setelah CHANNEL_WELCOME_TTL detik.
    """
    sent = None
    async with _welcome_lock:
        existing = get_bot_setting(WELCOME_SETTING_KEY)
        if existing and existing.get("msg_id"):
            # Welcome lama masih dianggap aktif → jangan kirim baru
            log.debug("[channel_welcome] Welcome lama masih aktif, skip kirim baru")
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

    # Hapus setelah TTL, di luar lock (supaya tidak menahan request lain)
    asyncio.create_task(_expire_channel_welcome(client, sent.id))


async def _expire_channel_welcome(client: Client, msg_id: int):
    await asyncio.sleep(CHANNEL_WELCOME_TTL)
    async with _welcome_lock:
        # FIX: clear DB dulu sebelum delete, supaya welcome baru bisa
        # langsung dikirim tanpa menunggu delete selesai
        current = get_bot_setting(WELCOME_SETTING_KEY)
        if current and current.get("msg_id") == msg_id:
            set_bot_setting(WELCOME_SETTING_KEY, {"msg_id": None, "sent_at": None})
    # delete dilakukan di luar lock (tidak perlu hold lock saat I/O Telegram)
    await safe_delete(client, MAIN_CHANNEL_ID, msg_id)

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

        # Pesan sambutan publik di channel (untuk semua user baru,
        # termasuk yang pernah join sebelumnya)
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
