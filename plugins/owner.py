"""
Panel Owner — Full inline keyboard, edit-in-place navigation.
Dashboard, Partner, Blacklist, Maintenance, Aktivitas, Pengaturan,
Ban users, Export data, Caption template, Health check.
"""
import functools
import logging
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ParseMode

from config import OWNER_ID, BOT_NAME
from db.helpers import (
    get_partner, upsert_partner, get_all_partners, get_active_partners,
    count_partners, search_partners, get_top_partners,
    get_blacklist, add_blacklist, remove_blacklist,
    set_maintenance, get_maintenance,
    count_users,
    get_posts_today, get_posts_this_week, get_posts_this_month,
    get_recent_activity, count_activity_today,
    get_bot_setting, set_bot_setting,
    count_posts_by_partner,
    is_banned, ban_user, unban_user, get_banned_list, count_banned,
    get_caption_template, set_caption_template, reset_caption_template,
    DEFAULT_CAPTION_TEMPLATE,
    get_broadcast_history, count_active_users,
)
from db.mongo import posts
from utils import paginate, safe_edit, send_or_edit, store_msg, progress_bar, answer_cb

log       = logging.getLogger("fessbot.owner")
PM        = ParseMode.HTML
PAGE_SIZE = 8
SEP       = "─" * 30

# ─── In-memory state (ephemeral) ──────────────────────────
_search_pending:    set[int] = set()
_bl_add_pending:    set[int] = set()
_bl_del_pending:    set[int] = set()
_ban_pending:       set[int] = set()
_caption_pending:   set[int] = set()
_maint_reason:      set[int] = set()
_viewing_channel:   dict[int, int] = {}


# ═══════════════════════════════════════════════════════════
#  DEKORATOR
# ═══════════════════════════════════════════════════════════

def owner_only(func):
    """
    Decorator: hanya izinkan OWNER_ID.
    TIDAK memanggil answer_cb di blok except — biarkan fungsi
    yang dibungkus menanganinya sendiri lewat finally block masing-masing.
    """
    @functools.wraps(func)
    async def wrapper(client, obj, *args, **kwargs):
        uid = getattr(getattr(obj, "from_user", None), "id", 0)
        if uid != OWNER_ID:
            if hasattr(obj, "answer"):
                try:
                    await obj.answer("🚫 Akses ditolak.", show_alert=True)
                except Exception:
                    pass
            return
        return await func(client, obj, *args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
#  HELPER MARKUP
# ═══════════════════════════════════════════════════════════

def back_home():
    return [[InlineKeyboardButton("🏠 Menu Utama", callback_data="home")]]


# ═══════════════════════════════════════════════════════════
#  📊 DASHBOARD
# ═══════════════════════════════════════════════════════════

def _dashboard_text() -> str:
    total_p  = count_partners()
    all_p    = get_all_partners()
    paused   = len([p for p in all_p if p.get("paused")])
    active   = total_p - paused
    total_u  = count_users()
    active_u = count_active_users()
    today    = get_posts_today()
    week     = get_posts_this_week()
    month    = get_posts_this_month()
    total_r  = posts.count_documents({})
    act_today = count_activity_today()
    pct_a    = round(active / total_p * 100) if total_p else 0
    pct_p    = round(paused / total_p * 100) if total_p else 0

    top5  = get_top_partners(5)
    top_lines = [
        f"  {i}. {'▶️' if not ch.get('paused') else '⏸'} "
        f"<b>{(ch.get('channel_name') or '?')[:28]}</b>  "
        f"<code>{ch.get('total_posts', 0)}</code>"
        for i, ch in enumerate(top5, 1)
    ]
    top_block = "\n".join(top_lines) if top_lines else "  —"

    maint = get_maintenance()
    maint_status = "🔴 ON" if maint.get("active") else "🟢 OFF"

    return (
        f"📊 <b>{BOT_NAME} — Dashboard</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"👥 <b>Users</b>\n"
        f"  Total     <code>{total_u}</code>\n"
        f"  Aktif     <code>{active_u}</code>\n"
        f"  Banned    <code>{count_banned()}</code>\n\n"
        f"📡 <b>Channel Partner</b>\n"
        f"  ▶️ Aktif   {progress_bar(active, total_p)}  <code>{active}</code> ({pct_a}%)\n"
        f"  ⏸ Paused  {progress_bar(paused, total_p)}  <code>{paused}</code> ({pct_p}%)\n"
        f"  Total     <code>{total_p}</code>\n\n"
        f"📦 <b>Repost</b>\n"
        f"  Hari ini  <code>{today}</code>\n"
        f"  7 hari    <code>{week}</code>\n"
        f"  30 hari   <code>{month}</code>\n"
        f"  All-time  <code>{total_r}</code>\n\n"
        f"🔔 Aktivitas hari ini  <code>{act_today}</code>\n"
        f"🔧 Maintenance         {maint_status}\n\n"
        f"🏆 <b>Top Partner</b>\n{top_block}"
    )


def _dashboard_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh",      callback_data="owner_dashboard"),
            InlineKeyboardButton("📋 Partner",      callback_data="owner_partner_0"),
        ],
        [
            InlineKeyboardButton("🏆 Top 10",       callback_data="owner_top10"),
            InlineKeyboardButton("📝 Aktivitas",    callback_data="owner_activity"),
        ],
        back_home(),
    ])


@Client.on_callback_query(filters.regex(r"^owner_dashboard$"))
@owner_only
async def cb_dashboard(client: Client, cb: CallbackQuery):
    try:
        await safe_edit(cb.message, _dashboard_text(), markup=_dashboard_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_dashboard] {e}")
    finally:
        await answer_cb(cb)


@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client: Client, message: Message):
    try:
        msg = await message.reply(_dashboard_text(), reply_markup=_dashboard_markup(), parse_mode=PM)
        store_msg(message.from_user.id, msg)
    except Exception as e:
        log.error(f"[cmd_stats] {e}")


# ═══════════════════════════════════════════════════════════
#  🏆 TOP 10 CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_top10$"))
@owner_only
async def cb_top10(client: Client, cb: CallbackQuery):
    try:
        top = get_top_partners(10)
        if not top:
            text = "🏆 <b>Top Channel</b>\n\nBelum ada data repost."
        else:
            lines = [f"🏆 <b>Top 10 Channel (All-time)</b>\n<code>{SEP}</code>"]
            for i, ch in enumerate(top, 1):
                icon  = "▶️" if not ch.get("paused") else "⏸"
                rp    = ch.get("total_posts", 0)
                uname = f"@{ch['username']}" if ch.get("username") else ""
                name  = (ch.get("channel_name") or "?")[:28]
                lines.append(f"{i:2}. {icon} <b>{name}</b>  {uname}  <code>{rp}</code>")
            text = "\n".join(lines)

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Dashboard", callback_data="owner_dashboard")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_top10] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📋 PARTNER LIST
# ═══════════════════════════════════════════════════════════

def _build_partner_list_markup(all_p: list, page: int):
    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)

    rows = []
    for ch in chunk:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        name  = (ch.get("channel_name") or str(ch["_id"]))[:35]
        rows.append([InlineKeyboardButton(
            f"{icon}  {name}",
            callback_data=f"owner_ch_{ch['_id']}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"owner_partner_{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"owner_partner_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton("🔎 Cari Channel", callback_data="owner_search"),
        InlineKeyboardButton("◀️ Dashboard",   callback_data="owner_dashboard"),
    ])
    return InlineKeyboardMarkup(rows)


def _partner_list_text(all_p: list, page: int) -> str:
    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)
    active = len([p for p in all_p if not p.get("paused")])
    lines  = [
        f"📋 <b>Channel Partner</b>  <code>{len(all_p)} total · {active} aktif</code>\n"
        f"<code>{SEP}</code>"
    ]
    for ch in chunk:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        uname = f"@{ch['username']}" if ch.get("username") else "—"
        rp    = ch.get("total_posts", 0)
        name  = (ch.get("channel_name") or "?")[:30]
        lines.append(
            f"\n{icon} <b>{name}</b>\n"
            f"     {uname}  ·  📦 {rp}"
        )
    return "\n".join(lines)


@Client.on_callback_query(filters.regex(r"^owner_partner_(\d+)$"))
@owner_only
async def cb_partner_list(client: Client, cb: CallbackQuery):
    try:
        page  = int(cb.matches[0].group(1))
        all_p = get_all_partners()
        if not all_p:
            await safe_edit(
                cb.message,
                "📋 <b>Channel Partner</b>\n\nBelum ada partner terdaftar.",
                markup=InlineKeyboardMarkup(back_home()),
                parse_mode=PM,
            )
        else:
            await safe_edit(
                cb.message,
                _partner_list_text(all_p, page),
                markup=_build_partner_list_markup(all_p, page),
                parse_mode=PM,
            )
    except Exception as e:
        log.error(f"[cb_partner_list] {e}")
    finally:
        await answer_cb(cb)


@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client: Client, message: Message):
    try:
        all_p = get_all_partners()
        if not all_p:
            text   = "📋 <b>Channel Partner</b>\n\nBelum ada partner."
            markup = InlineKeyboardMarkup(back_home())
        else:
            text   = _partner_list_text(all_p, 0)
            markup = _build_partner_list_markup(all_p, 0)
        msg = await message.reply(text, reply_markup=markup, parse_mode=PM)
        store_msg(message.from_user.id, msg)
    except Exception as e:
        log.error(f"[cmd_listpartner] {e}")


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
    mf       = partner.get("media_filter", "all")
    mf_label = {"all": "📷+🎬+📝 Semua", "photo": "📷 Foto", "video": "🎬 Video", "text": "📝 Teks"}.get(mf, mf)

    text = (
        f"📡 <b>{name}</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"Username      {uname}\n"
        f"Owner         <b>{owner_nm}</b>"
        + (f"  (<code>{owner_id}</code>)" if owner_id else "") + "\n"
        f"Status        {status}\n"
        f"Filter media  {mf_label}\n"
        f"Total repost  <code>{rp}</code>\n"
        f"Terdaftar     {added_s}\n"
    )
    if reason:
        text += f"\n⚠️ <i>{reason}</i>\n"
    return text


def _partner_detail_markup(partner: dict, channel_id: int) -> InlineKeyboardMarkup:
    paused = partner.get("paused", False)
    toggle = (
        InlineKeyboardButton("▶️ Aktifkan", callback_data=f"owner_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause",    callback_data=f"owner_pause_{channel_id}")
    )
    mf = partner.get("media_filter", "all")
    next_mf = {"all": "photo", "photo": "video", "video": "text", "text": "all"}
    mf_label = {"all": "📷+🎬 Filter: Semua", "photo": "📷 Filter: Foto", "video": "🎬 Filter: Video", "text": "📝 Filter: Teks"}
    return InlineKeyboardMarkup([
        [toggle],
        [InlineKeyboardButton(mf_label.get(mf, "Filter"), callback_data=f"owner_mf_{channel_id}_{next_mf.get(mf, 'all')}")],
        [InlineKeyboardButton("🗑️ Lepas Channel", callback_data=f"owner_remove_confirm_{channel_id}")],
        [InlineKeyboardButton("◀️ Daftar Partner", callback_data="owner_partner_0")],
    ])


@Client.on_callback_query(filters.regex(r"^owner_ch_(-?\d+)$"))
@owner_only
async def cb_owner_ch_detail(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)
        if not partner:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return
        _viewing_channel[cb.from_user.id] = channel_id
        await safe_edit(
            cb.message,
            _partner_detail_text(partner, channel_id),
            markup=_partner_detail_markup(partner, channel_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_ch_detail] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_pause_(-?\d+)$"))
@owner_only
async def cb_owner_pause(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)
        if not partner:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return
        upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh admin"})
        await answer_cb(cb, "⏸ Channel dijeda.")
        answered = True
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
        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _partner_detail_text(p_fresh, channel_id),
            markup=_partner_detail_markup(p_fresh, channel_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_pause] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_run_(-?\d+)$"))
@owner_only
async def cb_owner_run(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)
        if not partner:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return
        upsert_partner(channel_id, {"paused": False, "reason": ""})
        await answer_cb(cb, "▶️ Channel aktif!")
        answered = True
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
        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _partner_detail_text(p_fresh, channel_id),
            markup=_partner_detail_markup(p_fresh, channel_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_run] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_mf_(-?\d+)_(\w+)$"))
@owner_only
async def cb_owner_mf(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        new_mf     = cb.matches[0].group(2)
        partner    = get_partner(channel_id)
        if not partner:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return
        upsert_partner(channel_id, {"media_filter": new_mf})
        mf_label = {"all": "Semua", "photo": "Foto saja", "video": "Video saja", "text": "Teks saja"}
        await answer_cb(cb, f"✅ Filter: {mf_label.get(new_mf, new_mf)}")
        answered = True
        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _partner_detail_text(p_fresh, channel_id),
            markup=_partner_detail_markup(p_fresh, channel_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_mf] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_remove_confirm_(-?\d+)$"))
@owner_only
async def cb_owner_remove_confirm(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)
        if not partner:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return
        text = (
            f"🗑️ <b>Hapus Channel?</b>\n\n"
            f"📡 <b>{partner.get('channel_name', channel_id)}</b>\n\n"
            f"Channel akan dilepas dari bot. Data repost tetap tersimpan."
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"owner_remove_do_{channel_id}"),
            InlineKeyboardButton("❌ Batal",     callback_data=f"owner_ch_{channel_id}"),
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_owner_remove_confirm] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_remove_do_(-?\d+)$"))
@owner_only
async def cb_owner_remove_do(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)
        ch_name    = partner.get("channel_name", str(channel_id)) if partner else str(channel_id)
        upsert_partner(channel_id, {"paused": True, "reason": "Dilepas oleh admin", "owner_id": None})
        await answer_cb(cb, "✅ Channel dilepas.")
        answered = True
        await safe_edit(
            cb.message,
            f"✅ <b>Channel dilepas.</b>\n\n📡 <b>{ch_name}</b> sudah dilepas dari bot.",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Partner", callback_data="owner_partner_0")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_remove_do] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🔎 SEARCH CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_search$"))
@owner_only
async def cb_owner_search(client: Client, cb: CallbackQuery):
    try:
        _search_pending.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            f"🔎 <b>Cari Channel Partner</b>\n\n"
            f"Ketik nama atau username channel yang ingin dicari:\n\n"
            f"<i>Kirim /cancel untuk membatalkan</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_partner_0")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_owner_search] {e}")
    finally:
        await answer_cb(cb)


# PERBAIKAN: filter.regex untuk skip semua pesan yang diawali "/" (command)
@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=3)
@owner_only
async def handle_owner_text_input(client: Client, message: Message):
    uid  = message.from_user.id
    text = message.text.strip()

    # ─── Search ──────────────────────────────────────
    if uid in _search_pending:
        _search_pending.discard(uid)
        results = search_partners(text)
        if not results:
            out    = f"🔎 <b>Tidak ditemukan:</b> <i>{text}</i>"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Partner", callback_data="owner_partner_0")]])
        else:
            lines = [f"🔎 <b>Hasil: {len(results)} channel</b>\n<code>{SEP}</code>"]
            rows  = []
            for ch in results[:10]:
                icon = "▶️" if not ch.get("paused") else "⏸"
                name = (ch.get("channel_name") or "?")[:30]
                lines.append(f"\n{icon} <b>{name}</b>")
                rows.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"owner_ch_{ch['_id']}")])
            rows.append([InlineKeyboardButton("◀️ Partner", callback_data="owner_partner_0")])
            out    = "\n".join(lines)
            markup = InlineKeyboardMarkup(rows)
        msg = await message.reply(out, reply_markup=markup, parse_mode=PM)
        store_msg(uid, msg)
        return

    # ─── Blacklist add ───────────────────────────────
    if uid in _bl_add_pending:
        _bl_add_pending.discard(uid)
        add_blacklist(text)
        msg = await message.reply(
            f"✅ <b>Kata ditambahkan ke blacklist:</b>\n<code>{text.lower()}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Blacklist", callback_data="owner_blacklist")]]),
            parse_mode=PM,
        )
        store_msg(uid, msg)
        return

    # ─── Blacklist del ───────────────────────────────
    if uid in _bl_del_pending:
        _bl_del_pending.discard(uid)
        remove_blacklist(text)
        msg = await message.reply(
            f"✅ <b>Kata dihapus dari blacklist:</b>\n<code>{text.lower()}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Blacklist", callback_data="owner_blacklist")]]),
            parse_mode=PM,
        )
        store_msg(uid, msg)
        return

    # ─── Ban pending ─────────────────────────────────
    if uid in _ban_pending:
        _ban_pending.discard(uid)
        try:
            target_id = int(text.strip())
            ban_user(target_id, reason="Diblokir oleh admin", banned_by=uid)
            msg = await message.reply(
                f"🚫 <b>User diblokir:</b> <code>{target_id}</code>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Banned List", callback_data="owner_banned_list")]]),
                parse_mode=PM,
            )
            store_msg(uid, msg)
        except ValueError:
            msg = await message.reply(
                "❌ ID tidak valid. Masukkan angka ID Telegram.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="owner_banned_list")]]),
                parse_mode=PM,
            )
            store_msg(uid, msg)
        return

    # ─── Caption pending ─────────────────────────────
    if uid in _caption_pending:
        _caption_pending.discard(uid)
        set_caption_template(text)
        msg = await message.reply(
            f"✅ <b>Caption template disimpan!</b>\n\n"
            f"<code>{text[:200]}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Pengaturan", callback_data="owner_settings")]]),
            parse_mode=PM,
        )
        store_msg(uid, msg)
        return

    # ─── Maint reason pending ────────────────────────
    if uid in _maint_reason:
        _maint_reason.discard(uid)
        set_maintenance(True, text)
        msg = await message.reply(
            f"🔴 <b>Maintenance diaktifkan!</b>\n\n"
            f"Alasan: <i>{text}</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔧 Tools", callback_data="owner_tools")]]),
            parse_mode=PM,
        )
        store_msg(uid, msg)
        return


# ═══════════════════════════════════════════════════════════
#  🔧 TOOLS MENU
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_tools$"))
@owner_only
async def cb_tools(client: Client, cb: CallbackQuery):
    try:
        maint = get_maintenance()
        ms    = "🔴 Aktif" if maint.get("active") else "🟢 Nonaktif"
        bl    = get_blacklist()
        text  = (
            f"🔧 <b>Tools Panel</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"🚫 Blacklist       <code>{len(bl)} kata</code>\n"
            f"🔧 Maintenance     {ms}\n\n"
            f"Pilih aksi:"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚫 Blacklist",        callback_data="owner_blacklist"),
                InlineKeyboardButton("🔧 Maintenance",      callback_data="owner_maintenance"),
            ],
            [
                InlineKeyboardButton("📝 Caption Template", callback_data="owner_caption"),
                InlineKeyboardButton("🏥 Health Check",     callback_data="owner_health"),
            ],
            [
                InlineKeyboardButton("🔄 Reset Settings",   callback_data="owner_reset_settings_confirm"),
            ],
            back_home(),
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_tools] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🚫 BLACKLIST
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_blacklist$"))
@owner_only
async def cb_blacklist(client: Client, cb: CallbackQuery):
    try:
        words = get_blacklist()
        if words:
            word_list = "\n".join(f"  • <code>{w}</code>" for w in words[:30])
            extra = f"\n  <i>...+{len(words)-30} lainnya</i>" if len(words) > 30 else ""
        else:
            word_list = "  <i>Kosong</i>"
            extra = ""

        text = (
            f"🚫 <b>Blacklist Kata</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"<code>{len(words)}</code> kata terdaftar:\n\n"
            f"{word_list}{extra}"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Tambah Kata", callback_data="owner_bl_add"),
                InlineKeyboardButton("➖ Hapus Kata",  callback_data="owner_bl_del"),
            ],
            [InlineKeyboardButton("🗑️ Hapus Semua",   callback_data="owner_bl_clear_confirm")],
            [InlineKeyboardButton("◀️ Tools",          callback_data="owner_tools")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_blacklist] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_bl_add$"))
@owner_only
async def cb_bl_add(client: Client, cb: CallbackQuery):
    try:
        _bl_add_pending.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            "➕ <b>Tambah Kata Blacklist</b>\n\nKetik kata yang ingin diblacklist:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_blacklist")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bl_add] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_bl_del$"))
@owner_only
async def cb_bl_del(client: Client, cb: CallbackQuery):
    answered = False
    try:
        words = get_blacklist()
        if not words:
            await answer_cb(cb, "Blacklist kosong.", True)
            answered = True
            return
        _bl_del_pending.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            "➖ <b>Hapus Kata Blacklist</b>\n\nKetik kata yang ingin dihapus:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_blacklist")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bl_del] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_bl_clear_confirm$"))
@owner_only
async def cb_bl_clear_confirm(client: Client, cb: CallbackQuery):
    try:
        await safe_edit(
            cb.message,
            "🗑️ <b>Hapus Semua Blacklist?</b>\n\nSemua kata akan dihapus permanen.",
            markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ya, Hapus Semua", callback_data="owner_bl_clear_do"),
                InlineKeyboardButton("❌ Batal",            callback_data="owner_blacklist"),
            ]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bl_clear_confirm] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_bl_clear_do$"))
@owner_only
async def cb_bl_clear_do(client: Client, cb: CallbackQuery):
    answered = False
    try:
        from db.mongo import blacklist_col
        blacklist_col.delete_one({"_id": "global"})
        await answer_cb(cb, "✅ Blacklist dikosongkan.")
        answered = True
        await safe_edit(
            cb.message,
            "✅ <b>Blacklist dikosongkan.</b>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Tools", callback_data="owner_tools")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_bl_clear_do] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🔧 MAINTENANCE
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_maintenance$"))
@owner_only
async def cb_maintenance(client: Client, cb: CallbackQuery):
    try:
        maint  = get_maintenance()
        active = maint.get("active", False)
        reason = maint.get("reason", "—")
        status = "🔴 Aktif" if active else "🟢 Nonaktif"
        text = (
            f"🔧 <b>Mode Maintenance</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"Status   {status}\n"
            f"Alasan   <i>{reason or '—'}</i>\n\n"
            f"Saat maintenance aktif, hanya Owner yang bisa akses bot."
        )
        rows = []
        if active:
            rows.append([InlineKeyboardButton("🟢 Nonaktifkan Maintenance", callback_data="owner_maint_off")])
        else:
            rows.append([InlineKeyboardButton("🔴 Aktifkan Maintenance",    callback_data="owner_maint_on")])
        rows.append([InlineKeyboardButton("◀️ Tools", callback_data="owner_tools")])
        await safe_edit(cb.message, text, markup=InlineKeyboardMarkup(rows), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_maintenance] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_maint_off$"))
@owner_only
async def cb_maint_off(client: Client, cb: CallbackQuery):
    answered = False
    try:
        set_maintenance(False, "")
        await answer_cb(cb, "🟢 Maintenance dinonaktifkan.")
        answered = True
        await safe_edit(
            cb.message,
            "🟢 <b>Maintenance dinonaktifkan.</b>\n\nBot kembali normal.",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Tools", callback_data="owner_tools")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_maint_off] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_maint_on$"))
@owner_only
async def cb_maint_on(client: Client, cb: CallbackQuery):
    try:
        _maint_reason.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            "🔴 <b>Aktifkan Maintenance</b>\n\nKetik alasan maintenance:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_maintenance")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_maint_on] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📝 CAPTION TEMPLATE
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_caption$"))
@owner_only
async def cb_caption(client: Client, cb: CallbackQuery):
    try:
        tpl  = get_caption_template()
        text = (
            f"📝 <b>Caption Template</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"Template saat ini:\n<code>{tpl[:500]}</code>\n\n"
            f"Variabel tersedia:\n"
            f"<code>{{channel_link}}</code> <code>{{original_caption}}</code>\n"
            f"<code>{{owner_link}}</code> <code>{{date}}</code> <code>{{time}}</code>\n"
            f"<code>{{bot_link}}</code> <code>{{post_number}}</code>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Ubah Template", callback_data="owner_caption_edit")],
            [InlineKeyboardButton("🔄 Reset Default",  callback_data="owner_caption_reset")],
            [InlineKeyboardButton("◀️ Tools",          callback_data="owner_tools")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_caption] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_caption_edit$"))
@owner_only
async def cb_caption_edit(client: Client, cb: CallbackQuery):
    try:
        _caption_pending.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            "✏️ <b>Edit Caption Template</b>\n\nKetik template baru:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_caption")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_caption_edit] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_caption_reset$"))
@owner_only
async def cb_caption_reset(client: Client, cb: CallbackQuery):
    answered = False
    try:
        reset_caption_template()
        await answer_cb(cb, "✅ Caption direset ke default.")
        answered = True
        await safe_edit(
            cb.message,
            f"✅ <b>Caption template direset.</b>\n\n<code>{DEFAULT_CAPTION_TEMPLATE[:300]}</code>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Caption", callback_data="owner_caption")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_caption_reset] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🏥 HEALTH CHECK
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_health$"))
@owner_only
async def cb_health(client: Client, cb: CallbackQuery):
    try:
        from db.mongo import client as mongo_client
        try:
            mongo_client.admin.command("ping")
            db_status = "🟢 Terhubung"
        except Exception:
            db_status = "🔴 Terputus"

        me       = await client.get_me()
        bot_info = f"@{me.username}" if me.username else str(me.id)

        total_p  = count_partners()
        active_p = len(get_active_partners())
        total_r  = posts.count_documents({})

        text = (
            f"🏥 <b>Health Check</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"🤖 Bot         {bot_info}\n"
            f"🗄️  MongoDB     {db_status}\n\n"
            f"📡 Partner     <code>{active_p}</code> aktif / <code>{total_p}</code> total\n"
            f"📦 Repost      <code>{total_r}</code> all-time\n\n"
            f"⏰ Waktu       <code>{datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}</code>"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Tools", callback_data="owner_tools")]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_health] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  ⚙️ PENGATURAN
# ═══════════════════════════════════════════════════════════

def _settings_text() -> str:
    auto_del   = get_bot_setting("auto_delete_repost", True)
    allow_text = get_bot_setting("allow_text_repost", True)
    rate_limit = get_bot_setting("rate_limit_enabled", True)
    return (
        f"⚙️ <b>Pengaturan Bot</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"🗑️ Auto hapus repost   {'✅ ON' if auto_del else '❌ OFF'}\n"
        f"📝 Repost teks         {'✅ ON' if allow_text else '❌ OFF'}\n"
        f"⚡ Rate limit          {'✅ ON' if rate_limit else '❌ OFF'}\n"
    )


def _settings_markup() -> InlineKeyboardMarkup:
    auto_del   = get_bot_setting("auto_delete_repost", True)
    allow_text = get_bot_setting("allow_text_repost", True)
    rate_limit = get_bot_setting("rate_limit_enabled", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if auto_del else '❌'} Auto Hapus Repost",
            callback_data="owner_toggle_auto_delete",
        )],
        [InlineKeyboardButton(
            f"{'✅' if allow_text else '❌'} Repost Teks",
            callback_data="owner_toggle_text_repost",
        )],
        [InlineKeyboardButton(
            f"{'✅' if rate_limit else '❌'} Rate Limit",
            callback_data="owner_toggle_rate_limit",
        )],
        [InlineKeyboardButton("◀️ Menu Utama", callback_data="home")],
    ])


@Client.on_callback_query(filters.regex(r"^owner_settings$"))
@owner_only
async def cb_settings(client: Client, cb: CallbackQuery):
    try:
        await safe_edit(cb.message, _settings_text(), markup=_settings_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_settings] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_reset_settings_confirm$"))
@owner_only
async def cb_reset_settings_confirm(client: Client, cb: CallbackQuery):
    try:
        await safe_edit(
            cb.message,
            "🔄 <b>Reset Semua Pengaturan?</b>\n\nSemua pengaturan akan kembali ke default.",
            markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ya, Reset", callback_data="owner_reset_settings_do"),
                InlineKeyboardButton("❌ Batal",     callback_data="owner_settings"),
            ]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_reset_settings_confirm] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_reset_settings_do$"))
@owner_only
async def cb_reset_settings_do(client: Client, cb: CallbackQuery):
    answered = False
    try:
        for key in ("auto_delete_repost", "allow_text_repost", "rate_limit_enabled"):
            set_bot_setting(key, True)
        await answer_cb(cb, "✅ Pengaturan direset.")
        answered = True
        await safe_edit(cb.message, _settings_text(), markup=_settings_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_reset_settings_do] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_toggle_auto_delete$"))
@owner_only
async def cb_toggle_auto_delete(client: Client, cb: CallbackQuery):
    answered = False
    try:
        cur = get_bot_setting("auto_delete_repost", True)
        set_bot_setting("auto_delete_repost", not cur)
        await answer_cb(cb, f"Auto delete: {'✅ ON' if not cur else '❌ OFF'}")
        answered = True
        await safe_edit(cb.message, _settings_text(), markup=_settings_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_toggle_auto_delete] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_toggle_text_repost$"))
@owner_only
async def cb_toggle_text_repost(client: Client, cb: CallbackQuery):
    answered = False
    try:
        cur = get_bot_setting("allow_text_repost", True)
        set_bot_setting("allow_text_repost", not cur)
        await answer_cb(cb, f"Repost teks: {'✅ ON' if not cur else '❌ OFF'}")
        answered = True
        await safe_edit(cb.message, _settings_text(), markup=_settings_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_toggle_text_repost] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_toggle_rate_limit$"))
@owner_only
async def cb_toggle_rate_limit(client: Client, cb: CallbackQuery):
    answered = False
    try:
        cur = get_bot_setting("rate_limit_enabled", True)
        set_bot_setting("rate_limit_enabled", not cur)
        await answer_cb(cb, f"Rate limit: {'✅ ON' if not cur else '❌ OFF'}")
        answered = True
        await safe_edit(cb.message, _settings_text(), markup=_settings_markup(), parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_toggle_rate_limit] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📝 AKTIVITAS
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_activity$"))
@owner_only
async def cb_activity(client: Client, cb: CallbackQuery):
    try:
        acts = get_recent_activity(limit=15)
        if not acts:
            text = f"📝 <b>Aktivitas</b>\n\nBelum ada aktivitas."
        else:
            event_label = {
                "repost_success":    "✅ Repost",
                "repost_fail":       "❌ Repost gagal",
                "repost_deleted":    "🗑️ Repost dihapus",
                "partner_added":     "➕ Partner baru",
                "partner_activated": "▶️ Partner aktif",
                "bot_removed":       "⚠️ Bot dicopot",
                "blacklist_blocked": "🚫 Blacklist",
                "partner_manual_add":"🔧 Daftar manual",
            }
            lines = [f"📝 <b>Aktivitas Terbaru</b>\n<code>{SEP}</code>"]
            for a in acts:
                ts    = a.get("ts")
                ts_s  = ts.strftime("%d/%m %H:%M") if ts else "—"
                evt   = event_label.get(a.get("event", ""), a.get("event", "?"))
                pid   = a.get("partner_id")
                pid_s = f"  <code>{pid}</code>" if pid else ""
                lines.append(f"<code>{ts_s}</code>  {evt}{pid_s}")
            text = "\n".join(lines)

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="owner_activity")],
            back_home(),
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_activity] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🚫 BANNED USERS
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_banned_list$"))
@owner_only
async def cb_banned_list(client: Client, cb: CallbackQuery):
    try:
        banned = get_banned_list()
        if not banned:
            lines = ["<i>Tidak ada user yang diblokir.</i>"]
        else:
            lines = []
            for b in banned[:15]:
                uid    = b["_id"]
                reason = b.get("reason", "—")
                ts     = b.get("banned_at")
                ts_s   = ts.strftime("%d/%m/%Y") if ts else "—"
                lines.append(f"🚫 <code>{uid}</code>  {ts_s}\n   <i>{reason[:40]}</i>")

        text = (
            f"🚫 <b>Banned Users</b>  <code>{count_banned()} total</code>\n"
            f"<code>{SEP}</code>\n\n"
            + "\n\n".join(lines)
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Ban User",   callback_data="owner_ban_add"),
                InlineKeyboardButton("➖ Unban User", callback_data="owner_ban_remove"),
            ],
            back_home(),
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_banned_list] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_ban_add$"))
@owner_only
async def cb_ban_add(client: Client, cb: CallbackQuery):
    try:
        _ban_pending.add(cb.from_user.id)
        await safe_edit(
            cb.message,
            "🚫 <b>Ban User</b>\n\nKetik <b>User ID Telegram</b> yang ingin diblokir:\n\n<i>Kirim /cancel untuk batal</i>",
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="owner_banned_list")]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_ban_add] {e}")
    finally:
        await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_ban_remove$"))
@owner_only
async def cb_ban_remove_prompt(client: Client, cb: CallbackQuery):
    answered = False
    try:
        banned = get_banned_list()
        if not banned:
            await answer_cb(cb, "Tidak ada user yang diblokir.", True)
            answered = True
            return
        rows = []
        for b in banned[:10]:
            uid = b["_id"]
            rows.append([InlineKeyboardButton(f"✅ Unban {uid}", callback_data=f"owner_unban_{uid}")])
        rows.append([InlineKeyboardButton("◀️ Kembali", callback_data="owner_banned_list")])
        await safe_edit(
            cb.message,
            "➖ <b>Unban User</b>\n\nPilih user yang ingin di-unban:",
            markup=InlineKeyboardMarkup(rows),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_ban_remove_prompt] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^owner_unban_(-?\d+)$"))
@owner_only
async def cb_unban(client: Client, cb: CallbackQuery):
    answered = False
    try:
        uid = int(cb.matches[0].group(1))
        unban_user(uid)
        await answer_cb(cb, f"✅ User {uid} di-unban.")
        answered = True
        await cb_banned_list(client, cb)
    except Exception as e:
        log.error(f"[cb_unban] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📤 EXPORT DATA
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^owner_export$"))
@owner_only
async def cb_export(client: Client, cb: CallbackQuery):
    try:
        all_p   = get_all_partners()
        total_r = posts.count_documents({})
        today   = get_posts_today()
        week    = get_posts_this_week()

        lines = [
            "📤 <b>Export Data FessBot</b>",
            f"<code>Dibuat: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}</code>",
            f"<code>{SEP}</code>",
            "",
            "📊 STATISTIK GLOBAL",
            f"Total Partner : {count_partners()}",
            f"Aktif         : {len(get_active_partners())}",
            f"Total User    : {count_users()}",
            f"Repost Hari ini: {today}",
            f"Repost 7 hari : {week}",
            f"Repost Semua  : {total_r}",
            "",
            "📋 DAFTAR CHANNEL PARTNER",
        ]
        for i, p in enumerate(all_p, 1):
            status = "AKTIF" if not p.get("paused") else "PAUSED"
            uname  = f"@{p['username']}" if p.get("username") else "—"
            name   = p.get("channel_name", str(p["_id"]))
            rp     = p.get("total_posts", 0)
            lines.append(f"{i}. [{status}] {name} {uname} — {rp} repost")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n<i>...dipotong karena terlalu panjang</i>"

        await safe_edit(
            cb.message,
            f"<pre>{text}</pre>",
            markup=InlineKeyboardMarkup([back_home()]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_export] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  NOOP (tombol halaman / dekoratif)
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^noop$"))
async def cb_noop(client: Client, cb: CallbackQuery):
    await answer_cb(cb)
