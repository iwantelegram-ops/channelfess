"""
Tombol "My Channel" — user bisa lihat dan kontrol channel miliknya.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from db.helpers import get_partners_by_owner, get_partner, upsert_partner, is_joined
from utils import check_membership, paginate

PAGE_SIZE = 5  # channel per halaman di my channel

def channel_list_markup(channels: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        cid    = ch["_id"]
        status = "⏸ PAUSED" if ch.get("paused") else "▶️ AKTIF"
        name   = ch.get("channel_name", str(cid))
        rows.append([InlineKeyboardButton(f"{status}  {name}", callback_data=f"ch_detail_{cid}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"my_channels_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"my_channels_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔙 Tutup", callback_data="close_msg")])
    return InlineKeyboardMarkup(rows)

def channel_detail_markup(channel_id: int, paused: bool) -> InlineKeyboardMarkup:
    toggle_label    = "▶️ Aktifkan Forward" if paused else "⏸ Pause Forward"
    toggle_callback = f"ch_run_{channel_id}" if paused else f"ch_pause_{channel_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=toggle_callback)],
        [InlineKeyboardButton("🔙 Kembali", callback_data="my_channels_0")]
    ])

# ── Tombol keyboard "My Channel" ──────────────────────────
@Client.on_message(filters.text & filters.private & filters.regex("^📂 My Channel$"))
async def my_channel_btn(client: Client, message: Message):
    user_id = message.from_user.id

    joined = await check_membership(client, user_id)
    if not joined:
        await message.reply("⚠️ Kamu harus join channel utama dulu.")
        return

    await show_my_channels(client, message, user_id, page=0, edit=False)

async def show_my_channels(client, source, user_id: int, page: int, edit: bool):
    channels    = get_partners_by_owner(user_id)
    if not channels:
        text = (
            "📂 **My Channel**\n\n"
            "Kamu belum memiliki channel partner yang terdaftar.\n\n"
            "Jadikan bot sebagai admin di channel kamu, "
            "lalu channel otomatis terdaftar di sini."
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Tutup", callback_data="close_msg")]])
        if edit:
            await source.message.edit_text(text, reply_markup=markup)
        else:
            await source.reply(text, reply_markup=markup)
        return

    chunk, total_pages = paginate(channels, page, PAGE_SIZE)
    text = f"📂 **My Channel**  (halaman {page+1}/{total_pages})\n\nPilih channel untuk mengatur:"
    markup = channel_list_markup(chunk, page, total_pages)

    if edit:
        await source.message.edit_text(text, reply_markup=markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^my_channels_(\d+)$"))
async def cb_my_channels(client: Client, cb: CallbackQuery):
    page    = int(cb.matches[0].group(1))
    user_id = cb.from_user.id
    await show_my_channels(client, cb, user_id, page=page, edit=True)
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^ch_detail_(-?\d+)$"))
async def cb_channel_detail(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Channel tidak ditemukan atau bukan milikmu.", show_alert=True)
        return

    paused  = partner.get("paused", False)
    status  = "⏸ PAUSED" if paused else "▶️ AKTIF"
    reason  = partner.get("reason", "")
    reason_line = f"\n⚠️ Alasan: _{reason}_" if reason else ""

    text = (
        f"📡 **{partner.get('channel_name', channel_id)}**\n"
        f"🆔 ID: `{channel_id}`\n"
        f"Status: {status}{reason_line}\n\n"
        f"Gunakan tombol di bawah untuk mengontrol:"
    )
    await cb.message.edit_text(text, reply_markup=channel_detail_markup(channel_id, paused))
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^ch_pause_(-?\d+)$"))
async def cb_ch_pause(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    upsert_partner(channel_id, {"paused": True, "reason": "Dipause oleh owner"})
    await cb.answer("⏸ Forward dijeda.", show_alert=True)
    await cb_channel_detail(client, cb)  # refresh detail

@Client.on_callback_query(filters.regex(r"^ch_run_(-?\d+)$"))
async def cb_ch_run(client: Client, cb: CallbackQuery):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Tidak diizinkan.", show_alert=True)
        return

    upsert_partner(channel_id, {"paused": False, "reason": ""})
    await cb.answer("▶️ Forward diaktifkan.", show_alert=True)
    await cb_channel_detail(client, cb)  # refresh detail

@Client.on_callback_query(filters.regex("^close_msg$"))
async def cb_close(client: Client, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()
