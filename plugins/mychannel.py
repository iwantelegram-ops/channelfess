"""
My Channel & Statistik Saya — panel user.
FIX: semua callback di-wrap try/except + answer_cb() selalu dipanggil.
"""
import logging
from datetime import datetime, timezone, timedelta
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.enums import ParseMode
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import (
    get_partners_by_owner, get_partner, upsert_partner,
    count_posts_by_partner, get_notif_setting, set_notif_setting,
    get_recent_posts_by_partner,
)
from db.mongo import posts as posts_col
from utils import check_membership, paginate, safe_edit, nav_to, store_msg, answer_cb
from db.helpers import get_maintenance as _get_maintenance

async def _check_maintenance(message):
    from config import OWNER_ID
    if message.from_user.id == OWNER_ID:
        return False
    maint = _get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang dalam perbaikan.")
        await message.reply(
            "<b>Bot sedang maintenance</b>\n\n" + reason + "\n\nCoba lagi nanti!",
        )
        return True
    return False

log      = logging.getLogger("fessbot.mychannel")
PM       = ParseMode.HTML
PAGE_SIZE = 6


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def _channel_row(ch: dict) -> list:
    icon = "▶️" if not ch.get("paused") else "⏸"
    name = (ch.get("channel_name") or str(ch["_id"]))[:40]
    return [InlineKeyboardButton(
        f"{icon}  {name}",
        callback_data=f"ch_detail_{ch['_id']}",
    )]

def _paginate_nav(page: int, total_pages: int, prefix: str):
    if total_pages <= 1:
        return None
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_{page+1}"))
    return nav


# ═══════════════════════════════════════════════════════════
#  DAFTAR CHANNEL  (dipanggil dari message DAN callback)
# ═══════════════════════════════════════════════════════════

async def _show_channel_list(client, cb_or_msg, user_id: int,
                             page: int, from_cb: bool):
    try:
        channels     = get_partners_by_owner(user_id)
        active_count = sum(1 for c in channels if not c.get("paused"))

        if not channels:
            text = (
                f"📂 <b>My Channel</b>\n"
                f"<code>{'─' * 26}</code>\n\n"
                f"Belum ada channel yang terdaftar.\n\n"
                f"<b>Cara mendaftar:</b>\n"
                f"1️⃣  Buka pengaturan channelmu\n"
                f"2️⃣  Tambahkan <b>@{BOT_USERNAME}</b> sebagai <b>Admin</b>\n"
                f"3️⃣  Channel muncul di sini otomatis ✅"
            )
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "➕ Tambah Bot ke Channel",
                    url=(f"https://t.me/{BOT_USERNAME}?startchannel=true"
                         f"&admin=post_messages+edit_messages+delete_messages+invite_users"),
                )
            ]])
        else:
            chunk, total_pages = paginate(channels, page, PAGE_SIZE)
            text = (
                f"📂 <b>My Channel</b>\n"
                f"<code>{'─' * 26}</code>\n\n"
                f"Total <code>{len(channels)}</code>  ·  "
                f"▶️ Aktif <code>{active_count}</code>  ·  "
                f"⏸ Pause <code>{len(channels)-active_count}</code>\n\n"
                f"Pilih channel untuk dikelola:"
            )
            rows = [_channel_row(ch) for ch in chunk]
            nav  = _paginate_nav(page, total_pages, "my_channels")
            if nav:
                rows.append(nav)
            rows.append([InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")])
            markup = InlineKeyboardMarkup(rows)

        if from_cb:
            target_msg = cb_or_msg.message
            res = await safe_edit(target_msg, text, markup=markup, parse_mode=PM)
            if not res:
                sent = await client.send_message(target_msg.chat.id, text,
                                                 reply_markup=markup, parse_mode=PM)
                store_msg(user_id, sent)
        else:
            sent = await cb_or_msg.reply(text, reply_markup=markup, parse_mode=PM)
            store_msg(user_id, sent)
    except Exception as e:
        log.error(f"[_show_channel_list] {e}")
        if from_cb:
            await safe_edit(cb_or_msg.message, "❌ Terjadi error. Ketuk /start untuk reset.")


@Client.on_message(filters.text & filters.private & filters.regex(r"^📂 My Channel$"))
async def my_channel_btn(client: Client, message: Message):
    if await _check_maintenance(message):
        return
    user_id = message.from_user.id
    joined  = await check_membership(client, user_id)
    if not joined:
        await message.reply(
            "⚠️ <b>Join dulu</b> channel utama ya sebelum bisa akses My Channel.",
            parse_mode=PM,
        )
        return
    await _show_channel_list(client, message, user_id, page=0, from_cb=False)


@Client.on_callback_query(filters.regex(r"^my_channels_(\d+)$"))
async def cb_my_channels(client: Client, cb: CallbackQuery):
    try:
        page = int(cb.matches[0].group(1))
        await _show_channel_list(client, cb, cb.from_user.id, page=page, from_cb=True)
    except Exception as e:
        log.error(f"[cb_my_channels] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  DETAIL CHANNEL
# ═══════════════════════════════════════════════════════════

def _detail_markup(partner: dict, channel_id: int, user_id: int) -> InlineKeyboardMarkup:
    paused   = partner.get("paused", False)
    notif_rp = get_notif_setting(user_id, "repost_notif", True)

    toggle_btn = (
        InlineKeyboardButton("▶️ Aktifkan Forward", callback_data=f"ch_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause Forward",    callback_data=f"ch_pause_{channel_id}")
    )
    return InlineKeyboardMarkup([
        [toggle_btn],
        [InlineKeyboardButton("📊 Statistik Detail", callback_data=f"ch_stats_{channel_id}")],
        [InlineKeyboardButton("📋 Riwayat Repost",   callback_data=f"ch_history_{channel_id}")],
        [InlineKeyboardButton(
            f"{'🔔' if notif_rp else '🔕'} Notif Repost",
            callback_data=f"ch_toggle_notif_{channel_id}",
        )],
        [InlineKeyboardButton("❌ Lepas Channel",    callback_data=f"ch_remove_confirm_{channel_id}")],
        [InlineKeyboardButton("◀️ Kembali",          callback_data="my_channels_0")],
    ])

def _detail_text(partner: dict, channel_id: int, user_id: int) -> str:
    paused   = partner.get("paused", False)
    status   = "▶️ Aktif" if not paused else "⏸ Dijeda"
    uname    = f"@{partner['username']}" if partner.get("username") else "—"
    reason   = partner.get("reason", "")
    rp       = count_posts_by_partner(channel_id)
    added    = partner.get("added_at")
    added_s  = added.strftime("%d %b %Y") if added else "—"
    notif_rp = get_notif_setting(user_id, "repost_notif", True)
    notif_bl = get_notif_setting(user_id, "blacklist_notif", True)

    text = (
        f"📡 <b>{partner.get('channel_name', channel_id)}</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Username      {uname}\n"
        f"Status        {status}\n"
        f"Total repost  <code>{rp}</code>\n"
        f"Terdaftar     {added_s}\n\n"
        f"🔔 Notif repost      {'✅' if notif_rp else '❌'}\n"
        f"🔕 Notif blacklist   {'✅' if notif_bl else '❌'}\n"
    )
    if reason:
        text += f"\n⚠️ <i>{reason}</i>\n"
    return text


@Client.on_callback_query(filters.regex(r"^ch_detail_(-?\d+)$"))
async def cb_channel_detail(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Channel tidak ditemukan atau bukan milikmu.", True)
            answered = True
            return

        text   = _detail_text(partner, channel_id, user_id)
        markup = _detail_markup(partner, channel_id, user_id)
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_channel_detail] {e}")
        await answer_cb(cb, "❌ Error, coba lagi.", True)
        answered = True
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  PAUSE / RUN
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_pause_(-?\d+)$"))
async def cb_ch_pause(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh owner"})
        await answer_cb(cb, "⏸ Channel dijeda.")
        answered = True

        partner_fresh = get_partner(channel_id)
        text   = _detail_text(partner_fresh, channel_id, user_id)
        markup = _detail_markup(partner_fresh, channel_id, user_id)
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_pause] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^ch_run_(-?\d+)$"))
async def cb_ch_run(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        upsert_partner(channel_id, {"paused": False, "reason": ""})
        await answer_cb(cb, "▶️ Channel aktif!")
        answered = True

        partner_fresh = get_partner(channel_id)
        text   = _detail_text(partner_fresh, channel_id, user_id)
        markup = _detail_markup(partner_fresh, channel_id, user_id)
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_run] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  TOGGLE NOTIFIKASI
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_toggle_notif_(-?\d+)$"))
async def cb_toggle_notif_repost(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        current = get_notif_setting(user_id, "repost_notif", True)
        set_notif_setting(user_id, "repost_notif", not current)
        status = "aktif ✅" if not current else "nonaktif ❌"
        await answer_cb(cb, f"Notif repost {status}")
        answered = True

        partner_fresh = get_partner(channel_id)
        text   = _detail_text(partner_fresh, channel_id, user_id)
        markup = _detail_markup(partner_fresh, channel_id, user_id)
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_toggle_notif_repost] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  STATISTIK DETAIL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_stats_(-?\d+)$"))
async def cb_ch_stats(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        now   = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week  = today - timedelta(days=7)
        month = today - timedelta(days=30)

        total   = posts_col.count_documents({"partner_id": channel_id})
        t_today = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": today}})
        t_week  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": week}})
        t_month = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": month}})
        avg_day = round(t_month / 30, 1)

        added   = partner.get("added_at")
        added_s = added.strftime("%d %b %Y") if added else "—"

        text = (
            f"📊 <b>Statistik Channel</b>\n"
            f"<code>{'─' * 26}</code>\n\n"
            f"📡 <b>{partner.get('channel_name', '?')}</b>\n\n"
            f"Hari ini     <code>{t_today}</code> repost\n"
            f"7 hari       <code>{t_week}</code> repost\n"
            f"30 hari      <code>{t_month}</code> repost\n"
            f"All-time     <code>{total}</code> repost\n\n"
            f"📈 Rata-rata  <code>{avg_day}</code> / hari\n\n"
            f"<code>{'─' * 26}</code>\n"
            f"Terdaftar    {added_s}"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_stats] {e}")
        await answer_cb(cb, "❌ Error saat ambil statistik.", True)
        answered = True
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  RIWAYAT REPOST
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_history_(-?\d+)$"))
async def cb_ch_history(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id  = int(cb.matches[0].group(1))
        user_id     = cb.from_user.id
        partner     = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        recent      = get_recent_posts_by_partner(channel_id, limit=7)
        main_id_str = str(MAIN_CHANNEL_ID).replace("-100", "")

        if not recent:
            lines = ["Belum ada riwayat repost."]
        else:
            lines = []
            for idx, p in enumerate(recent, 1):
                added = p.get("added_at")
                ts    = added.strftime("%d %b %Y %H:%M") if added else "—"
                link  = f"https://t.me/c/{main_id_str}/{p['main_msg_id']}"
                lines.append(f"{idx}. <a href='{link}'>Lihat repost</a> · {ts}")

        text = (
            f"📋 <b>Riwayat Repost Terakhir</b>\n"
            f"<code>{'─' * 26}</code>\n\n"
            f"📡 <b>{partner.get('channel_name', '?')}</b>\n\n"
            + "\n".join(lines)
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_history] {e}")
        await answer_cb(cb, "❌ Error saat ambil riwayat.", True)
        answered = True
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  LEPAS CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_remove_confirm_(-?\d+)$"))
async def cb_ch_remove_confirm(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        ch_name = partner.get("channel_name", str(channel_id))
        text = (
            f"❌ <b>Lepas Channel?</b>\n\n"
            f"📡 <b>{ch_name}</b>\n\n"
            f"Channel ini akan <b>dilepas</b> dari FessBot.\n"
            f"Repost otomatis akan berhenti.\n\n"
            f"<i>Data repost tetap tersimpan.</i>"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ya, Lepas", callback_data=f"ch_remove_do_{channel_id}"),
            InlineKeyboardButton("❌ Batal",     callback_data=f"ch_detail_{channel_id}"),
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_remove_confirm] {e}")
        await answer_cb(cb, "❌ Error.", True)
        answered = True
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^ch_remove_do_(-?\d+)$"))
async def cb_ch_remove_do(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        ch_name = partner.get("channel_name", str(channel_id))
        upsert_partner(channel_id, {
            "paused": True,
            "reason": "Dilepas oleh owner",
            "owner_id": None,
        })
        await answer_cb(cb, "Channel dilepas.")
        answered = True

        await safe_edit(
            cb.message,
            f"✅ <b>Channel dilepas.</b>\n\n"
            f"📡 <b>{ch_name}</b> sudah tidak terhubung.\n\n"
            f"Untuk mendaftarkan ulang, tambahkan bot sebagai Admin di channelmu.",
            markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ My Channel", callback_data="my_channels_0")
            ]]),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_ch_remove_do] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📊 STATISTIK SAYA
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^📊 Statistik Saya$"))
async def statistik_saya(client: Client, message: Message):
    if await _check_maintenance(message):
        return
    user_id  = message.from_user.id
    channels = get_partners_by_owner(user_id)

    if not channels:
        text = (
            f"📊 <b>Statistik Saya</b>\n\n"
            f"Kamu belum punya channel terdaftar."
        )
        await message.reply(text, parse_mode=PM)
        return

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - timedelta(days=7)

    lines = [f"📊 <b>Statistik Saya</b>\n<code>{'─' * 26}</code>"]
    grand_total = grand_today = grand_week = 0

    for ch in channels:
        cid    = ch["_id"]
        total  = posts_col.count_documents({"partner_id": cid})
        t_day  = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": today}})
        t_week = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": week}})
        icon   = "▶️" if not ch.get("paused") else "⏸"
        grand_total += total
        grand_today += t_day
        grand_week  += t_week

        name = (ch.get("channel_name") or "?")[:35]
        lines.append(
            f"\n{icon} <b>{name}</b>\n"
            f"  Hari ini <code>{t_day}</code>  ·  "
            f"7 hari <code>{t_week}</code>  ·  "
            f"Total <code>{total}</code>"
        )

    lines.append(
        f"\n<code>{'─' * 26}</code>\n"
        f"🔢 <b>Grand Total</b>\n"
        f"  Hari ini <code>{grand_today}</code>  ·  "
        f"7 hari <code>{grand_week}</code>  ·  "
        f"All-time <code>{grand_total}</code>"
    )

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("📂 My Channel", callback_data="my_channels_0")
    ]])
    await message.reply("\n".join(lines), reply_markup=markup, parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  🔔 NOTIFIKASI SETTINGS
# ═══════════════════════════════════════════════════════════

def _notif_text_and_markup(user_id: int):
    notif_rp = get_notif_setting(user_id, "repost_notif", True)
    notif_bl = get_notif_setting(user_id, "blacklist_notif", True)
    notif_st = get_notif_setting(user_id, "status_notif", True)

    text = (
        f"🔔 <b>Pengaturan Notifikasi</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"📦 Notif Repost          {'✅ Aktif' if notif_rp else '❌ Nonaktif'}\n"
        f"🚫 Notif Blacklist       {'✅ Aktif' if notif_bl else '❌ Nonaktif'}\n"
        f"📡 Notif Status Channel  {'✅ Aktif' if notif_st else '❌ Nonaktif'}\n"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🔔' if notif_rp else '🔕'} Notif Repost",
            callback_data="notif_toggle_repost",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_bl else '🔕'} Notif Blacklist",
            callback_data="notif_toggle_blacklist",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_st else '🔕'} Notif Status Channel",
            callback_data="notif_toggle_status",
        )],
    ])
    return text, markup


@Client.on_message(filters.text & filters.private & filters.regex(r"^🔔 Notifikasi$"))
async def notifikasi_settings(client: Client, message: Message):
    if await _check_maintenance(message):
        return
    user_id = message.from_user.id
    text, markup = _notif_text_and_markup(user_id)
    await message.reply(text, reply_markup=markup, parse_mode=PM)


@Client.on_callback_query(filters.regex(r"^notif_toggle_(repost|blacklist|status)$"))
async def cb_notif_toggle(client: Client, cb: CallbackQuery):
    answered = False
    try:
        key_map = {
            "repost":    "repost_notif",
            "blacklist": "blacklist_notif",
            "status":    "status_notif",
        }
        kind    = cb.matches[0].group(1)
        db_key  = key_map[kind]
        user_id = cb.from_user.id
        current = get_notif_setting(user_id, db_key, True)
        set_notif_setting(user_id, db_key, not current)

        status = "aktif ✅" if not current else "nonaktif ❌"
        await answer_cb(cb, f"Notif {kind} {status}")
        answered = True

        text, markup = _notif_text_and_markup(user_id)
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_notif_toggle] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  MISC CALLBACKS
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^close_msg$"))
async def cb_close(client: Client, cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await answer_cb(cb)


@Client.on_callback_query(filters.regex("^noop$"))
async def cb_noop(client: Client, cb: CallbackQuery):
    await answer_cb(cb)
