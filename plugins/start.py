"""
/start — Welcome screen dengan full inline keyboard.
Tidak ada reply keyboard (bottom bar) sama sekali.
Rate-limit & ban check sudah ditangani global_guard (group -1).
"""
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME, BOT_NAME
from db.helpers import (
    upsert_user, get_maintenance, count_partners, get_active_partners,
)
from db.mongo import posts
from utils import check_membership, store_msg, send_or_edit, answer_cb, safe_edit

log = logging.getLogger("fessbot.start")
PM  = ParseMode.HTML
SEP = "─" * 30


# ═══════════════════════════════════════════════════════════
#  MARKUP GENERATORS
# ═══════════════════════════════════════════════════════════

def owner_main_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Dashboard",    callback_data="owner_dashboard"),
            InlineKeyboardButton("📋 Partner",      callback_data="owner_partner_0"),
        ],
        [
            InlineKeyboardButton("📣 Broadcast",    callback_data="owner_broadcast"),
            InlineKeyboardButton("🔧 Tools",        callback_data="owner_tools"),
        ],
        [
            InlineKeyboardButton("📝 Aktivitas",    callback_data="owner_activity"),
            InlineKeyboardButton("⚙️ Pengaturan",   callback_data="owner_settings"),
        ],
        [
            InlineKeyboardButton("🚫 Banned Users", callback_data="owner_banned_list"),
            InlineKeyboardButton("📤 Export Data",  callback_data="owner_export"),
        ],
    ])


def user_main_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 My Channel",     callback_data="user_channels_0"),
            InlineKeyboardButton("📊 Statistik Saya", callback_data="user_stats"),
        ],
        [
            InlineKeyboardButton("🔔 Notifikasi",     callback_data="user_notif"),
            InlineKeyboardButton("ℹ️ Info Bot",        callback_data="user_info"),
        ],
        [
            InlineKeyboardButton("📖 Tutorial",       callback_data="user_tutorial"),
            InlineKeyboardButton("🆘 Bantuan",        callback_data="user_help"),
        ],
    ])


def not_joined_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📢 Join Channel Utama",
            url=f"https://t.me/{MAIN_CHANNEL_USERNAME}",
        )],
        [InlineKeyboardButton(
            "✅ Sudah Join — Verifikasi",
            callback_data="recheck_join",
        )],
    ])


def setup_admin_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "➕ Tambah Bot sebagai Admin",
            url=(
                f"https://t.me/{BOT_USERNAME}"
                f"?startchannel=true"
                f"&admin=post_messages+edit_messages+delete_messages+invite_users"
            ),
        )],
        [InlineKeyboardButton("📂 My Channel", callback_data="user_channels_0")],
    ])


# ═══════════════════════════════════════════════════════════
#  /start HANDLER
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.command("start") & filters.private, group=0)
async def start(client: Client, message: Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "Pengguna"
    log.info(f"[start] user_id={user_id}")

    try:
        # ── Owner ──────────────────────────────────────────────
        if user_id == OWNER_ID:
            try:
                total_p  = count_partners()
                active_p = len(get_active_partners())
                total_r  = posts.count_documents({})
            except Exception as e:
                log.error(f"[start/owner] DB error: {e}")
                total_p = active_p = total_r = 0

            text = (
                f"⚡ <b>{BOT_NAME} v3 — Owner Panel</b>\n"
                f"<code>{SEP}</code>\n\n"
                f"📡 Partner    <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
                f"📦 All-time   <code>{total_r}</code> repost\n\n"
                f"Selamat datang kembali, pilih menu: 👇"
            )
            msg = await message.reply(text, reply_markup=owner_main_markup(), parse_mode=PM)
            store_msg(user_id, msg)
            return

        # ── Maintenance ────────────────────────────────────────
        try:
            maint = get_maintenance()
        except Exception as e:
            log.error(f"[start] maintenance check error: {e}")
            maint = {"active": False}

        if maint.get("active"):
            reason = maint.get("reason", "Sedang dalam pemeliharaan.")
            await message.reply(
                f"🔧 <b>Bot Sedang Maintenance</b>\n\n"
                f"<i>{reason}</i>\n\n"
                f"Coba lagi beberapa saat. 🙏",
                parse_mode=PM,
            )
            return

        # ── User — cek join ────────────────────────────────────
        try:
            joined = await check_membership(client, user_id)
        except Exception as e:
            log.error(f"[start] membership check error: {e}")
            joined = False

        try:
            upsert_user(user_id, {
                "joined":    joined,
                "last_seen": datetime.now(timezone.utc),
                "username":  message.from_user.username or "",
                "name":      user_name,
            })
        except Exception as e:
            log.error(f"[start] upsert_user error: {e}")

        if not joined:
            msg = await message.reply(
                f"👋 <b>Halo, {user_name}!</b>\n\n"
                f"Untuk menggunakan <b>{BOT_NAME}</b>, kamu perlu bergabung "
                f"ke channel utama kami terlebih dahulu.\n\n"
                f"1️⃣ Klik <b>Join Channel Utama</b>\n"
                f"2️⃣ Klik <b>Sudah Join — Verifikasi</b>\n\n"
                f"<i>Proses otomatis, tanpa perlu kirim pesan apapun.</i>",
                reply_markup=not_joined_markup(),
                parse_mode=PM,
            )
            store_msg(user_id, msg)
            return

        # ── User sudah join ────────────────────────────────────
        try:
            upsert_user(user_id, {"joined": True, "joined_at": datetime.now(timezone.utc)})
        except Exception as e:
            log.error(f"[start] upsert joined_at error: {e}")

        text = (
            f"⚡ <b>Halo, {user_name}!</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"<b>{BOT_NAME}</b> meneruskan konten dari channelmu "
            f"ke channel utama secara real-time.\n\n"
            f"<b>🚀 Cara mulai:</b>\n"
            f"1️⃣  Tambahkan bot sebagai <b>Admin</b> di channelmu\n"
            f"2️⃣  Channel otomatis terdaftar\n"
            f"3️⃣  Konten di-repost real-time ✅\n\n"
            f"Pilih menu di bawah untuk mulai:"
        )
        msg = await message.reply(text, reply_markup=user_main_markup(), parse_mode=PM)
        store_msg(user_id, msg)

    except Exception as e:
        log.error(f"[start] unhandled exception: {e}", exc_info=True)
        try:
            await message.reply(
                f"❌ <b>Terjadi kesalahan internal.</b>\n\n"
                f"<code>{type(e).__name__}: {e}</code>\n\n"
                f"Coba lagi dalam beberapa detik.",
                parse_mode=PM,
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  CALLBACK: HOME (kembali ke main menu)
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^home$"))
async def cb_home(client: Client, cb: CallbackQuery):
    try:
        user_id   = cb.from_user.id
        user_name = cb.from_user.first_name or "Pengguna"

        if user_id == OWNER_ID:
            try:
                total_p  = count_partners()
                active_p = len(get_active_partners())
                total_r  = posts.count_documents({})
            except Exception as e:
                log.error(f"[cb_home/owner] DB error: {e}")
                total_p = active_p = total_r = 0

            text = (
                f"⚡ <b>{BOT_NAME} v3 — Owner Panel</b>\n"
                f"<code>{SEP}</code>\n\n"
                f"📡 Partner    <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
                f"📦 All-time   <code>{total_r}</code> repost\n\n"
                f"Pilih menu: 👇"
            )
            await safe_edit(cb.message, text, markup=owner_main_markup(), parse_mode=PM)
        else:
            text = (
                f"⚡ <b>Halo, {user_name}!</b>\n"
                f"<code>{SEP}</code>\n\n"
                f"Pilih menu di bawah:"
            )
            await safe_edit(cb.message, text, markup=user_main_markup(), parse_mode=PM)

    except Exception as e:
        log.error(f"[cb_home] {e}", exc_info=True)
    finally:
        await answer_cb(cb)
