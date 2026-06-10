"""
Panel Owner — Dashboard, Stats, Partner list, Search, Broadcast,
Blacklist kata, Maintenance mode, Pause/Run channel.
"""
import asyncio
import functools
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
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

PAGE_SIZE = 10

# ─────────────────────────────────────────────────────────
#  DECORATOR
# ─────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _bar(val, total, width=12):
    if total == 0:
        return "░" * width
    filled = round((val / total) * width)
    return "█" * filled + "░" * (width - filled)

def _build_stats_text(total_users, active, paused, total_posts, today_posts):
    total_p = active + paused
    pct_a   = round(active / total_p * 100) if total_p else 0
    return (
        f"📊 **Dashboard FessBot**\n"
        f"`{'─'*28}`\n\n"
        f"👥 **Users**\n"
        f"  `{total_users:,}` terdaftar\n\n"
        f"📡 **Channel Partner**\n"
        f"  ▶️ Aktif   {_bar(active, total_p)} `{active}` ({pct_a}%)\n"
        f"  ⏸ Paused  {_bar(paused, total_p)} `{paused}`\n"
        f"  Total     `{total_p}`\n\n"
        f"📦 **Repost**\n"
        f"  Hari ini : `{today_posts:,}`\n"
        f"  All-time : `{total_posts:,}`\n"
    )

# Tombol navigasi bawah — selalu ada di setiap panel owner
def _nav_row(*extra):
    """
    Baris navigasi bawah. Selalu ada: Dashboard | Partner.
    Tambahkan tombol ekstra dengan *extra jika perlu.
    """
    row = [
        InlineKeyboardButton("📊 Dashboard", callback_data="owner_stats"),
        InlineKeyboardButton("📋 Partner",   callback_data="list_partner_0"),
    ]
    result = []
    if extra:
        result.append(list(extra))
    result.append(row)
    return result

async def safe_edit(message, text, reply_markup=None):
    """Edit pesan, abaikan MessageNotModified."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass

# ─────────────────────────────────────────────────────────
#  KEYBOARD SHORTCUTS (Reply Keyboard → buka panel inline)
# ─────────────────────────────────────────────────────────
@Client.on_message(filters.text & filters.private & filters.regex("^📊 Dashboard$"))
@owner_only
async def kb_dashboard(client, message):
    await _send_stats(client, message, edit=False)

@Client.on_message(filters.text & filters.private & filters.regex("^📋 Channel Partner$"))
@owner_only
async def kb_partner(client, message):
    await send_partner_list(client, message, page=0, edit=False)

@Client.on_message(filters.text & filters.private & filters.regex("^📣 Broadcast$"))
@owner_only
async def kb_broadcast(client, message):
    total = users.count_documents({})
    await message.reply(
        f"📣 **Broadcast ke Semua User**\n\n"
        f"Target: **{total:,} user** terdaftar\n\n"
        f"Ketik `/broadcast <pesan>` untuk kirim.\n"
        f"Atau pilih opsi di bawah:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 Broadcast ke Partner", callback_data="broadcast_partners")],
            *_nav_row(),
        ])
    )

@Client.on_message(filters.text & filters.private & filters.regex("^🔧 Tools$"))
@owner_only
async def kb_tools(client, message):
    maint  = get_maintenance()
    status = "🟢 Normal" if not maint.get("active") else "🔴 Maintenance"
    bl     = get_blacklist()
    await message.reply(
        f"🔧 **Tools Panel**\n\n"
        f"Status bot  : {status}\n"
        f"Blacklist   : `{len(bl)}` kata\n\n"
        f"Pilih aksi:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚫 Blacklist",    callback_data="blacklist_menu"),
                InlineKeyboardButton("🔧 Maintenance",  callback_data="maintenance_menu"),
            ],
            [InlineKeyboardButton("🔎 Cari Channel",    callback_data="search_channel_prompt")],
            *_nav_row(),
        ])
    )

# ─────────────────────────────────────────────────────────
#  STATS / DASHBOARD
# ─────────────────────────────────────────────────────────
async def _send_stats(client, source, edit=False):
    total_p     = count_partners()
    total_posts = posts.count_documents({})
    total_users = users.count_documents({})
    all_p       = get_all_partners()
    paused      = len([p for p in all_p if p.get("paused")])
    active      = total_p - paused
    today       = get_posts_today()

    text = _build_stats_text(total_users, active, paused, total_posts, today)
    btn  = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh",          callback_data="owner_stats"),
            InlineKeyboardButton("🔎 Cari Channel",     callback_data="search_channel_prompt"),
        ],
        [
            InlineKeyboardButton("📣 Broadcast",        callback_data="broadcast_menu"),
            InlineKeyboardButton("🚫 Blacklist",        callback_data="blacklist_menu"),
            InlineKeyboardButton("🔧 Maintenance",      callback_data="maintenance_menu"),
        ],
        # ── navigasi bawah ──
        [
            InlineKeyboardButton("📊 Dashboard",        callback_data="owner_stats"),
            InlineKeyboardButton("📋 Partner",          callback_data="list_partner_0"),
        ],
    ])
    if edit:
        await safe_edit(source.message, text, reply_markup=btn)
    else:
        await source.reply(text, reply_markup=btn)

@Client.on_message(filters.command("stats") & filters.private)
@owner_only
async def cmd_stats(client, message):
    await _send_stats(client, message, edit=False)

@Client.on_callback_query(filters.regex("^owner_stats$"))
@owner_only
async def cb_owner_stats(client, cb):
    await _send_stats(client, cb, edit=True)
    await cb.answer("✅ Diperbarui")

# ─────────────────────────────────────────────────────────
#  PAUSE / RUN
# ─────────────────────────────────────────────────────────
@Client.on_message(filters.command("pause") & filters.private)
@owner_only
async def cmd_pause(client, message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply("**Format:** `/pause <ID> <alasan>`\n**Contoh:** `/pause -1001234567890 Konten tidak sesuai`")
        return
    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID harus angka.")
        return

    reason  = parts[2]
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return

    upsert_partner(channel_id, {"paused": True, "reason": reason})
    ch_name = partner.get("channel_name", str(channel_id))

    if oid := partner.get("owner_id"):
        try:
            await client.send_message(oid,
                f"⏸ **Channel dijeda oleh admin.**\n\n"
                f"📡 **{ch_name}**\n📝 Alasan: _{reason}_\n\nHubungi admin untuk info lanjut.")
        except Exception:
            pass

    await message.reply(f"✅ **{ch_name}** dijeda.\n📝 _{reason}_\n💬 Notifikasi terkirim.")

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

    reason  = parts[2]
    partner = get_partner(channel_id)
    if not partner:
        await message.reply("❌ Channel tidak ditemukan.")
        return

    upsert_partner(channel_id, {"paused": False, "reason": ""})
    ch_name = partner.get("channel_name", str(channel_id))

    if oid := partner.get("owner_id"):
        try:
            await client.send_message(oid,
                f"▶️ **Channel aktif kembali!**\n\n"
                f"📡 **{ch_name}**\n💬 Pesan admin: _{reason}_\n\nRepost sudah berjalan lagi. 🚀")
        except Exception:
            pass

    await message.reply(f"✅ **{ch_name}** aktif kembali.\n💬 Notifikasi terkirim.")

# ── Inline pause/run dari detail channel ─────────────────
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
            await client.send_message(oid,
                f"⏸ **Channel dijeda oleh admin.**\n📡 **{partner.get('channel_name')}**\n\nHubungi admin untuk info lanjut.")
        except Exception:
            pass
    await cb.answer("⏸ Dijeda", show_alert=False)
    await _show_partner_detail(cb, channel_id)

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
            await client.send_message(oid,
                f"▶️ **Channel aktif kembali!**\n📡 **{partner.get('channel_name')}**\n\nRepost sudah berjalan lagi. 🚀")
        except Exception:
            pass
    await cb.answer("▶️ Diaktifkan", show_alert=False)
    await _show_partner_detail(cb, channel_id)

# ─────────────────────────────────────────────────────────
#  PARTNER LIST + DETAIL
# ─────────────────────────────────────────────────────────
@Client.on_message(filters.command("listpartner") & filters.private)
@owner_only
async def cmd_listpartner(client, message):
    await send_partner_list(client, message, page=0, edit=False)

@Client.on_callback_query(filters.regex(r"^list_partner_(\d+)$"))
@owner_only
async def cb_listpartner(client, cb):
    page = int(cb.matches[0].group(1))
    await send_partner_list(client, cb, page=page, edit=True)
    await cb.answer()

async def send_partner_list(client, source, page: int, edit: bool, data=None):
    all_p = data if data is not None else get_all_partners()
    if not all_p:
        text   = "📋 **Channel Partner**\n\nBelum ada partner terdaftar."
        markup = InlineKeyboardMarkup([*_nav_row()])
        if edit:
            await safe_edit(source.message, text, reply_markup=markup)
        else:
            await source.reply(text, reply_markup=markup)
        return

    chunk, total_pages = paginate(all_p, page, PAGE_SIZE)
    lines = [f"📋 **Channel Partner** — hal. {page+1}/{total_pages}  (`{len(all_p)}` total)\n"]
    for ch in chunk:
        status = "▶️" if not ch.get("paused") else "⏸"
        uname  = f"@{ch['username']}" if ch.get("username") else "—"
        rp     = ch.get("total_posts", 0)
        lines.append(
            f"{status} **{ch.get('channel_name','?')}**\n"
            f"    👤 {ch.get('owner_name','?')}  ·  {uname}\n"
            f"    📦 {rp} repost  ·  🆔 `{ch['_id']}`"
        )
    text = "\n\n".join(lines)

    # Paginasi
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"list_partner_{page-1}"))
    nav.append(InlineKeyboardButton(f"· {page+1}/{total_pages} ·", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"list_partner_{page+1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔎 Cari Channel", callback_data="search_channel_prompt")])
    # ── navigasi bawah ──
    rows.extend(_nav_row())

    markup = InlineKeyboardMarkup(rows)
    if edit:
        await safe_edit(source.message, text, reply_markup=markup)
    else:
        await source.reply(text, reply_markup=markup)

# ── Detail channel ────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^owner_ch_(-?\d+)$"))
@owner_only
async def cb_owner_ch_detail(client, cb):
    channel_id = int(cb.matches[0].group(1))
    await _show_partner_detail(cb, channel_id)
    await cb.answer()

async def _show_partner_detail(source, channel_id: int):
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

    reason_line = f"\n⚠️ _{reason}_" if reason else ""
    text = (
        f"📡 **{partner.get('channel_name', channel_id)}**\n"
        f"┌ Username : {uname}\n"
        f"├ Owner    : {partner.get('owner_name','?')}\n"
        f"├ Status   : {status}{reason_line}\n"
        f"├ Repost   : `{rp_count}` kali\n"
        f"└ Daftar   : {added_str}\n\n"
        f"Aksi:"
    )

    toggle_btn = (
        InlineKeyboardButton("▶️ Aktifkan", callback_data=f"owner_run_{channel_id}")
        if paused else
        InlineKeyboardButton("⏸ Pause",    callback_data=f"owner_pause_{channel_id}")
    )

    markup = InlineKeyboardMarkup([
        [toggle_btn],
        # ── navigasi bawah ──
        *_nav_row(),
    ])

    if hasattr(source, "message"):
        await safe_edit(source.message, text, reply_markup=markup)
    else:
        await source.reply(text, reply_markup=markup)

# ─────────────────────────────────────────────────────────
#  SEARCH CHANNEL
# ─────────────────────────────────────────────────────────
_search_pending = set()

@Client.on_callback_query(filters.regex("^search_channel_prompt$"))
@owner_only
async def cb_search_prompt(client, cb):
    _search_pending.add(cb.from_user.id)
    await safe_edit(
        cb.message,
        "🔎 **Cari Channel Partner**\n\nKetik nama channel atau username yang ingin dicari:",
        reply_markup=InlineKeyboardMarkup([*_nav_row(
            InlineKeyboardButton("✖️ Batal", callback_data="owner_stats")
        )])
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
    if message.text in {"📊 Dashboard","📋 Channel Partner","📣 Broadcast","🔧 Tools","📂 My Channel","ℹ️ Info Bot"}:
        return

    _search_pending.discard(message.from_user.id)
    query   = message.text.strip()
    results = search_partners(query)

    if not results:
        await message.reply(
            f"🔎 Tidak ada channel dengan kata kunci **\"{query}\"**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 Cari Lagi", callback_data="search_channel_prompt")],
                *_nav_row(),
            ])
        )
        return

    lines = [f"🔎 **Hasil pencarian:** \"{query}\" — {len(results)} ditemukan\n"]
    rows  = []
    for ch in results[:10]:
        status = "▶️" if not ch.get("paused") else "⏸"
        uname  = f"@{ch['username']}" if ch.get("username") else "—"
        lines.append(f"{status} **{ch.get('channel_name','?')}** · {uname}\n🆔 `{ch['_id']}`")
        rows.append([InlineKeyboardButton(
            f"{status} {ch.get('channel_name','?')}",
            callback_data=f"owner_ch_{ch['_id']}"
        )])

    rows.append([InlineKeyboardButton("🔎 Cari Lagi", callback_data="search_channel_prompt")])
    rows.extend(_nav_row())
    await message.reply("\n\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))

# ─────────────────────────────────────────────────────────
#  BROADCAST
# ─────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^broadcast_menu$"))
@owner_only
async def cb_broadcast_menu(client, cb):
    total = users.count_documents({})
    await safe_edit(
        cb.message,
        f"📣 **Broadcast ke Semua User**\n\n"
        f"Target: **{total:,} user** terdaftar\n\n"
        f"Ketik `/broadcast <pesan>` untuk kirim.\n"
        f"Atau tap tombol di bawah untuk broadcast ke partner saja.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 Broadcast ke Partner", callback_data="broadcast_partners")],
            *_nav_row(),
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
    success  = 0
    failed   = 0

    prog_msg = await message.reply(f"📣 Mengirim broadcast ke **{total}** user...\n`░░░░░░░░░░` 0%")

    for i, uid in enumerate(user_ids, 1):
        try:
            await client.send_message(uid, text)
            success += 1
        except Exception:
            failed += 1
        if i % 20 == 0 or i == total:
            pct = round(i / total * 100)
            bar = _bar(i, total, 10)
            try:
                await prog_msg.edit_text(
                    f"📣 Broadcast berjalan...\n"
                    f"`{bar}` {pct}%\n\n"
                    f"✅ Berhasil: `{success}`  ❌ Gagal: `{failed}`"
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await prog_msg.edit_text(
        f"✅ **Broadcast selesai!**\n\n"
        f"📨 Terkirim : `{success:,}`\n"
        f"❌ Gagal    : `{failed:,}`\n"
        f"👥 Total    : `{total:,}`"
    )

@Client.on_callback_query(filters.regex("^broadcast_partners$"))
@owner_only
async def cb_broadcast_partners(client, cb):
    await safe_edit(
        cb.message,
        "📡 Ketik `/broadcastpartner <pesan>` untuk broadcast ke semua **owner channel partner**.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Broadcast Menu", callback_data="broadcast_menu")],
            *_nav_row(),
        ])
    )
    await cb.answer()

@Client.on_message(filters.command("broadcastpartner") & filters.private)
@owner_only
async def cmd_broadcast_partner(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/broadcastpartner <pesan>`")
        return

    text      = parts[1]
    all_p     = get_all_partners()
    owner_ids = list({p["owner_id"] for p in all_p if p.get("owner_id")})
    total     = len(owner_ids)
    success   = 0
    failed    = 0

    prog_msg = await message.reply(f"📡 Broadcast ke **{total}** owner partner...")

    for uid in owner_ids:
        try:
            await client.send_message(uid, text)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await prog_msg.edit_text(
        f"✅ **Broadcast partner selesai!**\n\n"
        f"📨 Terkirim : `{success}`\n"
        f"❌ Gagal    : `{failed}`\n"
        f"👥 Total    : `{total}`"
    )

# ─────────────────────────────────────────────────────────
#  BLACKLIST
# ─────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^blacklist_menu$"))
@owner_only
async def cb_blacklist_menu(client, cb):
    words = get_blacklist()
    if words:
        words_text = "\n".join(f"  • `{w}`" for w in words)
        text = (
            f"🚫 **Blacklist Kata** (`{len(words)}` kata)\n\n{words_text}\n\n"
            f"Gunakan `/addbl <kata>` untuk tambah\n"
            f"atau `/rmbl <kata>` untuk hapus."
        )
    else:
        text = "🚫 **Blacklist Kata**\n\nBelum ada kata yang diblacklist.\n\nGunakan `/addbl <kata>` untuk tambah."
    await safe_edit(
        cb.message, text,
        reply_markup=InlineKeyboardMarkup([*_nav_row()])
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
    await message.reply(f"✅ Kata **\"{word}\"** ditambahkan ke blacklist.")

@Client.on_message(filters.command("rmbl") & filters.private)
@owner_only
async def cmd_rmbl(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("**Format:** `/rmbl <kata>`")
        return
    word = parts[1].strip().lower()
    remove_blacklist(word)
    await message.reply(f"✅ Kata **\"{word}\"** dihapus dari blacklist.")

@Client.on_message(filters.command("listbl") & filters.private)
@owner_only
async def cmd_listbl(client, message):
    words = get_blacklist()
    if not words:
        await message.reply("🚫 Blacklist kosong.")
        return
    text = "🚫 **Daftar Blacklist:**\n\n" + "\n".join(f"• `{w}`" for w in words)
    await message.reply(text)

# ─────────────────────────────────────────────────────────
#  MAINTENANCE MODE
# ─────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^maintenance_menu$"))
@owner_only
async def cb_maintenance_menu(client, cb):
    maint        = get_maintenance()
    active       = maint.get("active", False)
    reason       = maint.get("reason", "—")
    status_icon  = "🔴 AKTIF" if active else "🟢 Normal"
    toggle_label = "🟢 Nonaktifkan Maintenance" if active else "🔴 Aktifkan Maintenance"
    toggle_cb    = "maintenance_off" if active else "maintenance_on_prompt"

    await safe_edit(
        cb.message,
        f"🔧 **Maintenance Mode**\n\n"
        f"Status  : {status_icon}\n"
        f"Alasan  : _{reason}_\n\n"
        f"Saat maintenance aktif, semua user (kecuali owner) tidak bisa akses bot.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_label, callback_data=toggle_cb)],
            *_nav_row(),
        ])
    )
    await cb.answer()

@Client.on_callback_query(filters.regex("^maintenance_on_prompt$"))
@owner_only
async def cb_maint_on_prompt(client, cb):
    await safe_edit(
        cb.message,
        "🔧 Ketik alasan maintenance:\n`/maintenance <alasan>`\n\nAtau tap untuk aktifkan dengan alasan default:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Aktifkan (alasan default)", callback_data="maintenance_on_default")],
            [InlineKeyboardButton("✖️ Batal", callback_data="maintenance_menu")],
            *_nav_row(),
        ])
    )
    await cb.answer()

@Client.on_callback_query(filters.regex("^maintenance_on_default$"))
@owner_only
async def cb_maint_on_default(client, cb):
    set_maintenance(True, "Bot sedang dalam perbaikan. Harap tunggu.")
    await safe_edit(
        cb.message,
        "🔴 **Maintenance mode aktif.**\n\nSemua user tidak bisa akses bot sementara.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Nonaktifkan", callback_data="maintenance_off")],
            *_nav_row(),
        ])
    )
    await cb.answer("🔴 Maintenance aktif", show_alert=False)

@Client.on_callback_query(filters.regex("^maintenance_off$"))
@owner_only
async def cb_maint_off(client, cb):
    set_maintenance(False, "")
    await safe_edit(
        cb.message,
        "🟢 **Maintenance mode dinonaktifkan.**\n\nBot kembali normal.",
        reply_markup=InlineKeyboardMarkup([*_nav_row()])
    )
    await cb.answer("🟢 Bot kembali normal", show_alert=False)

@Client.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def cmd_maintenance(client, message):
    parts  = message.text.split(None, 1)
    reason = parts[1] if len(parts) > 1 else "Bot sedang dalam perbaikan. Harap tunggu."
    set_maintenance(True, reason)
    await message.reply(
        f"🔴 **Maintenance aktif.**\n📝 Alasan: _{reason}_",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Nonaktifkan", callback_data="maintenance_off")]
        ])
    )

@Client.on_message(filters.command("unmaintenance") & filters.private)
@owner_only
async def cmd_unmaintenance(client, message):
    set_maintenance(False, "")
    await message.reply("🟢 **Maintenance dinonaktifkan.** Bot kembali normal.")

# ─────────────────────────────────────────────────────────
#  MISC
# ─────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^close_owner_msg$"))
async def cb_close_owner(client, cb):
    await cb.message.delete()
    await cb.answer()

@Client.on_callback_query(filters.regex("^noop$"))
async def cb_noop(client, cb):
    await cb.answer()
