"""
My Channel — user lihat, kontrol & lihat statistik channel miliknya.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from db.helpers import (
    get_partners_by_owner, get_partner, upsert_partner,
    count_posts_by_partner
)
from utils import check_membership, paginate

PAGE_SIZE = 5

def channel_list_markup(channels, page, total_pages):
    rows = []
    for ch in channels:
        cid  = ch["_id"]
        icon = "▶️" if not ch.get("paused") else "⏸"
        name = ch.get("channel_name", str(cid))
        rows.append([InlineKeyboardButton(f"{icon}  {name}", callback_data=f"ch_detail_{cid}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"my_channels_{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"· {page+1}/{total_pages} ·", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"my_channels_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")])
    return InlineKeyboardMarkup(rows)

def channel_detail_markup(channel_id, paused):
    toggle_label = "▶️  Aktifkan Forward" if paused else "⏸  Pause Forward"
    toggle_cb    = f"ch_run_{channel_id}" if paused else f"ch_pause_{channel_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=toggle_cb)],
        [
            InlineKeyboardButton("📊 Statistik Channel", callback_data=f"ch_stats_{channel_id}"),
            InlineKeyboardButton("🔙 Kembali", callback_data="my_channels_0"),
        ]
    ])

# ── Keyboard shortcut ─────────────────────────────────────
@Client.on_message(filters.text & filters.private & filters.regex("^📂 My Channel$"))
async def my_channel_btn(client, message):
    user_id = message.from_user.id
    joined  = await check_membership(client, user_id)
    if not joined:
        await message.reply("⚠️ Join channel utama dulu ya.")
        return
    await show_my_channels(client, message, user_id, page=0, edit=False)

async def show_my_channels(client, source, user_id, page, edit):
    channels = get_partners_by_owner(user_id)
    if not channels:
        text = (
            "📂 **My Channel**\n\n"
            "Belum ada channel terdaftar.\n\n"
            "**Cara daftar:**\n"
            "`1.` Buka channel kamu\n"
            "`2.` Tambahkan bot sebagai **Admin**\n"
            "`3.` Channel langsung muncul di sini ✅"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Tutup", callback_data="close_msg")]])
        if edit:
            await source.message.edit_text(text, reply_markup=markup)
        else:
            await source.reply(text, reply_markup=markup)
        return

    active_count = sum(1 for c in channels if not c.get("paused"))
    chunk, total_pages = paginate(channels, page, PAGE_SIZE)
    text   = (
        f"📂 **My Channel**\n\n"
        f"Total: **{len(channels)}** channel  ·  ▶️ **{active_count}** aktif\n\n"
        f"Pilih channel untuk ngatur:"
    )
    markup = channel_list_markup(chunk, page, total_pages)
    if edit:
        await source.message.edit_text(text, reply_markup=markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^my_channels_(\d+)$"))
async def cb_my_channels(client, cb):
    page = int(cb.matches[0].group(1))
    await show_my_channels(client, cb, cb.from_user.id, page=page, edit=True)
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^ch_detail_(-?\d+)$"))
async def cb_channel_detail(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Channel tidak ditemukan atau bukan milikmu.", show_alert=True)
        return

    paused = partner.get("paused", False)
    status = "▶️ Aktif" if not paused else "⏸ Dijeda"
    uname  = f"@{partner['username']}" if partner.get("username") else "—"
    reason = partner.get("reason", "")
    rp     = count_posts_by_partner(channel_id)
    reason_line = f"\n⚠️ _{reason}_" if reason else ""

    text = (
        f"📡 **{partner.get('channel_name', channel_id)}**\n"
        f"┌ Username : {uname}\n"
        f"├ Status   : {status}{reason_line}\n"
        f"├ Repost   : `{rp}` kali\n"
        f"└ ID       : `{channel_id}`\n\n"
        f"Pilih aksi:"
    )
    await cb.message.edit_text(text, reply_markup=channel_detail_markup(channel_id, paused))
    await cb.answer()

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

    total   = posts_col.count_documents({"partner_id": channel_id})
    t_today = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": today}})
    t_week  = posts_col.count_documents({"partner_id": channel_id, "added_at": {"$gte": week}})
    added   = partner.get("added_at")
    added_str = added.strftime("%d %b %Y") if added else "—"

    text = (
        f"📊 **Statistik Channel**\n\n"
        f"📡 **{partner.get('channel_name')}**\n"
        f"`─────────────────────`\n"
        f"📦 Repost hari ini : `{t_today}`\n"
        f"📦 Repost 7 hari   : `{t_week}`\n"
        f"📦 Total repost    : `{total}`\n"
        f"`─────────────────────`\n"
        f"📅 Terdaftar       : {added_str}"
    )
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Kembali", callback_data=f"ch_detail_{channel_id}")]
        ])
    )
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^ch_pause_(-?\d+)$"))
async def cb_ch_pause(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh owner"})
    await cb.answer("⏸ Dijeda.", show_alert=False)
    await cb_channel_detail(client, cb)

@Client.on_callback_query(filters.regex(r"^ch_run_(-?\d+)$"))
async def cb_ch_run(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    await cb.answer("▶️ Aktif!", show_alert=False)
    await cb_channel_detail(client, cb)

@Client.on_callback_query(filters.regex("^close_msg$"))
async def cb_close(client, cb):
    await cb.message.delete()
    await cb.answer()
