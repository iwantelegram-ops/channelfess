"""
/start — welcome screen, owner vs user.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import upsert_user, get_maintenance
from utils import check_membership
from datetime import datetime

# ── Teks ──────────────────────────────────────────────────

OWNER_WELCOME = (
    "⚡ **FessBot — Control Panel**\n\n"
    "`System online · All services running`\n\n"
    "Gunakan menu di bawah layar. 👇"
)

USER_NOT_JOINED = (
    "👋 **Halo, {name}!**\n\n"
    "Sebelum lanjut, join **channel utama** dulu ya.\n\n"
    "Tap **Join** → lalu **Cek Ulang**."
)

USER_JOINED = (
    "⚡ **Halo, {name}!**\n\n"
    "**FessBot** otomatis repost foto & video dari channelmu ke channel utama.\n\n"
    "**Setup:**\n"
    "`1.` Tambah bot sebagai **Admin** di channelmu\n"
    "`2.` Channel terdaftar otomatis\n"
    "`3.` Konten di-repost real-time ✅\n\n"
    "Buka **My Channel** untuk mulai. 👇"
)

# ── Keyboards ─────────────────────────────────────────────

def owner_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Dashboard"), KeyboardButton("📋 Partner")],
            [KeyboardButton("📣 Broadcast"), KeyboardButton("🔧 Tools")],
        ],
        resize_keyboard=True,
    )

def user_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📂 My Channel"), KeyboardButton("ℹ️ Info Bot")]],
        resize_keyboard=True,
    )

# ── Handler /start ────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private, group=1)
async def start(client: Client, message: Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "Pengguna"

    # Owner
    if user_id == OWNER_ID:
        await message.reply(OWNER_WELCOME, reply_markup=owner_keyboard())
        return

    # Maintenance
    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(f"🔧 **Bot sedang maintenance**\n\n_{reason}_\n\nCoba lagi nanti ya! 🙏")
        return

    # User
    joined = await check_membership(client, user_id)
    upsert_user(user_id, {"joined": joined, "last_seen": datetime.utcnow()})

    if not joined:
        await message.reply(
            USER_NOT_JOINED.format(name=user_name),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel Utama",
                    url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
                [InlineKeyboardButton("✅ Udah Join — Cek Ulang",
                    callback_data="recheck_join")],
            ])
        )
    else:
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        await message.reply(
            USER_JOINED.format(name=user_name),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Tambah Bot sebagai Admin",
                    url=f"https://t.me/{BOT_USERNAME}?startchannel=true"
                        f"&admin=post_messages+edit_messages+delete_messages+invite_users")],
            ])
        )
        await message.reply("Menu:", reply_markup=user_keyboard())

# ── Info Bot ──────────────────────────────────────────────

@Client.on_message(filters.text & filters.private & filters.regex("^ℹ️ Info Bot$"))
async def info_bot(client: Client, message: Message):
    from db.helpers import count_partners, get_active_partners
    from db.mongo import posts, users
    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts.count_documents({})
    total_u  = users.count_documents({})
    await message.reply(
        f"ℹ️ **FessBot Info**\n"
        f"`{'─' * 24}`\n\n"
        f"👥 Users terdaftar   `{total_u:,}`\n"
        f"📡 Channel partner   `{total_p}` · `{active_p}` aktif\n"
        f"📦 Total repost      `{total_r:,}`\n\n"
        f"🤖 @{BOT_USERNAME}\n"
        f"📢 @{MAIN_CHANNEL_USERNAME}"
    )
