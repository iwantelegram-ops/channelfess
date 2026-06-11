"""
Auto-repost dari channel partner ke channel utama.
- Deteksi bot jadi admin → daftarkan partner
- Blacklist kata otomatis
- Media filter per channel (photo/video/text/all)
- FloodWait handling dengan exponential backoff
- Notifikasi ke owner channel
- Counter total_posts per partner
- Auto-hapus repost jika post asli dihapus (lazy check + raw update)
- Log aktivitas ke MongoDB
- Caption template kustom dari MongoDB
- Support foto, video, teks
"""
import asyncio
import logging
from datetime import datetime, timezone

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
    get_recent_posts_by_partner, get_caption_template,
)
from utils import safe_send, safe_delete, answer_cb

log = logging.getLogger("fessbot.repost")
PM  = ParseMode.MARKDOWN


# ═══════════════════════════════════════════════════════════
#  CAPTION BUILDER — menggunakan template dari MongoDB
# ═══════════════════════════════════════════════════════════

def build_caption(original_caption, channel_title, invite_link,
                  owner_name, owner_id, post_number, bot_name, bot_username):
    now  = datetime.now(timezone.utc)
    date = now.strftime("%d %b %Y")
    time = now.strftime("%H:%M UTC")

    ch_link   = f"[{channel_title}]({invite_link})" if invite_link else f"**{channel_title}**"
    owner_link = f"[{owner_name}](tg://user?id={owner_id})"
    bot_link   = f"[{bot_name}](https://t.me/{bot_username}?start=start)"

    template = get_caption_template()

    cap = template.format(
        channel_link      = ch_link,
        original_caption  = original_caption.strip() if original_caption else "",
        owner_link        = owner_link,
        date              = date,
        time              = time,
        bot_link          = bot_link,
        post_number       = post_number,
        channel_title     = channel_title,
        owner_name        = owner_name,
    )

    if not original_caption and "{original_caption}" in template:
        cap = cap.replace("\n\n\n", "\n\n")

    return cap.strip()


# ═══════════════════════════════════════════════════════════
#  HELPER — INVITE LINK
# ═══════════════════════════════════════════════════════════

async def _get_or_create_invite_link(client: Client, channel_id: int) -> str:
    partner = get_partner(channel_id)
    if partner and partner.get("invite_link"):
        return partner["invite_link"]

    _NO_PERM = (ChatAdminRequired, ChatWriteForbidden, ChannelPrivate, UserNotParticipant)
    try:
        link = await client.export_chat_invite_link(channel_id)
        if link:
            upsert_partner(channel_id, {"invite_link": link})
            return link
    except _NO_PERM:
        log.debug(f"[invite_link] Tidak ada izin untuk {channel_id}")
    except FloodWait as e:
        log.warning(f"[invite_link] FloodWait {e.value}s, skip")
    except Exception as e:
        log.warning(f"[invite_link] Gagal untuk {channel_id}: {e}")
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
    old_status = update.old_chat_member.status if update.old_chat_member else None

    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        if old_status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            inviter    = update.from_user
            owner_id   = inviter.id   if inviter else 0
            owner_name = inviter.first_name if inviter else "Unknown"

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
                "media_filter": "all",
            })
            log_activity("partner_added", channel_id, {"owner_id": owner_id})
            log.info(f"[admin_change] Channel terdaftar: {update.chat.title} ({channel_id})")

            try:
                await client.get_chat(channel_id)
            except Exception:
                pass

            if inviter:
                await safe_send(client.send_message(
                    owner_id,
                    f"🎉 **Channel berhasil terhubung!**\n\n"
                    f"📡 **{update.chat.title}** sudah terdaftar.\n\n"
                    f"Aktifkan sekarang agar postinganmu mulai di-repost?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Aktifkan Sekarang", callback_data=f"confirm_sync_{channel_id}")],
                        [InlineKeyboardButton("⏸ Nanti Saja",        callback_data=f"confirm_nosync_{channel_id}")],
                    ]),
                ))

    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin"})
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
                            f"Repost otomatis dihentikan. Tambahkan bot kembali sebagai admin untuk melanjutkan.",
                        )
                    except Exception as e:
                        log.warning(f"[on_bot_admin_change] Gagal notif ke {oid}: {e}")


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
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📂 My Channel", callback_data="user_channels_0")
                ]]),
            )
        except Exception:
            pass

        await answer_cb(cb, "✅ Aktif!")
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
                f"Aktifkan kapan saja di **My Channel**.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📂 My Channel", callback_data="user_channels_0")
                ]]),
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
            "`2.` Reply pesan forward itu dengan `/daftarkan`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📂 My Channel", callback_data="user_channels_0")
            ]]),
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
    except Exception as e:
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
        "media_filter": "all",
    })
    log_activity("partner_manual_add", channel_id, {"owner_id": user_id})

    await message.reply(
        f"🎉 **Channel terdaftar!**\n\n📡 **{chat.title}**\n\nAktifkan sekarang?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Aktifkan Sekarang", callback_data=f"confirm_sync_{channel_id}")],
            [InlineKeyboardButton("⏸ Nanti Saja",             callback_data=f"confirm_nosync_{channel_id}")],
        ]),
    )


# ═══════════════════════════════════════════════════════════
#  REPOST — foto, video, teks
# ═══════════════════════════════════════════════════════════

MEDIA_FILTER = (filters.photo | filters.video | filters.text)


@Client.on_message(filters.channel & MEDIA_FILTER)
async def repost(client: Client, message: Message):
    channel_id = message.chat.id
    partner    = get_partner(channel_id)

    if not partner or partner.get("paused"):
        return

    # ── Media filter per channel ───────────────────────────
    mf          = partner.get("media_filter", "all")
    is_photo    = bool(message.photo)
    is_video    = bool(message.video)
    is_text_only = bool(message.text and not message.photo and not message.video)

    if mf == "photo" and not is_photo:
        return
    if mf == "video" and not is_video:
        return
    if mf == "text" and not is_text_only:
        return

    if not (is_photo or is_video or is_text_only):
        return

    # ── Teks murni — cek setting global ───────────────────
    if is_text_only:
        allow_text = get_bot_setting("allow_text_repost", True)
        if not allow_text:
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
                        f"⚠️ Kata: `{matched_word}`",
                    )
                except Exception:
                    pass
        log_activity("blacklist_blocked", channel_id, {"word": matched_word})
        return

    post_number = count_posts_by_partner(channel_id) + 1

    me             = await client.get_me()
    bot_name_real  = me.first_name or me.username or "Bot"
    bot_uname_real = me.username or ""

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

    # ── Buat link post asli ────────────────────────────────
    uname = partner.get("username", "")
    if uname:
        original_url = f"https://t.me/{uname}/{message.id}"
    else:
        cid_str      = str(channel_id).replace("-100", "")
        original_url = f"https://t.me/c/{cid_str}/{message.id}"

    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 Lihat Post Asli", url=original_url)
    ]])

    # ── Kirim ke channel utama ─────────────────────────────
    sent = None
    if is_photo:
        sent = await safe_send(
            client.send_photo(
                chat_id      = MAIN_CHANNEL_ID,
                photo        = message.photo.file_id,
                caption      = cap,
                parse_mode   = PM,
                reply_markup = btn,
            )
        )
    elif is_video:
        thumb = None
        if message.video.thumbs:
            thumb = message.video.thumbs[0].file_id
        sent = await safe_send(
            client.send_video(
                chat_id            = MAIN_CHANNEL_ID,
                video              = message.video.file_id,
                caption            = cap,
                duration           = message.video.duration,
                width              = message.video.width,
                height             = message.video.height,
                thumb              = thumb,
                parse_mode         = PM,
                reply_markup       = btn,
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

    if sent:
        save_post(channel_id, message.id, sent.id)
        increment_partner_posts(channel_id)
        log_activity("repost_success", channel_id, {"main_msg_id": sent.id})

        asyncio.create_task(_lazy_check_channel(client, channel_id))

        owner_id = partner.get("owner_id")
        if owner_id:
            should_notify = get_notif_setting(owner_id, "repost_notif", True)
            if should_notify:
                main_id_str = str(MAIN_CHANNEL_ID).replace("-100", "")
                try:
                    await client.send_message(
                        owner_id,
                        f"✅ **Repost berhasil!**\n\n"
                        f"📡 **{partner.get('channel_name')}**\n"
                        f"📦 Repost ke-{post_number}\n"
                        f"🔗 [Lihat di channel utama](https://t.me/c/{main_id_str}/{sent.id})",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    log.debug(f"[repost] Gagal notif ke {owner_id}: {e}")
    else:
        log.warning(f"[repost] Gagal repost dari {channel_id} msg {message.id}")
        log_activity("repost_fail", channel_id)


# ═══════════════════════════════════════════════════════════
#  HAPUS REPOST — raw update + lazy check
# ═══════════════════════════════════════════════════════════

@Client.on_raw_update()
async def on_raw_delete(client: Client, update, users, chats):
    if not isinstance(update, raw.types.UpdateDeleteChannelMessages):
        return
    raw_channel_id = update.channel_id
    channel_id     = int(f"-100{raw_channel_id}")
    log.info(f"[raw_delete] channel={channel_id} msgs={update.messages}")
    await _process_deleted(client, channel_id, update.messages)


async def _lazy_check_channel(client: Client, channel_id: int):
    """
    Cek max 10 post lama dari channel_id saat ada aktivitas baru.
    Jika sudah dihapus di channel asli → hapus repostnya.
    """
    old_posts = get_recent_posts_by_partner(channel_id, limit=10)
    if not old_posts:
        return
    for post in old_posts:
        try:
            msg = await client.get_messages(channel_id, post["partner_msg_id"])
            if msg is None or msg.empty:
                log.info(f"[lazy_check] Post {post['partner_msg_id']} sudah dihapus")
                await _process_deleted(client, channel_id, [post["partner_msg_id"]])
        except Exception:
            await _process_deleted(client, channel_id, [post["partner_msg_id"]])
        await asyncio.sleep(0.3)


async def _process_deleted(client, channel_id: int, msg_ids: list):
    if not get_bot_setting("auto_delete_repost", True):
        return
    for msg_id in msg_ids:
        post = get_post(channel_id, msg_id)
        if not post:
            continue
        ok = await safe_delete(client, MAIN_CHANNEL_ID, post["main_msg_id"])
        if ok:
            log.info(f"[delete_repost] ✅ main_msg_id={post['main_msg_id']} dihapus")
            log_activity("repost_deleted", channel_id, {"main_msg_id": post["main_msg_id"]})
            delete_post(channel_id, msg_id)
        else:
            log.warning(f"[delete_repost] ❌ Gagal hapus main_msg_id={post['main_msg_id']}")
