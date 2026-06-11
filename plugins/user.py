"""
Panel User — My Channel, Statistik, Notifikasi, Info Bot, Tutorial, Bantuan.
Full inline keyboard, edit-in-place. Tidak ada reply keyboard.
"""
import logging
from datetime import datetime, timezone, timedelta
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ParseMode

from config import (
    MAIN_CHANNEL_ID, MAIN_CHANNEL_USERNAME,
    BOT_USERNAME, OWNER_USERNAME, OWNER_NAME, BOT_NAME, BOT_DESC,
)
from db.helpers import (
    get_partners_by_owner, get_partner, upsert_partner,
    count_posts_by_partner, get_notif_setting, set_notif_setting,
    get_recent_posts_by_partner, count_partners, get_active_partners,
    count_users, get_maintenance, is_banned,
)
from db.mongo import posts as posts_col
from utils import check_membership, paginate, safe_edit, store_msg, answer_cb

log      = logging.getLogger("fessbot.user")
PM       = ParseMode.HTML
PAGE_SIZE = 6
SEP      = "─" * 30


# ═══════════════════════════════════════════════════════════
#  MAINTENANCE + BAN CHECK
# ═══════════════════════════════════════════════════════════

async def _is_blocked(client, cb_or_msg, user_id: int) -> bool:
    from config import OWNER_ID
    if user_id == OWNER_ID:
        return False
    if is_banned(user_id):
        txt = "🚫 <b>Akun kamu diblokir.</b>\n\nHubungi admin untuk info lebih lanjut."
        if hasattr(cb_or_msg, "message"):
            await safe_edit(cb_or_msg.message, txt, markup=None, parse_mode=PM)
        else:
            await cb_or_msg.reply(txt, parse_mode=PM)
        return True
    maint = get_maintenance()
    if maint.get("active"):
        reason = maint.get("reason", "Sedang dalam pemeliharaan.")
        txt = f"🔧 <b>Bot Maintenance</b>\n\n<i>{reason}</i>\n\nCoba lagi nanti."
        if hasattr(cb_or_msg, "message"):
            await safe_edit(cb_or_msg.message, txt, markup=None, parse_mode=PM)
        else:
            await cb_or_msg.reply(txt, parse_mode=PM)
        return True
    return False


# ═══════════════════════════════════════════════════════════
#  📂 MY CHANNEL LIST
# ═══════════════════════════════════════════════════════════

def _channel_list_text(channels: list, page: int) -> str:
    active = sum(1 for c in channels if not c.get("paused"))
    return (
        f"📂 <b>My Channel</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"Total <code>{len(channels)}</code>  ·  "
        f"▶️ Aktif <code>{active}</code>  ·  "
        f"⏸ Pause <code>{len(channels)-active}</code>\n\n"
        f"Pilih channel:"
    )


def _channel_list_markup(channels: list, page: int) -> InlineKeyboardMarkup:
    chunk, total_pages = paginate(channels, page, PAGE_SIZE)
    rows = []
    for ch in chunk:
        icon = "▶️" if not ch.get("paused") else "⏸"
        name = (ch.get("channel_name") or str(ch["_id"]))[:35]
        rows.append([InlineKeyboardButton(
            f"{icon}  {name}",
            callback_data=f"ch_detail_{ch['_id']}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"user_channels_{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"user_channels_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➕ Tambah Channel", url=(
        f"https://t.me/{BOT_USERNAME}?startchannel=true"
        f"&admin=post_messages+edit_messages+delete_messages+invite_users"
    ))])
    rows.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="home")])
    return InlineKeyboardMarkup(rows)


@Client.on_callback_query(filters.regex(r"^user_channels_(\d+)$"))
async def cb_user_channels(client: Client, cb: CallbackQuery):
    try:
        user_id = cb.from_user.id
        if await _is_blocked(client, cb, user_id):
            await answer_cb(cb)
            return

        joined = await check_membership(client, user_id)
        if not joined:
            await safe_edit(
                cb.message,
                "⚠️ <b>Kamu belum join channel utama.</b>\n\nJoin dulu untuk menggunakan fitur ini.",
                markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}"),
                ]]),
                parse_mode=PM,
            )
            await answer_cb(cb)
            return

        page     = int(cb.matches[0].group(1))
        channels = get_partners_by_owner(user_id)

        if not channels:
            await safe_edit(
                cb.message,
                f"📂 <b>My Channel</b>\n"
                f"<code>{SEP}</code>\n\n"
                f"Kamu belum punya channel terdaftar.\n\n"
                f"<b>Cara mendaftar:</b>\n"
                f"1️⃣  Buka pengaturan channelmu\n"
                f"2️⃣  Tambahkan <b>@{BOT_USERNAME}</b> sebagai Admin\n"
                f"3️⃣  Channel muncul di sini otomatis ✅",
                markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Tambah Bot ke Channel", url=(
                        f"https://t.me/{BOT_USERNAME}?startchannel=true"
                        f"&admin=post_messages+edit_messages+delete_messages+invite_users"
                    ))],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
                ]),
                parse_mode=PM,
            )
        else:
            await safe_edit(
                cb.message,
                _channel_list_text(channels, page),
                markup=_channel_list_markup(channels, page),
                parse_mode=PM,
            )
    except Exception as e:
        log.error(f"[cb_user_channels] {e}")
    finally:
        await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  DETAIL CHANNEL
# ═══════════════════════════════════════════════════════════

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
    mf       = partner.get("media_filter", "all")
    mf_label = {"all": "Semua", "photo": "Foto", "video": "Video", "text": "Teks"}.get(mf, mf)

    text = (
        f"📡 <b>{partner.get('channel_name', channel_id)}</b>\n"
        f"<code>{SEP}</code>\n\n"
        f"Username      {uname}\n"
        f"Status        {status}\n"
        f"Filter media  {mf_label}\n"
        f"Total repost  <code>{rp}</code>\n"
        f"Terdaftar     {added_s}\n\n"
        f"🔔 Notif repost     {'✅' if notif_rp else '❌'}\n"
        f"🔕 Notif blacklist  {'✅' if notif_bl else '❌'}"
    )
    if reason:
        text += f"\n\n⚠️ <i>{reason}</i>"
    return text


def _detail_markup(partner: dict, channel_id: int, user_id: int) -> InlineKeyboardMarkup:
    paused   = partner.get("paused", False)
    notif_rp = get_notif_setting(user_id, "repost_notif", True)
    notif_bl = get_notif_setting(user_id, "blacklist_notif", True)
    toggle   = (
        InlineKeyboardButton("▶️ Aktifkan", callback_data=f"ch_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause",    callback_data=f"ch_pause_{channel_id}")
    )
    return InlineKeyboardMarkup([
        [toggle],
        [
            InlineKeyboardButton("📊 Statistik",     callback_data=f"ch_stats_{channel_id}"),
            InlineKeyboardButton("📋 Riwayat",       callback_data=f"ch_history_{channel_id}"),
        ],
        [
            InlineKeyboardButton(
                f"{'🔔' if notif_rp else '🔕'} Notif Repost",
                callback_data=f"ch_notif_rp_{channel_id}",
            ),
            InlineKeyboardButton(
                f"{'🔔' if notif_bl else '🔕'} Notif BL",
                callback_data=f"ch_notif_bl_{channel_id}",
            ),
        ],
        [InlineKeyboardButton("❌ Lepas Channel", callback_data=f"ch_remove_confirm_{channel_id}")],
        [InlineKeyboardButton("◀️ My Channel",   callback_data="user_channels_0")],
    ])


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

        await safe_edit(
            cb.message,
            _detail_text(partner, channel_id, user_id),
            markup=_detail_markup(partner, channel_id, user_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_channel_detail] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


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

        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _detail_text(p_fresh, channel_id, user_id),
            markup=_detail_markup(p_fresh, channel_id, user_id),
            parse_mode=PM,
        )
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

        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _detail_text(p_fresh, channel_id, user_id),
            markup=_detail_markup(p_fresh, channel_id, user_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_ch_run] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^ch_notif_rp_(-?\d+)$"))
async def cb_notif_rp(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        cur = get_notif_setting(user_id, "repost_notif", True)
        set_notif_setting(user_id, "repost_notif", not cur)
        status = "aktif ✅" if not cur else "nonaktif ❌"
        await answer_cb(cb, f"Notif repost {status}")
        answered = True

        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _detail_text(p_fresh, channel_id, user_id),
            markup=_detail_markup(p_fresh, channel_id, user_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_notif_rp] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^ch_notif_bl_(-?\d+)$"))
async def cb_notif_bl(client: Client, cb: CallbackQuery):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        user_id    = cb.from_user.id
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != user_id:
            await answer_cb(cb, "Tidak diizinkan.", True)
            answered = True
            return

        cur = get_notif_setting(user_id, "blacklist_notif", True)
        set_notif_setting(user_id, "blacklist_notif", not cur)
        status = "aktif ✅" if not cur else "nonaktif ❌"
        await answer_cb(cb, f"Notif blacklist {status}")
        answered = True

        p_fresh = get_partner(channel_id)
        await safe_edit(
            cb.message,
            _detail_text(p_fresh, channel_id, user_id),
            markup=_detail_markup(p_fresh, channel_id, user_id),
            parse_mode=PM,
        )
    except Exception as e:
        log.error(f"[cb_notif_bl] {e}")
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

        now    = datetime.now(timezone.utc)
        today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week   = today - timedelta(days=7)
        month  = today - timedelta(days=30)

        total   = posts_col.count_documents({"partner_id": channel_id})
        t_today = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": today}})
        t_week  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": week}})
        t_month = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": month}})
        avg_day = round(t_month / 30, 1) if t_month else 0

        added   = partner.get("added_at")
        added_s = added.strftime("%d %b %Y") if added else "—"

        text = (
            f"📊 <b>Statistik Channel</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"📡 <b>{partner.get('channel_name', '?')}</b>\n\n"
            f"Hari ini   <code>{t_today}</code> repost\n"
            f"7 hari     <code>{t_week}</code> repost\n"
            f"30 hari    <code>{t_month}</code> repost\n"
            f"All-time   <code>{total}</code> repost\n\n"
            f"📈 Rata-rata  <code>{avg_day}</code> / hari\n"
            f"Terdaftar    {added_s}"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_stats] {e}")
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
            lines = ["<i>Belum ada riwayat repost.</i>"]
        else:
            lines = []
            for idx, p in enumerate(recent, 1):
                added = p.get("added_at")
                ts    = added.strftime("%d %b %Y %H:%M") if added else "—"
                link  = f"https://t.me/c/{main_id_str}/{p['main_msg_id']}"
                lines.append(f"{idx}. <a href='{link}'>Lihat repost</a>  ·  {ts}")

        text = (
            f"📋 <b>Riwayat Repost Terakhir</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"📡 <b>{partner.get('channel_name', '?')}</b>\n\n"
            + "\n".join(lines)
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Kembali", callback_data=f"ch_detail_{channel_id}")
        ]])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_ch_history] {e}")
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
            f"Channel ini akan dilepas dari bot.\n"
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
            "paused":   True,
            "reason":   "Dilepas oleh owner",
            "owner_id": None,
        })
        await answer_cb(cb, "✅ Channel dilepas.")
        answered = True

        await safe_edit(
            cb.message,
            f"✅ <b>Channel dilepas.</b>\n\n"
            f"📡 <b>{ch_name}</b> sudah tidak terhubung.\n\n"
            f"Tambahkan bot kembali sebagai admin untuk mendaftar ulang.",
            markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ My Channel", callback_data="user_channels_0")
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

@Client.on_callback_query(filters.regex(r"^user_stats$"))
async def cb_user_stats(client: Client, cb: CallbackQuery):
    answered = False
    try:
        user_id  = cb.from_user.id
        channels = get_partners_by_owner(user_id)

        if not channels:
            text = (
                f"📊 <b>Statistik Saya</b>\n\n"
                f"Kamu belum punya channel terdaftar.\n\n"
                f"Tambahkan bot sebagai admin di channelmu untuk mulai."
            )
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Menu", callback_data="home")]])
        else:
            now    = datetime.now(timezone.utc)
            today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week   = today - timedelta(days=7)

            lines          = [f"📊 <b>Statistik Saya</b>\n<code>{SEP}</code>"]
            grand_total    = grand_today = grand_week = 0

            for ch in channels:
                cid    = ch["_id"]
                total  = posts_col.count_documents({"partner_id": cid})
                t_day  = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": today}})
                t_week = posts_col.count_documents({"partner_id": cid, "added_at": {"$gte": week}})
                icon   = "▶️" if not ch.get("paused") else "⏸"
                grand_total += total
                grand_today += t_day
                grand_week  += t_week
                name = (ch.get("channel_name") or "?")[:30]
                lines.append(
                    f"\n{icon} <b>{name}</b>\n"
                    f"  Hari ini <code>{t_day}</code>  ·  7h <code>{t_week}</code>  ·  Total <code>{total}</code>"
                )

            lines.append(
                f"\n<code>{SEP}</code>\n"
                f"🔢 <b>Grand Total</b>\n"
                f"  Hari ini <code>{grand_today}</code>  ·  "
                f"7h <code>{grand_week}</code>  ·  All-time <code>{grand_total}</code>"
            )
            text   = "\n".join(lines)
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh",    callback_data="user_stats")],
                [InlineKeyboardButton("◀️ Menu Utama", callback_data="home")],
            ])

        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_user_stats] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🔔 NOTIFIKASI GLOBAL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^user_notif$"))
async def cb_user_notif(client: Client, cb: CallbackQuery):
    answered = False
    try:
        user_id  = cb.from_user.id
        notif_rp = get_notif_setting(user_id, "repost_notif", True)
        notif_bl = get_notif_setting(user_id, "blacklist_notif", True)
        notif_st = get_notif_setting(user_id, "status_notif", True)

        text = (
            f"🔔 <b>Pengaturan Notifikasi</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"Aktifkan / nonaktifkan notif yang kamu terima dari bot:\n\n"
            f"{'✅' if notif_rp else '❌'}  Notif setiap repost berhasil\n"
            f"{'✅' if notif_bl else '❌'}  Notif postingan diblacklist\n"
            f"{'✅' if notif_st else '❌'}  Notif status channel (admin/remove)\n"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{'🔔' if notif_rp else '🔕'} Notif Repost",
                callback_data="notif_toggle_rp",
            )],
            [InlineKeyboardButton(
                f"{'🔔' if notif_bl else '🔕'} Notif Blacklist",
                callback_data="notif_toggle_bl",
            )],
            [InlineKeyboardButton(
                f"{'🔔' if notif_st else '🔕'} Notif Status Channel",
                callback_data="notif_toggle_st",
            )],
            [InlineKeyboardButton("◀️ Menu Utama", callback_data="home")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_user_notif] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^notif_toggle_(rp|bl|st)$"))
async def cb_notif_toggle_global(client: Client, cb: CallbackQuery):
    answered = False
    try:
        user_id  = cb.from_user.id
        which    = cb.matches[0].group(1)
        key_map  = {"rp": "repost_notif", "bl": "blacklist_notif", "st": "status_notif"}
        key      = key_map[which]
        cur      = get_notif_setting(user_id, key, True)
        set_notif_setting(user_id, key, not cur)
        lbl_map  = {"rp": "Repost", "bl": "Blacklist", "st": "Status"}
        status   = "aktif ✅" if not cur else "nonaktif ❌"
        await answer_cb(cb, f"Notif {lbl_map[which]}: {status}")
        answered = True
        await cb_user_notif(client, cb)
    except Exception as e:
        log.error(f"[cb_notif_toggle_global] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  ℹ️ INFO BOT
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^user_info$"))
async def cb_user_info(client: Client, cb: CallbackQuery):
    answered = False
    try:
        total_p  = count_partners()
        active_p = len(get_active_partners())
        total_r  = posts_col.count_documents({})
        total_u  = count_users()
        owner_line = f"@{OWNER_USERNAME}" if OWNER_USERNAME else OWNER_NAME

        text = (
            f"ℹ️ <b>Tentang {BOT_NAME}</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"🤖 <b>Bot</b>\n"
            f"   @{BOT_USERNAME}\n"
            f"   <i>{BOT_DESC}</i>\n\n"
            f"👤 <b>Owner</b>\n"
            f"   {owner_line}\n\n"
            f"📢 <b>Channel Utama</b>\n"
            f"   @{MAIN_CHANNEL_USERNAME}\n\n"
            f"<code>{SEP}</code>\n"
            f"📊 <b>Statistik Global</b>\n"
            f"   👥 Users        <code>{total_u}</code>\n"
            f"   📡 Partner      <code>{active_p}</code> aktif · <code>{total_p}</code> total\n"
            f"   📦 Total repost <code>{total_r}</code>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Kunjungi Channel", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
            [InlineKeyboardButton("📖 Tutorial",         callback_data="user_tutorial")],
            [InlineKeyboardButton("◀️ Menu Utama",       callback_data="home")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_user_info] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  📖 TUTORIAL
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^user_tutorial$"))
async def cb_user_tutorial(client: Client, cb: CallbackQuery):
    answered = False
    try:
        text = (
            f"📖 <b>Tutorial {BOT_NAME}</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"1️⃣ <b>Daftarkan Channel</b>\n"
            f"• Buka pengaturan channel → Administrator → Tambah Admin\n"
            f"• Cari <b>@{BOT_USERNAME}</b>, aktifkan izin:\n"
            f"  ✅ Kirim · Edit · Hapus Pesan · Invite Users\n"
            f"• Simpan → channel <b>otomatis terdaftar</b>\n\n"
            f"2️⃣ <b>Aktifkan Repost</b>\n"
            f"• Buka <b>My Channel</b> → pilih channel\n"
            f"• Ketuk <b>▶️ Aktifkan</b>\n"
            f"• Konten akan di-repost real-time ke channel utama\n\n"
            f"3️⃣ <b>Auto Hapus Repost</b>\n"
            f"• Hapus postingan di channelmu\n"
            f"• Bot otomatis hapus repost di channel utama\n"
            f"• ⚠️ Deteksi terjadi saat ada postingan baru berikutnya\n\n"
            f"4️⃣ <b>Filter Media</b>\n"
            f"• Owner dapat atur apakah foto, video, atau teks yang di-repost\n\n"
            f"5️⃣ <b>Notifikasi</b>\n"
            f"• Atur di menu <b>🔔 Notifikasi</b>\n\n"
            f"6️⃣ <b>Troubleshoot</b>\n"
            f"• Status channel harus <b>Aktif ▶️</b>\n"
            f"• Bot harus masih jadi <b>Admin</b>\n"
            f"• Periksa filter blacklist\n\n"
            f"<code>{SEP}</code>\n"
            f"📬 Bantuan: @{OWNER_USERNAME or BOT_USERNAME}"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Tambah Bot ke Channel", url=(
                f"https://t.me/{BOT_USERNAME}?startchannel=true"
                f"&admin=post_messages+edit_messages+delete_messages+invite_users"
            ))],
            [InlineKeyboardButton("◀️ Info Bot",   callback_data="user_info")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_user_tutorial] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  🆘 BANTUAN
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^user_help$"))
async def cb_user_help(client: Client, cb: CallbackQuery):
    answered = False
    try:
        text = (
            f"🆘 <b>Bantuan & FAQ</b>\n"
            f"<code>{SEP}</code>\n\n"
            f"<b>Q: Konten tidak ter-repost?</b>\n"
            f"A: Pastikan:\n"
            f"  • Status channel <b>Aktif ▶️</b>\n"
            f"  • Bot masih jadi <b>Admin</b> di channelmu\n"
            f"  • Konten bukan berisi kata blacklist\n"
            f"  • Filter media sesuai (foto/video/teks)\n\n"
            f"<b>Q: Channel tidak terdaftar otomatis?</b>\n"
            f"A: Pastikan kamu memberi izin yang benar saat menambahkan bot sebagai admin. "
            f"Atau forward satu postingan dari channelmu lalu reply dengan /daftarkan\n\n"
            f"<b>Q: Cara hapus repost yang sudah masuk?</b>\n"
            f"A: Hapus postingan di channelmu, bot akan otomatis hapus repost di channel utama.\n\n"
            f"<b>Q: Bisa repost audio/dokumen?</b>\n"
            f"A: Saat ini hanya foto, video, dan teks yang didukung.\n\n"
            f"<code>{SEP}</code>\n"
            f"Masih bingung? Hubungi: @{OWNER_USERNAME or BOT_USERNAME}"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Baca Tutorial",  callback_data="user_tutorial")],
            [InlineKeyboardButton("◀️ Menu Utama",     callback_data="home")],
        ])
        await safe_edit(cb.message, text, markup=markup, parse_mode=PM)
    except Exception as e:
        log.error(f"[cb_user_help] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  CLOSE / NOOP
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^close_msg$"))
async def cb_close(client: Client, cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await answer_cb(cb)
