"""
/start — welcome screen, owner vs user.
Parse mode: HTML di seluruh file.
"""
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from config import OWNER_ID, MAIN_CHANNEL_USERNAME, BOT_USERNAME
from db.helpers import upsert_user, get_maintenance
from utils import check_membership
from datetime import datetime

PM = enums.ParseMode.HTML

# ── Teks ──────────────────────────────────────────────────

OWNER_WELCOME = (
    "⚡ <b>FessBot — Control Panel</b>\n\n"
    "<code>System online · All services running</code>\n\n"
    "Gunakan menu di bawah layar. 👇"
)

USER_NOT_JOINED = (
    "👋 <b>Halo, {name}!</b>\n\n"
    "Sebelum lanjut, join <b>channel utama</b> dulu ya.\n\n"
    "Tap <b>Join</b> → lalu <b>Cek Ulang</b>."
)

USER_JOINED = (
    "⚡ <b>Halo, {name}!</b>\n\n"
    "<b>FessBot</b> otomatis repost foto &amp; video dari channelmu ke channel utama.\n\n"
    "<b>Setup:</b>\n"
    "<code>1.</code> Tambah bot sebagai <b>Admin</b> di channelmu\n"
    "<code>2.</code> Channel terdaftar otomatis\n"
    "<code>3.</code> Konten di-repost real-time ✅\n\n"
    "Buka <b>My Channel</b> untuk mulai. 👇"
)

# ── Keyboards ─────────────────────────────────────────────

def owner_keyboard():
    """Keyboard utama owner — dipakai di /start dan di-import owner.py."""
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
        await message.reply(OWNER_WELCOME, reply_markup=owner_keyboard(), parse_mode=PM)
        return

    # Maintenance
    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang maintenance.")
        await message.reply(
            f"🔧 <b>Bot sedang maintenance</b>\n\n<i>{reason}</i>\n\nCoba lagi nanti ya! 🙏",
            parse_mode=PM
        )
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
            ]),
            parse_mode=PM
        )
    else:
        upsert_user(user_id, {"joined": True, "joined_at": datetime.utcnow()})
        await message.reply(
            USER_JOINED.format(name=user_name),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Tambah Bot sebagai Admin",
                    url=f"https://t.me/{BOT_USERNAME}?startchannel=true"
                        f"&admin=post_messages+edit_messages+delete_messages+invite_users")],
            ]),
            parse_mode=PM
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
        f"ℹ️ <b>FessBot Info</b>\n"
        f"<code>{'─' * 24}</code>\n\n"
        f"👥 Users terdaftar   <code>{total_u}</code>\n"
        f"📡 Channel partner   <code>{total_p}</code> · <code>{active_p}</code> aktif\n"
        f"📦 Total repost      <code>{total_r}</code>\n\n"
        f"🤖 @{BOT_USERNAME}\n"
        f"📢 @{MAIN_CHANNEL_USERNAME}",
        parse_mode=PM
    )
