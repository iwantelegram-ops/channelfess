"""
Broadcast — full inline keyboard, edit-in-place.
"""
import logging
import functools
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ParseMode

from config import OWNER_ID, BROADCAST_DELAY
from db.helpers import (
    get_all_user_ids, get_all_partners,
    save_broadcast, get_broadcast_history,
    count_users,
)
from utils import safe_edit, blast_message, store_msg, answer_cb

log = logging.getLogger("fessbot.broadcast")
PM  = ParseMode.HTML
SEP = "─" * 30

_bc_state: dict[int, dict] = {}
_bc_text_pending: set[int] = set()


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(client, obj, *args, **kwargs):
        uid = getattr(getattr(obj, "from_user", None), "id", 0)
        if uid != OWNER_ID:
            if hasattr(obj, "answer"):
                await answer_cb(obj, "🚫 Akses ditolak.", show_alert=True)
            return
        return await func(client, obj, *args, **kwargs)
    return wrapper


def _broadcast_menu_markup(total_u: int, total_p: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"👥 Semua User ({total_u})", callback_data="bc_target_all"),
        ],
        [
            InlineKeyboardButton(f"📡 Owner Partner ({total_p})", callback_data="bc_target_partner"),
        ],
        [InlineKeyboardButton("📜 Riwayat", callback_data="bc_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
    ])


@Client.on_callback_query(filters.regex(r"^owner_broadcast$"))
@owner_only
async def cb_broadcast_menu(client: Client, cb: CallbackQuery):
    try:
        total_u  = count_users()
        partners = get_all_partners()
        total_p  = len({p["owner_id"] for p in partners if p.get("owner_id")})
        text = (
            f"📣 <b>Broadcast Center</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"👥 User terdaftar      <code>{total_u}</code>\n"
            f"📡 Owner partner unik  <code>{total_p}</code>\n\n"
            f"Pilih target broadcast:"
        )
        await safe_edit(cb.message, text, markup=_broadcast_menu_markup(total_u, total_p), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_broadcast_menu] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^bc_target_(all|partner)$"))
@owner_only
async def cb_bc_target(client: Client, cb: CallbackQuery):
    try:
        mode = cb.matches[0].group(1)
        uid  = cb.from_user.id
        _bc_state[uid] = {"mode": mode}
        _bc_text_pending.add(uid)

        if mode == "all":
            total        = count_users()
            target_label = f"semua user ({total})"
        else:
            partners = get_all_partners()
            owners   = {p["owner_id"] for p in partners if p.get("owner_id")}
            total    = len(owners)
            target_label = f"owner partner ({total})"

        await safe_edit(
            cb.message,
            f"📣 <b>Broadcast ke {target_label}</b>\n\n"
            f"Ketik pesan yang ingin dikirim:\n\n"
            f"<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Batal", callback_data="owner_broadcast"),
            ]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bc_target] {e}")
    finally:
        await answer_cb(cb)


@Client.on_message(filters.text & filters.private, group=4)
@owner_only
async def receive_broadcast_text(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in _bc_text_pending:
        return

    text_input = message.text.strip()
    if text_input.startswith("/"):
        _bc_text_pending.discard(uid)
        _bc_state.pop(uid, None)
        return

    state = _bc_state.get(uid)
    if not state:
        _bc_text_pending.discard(uid)
        return

    _bc_text_pending.discard(uid)
    _bc_state[uid]["preview_text"] = text_input
    mode = state["mode"]

    if mode == "all":
        total        = count_users()
        target_label = f"semua user (<code>{total}</code>)"
    else:
        partners = get_all_partners()
        owners   = {p["owner_id"] for p in partners if p.get("owner_id")}
        total    = len(owners)
        target_label = f"owner partner (<code>{total}</code>)"

    preview = (
        f"👁 <b>Preview Broadcast</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"Target: {target_label}\n\n"
        f"<b>Isi pesan:</b>\n"
        f"{text_input}\n\n"
        f"<code>{SEP}</code>\n"
        f"Kirim broadcast ini?"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Kirim",  callback_data="bc_confirm"),
        InlineKeyboardButton("✏️ Edit",   callback_data=f"bc_re_edit"),
        InlineKeyboardButton("❌ Batal",  callback_data="bc_cancel"),
    ]])
    msg = await message.reply(preview, reply_markup=markup, parse_mode=PM)
    store_msg(uid, msg)


@Client.on_callback_query(filters.regex(r"^bc_re_edit$"))
@owner_only
async def cb_bc_re_edit(client: Client, cb: CallbackQuery):
    try:
        uid = cb.from_user.id
        state = _bc_state.get(uid)
        if not state:
            await answer_cb(cb, "State kadaluarsa.", True)
            return
        state.pop("preview_text", None)
        _bc_text_pending.add(uid)
        await safe_edit(
            cb.message,
            "✏️ <b>Edit Pesan Broadcast</b>\n\nKetik pesan baru:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_broadcast")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bc_re_edit] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^bc_confirm$"))
@owner_only
async def cb_bc_confirm(client: Client, cb: CallbackQuery):
    answered = False
    try:
        uid   = cb.from_user.id
        state = _bc_state.get(uid)
        if not state or "preview_text" not in state:
            await answer_cb(cb, "State kadaluarsa. Mulai ulang.", True)
            answered = True
            return

        mode    = state["mode"]
        bc_text = state["preview_text"]
        _bc_state.pop(uid, None)

        if mode == "all":
            targets      = get_all_user_ids()
            target_label = "Semua User"
        else:
            partners = get_all_partners()
            targets  = list({p["owner_id"] for p in partners if p.get("owner_id")})
            target_label = "Owner Partner"

        await safe_edit(
            cb.message,
            f"📤 <b>Mengirim broadcast...</b>\n\n"
            f"Target: <code>{len(targets)}</code> {target_label.lower()}\n"
            f"<i>Harap tunggu...</i>",
            markup=InlineKeyboardMarkup([]),
            parse_mode=PM,
        )
        await answer_cb(cb, "Mengirim...")
        answered = True

        success, fail = await blast_message(
            client, targets, bc_text, parse_mode=PM, delay=BROADCAST_DELAY
        )
        save_broadcast(uid, target_label, bc_text, success, fail)

        await safe_edit(
            cb.message,
            f"✅ <b>Broadcast Selesai!</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"Target     <b>{target_label}</b>\n"
            f"Berhasil   <code>{success}</code> ✅\n"
            f"Gagal      <code>{fail}</code> ❌\n"
            f"Total      <code>{success+fail}</code>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="home")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bc_confirm] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^bc_cancel$"))
@owner_only
async def cb_bc_cancel(client: Client, cb: CallbackQuery):
    try:
        _bc_state.pop(cb.from_user.id, None)
        _bc_text_pending.discard(cb.from_user.id)
        await safe_edit(
            cb.message,
            "❌ <b>Broadcast dibatalkan.</b>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="home")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bc_cancel] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^bc_history$"))
@owner_only
async def cb_bc_history(client: Client, cb: CallbackQuery):
    try:
        history = get_broadcast_history(limit=5)
        if not history:
            text = f"📜 <b>Riwayat Broadcast</b>\n\nBelum ada broadcast."
        else:
            lines = [f"📜 <b>Riwayat Broadcast (5 terakhir)</b>\n<code>{SEP}</code>"]
            for bc in history:
                sent_at = bc.get("sent_at")
                ts      = sent_at.strftime("%d %b %Y %H:%M") if sent_at else "—"
                target  = bc.get("target", "—")
                preview = (bc.get("message") or "")[:50]
                suc     = bc.get("success", 0)
                fail    = bc.get("fail", 0)
                lines.append(
                    f"\n📅 <code>{ts}</code>\n"
                    f"Target  <b>{target}</b>\n"
                    f"Pesan   <i>{preview}...</i>\n"
                    f"Hasil   ✅ <code>{suc}</code>  ❌ <code>{fail}</code>"
                )
            text = "\n".join(lines)

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Broadcast", callback_data="owner_broadcast")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_bc_history] {e}")
    finally:
        await answer_cb(cb)
