"""
Guard — Rate limiting, ban check, /cancel, maintenance guard.
Group paling rendah (99) agar jalan terakhir sebagai fallback.
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from config import OWNER_ID
from db.helpers import (
    get_maintenance, is_banned, check_rate_limit, record_rate_hit, get_bot_setting
)

log = logging.getLogger("fessbot.guard")
PM  = ParseMode.HTML

# Set state yang perlu di-clear saat /cancel
_pending_states: list = []


def register_pending_set(s: set):
    """Daftarkan set state yang harus di-clear saat /cancel."""
    _pending_states.append(s)


@Client.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client: Client, message: Message):
    """Reset semua pending input state untuk user ini."""
    uid = message.from_user.id
    cleared = False

    # Import semua state sets dari plugins
    try:
        from plugins.owner import (
            _search_pending, _bl_add_pending, _bl_del_pending,
            _ban_pending, _caption_pending, _maint_reason,
        )
        for s in (_search_pending, _bl_add_pending, _bl_del_pending,
                  _ban_pending, _caption_pending, _maint_reason):
            if uid in s:
                s.discard(uid)
                cleared = True
    except Exception:
        pass

    try:
        from plugins.broadcast import _bc_text_pending, _bc_state
        if uid in _bc_text_pending:
            _bc_text_pending.discard(uid)
            _bc_state.pop(uid, None)
            cleared = True
    except Exception:
        pass

    if cleared:
        await message.reply(
            "✅ <b>Dibatalkan.</b>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="home")
            ]]),
            parse_mode=PM,
        )
    else:
        await message.reply(
            "ℹ️ Tidak ada aksi yang aktif.",
            parse_mode=PM,
        )


@Client.on_message(filters.private, group=99)
async def global_guard(client: Client, message: Message):
    """
    Catch-all guard — rate limit & ban check untuk semua pesan private.
    Berjalan di group 99 (terakhir) jadi tidak menghalangi plugin lain.
    """
    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id == OWNER_ID:
        return

    # Ban check
    if is_banned(user_id):
        await message.reply(
            "🚫 <b>Akun kamu diblokir dari menggunakan bot ini.</b>",
            parse_mode=PM,
        )
        return

    # Rate limit check
    rate_enabled = get_bot_setting("rate_limit_enabled", True)
    if rate_enabled:
        if not check_rate_limit(user_id, limit=20):
            await message.reply(
                "⚡ <b>Terlalu banyak permintaan!</b>\n\nTunggu sebentar sebelum mencoba lagi.",
                parse_mode=PM,
            )
            return
        record_rate_hit(user_id)
