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
#  ✅ RECHECK JOIN
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^recheck_join$"))
async def cb_recheck_join(client: Client, cb):
    user_id   = cb.from_user.id
    user_name = cb.from_user.first_name or "Pengguna"
    try:
        joined = await check_membership(client, user_id)
        if not joined:
            await answer_cb(cb, "❌ Kamu belum join. Coba join dulu ya!", show_alert=True)
            return

        upsert_user(user_id, {
            "joined":    True,
            "joined_at": datetime.now(timezone.utc),
        })
        await answer_cb(cb, "✅ Berhasil! Selamat datang.")
        welcome_text = (
            f"⚡ <b>Halo, {user_name}!</b>\n\n"
            f"<b>FessBot</b> otomatis meneruskan foto &amp; video dari channelmu "
            f"ke channel utama.\n\n"
            f"<b>Cara setup:</b>\n"
            f"1️⃣  Tambahkan bot sebagai <b>Admin</b> di channelmu\n"
            f"2️⃣  Channel otomatis terdaftar\n"
            f"3️⃣  Konten di-repost real-time ✅\n\n"
            f"Buka <b>My Channel</b> untuk mulai. 👇"
        )
        await client.send_message(
            cb.message.chat.id, welcome_text,
            reply_markup=user_keyboard(), parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_recheck_join] {e}")
        await answer_cb(cb, "❌ Error, coba lagi.", show_alert=True)


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
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Kunjungi Channel Utama",
                             url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")
    ]])
    await message.reply(text, reply_markup=markup, parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  ❓ Bantuan
# ═══════════════════════════════════════════════════════════

# ── Halaman bantuan ──────────────────────────────────────────
def _bantuan_pages(bot_username: str):
    return [
        # Halaman 1 — Apa itu FessBot
        (
            f"❓ <b>Bantuan FessBot</b>  <code>1/5</code>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"🤖 <b>Apa itu {BOT_NAME}?</b>\n\n"
            f"{BOT_NAME} adalah bot yang secara otomatis\n"
            f"meneruskan (<i>repost</i>) foto &amp; video dari\n"
            f"channel kamu ke <b>channel utama</b>.\n\n"
            f"Semua konten tampil rapi dengan\n"
            f"kredit ke channel asalmu. ✨\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"<i>Ketuk ▶️ untuk lanjut</i>"
        ),
        # Halaman 2 — Cara daftar
        (
            f"❓ <b>Bantuan FessBot</b>  <code>2/5</code>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"📡 <b>Cara Daftarkan Channel</b>\n\n"
            f"1️⃣  Buka <b>pengaturan channel</b> kamu\n"
            f"2️⃣  Pilih <b>Administrator</b> → <b>Tambah Admin</b>\n"
            f"3️⃣  Cari <b>@{bot_username}</b>\n"
            f"4️⃣  Aktifkan izin:\n"
            f"     ✅ Kirim Pesan\n"
            f"     ✅ Edit Pesan\n"
            f"     ✅ Hapus Pesan\n"
            f"5️⃣  Simpan → channel <b>otomatis terdaftar!</b>\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"<i>◀️ Kembali · ▶️ Lanjut</i>"
        ),
        # Halaman 3 — Aktifkan & pause
        (
            f"❓ <b>Bantuan FessBot</b>  <code>3/5</code>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"▶️ <b>Aktifkan / Pause Repost</b>\n\n"
            f"• Ketuk <b>📂 My Channel</b> di menu\n"
            f"• Pilih channel yang ingin dikelola\n"
            f"• Ketuk <b>▶️ Aktifkan</b> untuk mulai repost\n"
            f"• Ketuk <b>⏸ Pause</b> untuk hentikan sementara\n\n"
            f"⚠️ <b>Repost tidak muncul?</b>\n"
            f"• Cek status channel → harus <b>Aktif</b>\n"
            f"• Pastikan bot masih jadi <b>Admin</b>\n"
            f"• Konten harus berupa <b>foto atau video</b>\n"
            f"• Periksa apakah ada kata terlarang\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"<i>◀️ Kembali · ▶️ Lanjut</i>"
        ),
        # Halaman 4 — Sinkron hapus
        (
            f"❓ <b>Bantuan FessBot</b>  <code>4/5</code>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"🗑 <b>Cara Hapus Repost di Channel Utama</b>\n\n"
            f"Jika kamu <b>menghapus postingan</b> di\n"
            f"channel kamu sendiri, bot akan otomatis\n"
            f"menghapus repost-nya di channel utama.\n\n"
            f"<b>Syarat agar sinkron bekerja:</b>\n"
            f"✅ Bot masih jadi Admin di channelmu\n"
            f"✅ Izin <b>Hapus Pesan</b> aktif di bot\n"
            f"✅ Fitur <b>Auto-Hapus Repost</b> diaktifkan\n"
            f"   oleh owner bot\n\n"
            f"⏱ Penghapusan terdeteksi saat ada\n"
            f"postingan baru berikutnya dari channelmu.\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"<i>◀️ Kembali · ▶️ Lanjut</i>"
        ),
        # Halaman 5 — Notifikasi & kontak
        (
            f"❓ <b>Bantuan FessBot</b>  <code>5/5</code>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"🔔 <b>Pengaturan Notifikasi</b>\n\n"
            f"Ketuk <b>🔔 Notifikasi</b> di menu untuk\n"
            f"atur notif yang kamu terima:\n"
            f"• ✅ Notif saat repost berhasil\n"
            f"• ✅ Notif saat repost ditolak (blacklist)\n"
            f"• ✅ Notif status bot di channelmu\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"📬 <b>Butuh bantuan lebih?</b>\n"
            f"Hubungi owner: @{OWNER_USERNAME or BOT_USERNAME}\n\n"
            f"<i>Selesai! Ketuk ◀️ untuk kembali ke awal.</i>"
        ),
    ]


def _bantuan_markup(page: int, total: int):
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"bantuan_page_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="noop_bantuan"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"bantuan_page_{page+1}"))
    rows = [nav]
    if page == 1:  # halaman cara daftar — tampilkan tombol add bot
        rows.append([InlineKeyboardButton(
            "➕ Tambah Bot ke Channel",
            url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                 f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
        )])
    return InlineKeyboardMarkup(rows)


@Client.on_message(filters.text & filters.private & filters.regex(r"^❓ Bantuan$"), group=1)
async def bantuan(client: Client, message: Message):
    pages  = _bantuan_pages(BOT_USERNAME)
    text   = pages[0]
    markup = _bantuan_markup(0, len(pages))
    await client.send_message(message.chat.id, text, reply_markup=markup, parse_mode=PM)


@Client.on_callback_query(filters.regex(r"^bantuan_page_(\d+)$"))
async def cb_bantuan_page(client: Client, cb):
    page   = int(cb.matches[0].group(1))
    pages  = _bantuan_pages(BOT_USERNAME)
    total  = len(pages)
    page   = max(0, min(page, total - 1))
    markup = _bantuan_markup(page, total)
    try:
        await cb.message.edit_text(pages[page], reply_markup=markup, parse_mode=PM)
    except Exception:
        pass
    await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^noop_bantuan$"))
async def cb_noop_bantuan(client: Client, cb):
    await answer_cb(cb)
