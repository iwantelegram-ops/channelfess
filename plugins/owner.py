"""
Perintah & callback khusus owner.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import OWNER_ID
from db.helpers import (
    get_partner, upsert_partner, get_all_partners, count_partners
)
from db.mongo import posts, users
from utils import paginate

PAGE_SIZE = 15

def owner_only(func):
    """Decorator — tolak jika bukan owner."""
    async def wrapper(client, message_or_cb, *args, **kwargs):
        uid = (message_or_cb.from_user.id
               if hasattr(message_or_cb, "from_user")
               else message_or_cb.from_user.id)
        if uid != OWNER_ID:
            if hasattr(message_or_cb, "answer"):
                await message_or_cb.answer("❌ Kamu bukan owner.", show_alert=True)
            else:
                await message_or_cb.reply("❌ Kamu bukan owner bot.")
            return
        return await func(client, message_or_cb, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ── /pause ────────────────────────────────────────────────
@Client.on_message(filters.command("pause") & filters.private)
@owner_only
async def cmd_pause(client: Client, message: Message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply("Format: `/pause <ID channel> <alasan>`")
        return

    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID channel harus berupa angka.")
        return

    reason  = parts[2]
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan di database.")
        return

    upsert_partner(channel_id, {"paused": True, "reason": reason})

    # Notif ke owner channel
    owner_id = partner.get("owner_id")
    ch_name  = partner.get("channel_name", str(channel_id))
    if owner_id:
        try:
            await client.send_message(
                owner_id,
                f"⏸ **Channel kamu dijeda oleh admin.**\n\n"
                f"📡 Channel: **{ch_name}**\n"
                f"📝 Alasan: _{reason}_\n\n"
                f"Seluruh forward dari channel kamu ke channel utama dihentikan sementara.\n"
                f"Hubungi admin untuk informasi lebih lanjut."
            )
        except Exception:
            pass

    await message.reply(
        f"✅ Channel **{ch_name}** (`{channel_id}`) dijeda.\n"
        f"Alasan: _{reason}_\n"
        f"Notifikasi telah dikirim ke owner channel."
    )

# ── /run ──────────────────────────────────────────────────
@Client.on_message(filters.command("run") & filters.private)
@owner_only
async def cmd_run(client: Client, message: Message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply("Format: `/run <ID channel> <alasan>`")
        return

    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID channel harus berupa angka.")
        return

    reason  = parts[2]
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan di database.")
        return

    upsert_partner(channel_id, {"paused": False, "reason": ""})

    owner_id = partner.get("owner_id")
    ch_name  = partner.get("channel_name", str(channel_id))
    if owner_id:
        try:
            await client.send_message(
                owner_id,
                f"▶️ **Channel kamu diaktifkan kembali.**\n\n"
                f"📡 Channel: **{ch_name}**\n"
                f"📝 Pesan admin: _{reason}_\n\n"
                f"Forward dari channel kamu ke channel utama kini berjalan kembali."
            )
        except Exception:
            pass

    await message.reply(
        f"✅ Channel **{ch_name}** (`{channel_id}`) diaktifkan.\n"
        f"Alasan: _{reason}_\n"
        f"Notifikasi telah dikirim ke owner channel."
    )

# ── /stats ────────────────────────────────────────────────
@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client: Client, message: Message):
    total_partners = count_partners()
    total_posts    = posts.count_documents({})
    total_users    = users.count_documents({})
    active         = count_partners() - len([p for p in get_all_partners() if p.get("paused")])
    paused_count   = total_partners - active

    text = (
        f"📊 **Statistik FessBot**\n\n"
        f"👥 Total user terdaftar  : `{total_users}`\n"
        f"📡 Channel partner aktif : `{active}`\n"
        f"⏸ Channel partner paused: `{paused_count}`\n"
        f"📦 Total repost tersimpan: `{total_posts}`\n"
    )
    await message.reply(text)

# ── /listpartner ──────────────────────────────────────────
@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client: Client, message: Message):
    await send_partner_list(client, message, page=0, edit=False)

@Client.on_callback_query(filters.regex(r"^list_partner_(\d+)$"))
@owner_only
async def cb_listpartner(client: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    await send_partner_list(client, cb, page=page, edit=True)
    await cb.answer()

@Client.on_callback_query(filters.regex("^owner_stats$"))
@owner_only
async def cb_owner_stats(client: Client, cb: CallbackQuery):
    total_partners = count_partners()
    total_posts    = posts.count_documents({})
    total_users    = users.count_documents({})
    all_p          = get_all_partners()
    paused_count   = len([p for p in all_p if p.get("paused")])
    active         = total_partners - paused_count

    text = (
        f"📊 **Statistik FessBot**\n\n"
        f"👥 Total user       : `{total_users}`\n"
        f"📡 Partner aktif    : `{active}`\n"
        f"⏸ Partner paused   : `{paused_count}`\n"
        f"📦 Total repost     : `{total_posts}`\n"
    )
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Daftar Channel Partner", callback_data="list_partner_0")],
        [InlineKeyboardButton("🔙 Tutup", callback_data="close_owner_msg")]
    ])
    await cb.message.edit_text(text, reply_markup=btn)
    await cb.answer()

@Client.on_callback_query(filters.regex("^close_owner_msg$"))
async def cb_close_owner(client: Client, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

async def send_partner_list(client, source, page: int, edit: bool):
    all_p = get_all_partners()
    if not all_p:
        text = "📋 Belum ada channel partner terdaftar."
        if edit:
            await source.message.edit_text(text)
        else:
            await source.reply(text)
        return

    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)

    lines = [f"📋 **Daftar Channel Partner** (hal. {page+1}/{total_pages})\n"]
    for i, ch in enumerate(chunk, start=page * PAGE_SIZE + 1):
        status  = "⏸" if ch.get("paused") else "▶️"
        uname   = f"@{ch['username']}" if ch.get("username") else "—"
        lines.append(
            f"{i}. {status} **{ch.get('channel_name','?')}**\n"
            f"    👤 {ch.get('owner_name','?')}  |  {uname}\n"
            f"    🆔 `{ch['_id']}`"
        )
    text = "\n\n".join(lines)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"list_partner_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_partner_{page+1}"))

    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton("🔙 Tutup", callback_data="close_owner_msg")])

    markup = InlineKeyboardMarkup(rows)
    if edit:
        await source.message.edit_text(text, reply_markup=markup)
    else:
        await source.reply(text, reply_markup=markup)
