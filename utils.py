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
    except Exception:
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
#  FLOOD-SAFE SEND
# ═══════════════════════════════════════════════════════════

async def safe_send(coro, retries: int = 5):
    """
    Jalankan coroutine dengan penanganan FloodWait otomatis.

    FIX: Coroutine Pyrogram tidak bisa di-reuse (RuntimeError setelah
    await pertama gagal). Karena itu retry hanya dilakukan untuk
    FloodWait — dan coro hanya di-await sekali. Jika kena FloodWait,
    tunggu lalu kembalikan None (caller harus retry dari awal jika perlu).
    Untuk kasus repost biasa, satu attempt sudah cukup.
    """
    try:
        return await coro
    except FloodWait as e:
        wait = e.value + 2
        if wait > FLOOD_SLEEP_THRESHOLD:
            log.warning(f"[FloodWait] {wait}s — lewati")
            return None
        log.warning(f"[FloodWait] Tunggu {wait}s lalu batal (coroutine tidak bisa di-retry)")
        await asyncio.sleep(wait)
        return None
    except (MessageNotModified, MessageIdInvalid):
        return None
    except Exception as e:
        log.error(f"[safe_send] {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  SAFE EDIT  — digunakan HANYA untuk inline keyboard callbacks
# ═══════════════════════════════════════════════════════════

async def safe_edit(msg, text: str, markup=None, parse_mode=None):
    """Edit pesan inline; return edited message atau None kalau gagal."""
    if msg is None:
        return None
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
        log.debug(f"[safe_edit] {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  SAFE CALLBACK ANSWER  — selalu berhasil
# ═══════════════════════════════════════════════════════════

async def answer_cb(cb, text: str = "", show_alert: bool = False):
    """Panggil cb.answer() dengan aman — tidak pernah throw."""
    try:
        await cb.answer(text, show_alert=show_alert)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  NAV HELPER — SELALU kirim pesan baru (tidak pernah edit)
# ═══════════════════════════════════════════════════════════
#
# Alasan: edit bergantung pada ID pesan lama yang mungkin sudah
# tidak ada, dihapus user, atau tidak diketahui bot. Akibatnya
# tombol tidak merespon sama sekali. Solusi: selalu reply/send baru.
#
# store_msg / get_stored_msg tetap ada untuk kompatibilitas backward,
# tapi tidak lagi dipakai untuk menentukan alur navigasi.

_last_bot_msg: dict[int, Message] = {}


def store_msg(user_id: int, msg):
    if msg is not None:
        _last_bot_msg[user_id] = msg


def get_stored_msg(user_id: int):
    return _last_bot_msg.get(user_id)


async def nav_to(client, user_id: int, chat_id: int, text: str,
                 inline_markup=None, reply_markup=None, parse_mode=None):
    """
    Kirim pesan baru ke chat_id.
    Jika inline_markup ada, pakai inline_markup.
    Jika reply_markup ada, pakai reply_markup.
    Return pesan yang dikirim, atau None bila gagal.
    """
    try:
        kwargs = {}
        if inline_markup:
            kwargs["reply_markup"] = inline_markup
        elif reply_markup:
            kwargs["reply_markup"] = reply_markup
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        msg = await client.send_message(chat_id, text, **kwargs)
        store_msg(user_id, msg)
        return msg
    except FloodWait as e:
        await asyncio.sleep(min(e.value + 1, FLOOD_SLEEP_THRESHOLD))
        return None
    except Exception as e:
        log.error(f"[nav_to] gagal kirim: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  PROGRESS BAR
# ═══════════════════════════════════════════════════════════

def progress_bar(val: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = round((val / total) * width)
    return "█" * filled + "░" * (width - filled)


# ═══════════════════════════════════════════════════════════
#  SAFE DELETE — khusus delete_messages (return bool, bukan Message)
# ═══════════════════════════════════════════════════════════

async def safe_delete(client, chat_id, message_ids, retries: int = 3):
    """
    Hapus pesan dengan penanganan FloodWait otomatis. Return True jika berhasil.

    FIX: kurangi retries default dari 5 ke 3 untuk hemat waktu;
    delete_messages tidak perlu banyak retry karena bukan idempotent risk.
    """
    if isinstance(message_ids, int):
        message_ids = [message_ids]
    for attempt in range(retries):
        try:
            await client.delete_messages(chat_id, message_ids)
            return True
        except FloodWait as e:
            wait = e.value + 2
            if wait > FLOOD_SLEEP_THRESHOLD:
                log.warning(f"[safe_delete] FloodWait {wait}s terlalu lama — lewati")
                return False
            log.warning(f"[safe_delete] FloodWait {wait}s (percobaan {attempt+1})")
            await asyncio.sleep(wait)
        except MessageIdInvalid:
            return True  # FIX: pesan sudah tidak ada = sukses (sudah dihapus)
        except Exception as e:
            log.error(f"[safe_delete] {type(e).__name__}: {e}")
            return False
    return False


# ═══════════════════════════════════════════════════════════
#  BROADCAST HELPER
# ═══════════════════════════════════════════════════════════

async def blast_message(client: Client, user_ids: list, text: str,
                        parse_mode=None, delay: float = 0.05):
    """Kirim pesan ke banyak user. Return (success_count, fail_count)."""
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
            wait = min(e.value + 2, FLOOD_SLEEP_THRESHOLD)
            await asyncio.sleep(wait)
            try:
                kwargs2 = {}
                if parse_mode:
                    kwargs2["parse_mode"] = parse_mode
                await client.send_message(uid, text, **kwargs2)
                success += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(delay)
    return success, fail
