"""
My Channel & Statistik Saya — panel user.
Navigasi: semua transisi menggunakan edit_text (halaman berubah, bukan pesan baru).
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
    get_partners_by_owner, get_partner, upsert_partner, remove_partner,
    count_posts_by_partner, get_notif_setting, set_notif_setting,
    get_recent_posts_by_partner,
)
from db.mongo import posts as posts_col
from utils import check_membership, paginate, safe_edit, nav_to, store_msg

log = logging.getLogger("fessbot.mychannel")
PM  = ParseMode.HTML
PAGE_SIZE = 6


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def _channel_row(ch: dict) -> list:
    icon = "▶️" if not ch.get("paused") else "⏸"
    return [InlineKeyboardButton(
        f"{icon}  {ch.get('channel_name', str(ch['_id']))}",
        callback_data=f"ch_detail_{ch['_id']}",
    )]

def _nav_back_btn(channel_id: int = None) -> list:
    if channel_id:
        return [InlineKeyboardButton("◀️ Kembali ke Daftar", callback_data="my_channels_0")]
    return [InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")]

def _paginate_rows(page: int, total_pages: int, cb_prefix: str) -> list | None:
    if total_pages <= 1:
        return None
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"{cb_prefix}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"{cb_prefix}_{page+1}"))
    return nav


# ═══════════════════════════════════════════════════════════
#  DAFTAR CHANNEL
# ═══════════════════════════════════════════════════════════

async def _show_channel_list(client, source, user_id: int, page: int, edit: bool):
    channels = get_partners_by_owner(user_id)

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
        if edit:
            await safe_edit(source.message, text, markup=markup, parse_mode=PM)
        else:
            msg = await nav_to(client, user_id, source.chat.id, text,
                               inline_markup=markup, parse_mode=PM)
            if not msg:
                await source.reply(text, reply_markup=markup, parse_mode=PM)
        return

    active_count = sum(1 for c in channels if not c.get("paused"))
    chunk, total_pages = paginate(channels, page, PAGE_SIZE)

    text = (
        f"📂 <b>My Channel</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Total: <code>{len(channels)}</code>  ·  "
        f"▶️ Aktif: <code>{active_count}</code>  ·  "
        f"⏸ Pause: <code>{len(channels)-active_count}</code>\n\n"
        f"Pilih channel untuk dikelola:"
    )

    rows = [_channel_row(ch) for ch in chunk]
    nav  = _paginate_rows(page, total_pages, "my_channels")
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")])
    markup = InlineKeyboardMarkup(rows)

    if edit:
        await safe_edit(source.message, text, markup=markup, parse_mode=PM)
    else:
        msg = await nav_to(client, user_id, source.chat.id, text,
                           inline_markup=markup, parse_mode=PM)
        if not msg:
            sent = await source.reply(text, reply_markup=markup, parse_mode=PM)
            store_msg(user_id, sent)


@Client.on_message(filters.text & filters.private & filters.regex(r"^📂 My Channel$"))
async def my_channel_btn(client: Client, message: Message):
    user_id = message.from_user.id
    joined  = await check_membership(client, user_id)
    if not joined:
        await message.reply(
            "⚠️ <b>Join dulu</b> channel utama ya sebelum bisa akses My Channel.",
            parse_mode=PM,
        )
        return
    await _show_channel_list(client, message, user_id, page=0, edit=False)


@Client.on_callback_query(filters.regex(r"^my_channels_(\d+)$"))
async def cb_my_channels(client: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    await _show_channel_list(client, cb, cb.from_user.id, page=page, edit=True)
    await cb.answer()


# ═══════════════════════════════════════════════════════════
#  DETAIL CHANNEL
# ═══════════════════════════════════════════════════════════

async def _show_channel_detail(cb: CallbackQuery, channel_id: int):
    partner = get_partner(channel_id)
    user_id = cb.from_user.id

    if not partner or partner.get("owner_id") != user_id:
        await cb.answer("Channel tidak ditemukan atau bukan milikmu.", show_alert=True)
        return

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

    toggle_btn = (
        InlineKeyboardButton("▶️ Aktifkan Forward",  callback_data=f"ch_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause Forward",     callback_data=f"ch_pause_{channel_id}")
    )

    markup = InlineKeyboardMarkup([
        [toggle_btn],
        [InlineKeyboardButton("📊 Statistik Detail",  callback_data=f"ch_stats_{channel_id}")],
        [InlineKeyboardButton("📋 Riwayat Repost",    callback_data=f"ch_history_{channel_id}")],
        [InlineKeyboardButton(
            f"🔔 Notif Repost {'✅' if notif_rp else '❌'}",
            callback_data=f"ch_toggle_notif_repost_{channel_id}",
        )],
        [InlineKeyboardButton("❌ Lepas Channel", callback_data=f"ch_remove_confirm_{channel_id}")],
        _nav_back_btn(),
    ])
    await safe_edit(cb.message, text, markup=markup, parse_mode=PM)


@Client.on_callback_query(filters.regex(r"^ch_detail_(-?\d+)$"))
async def cb_channel_detail(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    await _show_channel_detail(cb, channel_id)
    await cb.answer()


# ═══════════════════════════════════════════════════════════
#  PAUSE / RUN
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_pause_(-?\d+)$"))
async def cb_ch_pause(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh owner"})
    await cb.answer("⏸ Channel dijeda.", show_alert=False)
    await _show_channel_detail(cb, channel_id)


@Client.on_callback_query(filters.regex(r"^ch_run_(-?\d+)$"))
async def cb_ch_run(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    await cb.answer("▶️ Channel aktif!", show_alert=False)
    await _show_channel_detail(cb, channel_id)


# ═══════════════════════════════════════════════════════════
#  TOGGLE NOTIFIKASI
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_toggle_notif_repost_(-?\d+)$"))
async def cb_toggle_notif_repost(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    user_id    = cb.from_user.id
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != user_id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    current = get_notif_setting(user_id, "repost_notif", True)
    set_notif_setting(user_id, "repost_notif", not current)
    status = "✅ aktif" if not current else "❌ nonaktif"
    await cb.answer(f"Notifikasi repost {status}", show_alert=False)
    await _show_channel_detail(cb, channel_id)


# ═══════════════════════════════════════════════════════════
#  STATISTIK DETAIL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_stats_(-?\d+)$"))
async def cb_ch_stats(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - timedelta(days=7)
    month = today - timedelta(days=30)

    total    = posts_col.count_documents({"partner_id": channel_id})
    t_today  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": today}})
    t_week   = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": week}})
    t_month  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": month}})

    # Hitung rata-rata per hari (30 hari terakhir)
    avg_day = round(t_month / 30, 1)

    added    = partner.get("added_at")
    added_s  = added.strftime("%d %b %Y") if added else "—"

    text = (
        f"📊 <b>Statistik Channel</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"📡 <b>{partner.get('channel_name')}</b>\n\n"
        f"Hari ini     <code>{t_today}</code> repost\n"
        f"7 hari       <code>{t_week}</code> repost\n"
        f"30 hari      <code>{t_month}</code> repost\n"
        f"All-time     <code>{total}</code> repost\n\n"
        f"📈 Rata-rata  <code>{avg_day}</code> / hari\n\n"
        f"<code>{'─' * 26}</code>\n"
        f"Terdaftar    {added_s}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")],
    ])
    await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    await cb.answer()


# ═══════════════════════════════════════════════════════════
#  RIWAYAT REPOST
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_history_(-?\d+)$"))
async def cb_ch_history(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    recent = get_recent_posts_by_partner(channel_id, limit=7)
    uname  = partner.get("username", "")
    main_id_str = str(MAIN_CHANNEL_ID).replace("-100", "")

    if not recent:
        lines = ["Belum ada riwayat repost."]
    else:
        lines = []
        for idx, p in enumerate(recent, 1):
            added = p.get("added_at")
            ts    = added.strftime("%d %b %Y %H:%M") if added else "—"
            main_link = f"https://t.me/c/{main_id_str}/{p['main_msg_id']}"
            lines.append(f"{idx}. <a href='{main_link}'>Lihat repost</a> · {ts}")

    text = (
        f"📋 <b>Riwayat Repost Terakhir</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"📡 <b>{partner.get('channel_name')}</b>\n\n"
        + "\n".join(lines)
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")],
    ])
    await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    await cb.answer()


# ═══════════════════════════════════════════════════════════
#  LEPAS / HAPUS CHANNEL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_remove_confirm_(-?\d+)$"))
async def cb_ch_remove_confirm(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    ch_name = partner.get("channel_name", str(channel_id))
    text = (
        f"❌ <b>Lepas Channel?</b>\n\n"
        f"📡 <b>{ch_name}</b>\n\n"
        f"Channel ini akan <b>dilepas</b> dari FessBot.\n"
        f"Repost otomatis akan berhenti.\n\n"
        f"<i>Data repost tetap tersimpan, channel bisa didaftarkan lagi kapan saja.</i>"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ya, Lepas",   callback_data=f"ch_remove_do_{channel_id}"),
            InlineKeyboardButton("❌ Batal",        callback_data=f"ch_detail_{channel_id}"),
        ]
    ])
    await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^ch_remove_do_(-?\d+)$"))
async def cb_ch_remove_do(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    ch_name = partner.get("channel_name", str(channel_id))
    upsert_partner(channel_id, {"paused": True, "reason": "Dilepas oleh owner", "owner_id": None})

    await safe_edit(
        cb.message,
        f"✅ <b>Channel dilepas.</b>\n\n"
        f"📡 <b>{ch_name}</b> sudah tidak terhubung ke FessBot.\n\n"
        f"Untuk mendaftarkan ulang, tambahkan bot sebagai Admin di channel kamu.",
        markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ My Channel", callback_data="my_channels_0")
        ]]),
        parse_mode=PM,
    )
    await cb.answer("Channel dilepas.", show_alert=False)


# ═══════════════════════════════════════════════════════════
#  📊 STATISTIK SAYA (semua channel milik user)
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^📊 Statistik Saya$"))
async def statistik_saya(client: Client, message: Message):
    user_id  = message.from_user.id
    channels = get_partners_by_owner(user_id)

    if not channels:
        text = (
            f"📊 <b>Statistik Saya</b>\n\n"
            f"Kamu belum punya channel terdaftar.\n"
            f"Tambahkan bot sebagai Admin di channelmu untuk mulai."
        )
        msg = await nav_to(client, user_id, message.chat.id, text, parse_mode=PM)
        if not msg:
            await message.reply(text, parse_mode=PM)
        return

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - timedelta(days=7)

    lines = [
        f"📊 <b>Statistik Saya</b>\n"
        f"<code>{'─' * 26}</code>\n"
    ]
    grand_total = 0
    grand_today = 0
    grand_week  = 0

    for ch in channels:
        cid    = ch["_id"]
        total  = posts_col.count_documents({"partner_id": cid})
        t_day  = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": today}})
        t_week = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": week}})
        icon   = "▶️" if not ch.get("paused") else "⏸"
        grand_total += total
        grand_today += t_day
        grand_week  += t_week

        lines.append(
            f"\n{icon} <b>{ch.get('channel_name','?')}</b>\n"
            f"  Hari ini <code>{t_day}</code>  ·  "
            f"7 hari <code>{t_week}</code>  ·  "
            f"Total <code>{total}</code>"
        )

    lines.append(
        f"\n<code>{'─' * 26}</code>\n"
        f"🔢 <b>Grand Total:</b>\n"
        f"  Hari ini <code>{grand_today}</code>  ·  "
        f"7 hari <code>{grand_week}</code>  ·  "
        f"All-time <code>{grand_total}</code>"
    )

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("📂 My Channel", callback_data="my_channels_0")
    ]])

    msg = await nav_to(
        client, user_id, message.chat.id,
        "\n".join(lines), inline_markup=markup, parse_mode=PM,
    )
    if not msg:
        await message.reply("\n".join(lines), reply_markup=markup, parse_mode=PM)


# ═══════════════════════════════════════════════════════════
#  🔔 NOTIFIKASI SETTINGS
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex(r"^🔔 Notifikasi$"))
async def notifikasi_settings(client: Client, message: Message):
    user_id = message.from_user.id
    notif_rp = get_notif_setting(user_id, "repost_notif", True)
    notif_bl = get_notif_setting(user_id, "blacklist_notif", True)
    notif_st = get_notif_setting(user_id, "status_notif", True)

    text = (
        f"🔔 <b>Pengaturan Notifikasi</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Atur notifikasi yang ingin kamu terima dari bot.\n\n"
        f"📦 Notif Repost          {'✅ Aktif' if notif_rp else '❌ Nonaktif'}\n"
        f"🚫 Notif Blacklist       {'✅ Aktif' if notif_bl else '❌ Nonaktif'}\n"
        f"📡 Notif Status Channel  {'✅ Aktif' if notif_st else '❌ Nonaktif'}\n"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🔔' if notif_rp else '🔕'} Notif Repost",
            callback_data="toggle_notif_repost",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_bl else '🔕'} Notif Blacklist",
            callback_data="toggle_notif_blacklist",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_st else '🔕'} Notif Status Channel",
            callback_data="toggle_notif_status",
        )],
    ])
    msg = await nav_to(
        client, user_id, message.chat.id, text,
        inline_markup=markup, parse_mode=PM,
    )
    if not msg:
        await message.reply(text, reply_markup=markup, parse_mode=PM)


@Client.on_callback_query(filters.regex(r"^toggle_notif_(repost|blacklist|status)$"))
async def cb_toggle_notif(client: Client, cb: CallbackQuery):
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

    notif_rp = get_notif_setting(user_id, "repost_notif", True)
    notif_bl = get_notif_setting(user_id, "blacklist_notif", True)
    notif_st = get_notif_setting(user_id, "status_notif", True)

    text = (
        f"🔔 <b>Pengaturan Notifikasi</b>\n"
        f"<code>{'─' * 26}</code>\n\n"
        f"Atur notifikasi yang ingin kamu terima dari bot.\n\n"
        f"📦 Notif Repost          {'✅ Aktif' if notif_rp else '❌ Nonaktif'}\n"
        f"🚫 Notif Blacklist       {'✅ Aktif' if notif_bl else '❌ Nonaktif'}\n"
        f"📡 Notif Status Channel  {'✅ Aktif' if notif_st else '❌ Nonaktif'}\n"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🔔' if notif_rp else '🔕'} Notif Repost",
            callback_data="toggle_notif_repost",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_bl else '🔕'} Notif Blacklist",
            callback_data="toggle_notif_blacklist",
        )],
        [InlineKeyboardButton(
            f"{'🔔' if notif_st else '🔕'} Notif Status Channel",
            callback_data="toggle_notif_status",
        )],
    ])
    await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    status = "aktif ✅" if not current else "nonaktif ❌"
    await cb.answer(f"Notifikasi {kind} {status}", show_alert=False)


# ═══════════════════════════════════════════════════════════
#  MISC callbacks
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^close_msg$"))
async def cb_close(client: Client, cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()

@Client.on_callback_query(filters.regex("^noop$"))
async def cb_noop(client: Client, cb: CallbackQuery):
    await cb.answer()
