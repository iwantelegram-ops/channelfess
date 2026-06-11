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
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import FloodWait, ChatWriteForbidden, PeerIdInvalid
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post,
    increment_partner_posts, contains_blacklisted, count_posts_by_partner,
    get_notif_setting, log_activity,
)
from utils import safe_send, safe_delete, answer_cb

log = logging.getLogger("fessbot.repost")
PM  = ParseMode.MARKDOWN


# ═══════════════════════════════════════════════════════════
#  CAPTION BUILDER — JANGAN DIUBAH (sesuai permintaan owner)
# ═══════════════════════════════════════════════════════════

def build_caption(original_caption, channel_title, channel_username,
                  owner_name, post_number, bot_username):
    now  = datetime.now(timezone.utc)
    date = now.strftime("%d %b %Y")
    time = now.strftime("%H:%M UTC")

    if channel_username:
        ch_link = f"**{channel_title}** (@{channel_username})"
    else:
        ch_link = f"**{channel_title}**"

    cap = f"{ch_link}\n"
    if original_caption:
        cap += f"\n{original_caption}\n"
    cap += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"👤  Owner   :  {owner_name}\n"
        f"📅  Tanggal :  {date}\n"
        f"🕒  Jam     :  {time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔁  via @{bot_username}"
    )
    return cap.strip()


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

            upsert_partner(channel_id, {
                "owner_id":     owner_id,
                "owner_name":   owner_name,
                "channel_name": update.chat.title,
                "username":     update.chat.username or "",
                "paused":       True,
                "reason":       "Menunggu konfirmasi owner",
                "added_at":     datetime.now(timezone.utc),
                "total_posts":  0,
            })
            log_activity("partner_added", channel_id, {"owner_id": owner_id})
            log.info(f"[admin_change] Channel terdaftar: {update.chat.title} ({channel_id})")

            if inviter:
                await safe_send(client.send_message(
                    owner_id,
                    f"🎉 **Channel berhasil terhubung!**\n\n"
                    f"📡 **{update.chat.title}** sudah terdaftar di FessBot.\n\n"
                    f"Aktifkan sekarang agar postinganmu mulai di-repost ke channel utama?",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Aktifkan", callback_data=f"confirm_sync_{channel_id}"),
                        InlineKeyboardButton("Nanti aja",  callback_data=f"confirm_nosync_{channel_id}"),
                    ]]),
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
                f"▶️ **Sinkronisasi aktif!**\n\n"
                f"📡 **{partner.get('channel_name', channel_id)}** kini meneruskan "
                f"postingan ke channel utama. 🚀\n\n"
                f"Buka **My Channel** untuk kelola kapan saja.",
                reply_markup=InlineKeyboardMarkup([]),
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
                f"⏸ **Oke, disimpan dulu.**\n\n"
                f"📡 **{partner.get('channel_name', channel_id)}** terdaftar tapi belum aktif.\n"
                f"Aktifkan lewat **My Channel** kapan saja.",
                reply_markup=InlineKeyboardMarkup([]),
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

    upsert_partner(channel_id, {
        "owner_id":     user_id,
        "owner_name":   message.from_user.first_name or "Unknown",
        "channel_name": chat.title,
        "username":     chat.username or "",
        "paused":       True,
        "reason":       "Menunggu konfirmasi owner",
        "added_at":     datetime.now(timezone.utc),
        "total_posts":  0,
    })
    log_activity("partner_manual_add", channel_id, {"owner_id": user_id})

    await message.reply(
        f"🎉 **Channel terdaftar!**\n\n📡 **{chat.title}**\n\nAktifkan sekarang?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aktifkan", callback_data=f"confirm_sync_{channel_id}"),
            InlineKeyboardButton("Nanti aja",  callback_data=f"confirm_nosync_{channel_id}"),
        ]]),
    )


# ═══════════════════════════════════════════════════════════
#  REPOST — foto, video, dokumen, audio, teks
# ═══════════════════════════════════════════════════════════

MEDIA_FILTER = (filters.photo | filters.video)


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

    post_number = count_posts_by_partner(channel_id) + 1
    cap = build_caption(
        original_caption = caption_text,
        channel_title    = partner.get("channel_name", message.chat.title),
        channel_username = partner.get("username", ""),
        owner_name       = partner.get("owner_name", "Unknown"),
        post_number      = post_number,
        bot_username     = BOT_USERNAME,
    )

    # Hanya proses foto atau video (dengan atau tanpa caption)
    if not (message.photo or message.video):
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

    sent = await safe_send(
        message.copy(MAIN_CHANNEL_ID, caption=cap, reply_markup=btn, parse_mode=PM)
    )

    if sent:
        save_post(channel_id, message.id, sent.id)
        increment_partner_posts(channel_id)
        log_activity("repost_success", channel_id, {"main_msg_id": sent.id})

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
#  HAPUS REPOST JIKA POST ASLI DIHAPUS
# ═══════════════════════════════════════════════════════════

@Client.on_deleted_messages(filters.channel)
async def delete_repost(client: Client, messages):
    # Pyrogram DeletedMessages: msg.chat bisa None di beberapa versi.
    # Strategi: cari channel_id dari chat attribute, atau fallback ke
    # query MongoDB berdasarkan msg.id saja (cari semua partner yang punya post itu).
    for msg in messages:
        msg_id = msg.id

        # Coba dapat channel_id dari msg.chat
        channel_id = getattr(getattr(msg, "chat", None), "id", None)

        if channel_id:
            # Jalur normal: channel_id diketahui
            post = get_post(channel_id, msg_id)
            if post:
                ok = await safe_delete(client, MAIN_CHANNEL_ID, post["main_msg_id"])
                if ok:
                    log_activity("repost_deleted", channel_id, {"main_msg_id": post["main_msg_id"]})
                delete_post(channel_id, msg_id)
        else:
            # Fallback: channel_id tidak diketahui — cari di semua post dengan msg_id ini
            from db.helpers import get_posts_by_msg_id
            matched = get_posts_by_msg_id(msg_id)
            for post in matched:
                ok = await safe_delete(client, MAIN_CHANNEL_ID, post["main_msg_id"])
                if ok:
                    log_activity("repost_deleted", post["partner_id"], {"main_msg_id": post["main_msg_id"]})
                delete_post(post["partner_id"], msg_id)
