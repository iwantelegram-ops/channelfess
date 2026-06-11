"""
Guard — Rate limiting, ban check, /cancel.
Group -1 agar berjalan SEBELUM semua handler lain.
Jika user banned atau kena rate-limit, StopPropagation mencegah handler lain jalan.
"""
import logging
from pyrogram import Client, filters, StopPropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from config import OWNER_ID
from db.helpers import (
    get_maintenance, is_banned, check_rate_limit, record_rate_hit, get_bot_setting
)

log = logging.getLogger("fessbot.guard")
PM  = ParseMode.HTML


@Client.on_message(filters.command("cancel") & filters.private, group=0)
async def cmd_cancel(client: Client, message: Message):
    """Reset semua pending input state untuk user ini."""
    uid = message.from_user.id
    cleared = False

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
        await message.reply("ℹ️ Tidak ada aksi yang aktif.", parse_mode=PM)


@Client.on_message(filters.private, group=-1)
async def global_guard(client: Client, message: Message):
    log.info(f"[guard] masuk: user_id={message.from_user.id if message.from_user else 'none'}, text={message.text!r}")  # ← TAMBAH INI
  #  user_id = message.from_user.id if message.from_user else None
    ...
    """
    Gate keeper — berjalan di group -1 (SEBELUM semua handler lain).
    Jika user diblokir atau kena rate-limit: kirim peringatan + StopPropagation.
    Jika lolos: catat rate hit dan biarkan handler lain jalan.
    """
    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id == OWNER_ID:
        return  # Owner dan pesan tanpa user: lewati guard

    # ── Ban check ───────────────────────────────────────────
    try:
        if is_banned(user_id):
            await message.reply(
                "🚫 <b>Akun kamu diblokir dari menggunakan bot ini.</b>\n\n"
                "Hubungi admin jika ini adalah kesalahan.",
                parse_mode=PM,
            )
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception as e:
        log.error(f"[guard] ban check error: {e}")

    # ── Rate limit check ────────────────────────────────────
    try:
        rate_enabled = get_bot_setting("rate_limit_enabled", True)
        if rate_enabled:
            if not check_rate_limit(user_id, limit=20):
                await message.reply(
                    "⚡ <b>Terlalu banyak permintaan!</b>\n\n"
                    "Tunggu sebentar sebelum mencoba lagi.",
                    parse_mode=PM,
                )
                raise StopPropagation
            record_rate_hit(user_id)
    except StopPropagation:
        raise
    except Exception as e:
        log.error(f"[guard] rate limit error: {e}")
