"""
Broadcast interaktif — tombol → ketik → preview → kirim.
FIX: owner_only_dec selalu answer callback; try/except di semua handler.
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.enums import ParseMode
from config import OWNER_ID, BROADCAST_DELAY
from db.helpers import (
    get_all_user_ids, get_all_partners,
    save_broadcast, get_broadcast_history,
    count_users,
)
from utils import safe_edit, nav_to, blast_message, store_msg, answer_cb

log = logging.getLogger("fessbot.broadcast")
PM  = ParseMode.HTML

# State: owner_id → {"mode": "all"|"partner", "preview_text"?: str}
_bc_state: dict[int, dict] = {}


# ═══════════════════════════════════════════════════════════
#  DEKORATOR owner-only  (FIX: selalu answer callback)
# ═══════════════════════════════════════════════════════════

def owner_only(func):
    import functools
    @functools.wraps(func)
    async def wrapper(client, obj, *args, **kwargs):
        uid = getattr(getattr(obj, "from_user", None), "id", 0)
        if uid != OWNER_ID:
            # Untuk callback: answer dulu baru return
            if hasattr(obj, "answer"):
                await answer_cb(obj, "🚫 Bukan owner.", show_alert=True)
            return
        return await func(client, obj, *args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════

def kb_broadcast_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 Broadcast Semua User"), KeyboardButton("📡 Broadcast Partner")],
        [KeyboardButton("📜 Riwayat Broadcast"),    KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_main():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Dashboard"),  KeyboardButton("📋 Partner")],
        [KeyboardButton("📣 Broadcast"),  KeyboardButton("🔧 Tools")],
        [KeyboardButton("📝 Aktivitas"),  KeyboardButton("⚙️ Pengaturan")],
    ], resize_keyboard=True)

def kb_waiting_input():
    return ReplyKeyboardMarkup([
        [KeyboardButton("❌ Batal Broadcast")],
    ], resize_keyboard=True)


# ═══════════════════════════════════════════════════════════
#  MENU BROADCAST
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^📣 Broadcast$"))
@owner_only
async def kb_broadcast_menu_btn(client: Client, message: Message):
    uid      = message.from_user.id
    total_u  = count_users()
    partners = get_all_partners()
    total_p  = len({p["owner_id"] for p in partners if p.get("owner_id")})

    text = (
        f"📣 <b>Broadcast Center</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"👥 User terdaftar       <code>{total_u}</code>\n"
        f"📡 Owner partner unik  <code>{total_p}</code>\n\n"
        f"Pilih target broadcast:"
    )
    await message.reply(text, reply_markup=kb_broadcast_menu(), parse_mode=PM)


@Client.on_message(filters.text & filters.private & filters.regex(r"^👥 Broadcast Semua User$"))
@owner_only
async def kb_bc_all_users(client: Client, message: Message):
    uid             = message.from_user.id
    _bc_state[uid]  = {"mode": "all"}
    total           = count_users()
    text = (
        f"👥 <b>Broadcast ke Semua User</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"Target: <code>{total}</code> user\n\n"
        f"✏️ Ketik pesan broadcast kamu:"
    )
    await message.reply(text, reply_markup=kb_waiting_input(), parse_mode=PM)


@Client.on_message(filters.text & filters.private & filters.regex(r"^📡 Broadcast Partner$"))
@owner_only
async def kb_bc_partner(client: Client, message: Message):
    uid      = message.from_user.id
    partners = get_all_partners()
    owners   = {p["owner_id"] for p in partners if p.get("owner_id")}
    _bc_state[uid] = {"mode": "partner"}
    text = (
        f"📡 <b>Broadcast ke Owner Partner</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"Target: <code>{len(owners)}</code> owner partner\n\n"
        f"✏️ Ketik pesan broadcast kamu:"
    )
    await message.reply(text, reply_markup=kb_waiting_input(), parse_mode=PM)


@Client.on_message(filters.text & filters.private & filters.regex(r"^❌ Batal Broadcast$"))
@owner_only
async def kb_cancel_broadcast(client: Client, message: Message):
    uid = message.from_user.id
    _bc_state.pop(uid, None)
    text = "❌ <b>Broadcast dibatalkan.</b>"
    await message.reply(text, reply_markup=kb_main(), parse_mode=PM)


@Client.on_message(filters.text & filters.private & filters.regex(r"^📜 Riwayat Broadcast$"))
@owner_only
async def kb_bc_history(client: Client, message: Message):
    uid     = message.from_user.id
    history = get_broadcast_history(limit=5)

    if not history:
        text = "📜 <b>Riwayat Broadcast</b>\n\nBelum ada broadcast yang dikirim."
    else:
        lines = [f"📜 <b>Riwayat Broadcast</b>\n<code>{'─' * 28}</code>"]
        for bc in history:
            sent_at = bc.get("sent_at")
            ts      = sent_at.strftime("%d %b %Y %H:%M") if sent_at else "—"
            target  = bc.get("target", "—")
            preview = (bc.get("message") or "")[:60]
            suc     = bc.get("success", 0)
            fail    = bc.get("fail", 0)
            lines.append(
                f"\n📅 <code>{ts}</code>\n"
                f"Target  <b>{target}</b>\n"
                f"Pesan   <i>{preview}…</i>\n"
                f"Hasil   ✅ <code>{suc}</code>  ❌ <code>{fail}</code>"
            )
        text = "\n".join(lines)

    await message.reply(text, reply_markup=kb_broadcast_menu(), parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  TERIMA INPUT PESAN BROADCAST  (group=5, setelah owner handlers)
# ═══════════════════════════════════════════════════════════

BROADCAST_MENU_BUTTONS = {
    "📊 Dashboard", "📋 Partner", "📣 Broadcast", "🔧 Tools",
    "📝 Aktivitas", "⚙️ Pengaturan", "🏠 Menu Utama",
    "👥 Broadcast Semua User", "📡 Broadcast Partner",
    "📜 Riwayat Broadcast", "❌ Batal Broadcast",
}


@Client.on_message(filters.text & filters.private, group=5)
@owner_only
async def receive_broadcast_input(client: Client, message: Message):
    uid   = message.from_user.id
    state = _bc_state.get(uid)

    # Tidak sedang menunggu input atau sudah ada preview
    if not state or "preview_text" in state:
        return

    text_input = message.text
    if text_input in BROADCAST_MENU_BUTTONS:
        return

    mode = state["mode"]
    _bc_state[uid]["preview_text"] = text_input

    if mode == "all":
        total        = count_users()
        target_label = f"semua user (<code>{total}</code>)"
    else:
        partners     = get_all_partners()
        owners       = {p["owner_id"] for p in partners if p.get("owner_id")}
        total        = len(owners)
        target_label = f"owner partner (<code>{total}</code>)"

    preview = (
        f"👁 <b>Preview Broadcast</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"Target: {target_label}\n\n"
        f"<b>Isi pesan:</b>\n"
        f"{text_input}\n\n"
        f"<code>{'─' * 28}</code>\n"
        f"Kirim broadcast ini?"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Kirim Sekarang", callback_data="bc_confirm"),
        InlineKeyboardButton("✏️ Edit Ulang",    callback_data="bc_edit"),
        InlineKeyboardButton("❌ Batal",          callback_data="bc_cancel"),
    ]])

    msg = await nav_to(client, uid, message.chat.id, preview,
                       inline_markup=markup, parse_mode=PM)
    if not msg:
        msg = await message.reply(preview, reply_markup=markup, parse_mode=PM)
    store_msg(uid, msg)


# ═══════════════════════════════════════════════════════════
#  CALLBACK: CONFIRM / EDIT / CANCEL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^bc_confirm$"))
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

        mode       = state["mode"]
        bc_text    = state["preview_text"]
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
            f"📤 <b>Mengirim broadcast…</b>\n\n"
            f"Target: <code>{len(targets)}</code> {target_label.lower()}\n"
            f"<i>Harap tunggu…</i>",
            markup=InlineKeyboardMarkup([]),
            parse_mode=PM,
        )
        await answer_cb(cb, "Mengirim…")
        answered = True

        success, fail = await blast_message(
            client, targets, bc_text, parse_mode=PM, delay=BROADCAST_DELAY
        )
        save_broadcast(uid, target_label, bc_text, success, fail)

        await safe_edit(
            cb.message,
            f"✅ <b>Broadcast Selesai!</b>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"Target     <b>{target_label}</b>\n"
            f"Berhasil   <code>{success}</code> ✅\n"
            f"Gagal      <code>{fail}</code> ❌\n"
            f"Total      <code>{success+fail}</code>",
            markup=InlineKeyboardMarkup([]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bc_confirm] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex("^bc_edit$"))
@owner_only
async def cb_bc_edit(client: Client, cb: CallbackQuery):
    answered = False
    try:
        uid   = cb.from_user.id
        state = _bc_state.get(uid)

        if not state:
            await answer_cb(cb, "State kadaluarsa.", True)
            answered = True
            return

        state.pop("preview_text", None)
        await safe_edit(
            cb.message,
            "✏️ <b>Edit Pesan Broadcast</b>\n\nKetik pesan baru kamu:",
            markup=InlineKeyboardMarkup([]),
            parse_mode=PM,
        )
        await answer_cb(cb, "Ketik pesan baru.")
        answered = True
    except Exception as e:
        log.error(f"[cb_bc_edit] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex("^bc_cancel$"))
@owner_only
async def cb_bc_cancel(client: Client, cb: CallbackQuery):
    answered = False
    try:
        _bc_state.pop(cb.from_user.id, None)
        await safe_edit(cb.message, "❌ <b>Broadcast dibatalkan.</b>",
                        markup=InlineKeyboardMarkup([]), parse_mode=PM)
        await answer_cb(cb, "Dibatalkan.")
        answered = True
    except Exception as e:
        log.error(f"[cb_bc_cancel] {e}")
    finally:
        if not answered:
            await answer_cb(cb)
