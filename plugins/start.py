"""
/start — Welcome screen. Owner dan user mendapat tampilan berbeda.
Parse mode: HTML di seluruh file.
"""
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.enums import ParseMode
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import (
    upsert_user, get_maintenance,
    count_partners, get_active_partners, count_users,
)
from db.mongo import posts
from utils import check_membership, store_msg

log = logging.getLogger("fessbot.start")
PM  = ParseMode.HTML


# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════

def owner_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Dashboard"), KeyboardButton("📋 Partner")],
            [KeyboardButton("📣 Broadcast"), KeyboardButton("🔧 Tools")],
            [KeyboardButton("📝 Aktivitas"), KeyboardButton("⚙️ Pengaturan")],
        ],
        resize_keyboard=True,
    )

def user_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📂 My Channel"), KeyboardButton("📊 Statistik Saya")],
            [KeyboardButton("🔔 Notifikasi"),  KeyboardButton("ℹ️ Info Bot")],
            [KeyboardButton("❓ Bantuan")],
        ],
        resize_keyboard=True,
    )

def not_joined_inline(channel_username: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel Utama",
                              url=f"https://t.me/{channel_username}")],
        [InlineKeyboardButton("✅ Sudah Join — Cek Ulang",
                              callback_data="recheck_join")],
    ])


# ═══════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.command("start") & filters.private, group=1)
async def start(client: Client, message: Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "Pengguna"

    # ── Owner ──────────────────────────────────────────────
    if user_id == OWNER_ID:
        total_p  = count_partners()
        active_p = len(get_active_partners())
        total_r  = posts.count_documents({})
        text = (
            f"⚡ <b>FessBot v2 — Control Panel</b>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"📡 Partner   <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
            f"📦 Repost    <code>{total_r}</code> all-time\n\n"
            f"Semua sistem berjalan normal. 🟢\n"
            f"Gunakan menu di bawah. 👇"
        )
        msg = await message.reply(text, reply_markup=owner_keyboard(), parse_mode=PM)
        store_msg(user_id, msg)
        return

    # ── Maintenance ────────────────────────────────────────
    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang dalam pemeliharaan.")
        await message.reply(
            f"🔧 <b>Bot sedang maintenance</b>\n\n"
            f"<i>{reason}</i>\n\n"
            f"Coba lagi beberapa saat ya! 🙏",
            parse_mode=PM,
        )
        return

    # ── User — cek join ────────────────────────────────────
    joined = await check_membership(client, user_id)
    upsert_user(user_id, {
        "joined":    joined,
        "last_seen": datetime.now(timezone.utc),
        "username":  message.from_user.username or "",
        "name":      user_name,
    })

    if not joined:
        msg = await message.reply(
            f"👋 <b>Halo, {user_name}!</b>\n\n"
            f"Untuk menggunakan <b>FessBot</b>, kamu perlu join channel utama dulu.\n\n"
            f"Ketuk <b>Join Channel Utama</b> di bawah, lalu ketuk "
            f"<b>Sudah Join — Cek Ulang</b>. 👇",
            reply_markup=not_joined_inline(MAIN_CHANNEL_USERNAME),
            parse_mode=PM,
        )
        store_msg(user_id, msg)
        return

    # ── User sudah join ────────────────────────────────────
    upsert_user(user_id, {"joined": True, "joined_at": datetime.now(timezone.utc)})
    msg = await message.reply(
        f"⚡ <b>Halo, {user_name}!</b>\n\n"
        f"<b>FessBot</b> otomatis meneruskan foto &amp; video dari channelmu "
        f"ke channel utama.\n\n"
        f"<b>Cara setup:</b>\n"
        f"1️⃣  Tambahkan bot sebagai <b>Admin</b> di channelmu\n"
        f"2️⃣  Channel otomatis terdaftar\n"
        f"3️⃣  Konten di-repost real-time ✅\n\n"
        f"Buka <b>My Channel</b> untuk mulai. 👇",
        reply_markup=user_keyboard(),
        parse_mode=PM,
    )
    store_msg(user_id, msg)


# ═══════════════════════════════════════════════════════════
#  ℹ️ Info Bot
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^ℹ️ Info Bot$"))
async def info_bot(client: Client, message: Message):
    from utils import nav_to
    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts.count_documents({})
    total_u  = count_users()

    text = (
        f"ℹ️ <b>Tentang FessBot</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"👥 Users terdaftar    <code>{total_u}</code>\n"
        f"📡 Channel partner    <code>{total_p}</code> total · <code>{active_p}</code> aktif\n"
        f"📦 Total repost       <code>{total_r}</code>\n\n"
        f"<code>{'─' * 28}</code>\n"
        f"🤖 @{BOT_USERNAME}\n"
        f"📢 Channel Utama → @{MAIN_CHANNEL_USERNAME}\n\n"
        f"<i>FessBot v2 — Auto Repost Bot</i>"
    )
    msg = await nav_to(
        client, message.from_user.id, message.chat.id, text, parse_mode=PM
    )
    if not msg:
        await message.reply(text, parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  ❓ Bantuan
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^❓ Bantuan$"))
async def bantuan(client: Client, message: Message):
    from utils import nav_to
    text = (
        f"❓ <b>Bantuan &amp; Panduan FessBot</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"<b>📌 Cara Daftar Channel:</b>\n"
        f"1️⃣  Buka pengaturan channelmu\n"
        f"2️⃣  Tambahkan <b>@{BOT_USERNAME}</b> sebagai Admin\n"
        f"     (izin: posting, edit, hapus pesan)\n"
        f"3️⃣  Channel otomatis terdaftar!\n\n"
        f"<b>📌 Cara Aktifkan Repost:</b>\n"
        f"• Buka <b>My Channel</b>\n"
        f"• Pilih channel → ketuk <b>Aktifkan Forward</b>\n\n"
        f"<b>📌 Cara Pause Repost:</b>\n"
        f"• Buka <b>My Channel</b> → pilih channel\n"
        f"• Ketuk <b>Pause Forward</b>\n\n"
        f"<b>📌 Kenapa postingan tidak muncul?</b>\n"
        f"• Pastikan bot masih jadi Admin di channelmu\n"
        f"• Pastikan status channel <b>Aktif</b> (bukan Paused)\n"
        f"• Pastikan konten bukan foto/video yang mengandung kata terlarang\n\n"
        f"<b>📌 Hubungi Admin:</b>\n"
        f"• Kirim pesan ke @{BOT_USERNAME}"
    )

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "➕ Tambah Bot ke Channel",
            url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                 f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
        )
    ]])

    msg = await nav_to(
        client, message.from_user.id, message.chat.id, text,
        inline_markup=markup, parse_mode=PM,
    )
    if not msg:
        await message.reply(text, reply_markup=markup, parse_mode=PM)
