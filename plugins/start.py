"""
/start handler — deteksi owner vs user, cek membership, panduan lengkap.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import upsert_user, get_user, get_all_partners, get_partners_by_owner
from utils import check_membership

OWNER_WELCOME = """
╔══════════════════════════════╗
║   🛡️  PANEL OWNER — FESSBOT  ║
╚══════════════════════════════╝

Selamat datang, Owner!

📡 **Cara Kerja Bot**
Bot ini meneruskan setiap postingan foto/video dari channel partner ke channel utama secara otomatis, lengkap dengan identitas channel, waktu post, dan tautan ke postingan asli.

━━━━━━━━━━━━━━━━━━━━━━━
📋 **Daftar Perintah Owner**
━━━━━━━━━━━━━━━━━━━━━━━

`/pause <ID> <alasan>`
→ Hentikan sementara forward dari channel partner

`/run <ID> <alasan>`
→ Aktifkan kembali forward channel partner

`/stats`
→ Statistik singkat: total partner, total repost

`/listpartner`
→ Daftar semua channel partner (halaman 15 per halaman)

━━━━━━━━━━━━━━━━━━━━━━━
ℹ️ Alasan pada /pause dan /run akan otomatis dikirim ke pemilik channel partner.
"""

USER_NOT_JOINED = """
👋 Halo, **{name}**!

Selamat datang di **FessBot** — bot repost otomatis untuk channel Telegram.

━━━━━━━━━━━━━━━━━━━━━━━
⚠️ **Kamu belum bergabung ke channel utama.**

Untuk menggunakan fitur bot ini, kamu harus join dulu ke channel utama kami.
━━━━━━━━━━━━━━━━━━━━━━━
"""

USER_JOINED = """
✅ **Kamu sudah terdaftar, {name}!**

━━━━━━━━━━━━━━━━━━━━━━━
📖 **Panduan Lengkap FessBot**
━━━━━━━━━━━━━━━━━━━━━━━

**Apa itu FessBot?**
Bot ini meneruskan postingan foto/video dari channel kamu ke channel utama secara otomatis, menjangkau lebih banyak audiens.

**Cara Menautkan Channel:**
1. Jadikan bot ini admin di channel kamu
   (minimal hak: _Post Messages_ & _Read Messages_)
2. Channel kamu otomatis terdaftar sebagai **channel partner**
3. Setiap foto/video yang kamu post akan muncul di channel utama

**Yang Ditampilkan di Repost:**
• Foto/video asli
• Caption asli kamu
• Nama & username channel kamu
• Tanggal dan jam posting
• Nama owner (kamu)
• Tombol link ke postingan asli

**Kontrol Channel:**
Gunakan tombol **My Channel** di bawah untuk melihat dan mengatur channel-channel kamu yang terdaftar.

━━━━━━━━━━━━━━━━━━━━━━━
💡 Klik tombol di bawah untuk mulai!
"""

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📂 My Channel")]],
        resize_keyboard=True
    )

@Client.on_message(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "Pengguna"

    # ── Owner ──────────────────────────────────────────────
    if user_id == OWNER_ID:
        all_partners = get_all_partners()
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Statistik", callback_data="owner_stats")],
            [InlineKeyboardButton("📋 Daftar Channel Partner", callback_data="list_partner_0")]
        ])
        await message.reply(OWNER_WELCOME, reply_markup=btn)
        return

    # ── Regular user ───────────────────────────────────────
    joined = await check_membership(client, user_id)
    upsert_user(user_id, {"joined": joined})

    if not joined:
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel Utama", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ Sudah Join — Cek Ulang", callback_data="recheck_join")]
        ])
        await message.reply(
            USER_NOT_JOINED.format(name=user_name),
            reply_markup=btn
        )
    else:
        from datetime import datetime
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Jadikan Bot Admin di Channelku",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users")]
        ])
        await message.reply(
            USER_JOINED.format(name=user_name),
            reply_markup=btn
        )
        await message.reply("Gunakan tombol di bawah untuk navigasi:", reply_markup=main_keyboard())
