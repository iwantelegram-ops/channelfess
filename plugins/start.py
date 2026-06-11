"""
/start — Welcome screen. Owner dan user mendapat tampilan berbeda.
Parse mode: HTML di seluruh file.
"""
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.enums import ParseMode
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME, OWNER_USERNAME, OWNER_NAME, BOT_NAME, BOT_DESC
from db.helpers import (
    upsert_user, get_maintenance,
    count_partners, get_active_partners, count_users,
)
from db.mongo import posts
from utils import check_membership, store_msg, nav_to, answer_cb, safe_edit

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


# recheck_join ditangani di membership.py


# ═══════════════════════════════════════════════════════════
#  ℹ️ Info Bot
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^ℹ️ Info Bot$"), group=1)
async def info_bot(client: Client, message: Message):
    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts.count_documents({})
    total_u  = count_users()

    owner_line = f"@{OWNER_USERNAME}" if OWNER_USERNAME else OWNER_NAME

    text = (
        f"ℹ️ <b>Tentang {BOT_NAME}</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"🤖 <b>Bot</b>\n"
        f"   @{BOT_USERNAME}\n"
        f"   <i>{BOT_DESC}</i>\n\n"
        f"👤 <b>Owner</b>\n"
        f"   {owner_line}\n\n"
        f"📢 <b>Channel Utama</b>\n"
        f"   @{MAIN_CHANNEL_USERNAME}\n\n"
        f"<code>{'─' * 28}</code>\n"
        f"📊 <b>Statistik</b>\n"
        f"   👥 Users        <code>{total_u}</code>\n"
        f"   📡 Partner      <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
        f"   📦 Total repost <code>{total_r}</code>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kunjungi Channel Utama",
                             url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
        [InlineKeyboardButton("📖 Tutorial Penggunaan", callback_data="tutorial")],
    ])
    await message.reply(text, reply_markup=markup, parse_mode=PM)

# ═══════════════════════════════════════════════════════════
#  📖 Tutorial
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^tutorial$"))
async def cb_tutorial(client: Client, cb: CallbackQuery):
    try:
        text = (
            f"📖 <b>Tutorial {BOT_NAME}</b>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"1️⃣ <b>Daftarkan Channel</b>\n"
            f"• Buka pengaturan channel → <b>Administrator → Tambah Admin</b>\n"
            f"• Cari <b>@{BOT_USERNAME}</b>, aktifkan izin:\n"
            f"  ✅ Kirim · Edit · Hapus Pesan\n"
            f"• Simpan → channel <b>otomatis terdaftar</b> ✅\n\n"
            f"2️⃣ <b>Aktifkan / Pause Repost</b>\n"
            f"• <b>📂 My Channel</b> → pilih channel\n"
            f"• Ketuk <b>▶️ Aktifkan</b> atau <b>⏸ Pause</b>\n\n"
            f"3️⃣ <b>Hapus Repost Sinkron</b>\n"
            f"• Hapus postingan di <b>channelmu sendiri</b>\n"
            f"• Bot otomatis hapus repost di channel utama\n"
            f"• Syarat sinkron berjalan:\n"
            f"  ✅ Bot masih Admin di channelmu\n"
            f"  ✅ Izin <b>Hapus Pesan</b> aktif\n"
            f"  ✅ Fitur Auto-Hapus diaktifkan owner\n"
            f"  ⚠️ Deteksi terjadi saat ada postingan baru berikutnya\n\n"
            f"4️⃣ <b>Notifikasi</b>\n"
            f"• <b>🔔 Notifikasi</b> → atur notif repost, blacklist, status\n\n"
            f"5️⃣ <b>Repost tidak muncul?</b>\n"
            f"• Status channel harus <b>Aktif ▶️</b>\n"
            f"• Bot harus masih jadi <b>Admin</b>\n"
            f"• Konten harus berupa <b>foto atau video</b>\n"
            f"• Periksa kata terlarang (blacklist)\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"📬 Bantuan: @{OWNER_USERNAME or BOT_USERNAME}"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "➕ Tambah Bot ke Channel",
                url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                     f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
            )
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_tutorial] {e}")
    finally:
        await answer_cb(cb)
