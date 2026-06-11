"""
Panel Owner — Dashboard, Stats, Partner list, Search, Broadcast,
Blacklist, Maintenance, Pause/Run channel.

Sistem navigasi:
  Setiap panel punya baris AKSI (atas) dan baris NAVIGASI (bawah).
  Baris navigasi selalu: [◀ Kembali ke konteks] [🏠 Dashboard]
  Tombol "kembali" menyesuaikan dari mana panel dibuka.
"""
import asyncio
import functools
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
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
from plugins.start import owner_keyboard

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

# Baris navigasi bawah standar
def _nav(back_label=None, back_cb=None):
    """
    Kembalikan satu baris navigasi.
    Jika back disertakan: [◀ back_label]  [🏠 Dashboard]
    Jika tidak: [🏠 Dashboard]
    """
    home = InlineKeyboardButton("🏠 Dashboard", callback_data="owner_stats")
    if back_label and back_cb:
        return [InlineKeyboardButton(f"◀️ {back_label}", callback_data=back_cb), home]
    return [home]


# ══════════════════════════════════════════════════════════
#  REPLY KEYBOARD — diimpor dari plugins.start
# ══════════════════════════════════════════════════════════

# Handler setiap tombol keyboard → buka panel inline
@Client.on_message(filters.text & filters.private & filters.regex("^📊 Dashboard$"))
@owner_only
async def kb_dashboard(client, message):
    await _send_stats(client, message, edit=False)

@Client.on_message(filters.text & filters.private & filters.regex("^📋 Partner$"))
@owner_only
async def kb_partner(client, message):
    await _send_partner_list(client, message, page=0, edit=False)

@Client.on_message(filters.text & filters.private & filters.regex("^📣 Broadcast$"))
@owner_only
async def kb_broadcast(client, message):
    await _send_broadcast_menu(client, message, edit=False)

@Client.on_message(filters.text & filters.private & filters.regex("^🔧 Tools$"))
@owner_only
async def kb_tools(client, message):
    await _send_tools_menu(client, message, edit=False)


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

def _stats_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Partner",       callback_data="list_partner_0"),
            InlineKeyboardButton("🔎 Cari Channel",  callback_data="search_prompt"),
        ],
        [
            InlineKeyboardButton("📣 Broadcast",     callback_data="broadcast_menu"),
            InlineKeyboardButton("🔧 Tools",         callback_data="tools_menu"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh",       callback_data="owner_stats"),
        ],
    ])

async def _send_stats(client, source, edit=False):
    text   = _stats_text()
    markup = _stats_markup()
    if edit:
        await safe_edit(source.message, text, markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client, message):
    await message.reply(_stats_text(), reply_markup=_stats_markup())
    await message.reply("Menu:", reply_markup=owner_keyboard())

@Client.on_callback_query(filters.regex("^owner_stats$"))
@owner_only
async def cb_owner_stats(client, cb):
    await _send_stats(client, cb, edit=True)
    await cb.answer("✅ Diperbarui")


# ══════════════════════════════════════════════════════════
#  TOOLS MENU
# ══════════════════════════════════════════════════════════

async def _send_tools_menu(client, source, edit=False):
    maint  = get_maintenance()
    bl     = get_blacklist()
    status = "🔴 Maintenance aktif" if maint.get("active") else "🟢 Normal"
    text   = (
        f"🔧 **Tools**\n"
        f"`{'─' * 26}`\n\n"
        f"Status bot   {status}\n"
        f"Blacklist    `{len(bl)}` kata\n"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 Blacklist",    callback_data="blacklist_menu"),
            InlineKeyboardButton("🔧 Maintenance",  callback_data="maintenance_menu"),
        ],
        [
            InlineKeyboardButton("🔎 Cari Channel", callback_data="search_prompt"),
        ],
        _nav(),
    ])
    if edit:
        await safe_edit(source.message, text, markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^tools_menu$"))
@owner_only
async def cb_tools_menu(client, cb):
    await _send_tools_menu(client, cb, edit=True)
    await cb.answer()


# ══════════════════════════════════════════════════════════
#  PARTNER LIST
# ══════════════════════════════════════════════════════════

async def _send_partner_list(client, source, page: int, edit: bool, data=None):
    all_p = data if data is not None else get_all_partners()

    if not all_p:
        text   = "📋 **Channel Partner**\n\nBelum ada partner terdaftar."
        markup = InlineKeyboardMarkup([_nav()])
        if edit:
            await safe_edit(source.message, text, markup)
        else:
            await source.reply(text, reply_markup=markup)
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

    rows = []

    # Paginasi
    if total_pages > 1:
        nav_page = []
        if page > 0:
            nav_page.append(InlineKeyboardButton("◀️", callback_data=f"list_partner_{page-1}"))
        nav_page.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_page.append(InlineKeyboardButton("▶️", callback_data=f"list_partner_{page+1}"))
        rows.append(nav_page)

    rows.append([InlineKeyboardButton("🔎 Cari Channel", callback_data="search_prompt")])
    rows.append(_nav())

    markup = InlineKeyboardMarkup(rows)
    if edit:
        await safe_edit(source.message, text, markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client, message):
    await _send_partner_list(client, message, page=0, edit=False)

@Client.on_callback_query(filters.regex(r"^list_partner_(\d+)$"))
@owner_only
async def cb_listpartner(client, cb):
    page = int(cb.matches[0].group(1))
    await _send_partner_list(client, cb, page=page, edit=True)
    await cb.answer()


# ══════════════════════════════════════════════════════════
#  DETAIL CHANNEL (owner view)
# ══════════════════════════════════════════════════════════

async def _send_partner_detail(source, channel_id: int):
    from db.helpers import count_posts_by_partner
    partner = get_partner(channel_id)
    if not partner:
        if hasattr(source, "answer"):
            await source.answer("Channel tidak ditemukan.", show_alert=True)
        return

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

    toggle = (
        InlineKeyboardButton("▶️ Aktifkan", callback_data=f"owner_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause",    callback_data=f"owner_pause_{channel_id}")
    )

    markup = InlineKeyboardMarkup([
        [toggle],
        _nav("Daftar Partner", "list_partner_0"),
    ])

    msg = source.message if hasattr(source, "message") else source
    await safe_edit(msg, text, markup)

@Client.on_callback_query(filters.regex(r"^owner_ch_(-?\d+)$"))
@owner_only
async def cb_owner_ch_detail(client, cb):
    channel_id = int(cb.matches[0].group(1))
    await _send_partner_detail(cb, channel_id)
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
    await _send_partner_detail(cb, channel_id)

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
    await _send_partner_detail(cb, channel_id)

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

_search_pending: set[int] = set()

@Client.on_callback_query(filters.regex("^search_prompt$"))
@owner_only
async def cb_search_prompt(client, cb):
    _search_pending.add(cb.from_user.id)
    await safe_edit(
        cb.message,
        "🔎 **Cari Channel Partner**\n\nKetik nama atau username channel:",
        InlineKeyboardMarkup([
            _nav("Batal", "owner_stats"),
        ])
    )
    await cb.answer()

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
    # Abaikan tombol keyboard
    if message.text in {"📊 Dashboard","📋 Partner","📣 Broadcast","🔧 Tools",
                        "📂 My Channel","ℹ️ Info Bot"}:
        return

    _search_pending.discard(message.from_user.id)
    query   = message.text.strip()
    results = search_partners(query)

    if not results:
        await message.reply(
            f"🔎 Tidak ada hasil untuk **\"{query}\"**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 Cari Lagi", callback_data="search_prompt")],
                _nav(),
            ])
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

    rows.append([InlineKeyboardButton("🔎 Cari Lagi", callback_data="search_prompt")])
    rows.append(_nav())
    await message.reply("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


# ══════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════

async def _send_broadcast_menu(client, source, edit=False):
    total  = users.count_documents({})
    total_p = len({p["owner_id"] for p in get_all_partners() if p.get("owner_id")})
    text = (
        f"📣 **Broadcast**\n"
        f"`{'─' * 26}`\n\n"
        f"Semua user   `{total:,}`\n"
        f"Owner partner `{total_p}`\n\n"
        f"Pilih target:"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Semua User",    callback_data="broadcast_prompt_all"),
            InlineKeyboardButton("📡 Owner Partner", callback_data="broadcast_prompt_partner"),
        ],
        _nav(),
    ])
    if edit:
        await safe_edit(source.message, text, markup)
    else:
        await source.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^broadcast_menu$"))
@owner_only
async def cb_broadcast_menu(client, cb):
    await _send_broadcast_menu(client, cb, edit=True)
    await cb.answer()

@Client.on_callback_query(filters.regex("^broadcast_prompt_(all|partner)$"))
@owner_only
async def cb_broadcast_prompt(client, cb):
    target = cb.matches[0].group(1)
    label  = "semua user" if target == "all" else "owner channel partner"
    await safe_edit(
        cb.message,
        f"📣 **Broadcast ke {label}**\n\nKetik `/broadcast <pesan>` untuk kirim ke semua user.\n"
        f"Atau `/broadcastpartner <pesan>` untuk kirim ke owner partner.",
        InlineKeyboardMarkup([
            _nav("Broadcast", "broadcast_menu"),
        ])
    )
    await cb.answer()

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

@Client.on_callback_query(filters.regex("^blacklist_menu$"))
@owner_only
async def cb_blacklist_menu(client, cb):
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
    await safe_edit(
        cb.message, text,
        InlineKeyboardMarkup([_nav("Tools", "tools_menu")])
    )
    await cb.answer()

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

@Client.on_callback_query(filters.regex("^maintenance_menu$"))
@owner_only
async def cb_maintenance_menu(client, cb):
    text, active = _maintenance_text()
    toggle_label = "🟢 Nonaktifkan" if active else "🔴 Aktifkan"
    toggle_cb    = "maint_off"      if active else "maint_on_prompt"
    await safe_edit(
        cb.message, text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_label, callback_data=toggle_cb)],
            _nav("Tools", "tools_menu"),
        ])
    )
    await cb.answer()

@Client.on_callback_query(filters.regex("^maint_on_prompt$"))
@owner_only
async def cb_maint_on_prompt(client, cb):
    await safe_edit(
        cb.message,
        "🔧 **Aktifkan Maintenance**\n\n"
        "Gunakan `/maintenance <alasan>` untuk alasan kustom.\n"
        "Atau tap tombol untuk alasan default:",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Aktifkan (default)", callback_data="maint_on_default")],
            _nav("Batal", "maintenance_menu"),
        ])
    )
    await cb.answer()

@Client.on_callback_query(filters.regex("^maint_on_default$"))
@owner_only
async def cb_maint_on_default(client, cb):
    set_maintenance(True, "Bot sedang dalam perbaikan. Harap tunggu.")
    text, active = _maintenance_text()
    await safe_edit(
        cb.message, text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Nonaktifkan", callback_data="maint_off")],
            _nav("Tools", "tools_menu"),
        ])
    )
    await cb.answer("🔴 Maintenance aktif")

@Client.on_callback_query(filters.regex("^maint_off$"))
@owner_only
async def cb_maint_off(client, cb):
    set_maintenance(False, "")
    text, active = _maintenance_text()
    await safe_edit(
        cb.message, text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Aktifkan", callback_data="maint_on_prompt")],
            _nav("Tools", "tools_menu"),
        ])
    )
    await cb.answer("🟢 Bot kembali normal")

@Client.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def cmd_maintenance(client, message):
    parts  = message.text.split(None, 1)
    reason = parts[1] if len(parts) > 1 else "Bot sedang dalam perbaikan. Harap tunggu."
    set_maintenance(True, reason)
    await message.reply(
        f"🔴 **Maintenance aktif**\n📝 _{reason}_",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Nonaktifkan", callback_data="maint_off")]
        ])
    )

@Client.on_message(filters.command("unmaintenance") & filters.private)
@owner_only
async def cmd_unmaintenance(client, message):
    set_maintenance(False, "")
    await message.reply("🟢 **Maintenance dinonaktifkan.** Bot kembali normal.")


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
