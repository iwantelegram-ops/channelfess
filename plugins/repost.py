"""
Auto-repost dari channel partner ke channel utama.
- Deteksi bot jadi admin → daftarkan partner
- Blacklist kata otomatis
- Notifikasi ke owner setiap repost
- Counter total_posts per partner
- FloodWait handling
"""
import asyncio
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, ChatWriteForbidden
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post,
    increment_partner_posts, contains_blacklisted, count_posts_by_partner
)


def build_caption(original_caption, channel_title, channel_username, owner_name, post_number):
    now   = datetime.now(timezone.utc)
    date  = now.strftime("%d %b %Y")
    time  = now.strftime("%H:%M UTC")
    uname = f"@{channel_username}" if channel_username else "—"

    cap = f"**{channel_title}**  {uname}\n"
    if original_caption:
        cap += f"\n{original_caption}\n"
    cap += (
        f"\n`───────────────────────`\n"
        f"👤 {owner_name}  ·  📅 {date}  ·  🕒 {time}\n"
        f"📦 Repost ke-{post_number} dari channel ini\n"
        f"`───────────────────────`"
    )
    return cap.strip()


async def safe_send(coro, retries=3):
    for attempt in range(retries):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value + 2
            print(f"[FloodWait] Tunggu {wait}s (percobaan {attempt+1}/{retries})")
            await asyncio.sleep(wait)
        except (ChatWriteForbidden, Exception) as e:
            print(f"[safe_send] Error: {e}")
            return None
    return None


# ── Deteksi bot dijadikan admin ───────────────────────────
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
            owner_id   = inviter.id if inviter else 0
            owner_name = inviter.first_name if inviter else "Unknown"

            upsert_partner(channel_id, {
                "owner_id":     owner_id,
                "owner_name":   owner_name,
                "channel_name": update.chat.title,
                "username":     update.chat.username or "",
                "paused":       True,
                "reason":       "Menunggu konfirmasi owner",
                "added_at":     datetime.utcnow(),
                "total_posts":  0,
            })

            if inviter:
                await safe_send(client.send_message(
                    owner_id,
                    f"🎉 **Channel berhasil terhubung!**\n\n"
                    f"📡 **{update.chat.title}** sudah terdaftar di FessBot.\n\n"
                    f"Aktifkan agar postinganmu mulai di-repost ke channel utama?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Aktifkan", callback_data=f"confirm_sync_{channel_id}"),
                            InlineKeyboardButton("Nanti aja", callback_data=f"confirm_nosync_{channel_id}")
                        ]
                    ])
                ))

    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin channel"})
            if oid := existing.get("owner_id"):
                try:
                    await client.send_message(
                        oid,
                        f"⚠️ **Bot dicopot dari admin channel.**\n\n"
                        f"📡 **{existing.get('channel_name')}**\n\n"
                        f"Repost otomatis dihentikan. Tambahkan bot kembali sebagai admin untuk melanjutkan."
                    )
                except Exception:
                    pass


# ── Konfirmasi sinkron ────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^confirm_sync_(-?\d+)$"))
async def cb_confirm_sync(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Channel tidak ditemukan.", show_alert=True)
        return

    upsert_partner(channel_id, {"paused": False, "reason": ""})
    ch_name = partner.get("channel_name", str(channel_id))

    await safe_send(cb.message.edit_text(
        f"▶️ **Sinkronisasi aktif!**\n\n"
        f"📡 **{ch_name}** kini meneruskan postingan ke channel utama. 🚀\n\n"
        f"Buka **My Channel** untuk ngatur kapan saja."
    ))
    await cb.answer("Aktif!", show_alert=False)


@Client.on_callback_query(filters.regex(r"^confirm_nosync_(-?\d+)$"))
async def cb_confirm_nosync(client, cb):
    channel_id = int(cb.matches[0].group(1))
    partner    = get_partner(channel_id)

    if not partner or partner.get("owner_id") != cb.from_user.id:
        await cb.answer("Channel tidak ditemukan.", show_alert=True)
        return

    ch_name = partner.get("channel_name", str(channel_id))
    upsert_partner(channel_id, {"paused": True, "reason": "Tidak diaktifkan oleh owner"})

    await safe_send(cb.message.edit_text(
        f"⏸ **Oke, disimpan dulu.**\n\n"
        f"📡 **{ch_name}** terdaftar tapi belum aktif.\n"
        f"Aktifkan lewat **My Channel** kapan saja."
    ))
    await cb.answer("Bisa diaktifkan nanti.", show_alert=False)


# ── /daftarkan fallback manual ────────────────────────────
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
        await asyncio.sleep(e.value + 2)
        await message.reply("⚠️ Rate limit, coba lagi sebentar.")
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
        await message.reply("❌ Tidak bisa verifikasi status kamu.")
        return

    upsert_partner(channel_id, {
        "owner_id":     user_id,
        "owner_name":   message.from_user.first_name or "Unknown",
        "channel_name": chat.title,
        "username":     chat.username or "",
        "paused":       True,
        "reason":       "Menunggu konfirmasi owner",
        "added_at":     datetime.utcnow(),
        "total_posts":  0,
    })

    await message.reply(
        f"🎉 **Channel terdaftar!**\n\n📡 **{chat.title}**\n\nAktifkan sekarang?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Aktifkan", callback_data=f"confirm_sync_{channel_id}"),
                InlineKeyboardButton("Nanti aja", callback_data=f"confirm_nosync_{channel_id}")
            ]
        ])
    )


# ── REPOST ────────────────────────────────────────────────
@Client.on_message(filters.channel & (filters.photo | filters.video))
async def repost(client: Client, message: Message):
    channel_id = message.chat.id
    partner    = get_partner(channel_id)

    if not partner or partner.get("paused"):
        return

    # Cek blacklist
    caption_text = message.caption or ""
    matched_word = contains_blacklisted(caption_text)
    if matched_word:
        owner_id = partner.get("owner_id")
        ch_name  = partner.get("channel_name", str(channel_id))
        if owner_id:
            try:
                await client.send_message(
                    owner_id,
                    f"🚫 **Postingan ditolak — blacklist**\n\n"
                    f"📡 **{ch_name}**\n"
                    f"⚠️ Kata terlarang ditemukan: `{matched_word}`\n\n"
                    f"Postingan ini tidak diteruskan ke channel utama."
                )
            except Exception:
                pass
        return

    post_number = count_posts_by_partner(channel_id) + 1

    cap = build_caption(
        original_caption = caption_text,
        channel_title    = partner.get("channel_name", message.chat.title),
        channel_username = partner.get("username", ""),
        owner_name       = partner.get("owner_name", "Unknown"),
        post_number      = post_number,
    )

    uname = partner.get("username", "")
    if uname:
        original_url = f"https://t.me/{uname}/{message.id}"
    else:
        cid_str      = str(channel_id).replace("-100", "")
        original_url = f"https://t.me/c/{cid_str}/{message.id}"

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Lihat Post Asli", url=original_url)]
    ])

    sent = await safe_send(message.copy(MAIN_CHANNEL_ID, caption=cap, reply_markup=btn))
    if sent:
        save_post(channel_id, message.id, sent.id)
        increment_partner_posts(channel_id)

        # Notifikasi ke owner channel
        owner_id = partner.get("owner_id")
        ch_name  = partner.get("channel_name", str(channel_id))
        if owner_id:
            try:
                await client.send_message(
                    owner_id,
                    f"✅ **Postingan berhasil di-repost!**\n\n"
                    f"📡 **{ch_name}**\n"
                    f"📦 Repost ke-{post_number}\n"
                    f"🔗 [Lihat di channel utama](https://t.me/c/{str(MAIN_CHANNEL_ID).replace('-100','')}/{sent.id})",
                    disable_web_page_preview=True
                )
            except Exception:
                pass


# ── Hapus repost jika asli dihapus ───────────────────────
@Client.on_deleted_messages(filters.channel)
async def delete_repost(client: Client, messages):
    for msg in messages:
        channel_id = getattr(getattr(msg, "chat", None), "id", None)
        if not channel_id:
            continue
        post = get_post(channel_id, msg.id)
        if post:
            await safe_send(client.delete_messages(MAIN_CHANNEL_ID, post["main_msg_id"]))
            delete_post(channel_id, msg.id)
