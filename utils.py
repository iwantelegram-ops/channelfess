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

_last_bot_msg: dict[int, Message] = {}


def store_msg(user_id: int, msg):
    if msg is not None:
        _last_bot_msg[user_id] = msg


def get_stored_msg(user_id: int):
    return _last_bot_msg.get(user_id)


async def check_membership(client: Client, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
        return member.status.value in ("member", "administrator", "creator")
    except Exception:
        return False


def paginate(data: list, page: int, page_size: int = 8):
    total = len(data)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    chunk = data[page * page_size:(page + 1) * page_size]
    return chunk, total_pages


async def safe_send(coro, retries: int = 5):
    for attempt in range(retries):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value + 2
            if wait > FLOOD_SLEEP_THRESHOLD:
                log.warning(f"[FloodWait] {wait}s — lewati")
                return None
            log.warning(f"[FloodWait] Tunggu {wait}s (percobaan {attempt+1})")
            await asyncio.sleep(wait)
        except (MessageNotModified, MessageIdInvalid):
            return None
        except Exception as e:
            log.error(f"[safe_send] {type(e).__name__}: {e}")
            return None
    return None


async def safe_edit(msg, text: str, markup=None, parse_mode=None):
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


async def answer_cb(cb, text: str = "", show_alert: bool = False):
    try:
        await cb.answer(text, show_alert=show_alert)
    except Exception:
        pass


async def send_or_edit(client, user_id: int, chat_id: int, text: str,
                       markup=None, parse_mode=None):
    """
    Edit pesan terakhir bot jika masih ada, otherwise kirim baru.
    Semua navigasi lewat sini agar chat tidak penuh pesan.
    """
    old_msg = get_stored_msg(user_id)
    if old_msg:
        edited = await safe_edit(old_msg, text, markup=markup, parse_mode=parse_mode)
        if edited:
            store_msg(user_id, edited)
            return edited

    try:
        kwargs = {}
        if markup:
            kwargs["reply_markup"] = markup
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        msg = await client.send_message(chat_id, text, **kwargs)
        store_msg(user_id, msg)
        return msg
    except FloodWait as e:
        await asyncio.sleep(min(e.value + 1, FLOOD_SLEEP_THRESHOLD))
        return None
    except Exception as e:
        log.error(f"[send_or_edit] {e}")
        return None


async def safe_delete(client, chat_id, message_ids, retries: int = 5):
    if isinstance(message_ids, int):
        message_ids = [message_ids]
    for attempt in range(retries):
        try:
            await client.delete_messages(chat_id, message_ids)
            return True
        except FloodWait as e:
            wait = e.value + 2
            if wait > FLOOD_SLEEP_THRESHOLD:
                return False
            await asyncio.sleep(wait)
        except MessageIdInvalid:
            return False
        except Exception as e:
            log.error(f"[safe_delete] {type(e).__name__}: {e}")
            return False
    return False


def progress_bar(val: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = round((val / total) * width)
    return "█" * filled + "░" * (width - filled)


async def blast_message(client: Client, user_ids: list, text: str,
                        parse_mode=None, delay: float = 0.05):
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
