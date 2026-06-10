"""
My Channel — user lihat dan kontrol channel miliknya.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.errors import MessageNotModified
from db.helpers import (
    get_partners_by_owner, get_partner, upsert_partner,
    count_posts_by_partner,
)
from utils import check_membership, paginate

PAGE_SIZE = 5

async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit_text(text, reply_markup=markup)
    except MessageNotModified:
        pass

def _nav_back(channel_id=None):
    """Baris navigasi bawah untuk panel user channel."""
    if channel_id:
        return [
            InlineKeyboardButton("◀️ Daftar Channel", callback_data="my_channels_0"),
        ]
    return [InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")]


# ══════════════════════════════════════════════════════════
#  DAFTAR CHANNEL
# ══════════════════════════════════════════════════════════

async def _show_channel_list(client, source, user_id, page, edit):
    channels = get_partners_by_owner(user_id)

    if not channels:
        text = (
            "📂 **My Channel**\n\n"
            "Belum ada channel terdaftar.\n\n"
            "**Cara daftar:**\n"
            "`1.` Buka pengaturan channelmu\n"
            "`2.` Tambahkan bot sebagai **Admin**\n"
            "`3.` Channel muncul di sini otomatis ✅"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")]])
        if edit:
            await safe_edit(source.message, text, markup)
        else:
            await source.reply(text, reply_markup=markup)
        return

    active_count = sum(1 for c in channels if not c.get("paused"))
    chunk, total_pages = paginate(channels, page, PAGE_SIZE)

    text = (
        f"📂 **My Channel**\n"
        f"`{'─' * 24}`\n\n"
        f"Total  `{len(channels)}`  ·  ▶️ Aktif `{active_count}`\n\n"
        f"Pilih channel:"
    )

    rows = []
    for ch in chunk:
        icon = "▶️" if not ch.get("paused") else "⏸"
        rows.append([InlineKeyboardButton(
            f"{icon}  {ch.get('channel_name', str(ch['_id']))}",
            callback_data=f"ch_detail_{ch['_id']}"
        )])

    # Paginasi
    if total_pages > 1:
        nav_page = []
        if page > 0:
            nav_page.append(InlineKeyboardButton("◀️", callback_data=f"my_channels_{page-1}"))
        nav_page.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_page.append(InlineKeyboardButton("▶️", callback_data=f"my_channels_{page+1}"))
        rows.append(nav_page)

    rows.append([InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")])

    markup = InlineKeyboardMarkup(rows)
    if edit:
        await safe_edit(source.message, text, markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_message(filters.text & filters.private & filters.regex("^📂 My Channel$"))
async def my_channel_btn(client, message):
    user_id = message.from_user.id
    joined  = await check_membership(client, user_id)
    if not joined:
        await message.reply("⚠️ Join channel utama dulu ya.")
        return
    await _show_channel_list(client, message, user_id, page=0, edit=False)

@Client.on_callback_query(filters.regex(r"^my_channels_(\d+)$"))
async def cb_my_channels(client, cb):
    page = int(cb.matches[0].group(1))
    await _show_channel_list(client, cb, cb.from_user.id, page=page, edit=True)
    await cb.answer()


# ══════════════════════════════════════════════════════════
#  DETAIL CHANNEL
# ══════════════════════════════════════════════════════════

async def _show_channel_detail(source, channel_id: int):
    partner = get_partner(channel_id)
    user_id = source.from_user.id if hasattr(source, "from_user") else None

    if not partner or partner.get("owner_id") != user_id:
        if hasattr(source, "answer"):
            await source.answer("Channel tidak ditemukan atau bukan milikmu.", show_alert=True)
        return

    paused    = partner.get("paused", False)
    status    = "▶️ Aktif" if not paused else "⏸ Dijeda"
    uname     = f"@{partner['username']}" if partner.get("username") else "—"
    reason    = partner.get("reason", "")
    rp        = count_posts_by_partner(channel_id)

    text = (
        f"📡 **{partner.get('channel_name', channel_id)}**\n"
        f"`{'─' * 24}`\n\n"
        f"Username  {uname}\n"
        f"Status    {status}\n"
        f"Repost    `{rp}` kali\n"
    )
    if reason:
        text += f"\n⚠️ _{reason}_\n"

    toggle = (
        InlineKeyboardButton("▶️ Aktifkan Forward",  callback_data=f"ch_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause Forward",     callback_data=f"ch_pause_{channel_id}")
    )

    markup = InlineKeyboardMarkup([
        [toggle],
        [InlineKeyboardButton("📊 Statistik",        callback_data=f"ch_stats_{channel_id}")],
        [InlineKeyboardButton("◀️ Daftar Channel",   callback_data="my_channels_0")],
    ])

    msg = source.message if hasattr(source, "message") else source
    await safe_edit(msg, text, markup)

@Client.on_callback_query(filters.regex(r"^ch_detail_(-?\d+)$"))
async def cb_channel_detail(client, cb):
    channel_id = int(cb.matches[0].group(1))
    await _show_channel_detail(cb, channel_id)
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^ch_pause_(-?\d+)$"))
async def cb_ch_pause(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh owner"})
    await cb.answer("⏸ Dijeda", show_alert=False)
    await _show_channel_detail(cb, channel_id)

@Client.on_callback_query(filters.regex(r"^ch_run_(-?\d+)$"))
async def cb_ch_run(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    await cb.answer("▶️ Aktif!", show_alert=False)
    await _show_channel_detail(cb, channel_id)


# ══════════════════════════════════════════════════════════
#  STATISTIK CHANNEL
# ══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^ch_stats_(-?\d+)$"))
async def cb_ch_stats(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    from db.mongo import posts as posts_col
    from datetime import datetime, timedelta, timezone
    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - timedelta(days=7)

    total    = posts_col.count_documents({"partner_id": channel_id})
    t_today  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": today}})
    t_week   = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": week}})
    added    = partner.get("added_at")
    added_str = added.strftime("%d %b %Y") if added else "—"

    text = (
        f"📊 **Statistik Channel**\n\n"
        f"📡 **{partner.get('channel_name')}**\n"
        f"`{'─' * 24}`\n\n"
        f"Hari ini   `{t_today}`\n"
        f"7 hari     `{t_week}`\n"
        f"All-time   `{total}`\n"
        f"`{'─' * 24}`\n"
        f"Terdaftar  {added_str}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Detail Channel", callback_data=f"ch_detail_{channel_id}")],
    ])
    await safe_edit(cb.message, text, markup)
    await cb.answer()


# ══════════════════════════════════════════════════════════
#  MISC
# ══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^close_msg$"))
async def cb_close(client, cb):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()
