"""
Panel Owner — Dashboard, Stats, Partner list, Search, Broadcast,
Blacklist, Maintenance, Pause/Run channel.

Sistem navigasi:
  Semua navigasi menggunakan ReplyKeyboardMarkup (bottom tombol).
  Keyboard berubah konteks sesuai panel aktif.
  Inline keyboard hanya untuk AKSI (pause/run, konfirmasi, paginasi).
"""
import asyncio
import functools
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from pyrogram.errors import MessageNotModified
from config import OWNER_ID
from db.helpers import (
    get_partner, upsert_partner, get_all_partners, get_active_partners,
    count_partners, search_partners,
    get_blacklist, add_blacklist, remove_blacklist,
    set_maintenance, get_maintenance,
    get_all_user_ids, get_posts_today,
)
from db.mongo import posts, users
from utils import paginate
# kb_main juga diekspor ke start.py sebagai owner_keyboard alias
# (start.py tetap punya owner_keyboard() untuk /start handler)

PAGE_SIZE = 8

# ══════════════════════════════════════════════════════════
#  DEKORATOR & UTILITAS
# ══════════════════════════════════════════════════════════

def owner_only(func):
    @functools.wraps(func)
    async def wrapper(client, obj, *args, **kwargs):
        uid = obj.from_user.id if hasattr(obj, "from_user") else 0
        if uid != OWNER_ID:
            if hasattr(obj, "answer"):
                await obj.answer("🚫 Bukan owner.", show_alert=True)
            else:
                await obj.reply("🚫 Akses ditolak.")
            return
        return await func(client, obj, *args, **kwargs)
    return wrapper

async def safe_edit(msg, text, markup=None):
    """Edit pesan — abaikan jika konten tidak berubah."""
    try:
        await msg.edit_text(text, reply_markup=markup)
    except MessageNotModified:
        pass

def _bar(val, total, width=10):
    if total == 0:
        return "░" * width
    filled = round((val / total) * width)
    return "█" * filled + "░" * (width - filled)


# ══════════════════════════════════════════════════════════
#  REPLY KEYBOARD DINAMIS (konteks navigasi)
# ══════════════════════════════════════════════════════════

def kb_main():
    """Keyboard utama owner."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Dashboard"), KeyboardButton("📋 Partner")],
            [KeyboardButton("📣 Broadcast"), KeyboardButton("🔧 Tools")],
        ],
        resize_keyboard=True,
    )

def kb_partner():
    """Keyboard panel Partner."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔎 Cari Channel"), KeyboardButton("🔄 Refresh Partner")],
            [KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_tools():
    """Keyboard panel Tools."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚫 Blacklist"), KeyboardButton("🔧 Maintenance")],
            [KeyboardButton("🔎 Cari Channel"), KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_broadcast():
    """Keyboard panel Broadcast."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👥 Broadcast Semua"), KeyboardButton("📡 Broadcast Partner")],
            [KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_blacklist():
    """Keyboard panel Blacklist."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 Refresh Blacklist")],
            [KeyboardButton("🔧 Tools"), KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_maintenance():
    """Keyboard panel Maintenance."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔴 Aktifkan Maintenance"), KeyboardButton("🟢 Nonaktifkan Maintenance")],
            [KeyboardButton("🔧 Tools"), KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_search():
    """Keyboard saat mode cari channel."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("❌ Batal Cari")],
            [KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

def kb_detail_channel(channel_id: int, paused: bool):
    """Keyboard saat melihat detail channel partner."""
    aksi = "▶️ Aktifkan Channel" if paused else "⏸ Pause Channel"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(aksi)],
            [KeyboardButton("◀️ Daftar Partner"), KeyboardButton("🏠 Menu Utama")],
        ],
        resize_keyboard=True,
    )

# State: simpan channel_id yang sedang dilihat owner (untuk tombol pause/run dari keyboard)
_viewing_channel: dict[int, int] = {}   # {owner_id: channel_id}
_search_pending:  set[int]       = set()


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Menu Utama
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^🏠 Menu Utama$"))
@owner_only
async def kb_menu_utama(client, message):
    _viewing_channel.pop(message.from_user.id, None)
    await message.reply("⚡ **Control Panel**\n\nPilih menu:", reply_markup=kb_main())

@Client.on_message(filters.text & filters.private & filters.regex("^📊 Dashboard$"))
@owner_only
async def kb_dashboard(client, message):
    await _send_stats(client, message)

@Client.on_message(filters.text & filters.private & filters.regex("^📋 Partner$"))
@owner_only
async def kb_partner_btn(client, message):
    await _send_partner_list(client, message, page=0)

@Client.on_message(filters.text & filters.private & filters.regex("^📣 Broadcast$"))
@owner_only
async def kb_broadcast_btn(client, message):
    await _send_broadcast_menu(client, message)

@Client.on_message(filters.text & filters.private & filters.regex("^🔧 Tools$"))
@owner_only
async def kb_tools_btn(client, message):
    await _send_tools_menu(client, message)


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Partner
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^🔄 Refresh Partner$"))
@owner_only
async def kb_refresh_partner(client, message):
    await _send_partner_list(client, message, page=0)

@Client.on_message(filters.text & filters.private & filters.regex("^◀️ Daftar Partner$"))
@owner_only
async def kb_back_to_partner(client, message):
    _viewing_channel.pop(message.from_user.id, None)
    await _send_partner_list(client, message, page=0)


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Tools
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^🚫 Blacklist$"))
@owner_only
async def kb_blacklist_btn(client, message):
    await _send_blacklist_menu(client, message)

@Client.on_message(filters.text & filters.private & filters.regex("^🔧 Maintenance$"))
@owner_only
async def kb_maintenance_btn(client, message):
    await _send_maintenance_menu(client, message)

@Client.on_message(filters.text & filters.private & filters.regex("^🔄 Refresh Blacklist$"))
@owner_only
async def kb_refresh_blacklist(client, message):
    await _send_blacklist_menu(client, message)


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Maintenance
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^🔴 Aktifkan Maintenance$"))
@owner_only
async def kb_maint_on(client, message):
    set_maintenance(True, "Bot sedang dalam perbaikan. Harap tunggu.")
    text, _ = _maintenance_text()
    await message.reply(text, reply_markup=kb_maintenance())

@Client.on_message(filters.text & filters.private & filters.regex("^🟢 Nonaktifkan Maintenance$"))
@owner_only
async def kb_maint_off(client, message):
    set_maintenance(False, "")
    text, _ = _maintenance_text()
    await message.reply(text, reply_markup=kb_maintenance())


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Broadcast
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^👥 Broadcast Semua$"))
@owner_only
async def kb_broadcast_all(client, message):
    total = users.count_documents({})
    await message.reply(
        f"📣 **Broadcast ke Semua User**\n\n"
        f"Total user: `{total:,}`\n\n"
        f"Gunakan perintah:\n`/broadcast <pesan>`",
        reply_markup=kb_broadcast()
    )

@Client.on_message(filters.text & filters.private & filters.regex("^📡 Broadcast Partner$"))
@owner_only
async def kb_broadcast_partner_btn(client, message):
    total_p = len({p["owner_id"] for p in get_all_partners() if p.get("owner_id")})
    await message.reply(
        f"📡 **Broadcast ke Owner Partner**\n\n"
        f"Total owner partner: `{total_p}`\n\n"
        f"Gunakan perintah:\n`/broadcastpartner <pesan>`",
        reply_markup=kb_broadcast()
    )


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Detail Channel (Pause/Run)
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^⏸ Pause Channel$"))
@owner_only
async def kb_pause_channel(client, message):
    uid        = message.from_user.id
    channel_id = _viewing_channel.get(uid)
    if not channel_id:
        await message.reply("⚠️ Tidak ada channel yang sedang dilihat.", reply_markup=kb_main())
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.", reply_markup=kb_main())
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh admin"})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(
                oid,
                f"⏸ **Channel dijeda oleh admin.**\n\n"
                f"📡 **{partner.get('channel_name')}**\nHubungi admin untuk info lanjut."
            )
        except Exception:
            pass
    await message.reply(f"✅ Channel **{partner.get('channel_name')}** dijeda.")
    await _send_partner_detail(client, message, channel_id)

@Client.on_message(filters.text & filters.private & filters.regex("^▶️ Aktifkan Channel$"))
@owner_only
async def kb_run_channel(client, message):
    uid        = message.from_user.id
    channel_id = _viewing_channel.get(uid)
    if not channel_id:
        await message.reply("⚠️ Tidak ada channel yang sedang dilihat.", reply_markup=kb_main())
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.", reply_markup=kb_main())
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(
                oid,
                f"▶️ **Channel aktif kembali!**\n\n"
                f"📡 **{partner.get('channel_name')}**\nRepost sudah berjalan lagi. 🚀"
            )
        except Exception:
            pass
    await message.reply(f"✅ Channel **{partner.get('channel_name')}** aktif kembali.")
    await _send_partner_detail(client, message, channel_id)


# ══════════════════════════════════════════════════════════
#  HANDLER TOMBOL KEYBOARD — Cari Channel
# ══════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.private & filters.regex("^🔎 Cari Channel$"))
@owner_only
async def kb_search_btn(client, message):
    _search_pending.add(message.from_user.id)
    await message.reply(
        "🔎 **Cari Channel Partner**\n\nKetik nama atau username channel:",
        reply_markup=kb_search()
    )

@Client.on_message(filters.text & filters.private & filters.regex("^❌ Batal Cari$"))
@owner_only
async def kb_cancel_search(client, message):
    _search_pending.discard(message.from_user.id)
    await message.reply("🔍 Pencarian dibatalkan.", reply_markup=kb_main())


# ══════════════════════════════════════════════════════════
#  DASHBOARD / STATS
# ══════════════════════════════════════════════════════════

def _stats_text():
    total_p     = count_partners()
    total_posts = posts.count_documents({})
    total_users = users.count_documents({})
    all_p       = get_all_partners()
    paused      = len([p for p in all_p if p.get("paused")])
    active      = total_p - paused
    today       = get_posts_today()
    pct_a       = round(active / total_p * 100) if total_p else 0

    return (
        f"📊 **Dashboard FessBot**\n"
        f"`{'─' * 26}`\n\n"
        f"👥 **Users**  `{total_users:,}`\n\n"
        f"📡 **Channel Partner**\n"
        f"  ▶️ Aktif    {_bar(active, total_p)} `{active}` · {pct_a}%\n"
        f"  ⏸ Paused   {_bar(paused, total_p)} `{paused}`\n"
        f"  Total      `{total_p}`\n\n"
        f"📦 **Repost**\n"
        f"  Hari ini  `{today:,}`\n"
        f"  All-time  `{total_posts:,}`\n"
    )

async def _send_stats(client, source):
    await source.reply(_stats_text(), reply_markup=kb_main())

@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client, message):
    await _send_stats(client, message)


# ══════════════════════════════════════════════════════════
#  TOOLS MENU
# ══════════════════════════════════════════════════════════

async def _send_tools_menu(client, source):
    maint  = get_maintenance()
    bl     = get_blacklist()
    status = "🔴 Maintenance aktif" if maint.get("active") else "🟢 Normal"
    text   = (
        f"🔧 **Tools**\n"
        f"`{'─' * 26}`\n\n"
        f"Status bot   {status}\n"
        f"Blacklist    `{len(bl)}` kata\n"
    )
    await source.reply(text, reply_markup=kb_tools())


# ══════════════════════════════════════════════════════════
#  PARTNER LIST
# ══════════════════════════════════════════════════════════

async def _send_partner_list(client, source, page: int, data=None):
    all_p = data if data is not None else get_all_partners()

    if not all_p:
        await source.reply(
            "📋 **Channel Partner**\n\nBelum ada partner terdaftar.",
            reply_markup=kb_partner()
        )
        return

    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)
    lines = [f"📋 **Channel Partner**  `{len(all_p)} total`\n"]
    for ch in chunk:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        uname = f"@{ch['username']}" if ch.get("username") else "—"
        rp    = ch.get("total_posts", 0)
        lines.append(
            f"{icon} **{ch.get('channel_name','?')}**\n"
            f"     {uname}  ·  📦 {rp}  ·  🆔 `{ch['_id']}`"
        )
    text = "\n\n".join(lines)

    # Inline hanya untuk: pilih channel + paginasi (aksi, bukan navigasi)
    rows = []
    for ch in chunk:
        icon = "▶️" if not ch.get("paused") else "⏸"
        rows.append([InlineKeyboardButton(
            f"{icon}  {ch.get('channel_name','?')}",
            callback_data=f"owner_ch_{ch['_id']}"
        )])

    if total_pages > 1:
        nav_page = []
        if page > 0:
            nav_page.append(InlineKeyboardButton("◀️", callback_data=f"list_partner_{page-1}"))
        nav_page.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_page.append(InlineKeyboardButton("▶️", callback_data=f"list_partner_{page+1}"))
        rows.append(nav_page)

    markup = InlineKeyboardMarkup(rows) if rows else None
    await source.reply(text, reply_markup=markup)
    # Kirim keyboard navigasi terpisah
    await client.send_message(source.chat.id, "📋 Pilih channel di atas atau gunakan menu:", reply_markup=kb_partner())

@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client, message):
    await _send_partner_list(client, message, page=0)

@Client.on_callback_query(filters.regex(r"^list_partner_(\d+)$"))
@owner_only
async def cb_listpartner(client, cb):
    page    = int(cb.matches[0].group(1))
    all_p   = get_all_partners()
    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)

    lines = [f"📋 **Channel Partner**  `{len(all_p)} total`\n"]
    for ch in chunk:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        uname = f"@{ch['username']}" if ch.get("username") else "—"
        rp    = ch.get("total_posts", 0)
        lines.append(
            f"{icon} **{ch.get('channel_name','?')}**\n"
            f"     {uname}  ·  📦 {rp}  ·  🆔 `{ch['_id']}`"
        )
    text = "\n\n".join(lines)

    rows = []
    for ch in chunk:
        icon = "▶️" if not ch.get("paused") else "⏸"
        rows.append([InlineKeyboardButton(
            f"{icon}  {ch.get('channel_name','?')}",
            callback_data=f"owner_ch_{ch['_id']}"
        )])

    if total_pages > 1:
        nav_page = []
        if page > 0:
            nav_page.append(InlineKeyboardButton("◀️", callback_data=f"list_partner_{page-1}"))
        nav_page.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_page.append(InlineKeyboardButton("▶️", callback_data=f"list_partner_{page+1}"))
        rows.append(nav_page)

    await safe_edit(cb.message, text, InlineKeyboardMarkup(rows) if rows else None)
    await cb.answer()


# ══════════════════════════════════════════════════════════
#  DETAIL CHANNEL (owner view)
# ══════════════════════════════════════════════════════════

async def _send_partner_detail(client, source, channel_id: int):
    from db.helpers import count_posts_by_partner
    partner = get_partner(channel_id)
    if not partner:
        if hasattr(source, "answer"):
            await source.answer("Channel tidak ditemukan.", show_alert=True)
        else:
            await source.reply("❌ Channel tidak ditemukan.")
        return

    uid = source.from_user.id if hasattr(source, "from_user") else OWNER_ID
    _viewing_channel[uid] = channel_id

    paused    = partner.get("paused", False)
    status    = "▶️ Aktif" if not paused else "⏸ Dijeda"
    uname     = f"@{partner['username']}" if partner.get("username") else "—"
    reason    = partner.get("reason", "")
    rp_count  = count_posts_by_partner(channel_id)
    added     = partner.get("added_at")
    added_str = added.strftime("%d %b %Y") if added else "—"

    text = (
        f"📡 **{partner.get('channel_name', channel_id)}**\n"
        f"`{'─' * 26}`\n"
        f"Username  {uname}\n"
        f"Owner     {partner.get('owner_name','?')}\n"
        f"Status    {status}\n"
        f"Repost    `{rp_count}` kali\n"
        f"Daftar    {added_str}\n"
    )
    if reason:
        text += f"\n⚠️ _{reason}_\n"

    if hasattr(source, "message"):
        # callback query — edit pesan, reply keyboard lewat send_message
        await safe_edit(source.message, text)
        await client.send_message(
            source.message.chat.id,
            f"Aksi untuk **{partner.get('channel_name')}**:",
            reply_markup=kb_detail_channel(channel_id, paused)
        )
    else:
        await source.reply(text, reply_markup=kb_detail_channel(channel_id, paused))

@Client.on_callback_query(filters.regex(r"^owner_ch_(-?\d+)$"))
@owner_only
async def cb_owner_ch_detail(client, cb):
    channel_id = int(cb.matches[0].group(1))
    await _send_partner_detail(client, cb, channel_id)
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^owner_pause_(-?\d+)$"))
@owner_only
async def cb_owner_pause(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner:
        await cb.answer("Channel tidak ditemukan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": True, "reason": "Dijeda oleh admin"})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(
                oid,
                f"⏸ **Channel dijeda oleh admin.**\n\n"
                f"📡 **{partner.get('channel_name')}**\nHubungi admin untuk info lanjut."
            )
        except Exception:
            pass
    await cb.answer("⏸ Dijeda", show_alert=False)
    await _send_partner_detail(client, cb, channel_id)

@Client.on_callback_query(filters.regex(r"^owner_run_(-?\d+)$"))
@owner_only
async def cb_owner_run(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)
    if not partner:
        await cb.answer("Channel tidak ditemukan.", show_alert=True)
        return
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(
                oid,
                f"▶️ **Channel aktif kembali!**\n\n"
                f"📡 **{partner.get('channel_name')}**\nRepost sudah berjalan lagi. 🚀"
            )
        except Exception:
            pass
    await cb.answer("▶️ Diaktifkan", show_alert=False)
    await _send_partner_detail(client, cb, channel_id)

# ── Pause/Run via command ──────────────────────────────────
@Client.on_message(filters.command("pause") & filters.private)
@owner_only
async def cmd_pause(client, message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply("**Format:** `/pause <ID> <alasan>`")
        return
    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID harus angka.")
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return
    reason = parts[2]
    upsert_partner(channel_id, {"paused": True, "reason": reason})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(oid,
                f"⏸ **Channel dijeda oleh admin.**\n\n"
                f"📡 **{partner.get('channel_name')}**\n📝 _{reason}_")
        except Exception:
            pass
    await message.reply(f"✅ **{partner.get('channel_name')}** dijeda.\n📝 _{reason}_")

@Client.on_message(filters.command("run") & filters.private)
@owner_only
async def cmd_run(client, message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply("**Format:** `/run <ID> <alasan>`")
        return
    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID harus angka.")
        return
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return
    reason = parts[2]
    upsert_partner(channel_id, {"paused": False, "reason": ""})
    if oid := partner.get("owner_id"):
        try:
            await client.send_message(oid,
                f"▶️ **Channel aktif kembali!**\n\n"
                f"📡 **{partner.get('channel_name')}**\n💬 _{reason}_")
        except Exception:
            pass
    await message.reply(f"✅ **{partner.get('channel_name')}** aktif kembali.")


# ══════════════════════════════════════════════════════════
#  CARI CHANNEL
# ══════════════════════════════════════════════════════════

@Client.on_message(
    filters.text & filters.private &
    ~filters.command(["start","stats","pause","run","listpartner","daftarkan",
                      "broadcast","broadcastpartner","maintenance","unmaintenance",
                      "addbl","rmbl","listbl"])
)
async def handle_search_input(client, message):
    if message.from_user.id != OWNER_ID:
        return
    if message.from_user.id not in _search_pending:
        return
    # Abaikan semua tombol keyboard
    if message.text in {
        "📊 Dashboard","📋 Partner","📣 Broadcast","🔧 Tools",
        "📂 My Channel","ℹ️ Info Bot","🏠 Menu Utama",
        "🔎 Cari Channel","🔄 Refresh Partner","◀️ Daftar Partner",
        "🚫 Blacklist","🔧 Maintenance","🔄 Refresh Blacklist",
        "🔴 Aktifkan Maintenance","🟢 Nonaktifkan Maintenance",
        "👥 Broadcast Semua","📡 Broadcast Partner",
        "⏸ Pause Channel","▶️ Aktifkan Channel",
        "❌ Batal Cari",
    }:
        return

    _search_pending.discard(message.from_user.id)
    query   = message.text.strip()
    results = search_partners(query)

    if not results:
        await message.reply(
            f"🔎 Tidak ada hasil untuk **\"{query}\"**",
            reply_markup=kb_partner()
        )
        return

    lines = [f"🔎 **\"{query}\"** — {len(results)} hasil\n"]
    rows  = []
    for ch in results[:10]:
        icon  = "▶️" if not ch.get("paused") else "⏸"
        uname = f"@{ch['username']}" if ch.get("username") else "—"
        lines.append(f"{icon} **{ch.get('channel_name','?')}**  {uname}")
        rows.append([InlineKeyboardButton(
            f"{icon}  {ch.get('channel_name','?')}",
            callback_data=f"owner_ch_{ch['_id']}"
        )])

    await message.reply(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows)
    )
    await client.send_message(message.chat.id, "Pilih channel di atas:", reply_markup=kb_partner())


# ══════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════

async def _send_broadcast_menu(client, source):
    total   = users.count_documents({})
    total_p = len({p["owner_id"] for p in get_all_partners() if p.get("owner_id")})
    text = (
        f"📣 **Broadcast**\n"
        f"`{'─' * 26}`\n\n"
        f"Semua user    `{total:,}`\n"
        f"Owner partner `{total_p}`\n\n"
        f"Pilih target di bawah:"
    )
    await source.reply(text, reply_markup=kb_broadcast())

@Client.on_message(filters.command("broadcast") & filters.private)
@owner_only
async def cmd_broadcast(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/broadcast <pesan>`")
        return
    text     = parts[1]
    user_ids = get_all_user_ids()
    total    = len(user_ids)
    success  = failed = 0
    prog     = await message.reply(f"📣 Mengirim ke `{total}` user...\n`░░░░░░░░░░` 0%")

    for i, uid in enumerate(user_ids, 1):
        try:
            await client.send_message(uid, text)
            success += 1
        except Exception:
            failed += 1
        if i % 20 == 0 or i == total:
            pct = round(i / total * 100)
            try:
                await prog.edit_text(
                    f"📣 Mengirim...\n`{_bar(i, total, 10)}` {pct}%\n\n"
                    f"✅ `{success}`  ❌ `{failed}`"
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await prog.edit_text(
        f"✅ **Broadcast selesai**\n\n"
        f"📨 Terkirim  `{success:,}`\n"
        f"❌ Gagal     `{failed:,}`\n"
        f"👥 Total     `{total:,}`"
    )

@Client.on_message(filters.command("broadcastpartner") & filters.private)
@owner_only
async def cmd_broadcast_partner(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/broadcastpartner <pesan>`")
        return
    text      = parts[1]
    owner_ids = list({p["owner_id"] for p in get_all_partners() if p.get("owner_id")})
    total     = len(owner_ids)
    success   = failed = 0
    prog      = await message.reply(f"📡 Mengirim ke `{total}` owner partner...")

    for uid in owner_ids:
        try:
            await client.send_message(uid, text)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await prog.edit_text(
        f"✅ **Broadcast partner selesai**\n\n"
        f"📨 Terkirim  `{success}`\n"
        f"❌ Gagal     `{failed}`\n"
        f"👥 Total     `{total}`"
    )


# ══════════════════════════════════════════════════════════
#  BLACKLIST
# ══════════════════════════════════════════════════════════

async def _send_blacklist_menu(client, source):
    words = get_blacklist()
    if words:
        word_lines = "\n".join(f"  • `{w}`" for w in words)
        text = (
            f"🚫 **Blacklist**  `{len(words)} kata`\n"
            f"`{'─' * 26}`\n\n"
            f"{word_lines}\n\n"
            f"Tambah: `/addbl <kata>`\n"
            f"Hapus:  `/rmbl <kata>`"
        )
    else:
        text = (
            f"🚫 **Blacklist**  `kosong`\n"
            f"`{'─' * 26}`\n\n"
            f"Belum ada kata terlarang.\n\n"
            f"Tambah: `/addbl <kata>`"
        )
    await source.reply(text, reply_markup=kb_blacklist())

@Client.on_message(filters.command("addbl") & filters.private)
@owner_only
async def cmd_addbl(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/addbl <kata>`")
        return
    word = parts[1].strip().lower()
    add_blacklist(word)
    await message.reply(f"✅ `{word}` ditambahkan ke blacklist.")

@Client.on_message(filters.command("rmbl") & filters.private)
@owner_only
async def cmd_rmbl(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/rmbl <kata>`")
        return
    word = parts[1].strip().lower()
    remove_blacklist(word)
    await message.reply(f"✅ `{word}` dihapus dari blacklist.")

@Client.on_message(filters.command("listbl") & filters.private)
@owner_only
async def cmd_listbl(client, message):
    words = get_blacklist()
    if not words:
        await message.reply("🚫 Blacklist kosong.")
        return
    await message.reply("🚫 **Blacklist:**\n\n" + "\n".join(f"• `{w}`" for w in words))


# ══════════════════════════════════════════════════════════
#  MAINTENANCE
# ══════════════════════════════════════════════════════════

def _maintenance_text():
    maint  = get_maintenance()
    active = maint.get("active", False)
    reason = maint.get("reason") or "—"
    status = "🔴 AKTIF" if active else "🟢 Normal"
    return (
        f"🔧 **Maintenance Mode**\n"
        f"`{'─' * 26}`\n\n"
        f"Status   {status}\n"
        f"Alasan   _{reason}_\n\n"
        f"Saat aktif, semua user kecuali owner tidak bisa akses bot."
    ), active

async def _send_maintenance_menu(client, source):
    text, _ = _maintenance_text()
    await source.reply(text, reply_markup=kb_maintenance())

@Client.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def cmd_maintenance(client, message):
    parts  = message.text.split(None, 1)
    reason = parts[1] if len(parts) > 1 else "Bot sedang dalam perbaikan. Harap tunggu."
    set_maintenance(True, reason)
    text, _ = _maintenance_text()
    await message.reply(text, reply_markup=kb_maintenance())

@Client.on_message(filters.command("unmaintenance") & filters.private)
@owner_only
async def cmd_unmaintenance(client, message):
    set_maintenance(False, "")
    await message.reply("🟢 **Maintenance dinonaktifkan.** Bot kembali normal.", reply_markup=kb_main())


# ══════════════════════════════════════════════════════════
#  MISC CALLBACKS
# ══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^close_owner_msg$"))
async def cb_close_owner(client, cb):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()

@Client.on_callback_query(filters.regex("^noop$"))
async def cb_noop(client, cb):
    await cb.answer()
