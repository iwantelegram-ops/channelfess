"""Shared utilities: membership check, pagination, flood-safe send, nav helper."""
import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import (
    UserNotParticipant, ChatAdminRequired, PeerIdInvalid,
    FloodWait, MessageNotModified, MessageIdInvalid,
)
from pyrogram.types import Message
from config import MAIN_CHANNEL_ID, FLOOD_SLEEP_THRESHOLD

log = logging.getLogger("fessbot.utils")


# ═══════════════════════════════════════════════════════════
#  MEMBERSHIP CHECK
# ═══════════════════════════════════════════════════════════

async def check_membership(client: Client, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
        return member.status.value in ("member", "administrator", "creator")
    except (UserNotParticipant, ChatAdminRequired, PeerIdInvalid, Exception):
        return False


# ═══════════════════════════════════════════════════════════
#  PAGINATION
# ═══════════════════════════════════════════════════════════

def paginate(data: list, page: int, page_size: int = 8):
    total = len(data)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    chunk = data[page * page_size:(page + 1) * page_size]
    return chunk, total_pages


# ═══════════════════════════════════════════════════════════
#  FLOOD-SAFE SEND / EDIT
# ═══════════════════════════════════════════════════════════

async def safe_send(coro, retries: int = 5):
    """
    Jalankan coroutine Telegram dengan penanganan FloodWait otomatis.
    - Exponential backoff jika FloodWait kecil
    - Skip jika FloodWait > FLOOD_SLEEP_THRESHOLD
    """
    for attempt in range(retries):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value + 2
            if wait > FLOOD_SLEEP_THRESHOLD:
                log.warning(f"[FloodWait] {wait}s terlalu lama, lewati.")
                return None
            log.warning(f"[FloodWait] Tunggu {wait}s (percobaan {attempt+1}/{retries})")
            await asyncio.sleep(wait)
        except MessageNotModified:
            return None
        except MessageIdInvalid:
            return None
        except Exception as e:
            log.error(f"[safe_send] Error: {type(e).__name__}: {e}")
            return None
    log.error("[safe_send] Semua percobaan gagal.")
    return None


async def safe_edit(msg, text: str, markup=None, parse_mode=None):
    """Edit pesan dengan penanganan error."""
    try:
        kwargs = {"reply_markup": markup}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        return await msg.edit_text(text, **kwargs)
    except (MessageNotModified, MessageIdInvalid):
        return None
    except FloodWait as e:
        await asyncio.sleep(min(e.value + 1, 10))
        return None
    except Exception as e:
        log.error(f"[safe_edit] {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  NAV HELPER — "halaman berubah, bukan pesan baru"
# ═══════════════════════════════════════════════════════════

# Simpan ID pesan terakhir yang dikirim bot ke user
_last_bot_msg: dict[int, Message] = {}


def store_msg(user_id: int, msg: Message):
    """Simpan referensi pesan bot terbaru untuk user ini."""
    _last_bot_msg[user_id] = msg


def get_stored_msg(user_id: int):
    return _last_bot_msg.get(user_id)


async def nav_to(client, user_id: int, chat_id: int, text: str,
                 inline_markup=None, reply_markup=None, parse_mode=None):
    """
    Navigasi ke 'halaman' baru:
    1. Coba edit pesan terakhir (pesan berubah, bukan baru)
    2. Jika gagal (pesan terlalu lama/dihapus), kirim pesan baru
    """
    prev = _last_bot_msg.get(user_id)
    edited = None

    if prev:
        edited = await safe_edit(prev, text, markup=inline_markup, parse_mode=parse_mode)

    if not edited:
        kwargs = {}
        if inline_markup:
            kwargs["reply_markup"] = inline_markup
        elif reply_markup:
            kwargs["reply_markup"] = reply_markup
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            msg = await client.send_message(chat_id, text, **kwargs)
            store_msg(user_id, msg)
            return msg
        except Exception as e:
            log.error(f"[nav_to] send gagal: {e}")
            return None
    else:
        store_msg(user_id, edited)
        return edited


# ═══════════════════════════════════════════════════════════
#  PROGRESS BAR
# ═══════════════════════════════════════════════════════════

def progress_bar(val: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = round((val / total) * width)
    return "█" * filled + "░" * (width - filled)


# ═══════════════════════════════════════════════════════════
#  BROADCAST HELPER
# ═══════════════════════════════════════════════════════════

async def blast_message(client: Client, user_ids: list, text: str,
                        parse_mode=None, delay: float = 0.05):
    """Kirim broadcast ke list user_ids. Return (success, fail)."""
    from config import FLOOD_SLEEP_THRESHOLD
    success = 0
    fail    = 0
    for uid in user_ids:
        try:
            kwargs = {}
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            await client.send_message(uid, text, **kwargs)
            success += 1
        except FloodWait as e:
            wait = e.value + 2
            if wait > FLOOD_SLEEP_THRESHOLD:
                log.warning(f"[broadcast] FloodWait {wait}s — berhenti sementara")
            await asyncio.sleep(min(wait, FLOOD_SLEEP_THRESHOLD))
            try:
                await client.send_message(uid, text)
                success += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(delay)
    return success, fail
