"""
Info Bot & Tutorial Penggunaan — Panel Informasi User.
Desain dan metode diidentikkan dengan struktur mychannel.py
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from config import MAIN_CHANNEL_USERNAME, BOT_USERNAME, OWNER_USERNAME, OWNER_NAME, BOT_NAME, BOT_DESC
from db.helpers import count_partners, get_active_partners, count_users
from db.mongo import posts as posts_col
from utils import safe_edit, answer_cb

log = logging.getLogger("fessbot.infobot")
PM  = ParseMode.HTML

# ═══════════════════════════════════════════════════════════
#  TEXT & MARKUP GENERATORS (Identik dengan metode mychannel.py)
# ═══════════════════════════════════════════════════════════

def _get_info_text_and_markup():
    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts_col.count_documents({})
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
        [InlineKeyboardButton("📢 Kunjungi Channel Utama", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
        [InlineKeyboardButton("📖 Tutorial Penggunaan", callback_data="infobot_tutorial")],
    ])
    return text, markup


def _get_tutorial_text_and_markup():
    SEP = "─" * 28
    text = (
        f"📖 <b>Tutorial {BOT_NAME}</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"1️⃣ <b>Daftarkan Channel</b>\n"
        f"• Buka pengaturan channel\n"
        f"  → <b>Administrator → Tambah Admin</b>\n"
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
        f"  ⚠️ Deteksi terjadi saat ada postingan baru\n\n"
        f"4️⃣ <b>Notifikasi</b>\n"
        f"• <b>🔔 Notifikasi</b> → atur notif repost, blacklist, status\n\n"
        f"5️⃣ <b>Repost tidak muncul?</b>\n"
        f"• Status channel harus <b>Aktif ▶️</b>\n"
        f"• Bot harus masih jadi <b>Admin</b>\n"
        f"• Konten harus berupa <b>foto atau video</b>\n"
        f"• Periksa kata terlarang (blacklist)\n\n"
        f"<code>{SEP}</code>\n"
        f"📬 Bantuan: @{OWNER_USERNAME or BOT_USERNAME}"
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tambah Bot ke Channel", 
                              url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users")],
        [InlineKeyboardButton("🔙 Kembali ke Info Bot", callback_data="infobot_back")]
    ])
    return text, markup


# ═══════════════════════════════════════════════════════════
#  HANDLERS (Identik dengan alur kerja mychannel.py)
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^ℹ️ Info Bot$"), group=1)
async def info_bot_msg(client: Client, message: Message):
    try:
        text, markup = _get_info_text_and_markup()
        await message.reply(text, reply_markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[info_bot_msg] {e}")


@Client.on_callback_query(filters.regex(r"^infobot_tutorial$"))
async def cb_infobot_tutorial(client: Client, cb: CallbackQuery):
    answered = False
    try:
        await answer_cb(cb, "Memuat tutorial...")
        answered = True
        
        text, markup = _get_tutorial_text_and_markup()
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_infobot_tutorial] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^infobot_back$"))
async def cb_infobot_back(client: Client, cb: CallbackQuery):
    answered = False
    try:
        await answer_cb(cb)
        answered = True
        
        text, markup = _get_info_text_and_markup()
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_infobot_back] {e}")
    finally:
        if not answered:
            await answer_cb(cb)
