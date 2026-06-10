"""
/start — deteksi owner vs user, welcome screen, panduan.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import upsert_user, get_user, get_maintenance
from utils import check_membership

OWNER_WELCOME = """
⚡ **FessBot — Control Panel**

`System online · All services running`

Pilih menu di bawah untuk mulai kelola bot.
"""

USER_NOT_JOINED = """
👋 Yo, **{name}**!

Sebelum lanjut, kamu perlu join **channel utama** dulu.

> Di sanalah semua postingan channelmu bakal tampil & dilihat orang banyak 🔥

Tap **Join** → lalu **Cek Ulang**.
"""

USER_JOINED = """
⚡ **Halo, {name}!**

**FessBot** otomatis repost foto & video dari channelmu ke channel utama — lebih banyak reach, tanpa effort ekstra.

**Setup cepat:**
`1.` Tambah bot sebagai **Admin** di channelmu
`2.` Channel langsung terdaftar otomatis
`3.` Setiap konten di-repost real-time ✅

Buka **My Channel** di bawah untuk mulai. 👇
"""

def owner_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Dashboard"), KeyboardButton("📋 Channel Partner")],
            [KeyboardButton("📣 Broadcast"), KeyboardButton("🔧 Tools")],
        ],
        resize_keyboard=True
    )

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📂 My Channel"), KeyboardButton("ℹ️ Info Bot")]],
        resize_keyboard=True
    )

@Client.on_message(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "Pengguna"

    # ── Owner ──────────────────────────────────────────────
    if user_id == OWNER_ID:
        btn = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Dashboard", callback_data="owner_stats"),
                InlineKeyboardButton("📋 Partner", callback_data="list_partner_0"),
            ],
            [
                InlineKeyboardButton("📣 Broadcast", callback_data="broadcast_menu"),
                InlineKeyboardButton("🔎 Cari Channel", callback_data="search_channel_prompt"),
            ],
            [
                InlineKeyboardButton("🚫 Blacklist", callback_data="blacklist_menu"),
                InlineKeyboardButton("🔧 Maintenance", callback_data="maintenance_menu"),
            ],
        ])
        await message.reply(OWNER_WELCOME, reply_markup=btn)
        await message.reply("Atau gunakan shortcut keyboard:", reply_markup=owner_keyboard())
        return

    # ── Cek maintenance ────────────────────────────────────
    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(
            f"🔧 **Bot sedang maintenance**\n\n_{reason}_\n\nCoba lagi nanti ya! 🙏"
        )
        return

    # ── Regular user ───────────────────────────────────────
    joined = await check_membership(client, user_id)
    upsert_user(user_id, {"joined": joined, "last_seen": __import__("datetime").datetime.utcnow()})

    if not joined:
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel Utama", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ Udah Join — Cek Ulang", callback_data="recheck_join")]
        ])
        await message.reply(USER_NOT_JOINED.format(name=user_name), reply_markup=btn)
    else:
        from datetime import datetime
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Tambah Bot sebagai Admin",
             url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users")]
        ])
        await message.reply(USER_JOINED.format(name=user_name), reply_markup=btn)
        await message.reply("Pilih menu:", reply_markup=main_keyboard())

@Client.on_message(filters.text & filters.private & filters.regex("^ℹ️ Info Bot$"))
async def info_bot(client: Client, message: Message):
    from db.helpers import count_partners, get_active_partners
    from db.mongo import posts, users
    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts.count_documents({})
    total_u  = users.count_documents({})
    await message.reply(
        f"ℹ️ **FessBot Info**\n\n"
        f"👥 Users terdaftar  : `{total_u:,}`\n"
        f"📡 Channel partner  : `{total_p}` (`{active_p}` aktif)\n"
        f"📦 Total repost     : `{total_r:,}`\n\n"
        f"🤖 Bot: @{BOT_USERNAME}\n"
        f"📢 Channel: @{MAIN_CHANNEL_USERNAME}"
    )
