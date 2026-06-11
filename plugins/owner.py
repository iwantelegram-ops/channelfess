"""
Panel Owner — Dashboard, Partner, Blacklist, Maintenance, Aktivitas, Pengaturan.
FIX:
  - Semua callback di-wrap try/except + answer_cb() selalu dipanggil.
  - Tidak ada duplicate noop handler (sudah di mychannel.py).
  - owner_only menangani exception dengan aman.
  - Tidak ada message "⬇️" berulang setiap klik inline.
"""
import functools
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.enums import ParseMode
from config import OWNER_ID
from db.helpers import (
    get_partner, upsert_partner, get_all_partners, get_active_partners,
    count_partners, search_partners, get_top_partners,
    get_blacklist, add_blacklist, remove_blacklist,
    set_maintenance, get_maintenance,
    count_users,
    get_posts_today, get_posts_this_week, get_posts_this_month,
    get_recent_activity,
    get_bot_setting, set_bot_setting,
    count_posts_by_partner,
)
from db.mongo import posts
from utils import paginate, safe_edit, nav_to, store_msg, progress_bar, answer_cb

log       = logging.getLogger("fessbot.owner")
PM        = ParseMode.HTML
PAGE_SIZE = 8


# ═══════════════════════════════════════════════════════════
#  DEKORATOR
# ═══════════════════════════════════════════════════════════

def owner_only(func):
    @functools.wraps(func)
    async def wrapper(client, obj, *args, **kwargs):
        uid = getattr(getattr(obj, "from_user", None), "id", 0)
        if uid != OWNER_ID:
            if hasattr(obj, "answer"):
                await answer_cb(obj, "🚫 Bukan owner.", show_alert=True)
            return
        try:
            return await func(client, obj, *args, **kwargs)
        except Exception as e:
            log.error(f"[owner:{func.__name__}] {e}")
            if hasattr(obj, "answer"):
                await answer_cb(obj, "❌ Terjadi error.", show_alert=True)
    return wrapper


# ═══════════════════════════════════════════════════════════
#  REPLY KEYBOARDS
# ═══════════════════════════════════════════════════════════

def kb_main():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Dashboard"),  KeyboardButton("📋 Partner")],
        [KeyboardButton("📣 Broadcast"),  KeyboardButton("🔧 Tools")],
        [KeyboardButton("📝 Aktivitas"),  KeyboardButton("⚙️ Pengaturan")],
    ], resize_keyboard=True)

def kb_partner():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔎 Cari Channel"), KeyboardButton("🔄 Refresh Partner")],
        [KeyboardButton("🏆 Top Channel"),  KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_tools():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚫 Blacklist"),    KeyboardButton("🔧 Maintenance")],
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_blacklist():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Tambah Kata"),  KeyboardButton("➖ Hapus Kata")],
        [KeyboardButton("🔄 Refresh BL"),  KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_maintenance():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔴 Aktifkan Maintenance"),
         KeyboardButton("🟢 Nonaktifkan Maintenance")],
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_search():
    return ReplyKeyboardMarkup([
        [KeyboardButton("❌ Batal Cari")],
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_detail_channel(paused: bool):
    label = "▶️ Aktifkan Channel" if paused else "⏸ Pause Channel"
    return ReplyKeyboardMarkup([
        [KeyboardButton(label)],
        [KeyboardButton("◀️ Daftar Partner"), KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_bl_input():
    return ReplyKeyboardMarkup([
        [KeyboardButton("❌ Batal")],
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_aktivitas():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔄 Refresh Aktivitas")],
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)

def kb_settings():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏠 Menu Utama")],
    ], resize_keyboard=True)


# ─── State ──────────────────────────────────────────────────
_viewing_channel: dict[int, int] = {}
_search_pending:  set[int]       = set()
_bl_add_pending:  set[int]       = set()
_bl_del_pending:  set[int]       = set()


# ═══════════════════════════════════════════════════════════
#  HELPER — kirim/edit konten + kirim keyboard (invisible char)
# ═══════════════════════════════════════════════════════════

async def _show(client, message: Message, text: str,
                inline_markup=None, reply_kb=None):
    """Edit stored message, lalu kirim keyboard jika berubah."""
    uid = message.from_user.id
    msg = await nav_to(client, uid, message.chat.id, text,
                       inline_markup=inline_markup, parse_mode=PM)
    if not msg:
        msg = await message.reply(text, reply_markup=inline_markup, parse_mode=PM)
        store_msg(uid, msg)
    if reply_kb:
        await client.send_message(message.chat.id, "‎", reply_markup=reply_kb)


# ═══════════════════════════════════════════════════════════
#  🏠 MENU UTAMA
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^🏠 Menu Utama$"))
@owner_only
async def kb_menu_utama(client: Client, message: Message):
    uid = message.from_user.id
    _viewing_channel.pop(uid, None)
    _search_pending.discard(uid)
    _bl_add_pending.discard(uid)
    _bl_del_pending.discard(uid)

    total_p  = count_partners()
    active_p = len(get_active_partners())
    total_r  = posts.count_documents({})
    today    = get_posts_today()

    text = (
        f"⚡ <b>FessBot v2 — Control Panel</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"📡 Partner   <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
        f"📦 Hari ini  <code>{today}</code> repost · All-time <code>{total_r}</code>\n\n"
        f"Pilih menu: 👇"
    )
    await _show(client, message, text, reply_kb=kb_main())


# ═══════════════════════════════════════════════════════════
#  📊 DASHBOARD
# ═══════════════════════════════════════════════════════════

def _dashboard_text() -> str:
    total_p  = count_partners()
    all_p    = get_all_partners()
    paused   = len([p for p in all_p if p.get("paused")])
    active   = total_p - paused
    total_u  = count_users()
    today    = get_posts_today()
    week     = get_posts_this_week()
    month    = get_posts_this_month()
    total_r  = posts.count_documents({})
    pct_a    = round(active / total_p * 100) if total_p else 0
    pct_p    = round(paused / total_p * 100) if total_p else 0

    top5  = get_top_partners(5)
    top_lines = [
        f"  {i}. {'▶️' if not ch.get('paused') else '⏸'} "
        f"<b>{(ch.get('channel_name') or '?')[:30]}</b>  "
        f"<code>{ch.get('total_posts', 0)}</code>"
        for i, ch in enumerate(top5, 1)
    ]
    top_block = "\n".join(top_lines) if top_lines else "  —"

    return (
        f"📊 <b>Dashboard FessBot v2</b>\n"
        f"<code>{'─' * 28}</code>\n\n"
        f"👥 <b>Users</b>   <code>{total_u}</code>\n\n"
        f"📡 <b>Channel Partner</b>\n"
        f"  ▶️ Aktif   {progress_bar(active, total_p)}  "
        f"<code>{active}</code> ({pct_a}%)\n"
        f"  ⏸ Paused  {progress_bar(paused, total_p)}  "
        f"<code>{paused}</code> ({pct_p}%)\n"
        f"  Total     <code>{total_p}</code>\n\n"
        f"📦 <b>Repost</b>\n"
        f"  Hari ini   <code>{today}</code>\n"
        f"  7 hari     <code>{week}</code>\n"
        f"  30 hari    <code>{month}</code>\n"
        f"  All-time   <code>{total_r}</code>\n\n"
        f"🏆 <b>Top Channel</b>\n"
        f"{top_block}"
    )


@Client.on_message(filters.text & filters.private & filters.regex(r"^📊 Dashboard$"))
@owner_only
async def kb_dashboard(client: Client, message: Message):
    await _show(client, message, _dashboard_text())


@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client: Client, message: Message):
    await message.reply(_dashboard_text(), parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  📋 PARTNER LIST
# ═══════════════════════════════════════════════════════════

def _build_partner_list(all_p: list, page: int):
    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)

    lines = [f"📋 <b>Channel Partner</b>  <code>{len(all_p)} total</code>"]
    for ch in chunk:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        uname = f"@{ch['username']}" if ch.get("username") else "—"
        rp    = ch.get("total_posts", 0)
        name  = (ch.get("channel_name") or "?")[:35]
        lines.append(
            f"\n{icon} <b>{name}</b>\n"
            f"     {uname}  ·  📦 {rp}  ·  🆔 <code>{ch['_id']}</code>"
        )
    text = "\n".join(lines)

    rows = [[InlineKeyboardButton(
        f"{'▶️' if not ch.get('paused') else '⏸'}  {(ch.get('channel_name') or '?')[:35]}",
        callback_data=f"owner_ch_{ch['_id']}",
    )] for ch in chunk]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"list_partner_{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"list_partner_{page+1}"))
    if nav:
        rows.append(nav)

    return text, rows


async def _send_partner_list(client, message: Message, page: int):
    all_p = get_all_partners()
    if not all_p:
        await _show(client, message,
                    "📋 <b>Channel Partner</b>\n\nBelum ada partner terdaftar.",
                    reply_kb=kb_partner())
        return

    text, rows = _build_partner_list(all_p, page)
    markup     = InlineKeyboardMarkup(rows) if rows else None
    await _show(client, message, text, inline_markup=markup, reply_kb=kb_partner())


@Client.on_message(filters.text & filters.private & filters.regex(r"^📋 Partner$"))
@owner_only
async def kb_partner_btn(client: Client, message: Message):
    await _send_partner_list(client, message, 0)

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔄 Refresh Partner$"))
@owner_only
async def kb_refresh_partner(client: Client, message: Message):
    await _send_partner_list(client, message, 0)

@Client.on_message(filters.text & filters.private & filters.regex(r"^◀️ Daftar Partner$"))
@owner_only
async def kb_back_to_partner(client: Client, message: Message):
    _viewing_channel.pop(message.from_user.id, None)
    await _send_partner_list(client, message, 0)

@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client: Client, message: Message):
    await _send_partner_list(client, message, 0)


@Client.on_callback_query(filters.regex(r"^list_partner_(\d+)$"))
@owner_only
async def cb_listpartner(client: Client, cb: CallbackQuery):
    try:
        page  = int(cb.matches[0].group(1))
        all_p = get_all_partners()
        if not all_p:
            await safe_edit(cb.message, "📋 Belum ada partner terdaftar.", parse_mode=PM)
        else:
            text, rows = _build_partner_list(all_p, page)
            await safe_edit(cb.message, text,
                            markup=InlineKeyboardMarkup(rows), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_listpartner] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🏆 TOP CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^🏆 Top Channel$"))
@owner_only
async def kb_top_channel(client: Client, message: Message):
    top = get_top_partners(10)
    if not top:
        text = "🏆 <b>Top Channel</b>\n\nBelum ada data repost."
    else:
        lines = ["🏆 <b>Top 10 Channel (all-time)</b>\n<code>─────────────────────────</code>"]
        for i, ch in enumerate(top, 1):
            icon  = "▶️" if not ch.get("paused") else "⏸"
            rp    = ch.get("total_posts", 0)
            uname = f"@{ch['username']}" if ch.get("username") else ""
            name  = (ch.get("channel_name") or "?")[:30]
            lines.append(
                f"{i:2}. {icon} <b>{name}</b>  {uname}  <code>{rp}</code>"
            )
        text = "\n".join(lines)
    await _show(client, message, text)


# ═══════════════════════════════════════════════════════════
#  DETAIL CHANNEL (owner view)
# ═══════════════════════════════════════════════════════════

def _partner_detail_text(partner: dict, channel_id: int) -> str:
    paused   = partner.get("paused", False)
    status   = "▶️ Aktif" if not paused else "⏸ Dijeda"
    uname    = f"@{partner['username']}" if partner.get("username") else "—"
    reason   = partner.get("reason", "")
    rp       = count_posts_by_partner(channel_id)
    added    = partner.get("added_at")
    added_s  = added.strftime("%d %b %Y") if added else "—"
    owner_id = partner.get("owner_id")
    owner_nm = partner.get("owner_name", "?")
    name     = (partner.get("channel_name") or str(channel_id))

    text = (
        f"📡 <b>{name}</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Username    {uname}\n"
        f"Owner       <b>{owner_nm}</b>"
        + (f"  (<code>{owner_id}</code>)" if owner_id else "") + "\n"
        f"Status      {status}\n"
        f"Repost      <code>{rp}</code> kali\n"
        f"Terdaftar   {added_s}\n"
    )
    if reason:
        text += f"\n⚠️ <i>{reason}</i>\n"
    return text


async def _show_partner_detail(client, source, channel_id: int):
    """
    source bisa Message atau CallbackQuery.
    Kalau CallbackQuery: edit inline message, update reply kb via send_message.
    Kalau Message: nav_to + send reply kb.
    """
    partner = get_partner(channel_id)
    if not partner:
        if hasattr(source, "answer"):
            await source.answer("Channel tidak ditemukan.", show_alert=True)
        else:
            await source.reply("❌ Channel tidak ditemukan.")
        return

    uid = getattr(getattr(source, "from_user", None), "id", OWNER_ID)
    _viewing_channel[uid] = channel_id

    paused = partner.get("paused", False)
    text   = _partner_detail_text(partner, channel_id)
    kb     = kb_detail_channel(paused)

    if hasattr(source, "message"):  # CallbackQuery
        await safe_edit(source.message, text, parse_mode=PM)
        await client.send_message(source.message.chat.id, "‎", reply_markup=kb)
    else:  # Message
        await _show(client, source, text, reply_kb=kb)


@Client.on_callback_query(filters.regex(r"^owner_ch_(-?\d+)$"))
@owner_only
async def cb_owner_ch_detail(client: Client, cb: CallbackQuery):
    try:
        channel_id = int(cb.matches[0].group(1))
        await _show_partner_detail(client, cb, channel_id)
    except Exception as e:
        log.error(f"[cb_owner_ch_detail] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  PAUSE / RUN  (reply keyboard buttons dari detail view)
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^⏸ Pause Channel$"))
@owner_only
async def kb_pause_channel(client: Client, message: Message):
    uid        = message.from_user.id
    channel_id = _viewing_channel.get(uid)
    if not channel_id:
        await message.reply("⚠️ Pilih channel dari daftar partner dulu.")
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh admin"})
    # Notif ke owner channel
    oid = partner.get("owner_id")
    if oid:
        try:
            await client.send_message(
                oid,
                f"⏸ <b>Channel dijeda oleh admin.</b>\n\n"
                f"📡 <b>{partner.get('channel_name', '')}</b>",
                parse_mode=PM,
            )
        except Exception:
            pass
    await _show_partner_detail(client, message, channel_id)


@Client.on_message(filters.text & filters.private & filters.regex(r"^▶️ Aktifkan Channel$"))
@owner_only
async def kb_run_channel(client: Client, message: Message):
    uid        = message.from_user.id
    channel_id = _viewing_channel.get(uid)
    if not channel_id:
        await message.reply("⚠️ Pilih channel dari daftar partner dulu.")
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    oid = partner.get("owner_id")
    if oid:
        try:
            await client.send_message(
                oid,
                f"▶️ <b>Channel aktif kembali!</b>\n\n"
                f"📡 <b>{partner.get('channel_name', '')}</b> 🚀",
                parse_mode=PM,
            )
        except Exception:
            pass
    await _show_partner_detail(client, message, channel_id)


# ═══════════════════════════════════════════════════════════
#  🔎 CARI CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔎 Cari Channel$"))
@owner_only
async def kb_search_btn(client: Client, message: Message):
    uid = message.from_user.id
    _search_pending.add(uid)
    await _show(
        client, message,
        "🔎 <b>Cari Channel Partner</b>\n\nKetik nama atau username channel:",
        reply_kb=kb_search(),
    )


@Client.on_message(filters.text & filters.private & filters.regex(r"^❌ Batal Cari$"))
@owner_only
async def kb_cancel_search(client: Client, message: Message):
    _search_pending.discard(message.from_user.id)
    await _send_partner_list(client, message, 0)


# ═══════════════════════════════════════════════════════════
#  🔧 TOOLS
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔧 Tools$"))
@owner_only
async def kb_tools_btn(client: Client, message: Message):
    maint  = get_maintenance()
    bl     = get_blacklist()
    status = "🔴 Maintenance aktif" if maint.get("active") else "🟢 Berjalan normal"
    reason = maint.get("reason", "")
    text = (
        f"🔧 <b>Tools</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Status      {status}\n"
        + (f"Alasan      <i>{reason}</i>\n" if reason else "") +
        f"Blacklist   <code>{len(bl)}</code> kata\n\n"
        f"Pilih:"
    )
    await _show(client, message, text, reply_kb=kb_tools())


# ═══════════════════════════════════════════════════════════
#  🚫 BLACKLIST
# ═══════════════════════════════════════════════════════════

async def _show_blacklist(client, message: Message):
    bl   = get_blacklist()
    text = (
        f"🚫 <b>Blacklist Kata</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        + ("\n".join(f"• <code>{w}</code>" for w in bl) if bl else "<i>(kosong)</i>") +
        f"\n\nTotal: <code>{len(bl)}</code> kata"
    )
    await _show(client, message, text, reply_kb=kb_blacklist())


@Client.on_message(filters.text & filters.private & filters.regex(r"^🚫 Blacklist$"))
@owner_only
async def kb_blacklist_btn(client: Client, message: Message):
    await _show_blacklist(client, message)

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔄 Refresh BL$"))
@owner_only
async def kb_refresh_bl(client: Client, message: Message):
    await _show_blacklist(client, message)

@Client.on_message(filters.text & filters.private & filters.regex(r"^➕ Tambah Kata$"))
@owner_only
async def kb_bl_add_prompt(client: Client, message: Message):
    _bl_add_pending.add(message.from_user.id)
    await _show(client, message,
                "➕ <b>Tambah Kata Blacklist</b>\n\nKetik kata yang ingin diblokir:",
                reply_kb=kb_bl_input())

@Client.on_message(filters.text & filters.private & filters.regex(r"^➖ Hapus Kata$"))
@owner_only
async def kb_bl_del_prompt(client: Client, message: Message):
    _bl_del_pending.add(message.from_user.id)
    await _show(client, message,
                "➖ <b>Hapus Kata Blacklist</b>\n\nKetik kata yang ingin dihapus:",
                reply_kb=kb_bl_input())

@Client.on_message(filters.text & filters.private & filters.regex(r"^❌ Batal$"))
@owner_only
async def kb_batal(client: Client, message: Message):
    uid = message.from_user.id
    _bl_add_pending.discard(uid)
    _bl_del_pending.discard(uid)
    await _show_blacklist(client, message)

@Client.on_message(filters.command("addbl") & filters.private)
@owner_only
async def cmd_addbl(client: Client, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply("Gunakan: <code>/addbl &lt;kata&gt;</code>", parse_mode=PM)
        return
    word = args[1].strip()
    add_blacklist(word)
    await message.reply(f"✅ Kata <code>{word}</code> ditambahkan.", parse_mode=PM)

@Client.on_message(filters.command("rmbl") & filters.private)
@owner_only
async def cmd_rmbl(client: Client, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply("Gunakan: <code>/rmbl &lt;kata&gt;</code>", parse_mode=PM)
        return
    word = args[1].strip()
    remove_blacklist(word)
    await message.reply(f"✅ Kata <code>{word}</code> dihapus.", parse_mode=PM)

@Client.on_message(filters.command("listbl") & filters.private)
@owner_only
async def cmd_listbl(client: Client, message: Message):
    bl   = get_blacklist()
    text = "🚫 <b>Blacklist</b>\n\n" + (
        "\n".join(f"• <code>{w}</code>" for w in bl) if bl else "<i>(kosong)</i>"
    )
    await message.reply(text, parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  🔧 MAINTENANCE
# ═══════════════════════════════════════════════════════════

async def _show_maintenance(client, message: Message):
    maint   = get_maintenance()
    status  = "🔴 <b>AKTIF</b>" if maint.get("active") else "🟢 <b>Normal</b>"
    reason  = maint.get("reason", "—")
    updated = maint.get("updated_at")
    upd_s   = updated.strftime("%d %b %Y %H:%M") if updated else "—"
    text = (
        f"🔧 <b>Maintenance Mode</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Status       {status}\n"
        f"Alasan       <i>{reason}</i>\n"
        f"Diperbarui   {upd_s}\n"
    )
    await _show(client, message, text, reply_kb=kb_maintenance())


@Client.on_message(filters.text & filters.private & filters.regex(r"^🔧 Maintenance$"))
@owner_only
async def kb_maintenance_btn(client: Client, message: Message):
    await _show_maintenance(client, message)

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔴 Aktifkan Maintenance$"))
@owner_only
async def kb_maint_on(client: Client, message: Message):
    set_maintenance(True, "Bot sedang dalam perbaikan. Harap tunggu.")
    await _show_maintenance(client, message)

@Client.on_message(filters.text & filters.private & filters.regex(r"^🟢 Nonaktifkan Maintenance$"))
@owner_only
async def kb_maint_off(client: Client, message: Message):
    set_maintenance(False, "")
    await _show_maintenance(client, message)

@Client.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def cmd_maintenance(client: Client, message: Message):
    args   = message.text.split(None, 1)
    reason = args[1] if len(args) > 1 else "Bot sedang dalam perbaikan."
    set_maintenance(True, reason)
    await message.reply(f"🔴 <b>Maintenance aktif.</b>\n\nAlasan: <i>{reason}</i>",
                        parse_mode=PM)

@Client.on_message(filters.command("unmaintenance") & filters.private)
@owner_only
async def cmd_unmaintenance(client: Client, message: Message):
    set_maintenance(False, "")
    await message.reply("🟢 <b>Maintenance nonaktif.</b>", parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  📝 AKTIVITAS
# ═══════════════════════════════════════════════════════════

EVENT_LABELS = {
    "repost_success":    "✅ Repost berhasil",
    "repost_fail":       "❌ Repost gagal",
    "repost_deleted":    "🗑 Repost dihapus",
    "partner_added":     "➕ Partner terdaftar",
    "partner_activated": "▶️ Partner diaktifkan",
    "partner_manual_add":"📋 Daftar manual",
    "bot_removed":       "⚠️ Bot dicopot",
    "blacklist_blocked": "🚫 Blacklist blocked",
}


async def _show_aktivitas(client, message: Message):
    activity = get_recent_activity(limit=15)
    if not activity:
        text = "📝 <b>Log Aktivitas</b>\n\nBelum ada aktivitas."
    else:
        lines = [f"📝 <b>Log Aktivitas (15 terakhir)</b>\n<code>{'─' * 28}</code>"]
        for ev in activity:
            event   = ev.get("event", "?")
            label   = EVENT_LABELS.get(event, f"• {event}")
            ts      = ev.get("ts")
            ts_s    = ts.strftime("%d/%m %H:%M") if ts else "—"
            pid     = ev.get("partner_id")
            ch_name = ""
            if pid:
                p = get_partner(pid)
                if p:
                    ch_name = f" · <b>{(p.get('channel_name') or '?')[:25]}</b>"
            lines.append(f"<code>{ts_s}</code>  {label}{ch_name}")
        text = "\n".join(lines)
    await _show(client, message, text, reply_kb=kb_aktivitas())


@Client.on_message(filters.text & filters.private & filters.regex(r"^📝 Aktivitas$"))
@owner_only
async def kb_aktivitas_btn(client: Client, message: Message):
    await _show_aktivitas(client, message)

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔄 Refresh Aktivitas$"))
@owner_only
async def kb_refresh_aktivitas(client: Client, message: Message):
    await _show_aktivitas(client, message)


# ═══════════════════════════════════════════════════════════
#  ⚙️ PENGATURAN
# ═══════════════════════════════════════════════════════════

def _settings_text_and_markup():
    notif_owner = get_bot_setting("owner_notif_all", True)
    auto_delete = get_bot_setting("auto_delete_repost", True)
    text_repost = get_bot_setting("allow_text_repost", True)

    text = (
        f"⚙️ <b>Pengaturan Bot</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"🔔 Notif ke owner (semua)   {'✅' if notif_owner else '❌'}\n"
        f"🗑 Auto-hapus repost        {'✅' if auto_delete else '❌'}\n"
        f"📝 Repost pesan teks        {'✅' if text_repost else '❌'}\n"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🔔' if notif_owner else '🔕'} Notif Owner",
            callback_data="setting_toggle_owner_notif_all",
        )],
        [InlineKeyboardButton(
            f"{'🗑' if auto_delete else '💾'} Auto-Hapus Repost",
            callback_data="setting_toggle_auto_delete_repost",
        )],
        [InlineKeyboardButton(
            f"{'📝' if text_repost else '🚫'} Repost Teks",
            callback_data="setting_toggle_allow_text_repost",
        )],
    ])
    return text, markup


@Client.on_message(filters.text & filters.private & filters.regex(r"^⚙️ Pengaturan$"))
@owner_only
async def kb_settings_btn(client: Client, message: Message):
    text, markup = _settings_text_and_markup()
    await _show(client, message, text, inline_markup=markup, reply_kb=kb_settings())


@Client.on_callback_query(
    filters.regex(r"^setting_toggle_(owner_notif_all|auto_delete_repost|allow_text_repost)$")
)
@owner_only
async def cb_toggle_setting(client: Client, cb: CallbackQuery):
    answered = False
    try:
        key     = cb.matches[0].group(1)
        current = get_bot_setting(key, True)
        set_bot_setting(key, not current)

        await answer_cb(cb, "✅ Setting diperbarui")
        answered = True

        text, markup = _settings_text_and_markup()
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_toggle_setting] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  INPUT HANDLER  group=4 — cari channel & input blacklist
# ═══════════════════════════════════════════════════════════

OWNER_BTNS = {
    "🏠 Menu Utama", "📊 Dashboard", "📋 Partner", "📣 Broadcast",
    "🔧 Tools", "📝 Aktivitas", "⚙️ Pengaturan",
    "🔎 Cari Channel", "🔄 Refresh Partner", "🏆 Top Channel",
    "◀️ Daftar Partner", "🚫 Blacklist", "🔧 Maintenance",
    "🔄 Refresh BL", "➕ Tambah Kata", "➖ Hapus Kata",
    "❌ Batal", "❌ Batal Cari",
    "🔴 Aktifkan Maintenance", "🟢 Nonaktifkan Maintenance",
    "🔄 Refresh Aktivitas", "⏸ Pause Channel", "▶️ Aktifkan Channel",
}


@Client.on_message(filters.text & filters.private, group=4)
@owner_only
async def owner_text_input(client: Client, message: Message):
    uid  = message.from_user.id
    text = message.text

    if text in OWNER_BTNS:
        return

    # ── Pencarian channel ──────────────────────────────────
    if uid in _search_pending:
        _search_pending.discard(uid)
        results = search_partners(text)
        if not results:
            await _show(client, message,
                        f"🔎 <b>Tidak ditemukan: «{text}»</b>",
                        reply_kb=kb_partner())
            return
        rows = [[InlineKeyboardButton(
            f"{'▶️' if not ch.get('paused') else '⏸'}  {(ch.get('channel_name') or '?')[:35]}",
            callback_data=f"owner_ch_{ch['_id']}",
        )] for ch in results]
        await _show(
            client, message,
            f"🔎 <b>Hasil: «{text}»</b>  —  <code>{len(results)}</code> channel",
            inline_markup=InlineKeyboardMarkup(rows),
            reply_kb=kb_partner(),
        )
        return

    # ── Tambah blacklist ───────────────────────────────────
    if uid in _bl_add_pending:
        _bl_add_pending.discard(uid)
        word = text.strip().lower()
        add_blacklist(word)
        await _show(client, message,
                    f"✅ <b>Ditambahkan:</b> <code>{word}</code>",
                    reply_kb=kb_blacklist())
        return

    # ── Hapus blacklist ────────────────────────────────────
    if uid in _bl_del_pending:
        _bl_del_pending.discard(uid)
        word = text.strip().lower()
        remove_blacklist(word)
        await _show(client, message,
                    f"✅ <b>Dihapus:</b> <code>{word}</code>",
                    reply_kb=kb_blacklist())
        return
