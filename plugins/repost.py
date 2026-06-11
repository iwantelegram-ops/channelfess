"""
Auto-repost dari channel partner ke channel utama.
- Deteksi bot jadi admin → daftarkan partner
- Blacklist kata otomatis
- FloodWait handling dengan exponential backoff
- Notifikasi ke owner (cek setting notif)
- Counter total_posts per partner
- Auto-hapus repost jika post asli dihapus
- Log aktivitas ke MongoDB
- Dukung foto, video, dokumen, audio, teks
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pyrogram import Client, filters, raw
from pyrogram.types import (
    Message, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import (
    FloodWait, ChatWriteForbidden, PeerIdInvalid, MessageIdInvalid,
    ChatAdminRequired, UserNotParticipant, ChannelPrivate,
)
from config import MAIN_CHANNEL_ID
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post,
    increment_partner_posts, contains_blacklisted, count_posts_by_partner,
    get_notif_setting, log_activity, get_bot_setting, get_all_partners,
)
from utils import safe_send, safe_delete, answer_cb

log = logging.getLogger("fessbot.repost")
PM  = ParseMode.MARKDOWN


# ═══════════════════════════════════════════════════════════
#  TASK HELPERS — safe background tasks
# ═══════════════════════════════════════════════════════════

async def _safe_task(coro):
    """Wrapper coroutine agar unhandled exception di background task tidak crash bot."""
    try:
        await coro
    except Exception as e:
        log.error(f"[bg_task] Unhandled exception: {e}")


def _ensure_bg_task(coro):
    """Buat background task dengan error handler."""
    import asyncio as _asyncio
    task = _asyncio.ensure_future(_safe_task(coro))
    return task



# ═══════════════════════════════════════════════════════════
#  CAPTION BUILDER — JANGAN DIUBAH (sesuai permintaan owner)
# ═══════════════════════════════════════════════════════════

def build_caption(original_caption, channel_title, invite_link,
                  owner_name, owner_id, post_number, bot_name, bot_username):
    now  = datetime.now(timezone.utc)
    date = now.strftime("%d %b %Y")
    time = now.strftime("%H:%M UTC")

    # Channel asal — clickable via invite_link (t.me/+ atau t.me/username)
    if invite_link:
        ch_link = f"[{channel_title}]({invite_link})"
    else:
        ch_link = f"**{channel_title}**"

    # Owner — clickable link ke profil user (tg://user?id=...)
    owner_link = f"[{owner_name}](tg://user?id={owner_id})"

    # Via bot — nama bot dari sistem, clickable link start bot
    bot_link = f"[{bot_name}](https://t.me/{bot_username}?start=start)"

    cap = f"{ch_link}\n"
    if original_caption:
        cap += f"\n{original_caption}\n"
    cap += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"👤  Owner   :  {owner_link}\n"
        f"📅  Tanggal :  {date}\n"
        f"🕒  Jam     :  {time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔁  via {bot_link}"
    )
    return cap.strip()


# ═══════════════════════════════════════════════════════════
#  HELPER — INVITE LINK
# ═══════════════════════════════════════════════════════════

async def _get_or_create_invite_link(client: Client, channel_id: int) -> str:
    """
    3 langkah:
      1. Cek DB — jika sudah ada, pakai langsung.
      2. Jika belum, generate via Telegram lalu simpan ke DB.
      3. Jika tidak ada izin (ChatAdminRequired dll), abaikan diam-diam → return "".
    """
    # Langkah 1 — ambil dari DB
    partner = get_partner(channel_id)
    if partner and partner.get("invite_link"):
        return partner["invite_link"]

    # Langkah 2 — generate dari Telegram
    _NO_PERM_ERRORS = (
        ChatAdminRequired,
        ChatWriteForbidden,
        ChannelPrivate,
        UserNotParticipant,
    )
    try:
        link = await client.export_chat_invite_link(channel_id)
        if link:
            upsert_partner(channel_id, {"invite_link": link})
            log.info(f"[invite_link] Generated untuk {channel_id}: {link}")
            return link
    except _NO_PERM_ERRORS:
        # Langkah 3 — tidak ada izin, abaikan tanpa error
        log.debug(f"[invite_link] Tidak ada izin generate untuk {channel_id}, diabaikan")
    except FloodWait as e:
        log.warning(f"[invite_link] FloodWait {e.value}s untuk {channel_id}, skip")
    except Exception as e:
        log.warning(f"[invite_link] Gagal generate untuk {channel_id}: {e}")
    return ""


# ═══════════════════════════════════════════════════════════
#  DETEKSI BOT JADI ADMIN
# ═══════════════════════════════════════════════════════════

@Client.on_chat_member_updated(filters.channel)
async def on_bot_admin_change(client: Client, update: ChatMemberUpdated):
    me = await client.get_me()
    if not update.new_chat_member or update.new_chat_member.user.id != me.id:
        return

    channel_id = update.chat.id
    new_status = update.new_chat_member.status
    old_status = update.old_chat_member.status if update.old_chat_member else ChatMemberStatus.LEFT

    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        if old_status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            inviter    = update.from_user
            owner_id   = inviter.id   if inviter else 0
            owner_name = inviter.first_name if inviter else "Unknown"

            # Generate invite link untuk caption clickable
            invite_link = await _get_or_create_invite_link(client, channel_id)

            upsert_partner(channel_id, {
                "owner_id":     owner_id,
                "owner_name":   owner_name,
                "channel_name": update.chat.title,
                "username":     update.chat.username or "",
                "invite_link":  invite_link,
                "paused":       True,
                "reason":       "Menunggu konfirmasi owner",
                "added_at":     datetime.now(timezone.utc),
                "total_posts":  0,
            })
            log_activity("partner_added", channel_id, {"owner_id": owner_id})
            log.info(f"[admin_change] Channel terdaftar: {update.chat.title} ({channel_id})")

            # Pastikan bot subscribe ke updates channel ini
            # (Telegram hanya kirim UpdateDeleteChannelMessages ke bot
            #  yang pernah resolve/fetch channel tersebut)
            try:
                await client.get_chat(channel_id)
            except Exception:
                pass

            if inviter:
                await safe_send(client.send_message(
                    owner_id,
                    f"🎉 **Channel berhasil terhubung!**\n\n"
                    f"📡 **{update.chat.title}** sudah terdaftar di FessBot.\n\n"
                    f"Aktifkan sekarang agar postinganmu mulai di-repost ke channel utama?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Ya, Aktifkan Sekarang", callback_data=f"confirm_sync_{channel_id}")],
                        [InlineKeyboardButton("⏸️ Nanti Saja", callback_data=f"confirm_nosync_{channel_id}")],
                    ]),
                ))

    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin channel"})
            log_activity("bot_removed", channel_id)
            oid = existing.get("owner_id")
            if oid:
                should_notify = get_notif_setting(oid, "status_notif", True)
                if should_notify:
                    try:
                        await client.send_message(
                            oid,
                            f"⚠️ **Bot dicopot dari admin channel.**\n\n"
                            f"📡 **{existing.get('channel_name')}**\n\n"
                            f"Repost otomatis dihentikan. Tambahkan bot kembali "
                            f"sebagai admin untuk melanjutkan.",
                        )
                    except Exception as e:
                        log.warning(f"[on_bot_admin_change] Gagal kirim notif ke {oid}: {e}")


# ═══════════════════════════════════════════════════════════
#  KONFIRMASI SINKRON
# ═══════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^confirm_sync_(-?\d+)$"))
async def cb_confirm_sync(client: Client, cb):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != cb.from_user.id:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return

        upsert_partner(channel_id, {"paused": False, "reason": ""})
        log_activity("partner_activated", channel_id)

        try:
            await cb.message.edit_text(
                f"✅ **Channel diaktifkan!**\n\n"
                f"📡 **{partner.get('channel_name', channel_id)}** kini meneruskan "
                f"postingan ke channel utama secara real-time. 🚀\n\n"
                f"Buka **My Channel** untuk kelola kapan saja.",
                reply_markup=None,
            )
        except Exception:
            pass

        await answer_cb(cb, "Aktif!")
        answered = True
    except Exception as e:
        log.error(f"[cb_confirm_sync] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


@Client.on_callback_query(filters.regex(r"^confirm_nosync_(-?\d+)$"))
async def cb_confirm_nosync(client: Client, cb):
    answered = False
    try:
        channel_id = int(cb.matches[0].group(1))
        partner    = get_partner(channel_id)

        if not partner or partner.get("owner_id") != cb.from_user.id:
            await answer_cb(cb, "Channel tidak ditemukan.", True)
            answered = True
            return

        upsert_partner(channel_id, {"paused": True, "reason": "Tidak diaktifkan oleh owner"})

        try:
            await cb.message.edit_text(
                f"⏸ **Tidak diaktifkan.**\n\n"
                f"📡 **{partner.get('channel_name', channel_id)}** terdaftar tapi belum aktif.\n"
                f"Anda bisa mengubahnya kapan saja di **My Channel**.",
                reply_markup=None,
            )
        except Exception:
            pass

        await answer_cb(cb, "Bisa diaktifkan nanti.")
        answered = True
    except Exception as e:
        log.error(f"[cb_confirm_nosync] {e}")
    finally:
        if not answered:
            await answer_cb(cb)


# ═══════════════════════════════════════════════════════════
#  /daftarkan — fallback manual
# ═══════════════════════════════════════════════════════════

@Client.on_message(filters.command("daftarkan") & filters.private)
async def cmd_daftarkan(client: Client, message: Message):
    reply = message.reply_to_message
    if not reply or not reply.forward_from_chat:
        await message.reply(
            "📋 **Cara daftarkan channel manual:**\n\n"
            "`1.` Forward satu postingan dari channelmu ke sini\n"
            "`2.` Reply pesan forward itu dengan `/daftarkan`"
        )
        return

    chat = reply.forward_from_chat
    if chat.type != ChatType.CHANNEL:
        await message.reply("❌ Harus forward dari channel.")
        return

    channel_id = chat.id
    user_id    = message.from_user.id

    try:
        me     = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply(f"❌ Bot belum jadi admin di **{chat.title}**.")
            return
    except FloodWait as e:
        await asyncio.sleep(min(e.value + 2, 60))
        await message.reply("⚠️ Rate limit Telegram, coba lagi sebentar.")
        return
    except (PeerIdInvalid, Exception) as e:
        await message.reply(f"❌ Tidak bisa akses channel.\n`{e}`")
        return

    try:
        user_member = await client.get_chat_member(channel_id, user_id)
        if user_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply("❌ Kamu harus admin channel tersebut.")
            return
    except Exception:
        await message.reply("❌ Tidak bisa verifikasi status kamu di channel.")
        return

    # Generate invite link untuk caption clickable
    invite_link = await _get_or_create_invite_link(client, channel_id)

    upsert_partner(channel_id, {
        "owner_id":     user_id,
        "owner_name":   message.from_user.first_name or "Unknown",
        "channel_name": chat.title,
        "username":     chat.username or "",
        "invite_link":  invite_link,
        "paused":       True,
        "reason":       "Menunggu konfirmasi owner",
        "added_at":     datetime.now(timezone.utc),
        "total_posts":  0,
    })
    log_activity("partner_manual_add", channel_id, {"owner_id": user_id})

    await message.reply(
        f"🎉 **Channel terdaftar!**\n\n📡 **{chat.title}**\n\nAktifkan sekarang?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Aktifkan Sekarang", callback_data=f"confirm_sync_{channel_id}")],
            [InlineKeyboardButton("⏸️ Nanti Saja", callback_data=f"confirm_nosync_{channel_id}")],
        ]),
    )


# ═══════════════════════════════════════════════════════════
#  REPOST — foto, video, dokumen, audio, teks
# ═══════════════════════════════════════════════════════════

MEDIA_FILTER = (filters.photo | filters.video | filters.text)


@Client.on_message(filters.channel & MEDIA_FILTER)
async def repost(client: Client, message: Message):
    channel_id = message.chat.id
    partner    = get_partner(channel_id)

    if not partner or partner.get("paused"):
        return

    # ── Blacklist ──────────────────────────────────────────
    caption_text = message.caption or message.text or ""
    matched_word = contains_blacklisted(caption_text)
    if matched_word:
        owner_id = partner.get("owner_id")
        if owner_id:
            should_notify = get_notif_setting(owner_id, "blacklist_notif", True)
            if should_notify:
                try:
                    await client.send_message(
                        owner_id,
                        f"🚫 **Postingan ditolak — kata terlarang**\n\n"
                        f"📡 **{partner.get('channel_name')}**\n"
                        f"⚠️ Kata: `{matched_word}`\n\n"
                        f"Postingan tidak diteruskan ke channel utama.",
                    )
                except Exception:
                    pass
        log_activity("blacklist_blocked", channel_id, {"word": matched_word})
        return

    # FIX: Guard duplikasi — jika post ini sudah pernah di-repost, skip
    if get_post(channel_id, message.id):
        log.debug(f"[repost] Skip duplikat dari {channel_id} msg {message.id}")
        return

    post_number = count_posts_by_partner(channel_id) + 1

    # Ambil info bot dari sistem (bukan dari env)
    me = await client.get_me()
    bot_name_real  = me.first_name or me.username or "Bot"
    bot_uname_real = me.username or ""

    # Ambil invite_link dari DB; kalau belum ada, generate sekarang
    invite_link = partner.get("invite_link", "")
    if not invite_link:
        invite_link = await _get_or_create_invite_link(client, channel_id)

    cap = build_caption(
        original_caption = caption_text,
        channel_title    = partner.get("channel_name", message.chat.title),
        invite_link      = invite_link,
        owner_name       = partner.get("owner_name", "Unknown"),
        owner_id         = partner.get("owner_id", 0),
        post_number      = post_number,
        bot_name         = bot_name_real,
        bot_username     = bot_uname_real,
    )

    # ── Cek tipe pesan ────────────────────────────────────
    is_media     = bool(message.photo or message.video)
    is_text_only = bool(message.text and not is_media)

    # Jika pesan teks murni, cek setting allow_text_repost
    if is_text_only:
        allow_text = get_bot_setting("allow_text_repost", True)
        if not allow_text:
            return

    # Jika bukan media dan bukan teks murni, abaikan
    if not is_media and not is_text_only:
        return

    uname = partner.get("username", "")
    if uname:
        original_url = f"https://t.me/{uname}/{message.id}"
    else:
        cid_str      = str(channel_id).replace("-100", "")
        original_url = f"https://t.me/c/{cid_str}/{message.id}"

    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 Lihat Post Asli", url=original_url)
    ]])

    # Kirim manual (bukan message.copy) agar bisa kontrol tanpa web preview.
    # Message.copy() di Pyrogram 2.x tidak support disable_web_page_preview.
    if message.photo:
        sent = await safe_send(
            client.send_photo(
                chat_id      = MAIN_CHANNEL_ID,
                photo        = message.photo.file_id,
                caption      = cap,
                parse_mode   = PM,
                reply_markup = btn,
            )
        )
    elif message.video:
        sent = await safe_send(
            client.send_video(
                chat_id      = MAIN_CHANNEL_ID,
                video        = message.video.file_id,
                caption      = cap,
                duration     = message.video.duration,
                width        = message.video.width,
                height       = message.video.height,
                thumb        = message.video.thumbs[0].file_id if message.video.thumbs else None,
                parse_mode   = PM,
                reply_markup = btn,
                supports_streaming = True,
            )
        )
    elif is_text_only:
        sent = await safe_send(
            client.send_message(
                chat_id                  = MAIN_CHANNEL_ID,
                text                     = cap,
                parse_mode               = PM,
                reply_markup             = btn,
                disable_web_page_preview = True,
            )
        )
    else:
        sent = None

    if sent:
        save_post(channel_id, message.id, sent.id)
        increment_partner_posts(channel_id)
        log_activity("repost_success", channel_id, {"main_msg_id": sent.id})

        # Lazy check: setiap ada post baru, sekalian cek post lama channel ini
        asyncio.ensure_future(_safe_task(_lazy_check_channel(client, channel_id)))

        owner_id = partner.get("owner_id")
        if owner_id:
            should_notify = get_notif_setting(owner_id, "repost_notif", True)
            if should_notify:
                main_id_str = str(MAIN_CHANNEL_ID).replace("-100", "")
                try:
                    await client.send_message(
                        owner_id,
                        f"✅ **Postingan berhasil di-repost!**\n\n"
                        f"📡 **{partner.get('channel_name')}**\n"
                        f"📦 Repost ke-{post_number}\n"
                        f"🔗 [Lihat di channel utama]"
                        f"(https://t.me/c/{main_id_str}/{sent.id})",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    log.debug(f"[repost] Gagal kirim notif ke {owner_id}: {e}")
    else:
        log.warning(f"[repost] Gagal repost dari {channel_id} msg {message.id}")
        log_activity("repost_fail", channel_id)


# ═══════════════════════════════════════════════════════════
#  HAPUS REPOST — dua lapisan: raw update + polling backup
# ═══════════════════════════════════════════════════════════

@Client.on_raw_update()
async def on_raw_delete(client: Client, update, users, chats):
    # Tetap ada sebagai lapisan pertama — bekerja jika Telegram suatu saat kirim event ini
    if not isinstance(update, raw.types.UpdateDeleteChannelMessages):
        return
    raw_channel_id = update.channel_id
    channel_id     = int(f"-100{raw_channel_id}")
    log.info(f"[raw_delete] channel={channel_id} msgs={update.messages}")
    await _process_deleted(client, channel_id, update.messages)


async def _lazy_check_channel(client: Client, channel_id: int):
    """
    Dipanggil saat ada post baru dari channel_id.
    Cek max 10 post lama dari channel ini — kalau sudah dihapus, hapus repostnya.
    Tidak agresif: hanya jalan saat ada aktivitas di channel tersebut.
    """
    from db.helpers import get_recent_posts_by_partner
    old_posts = get_recent_posts_by_partner(channel_id, limit=10)
    if not old_posts:
        return
    for post in old_posts:
        try:
            msg = await client.get_messages(channel_id, post["partner_msg_id"])
            if msg is None or msg.empty:
                log.info(f"[lazy_check] Post {post['partner_msg_id']} sudah dihapus → hapus repost")
                await _process_deleted(client, channel_id, [post["partner_msg_id"]])
        except Exception:
            # Tidak bisa akses → anggap sudah dihapus
            await _process_deleted(client, channel_id, [post["partner_msg_id"]])
        await asyncio.sleep(0.3)


async def _process_deleted(client, channel_id: int, msg_ids: list):
    """Cek DB dan hapus repost di channel utama untuk setiap msg_id yang dihapus.
    Hanya berjalan jika setting 'auto_delete_repost' aktif.
    """
    if not get_bot_setting("auto_delete_repost", True):
        return
    for msg_id in msg_ids:
        post = get_post(channel_id, msg_id)
        if not post:
            continue
        ok = await safe_delete(client, MAIN_CHANNEL_ID, post["main_msg_id"])
        if ok:
            log.info(f"[delete_repost] ✅ main_msg_id={post['main_msg_id']} "
                     f"dihapus (partner={channel_id} msg={msg_id})")
            log_activity("repost_deleted", channel_id, {"main_msg_id": post["main_msg_id"]})
        else:
            log.warning(f"[delete_repost] ❌ Gagal hapus main_msg_id={post['main_msg_id']}")
        delete_post(channel_id, msg_id)



# ═══════════════════════════════════════════════════════════
#  SCHEDULER — UPDATE OWNER NAME HARIAN (jam 00:00 UTC)
# ═══════════════════════════════════════════════════════════

async def _update_owner_names(client: Client):
    """
    Iterasi semua partner channel, ambil nama terbaru owner dari Telegram,
    bandingkan dengan DB — jika berubah, simpan.

    Berjalan lambat tapi aman:
    - 3 detik antar request normal
    - Jika kena FloodWait, tunggu sesuai nilai + 5 detik
    - Error lain (user privasi, deactivated dll) → skip diam-diam
    """
    partners = get_all_partners()
    if not partners:
        return

    log.info(f"[owner_name_sync] Mulai sync {len(partners)} partner(s)...")
    updated = 0

    for p in partners:
        owner_id = p.get("owner_id")
        if not owner_id:
            await asyncio.sleep(3)
            continue

        try:
            user = await client.get_users(owner_id)
            new_name = (user.first_name or "").strip()
            if user.last_name:
                new_name = f"{new_name} {user.last_name}".strip()
            if not new_name:
                new_name = user.username or "Unknown"

            old_name = p.get("owner_name", "")
            if new_name != old_name:
                upsert_partner(p["_id"], {"owner_name": new_name})
                log.info(
                    f"[owner_name_sync] channel={p['_id']} "
                    f"'{old_name}' → '{new_name}'"
                )
                updated += 1

        except FloodWait as e:
            wait = e.value + 5
            log.warning(f"[owner_name_sync] FloodWait {wait}s, menunggu...")
            await asyncio.sleep(wait)
            # Jangan skip — coba lagi di iterasi berikutnya (next run)
        except Exception as e:
            log.debug(f"[owner_name_sync] Skip owner_id={owner_id}: {e}")

        # Jeda aman antar request
        await asyncio.sleep(3)

    log.info(f"[owner_name_sync] Selesai — {updated} nama diperbarui.")


async def _schedule_midnight_owner_sync(client: Client):
    """
    Loop selamanya: tunggu sampai jam 00:00 UTC berikutnya, lalu jalankan sync.
    Menggunakan waktu nyata (bukan interval tetap) agar tidak drift.
    """
    while True:
        now  = datetime.now(timezone.utc)
        # Tengah malam UTC berikutnya
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_seconds = (next_midnight - now).total_seconds()
        log.info(
            f"[owner_name_sync] Sync berikutnya dalam "
            f"{int(wait_seconds // 3600)}j "
            f"{int((wait_seconds % 3600) // 60)}m"
        )
        await asyncio.sleep(wait_seconds)
        try:
            await _update_owner_names(client)
        except Exception as e:
            log.error(f"[owner_name_sync] Error tak terduga: {e}")


async def start_owner_name_scheduler(client: Client):
    """Dipanggil sekali saat bot start dari main.py."""
    _ensure_bg_task(_schedule_midnight_owner_sync(client))
    log.info("[owner_name_sync] Scheduler diaktifkan.")
