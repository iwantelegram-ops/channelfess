"""
Auto-repost dari channel partner ke channel utama.
Deteksi bot dijadikan admin → daftarkan sebagai partner.
FloodWait ditangani dengan asyncio.sleep otomatis.
"""
import asyncio
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, MessageNotModified, ChatWriteForbidden
from config import MAIN_CHANNEL_ID, BOT_USERNAME
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post
)
from datetime import datetime, timezone


def build_caption(original_caption, channel_title, channel_username, owner_name):
    now   = datetime.now(timezone.utc)
    date  = now.strftime("%d %b %Y")
    time  = now.strftime("%H:%M UTC")
    uname = f"@{channel_username}" if channel_username else "—"

    return f"""**{channel_title}**  {uname}

{original_caption or ""}

━━━━━━━━━━━━━━━━━━━━
👤  **Owner**   :  {owner_name}
📅  **Tanggal** :  {date}
🕒  **Jam**     :  {time}
━━━━━━━━━━━━━━━━━━━━
🔁  [via {BOT_USERNAME}](https://t.me/{BOT_USERNAME}?start=start)""".strip()


async def safe_send(coro, retries=3):
    """Jalankan coroutine Telegram dengan penanganan FloodWait otomatis."""
    for attempt in range(retries):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value + 2  # tambah buffer 2 detik
            print(f"[FloodWait] Tunggu {wait}s (percobaan {attempt+1}/{retries})")
            await asyncio.sleep(wait)
        except (ChatWriteForbidden, Exception) as e:
            print(f"[safe_send] Error: {e}")
            return None
    return None


# ── Deteksi bot dijadikan admin di channel ────────────────
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
                "added_at":     datetime.utcnow()
            })

            if inviter:
                await safe_send(client.send_message(
                    owner_id,
                    f"🎉 **Channel berhasil ditambahkan!**\n\n"
                    f"📡 **{update.chat.title}** sudah terhubung ke bot.\n\n"
                    f"Apakah kamu ingin mulai meneruskan postingan dari channel ini ke channel utama?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Sinkron", callback_data=f"confirm_sync_{channel_id}"),
                            InlineKeyboardButton("❌ Tidak",   callback_data=f"confirm_nosync_{channel_id}")
                        ]
                    ])
                ))

    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin channel"})


# ── Callback konfirmasi sinkron ───────────────────────────
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
        f"✅ **Sinkronisasi aktif!**\n\n"
        f"📡 **{ch_name}** kini meneruskan postingan ke channel utama secara otomatis.\n\n"
        f"Gunakan tombol **My Channel** untuk mengatur channel kamu kapan saja."
    ))
    await cb.answer("Sinkron diaktifkan!")


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
        f"⏸ **Sinkronisasi tidak diaktifkan.**\n\n"
        f"📡 **{ch_name}** terdaftar tapi tidak meneruskan postingan.\n\n"
        f"Kamu bisa mengaktifkannya kapan saja lewat tombol **My Channel**."
    ))
    await cb.answer("Oke, bisa diaktifkan nanti.")


# ── /daftarkan — fallback manual ──────────────────────────
@Client.on_message(filters.command("daftarkan") & filters.private)
async def cmd_daftarkan(client: Client, message: Message):
    reply = message.reply_to_message
    if not reply or not reply.forward_from_chat:
        await message.reply(
            "📋 **Cara mendaftarkan channel secara manual:**\n\n"
            "1. Buka channel kamu\n"
            "2. Forward salah satu postingan dari channel kamu ke sini\n"
            "3. Reply pesan forward itu dengan `/daftarkan`"
        )
        return

    chat = reply.forward_from_chat
    if chat.type != ChatType.CHANNEL:
        await message.reply("❌ Pesan yang di-forward harus berasal dari channel.")
        return

    channel_id = chat.id
    user_id    = message.from_user.id

    try:
        me     = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply(f"❌ Bot belum dijadikan admin di **{chat.title}**.")
            return
    except FloodWait as e:
        await asyncio.sleep(e.value + 2)
        await message.reply("⚠️ Terkena rate limit, coba lagi sebentar.")
        return
    except Exception as e:
        await message.reply(f"❌ Bot tidak bisa mengakses channel ini.\n`{e}`")
        return

    try:
        user_member = await client.get_chat_member(channel_id, user_id)
        if user_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply("❌ Kamu harus admin channel tersebut.")
            return
    except Exception:
        await message.reply("❌ Tidak bisa memverifikasi status kamu di channel tersebut.")
        return

    upsert_partner(channel_id, {
        "owner_id":     user_id,
        "owner_name":   message.from_user.first_name or "Unknown",
        "channel_name": chat.title,
        "username":     chat.username or "",
        "paused":       True,
        "reason":       "Menunggu konfirmasi owner",
        "added_at":     datetime.utcnow()
    })

    await message.reply(
        f"🎉 **Channel berhasil ditambahkan!**\n\n"
        f"📡 **{chat.title}** sudah terhubung ke bot.\n\n"
        f"Apakah kamu ingin mulai meneruskan postingan ke channel utama?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sinkron", callback_data=f"confirm_sync_{channel_id}"),
                InlineKeyboardButton("❌ Tidak",   callback_data=f"confirm_nosync_{channel_id}")
            ]
        ])
    )


# ── Repost foto/video dari channel partner ────────────────
@Client.on_message(filters.channel & (filters.photo | filters.video))
async def repost(client: Client, message: Message):
    channel_id = message.chat.id
    partner    = get_partner(channel_id)

    if not partner or partner.get("paused"):
        return

    caption = build_caption(
        original_caption = message.caption or "",
        channel_title    = partner.get("channel_name", message.chat.title),
        channel_username = partner.get("username", ""),
        owner_name       = partner.get("owner_name", "Unknown"),
    )

    uname = partner.get("username", "")
    if uname:
        original_url = f"https://t.me/{uname}/{message.id}"
    else:
        cid_str      = str(channel_id).replace("-100", "")
        original_url = f"https://t.me/c/{cid_str}/{message.id}"

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Lihat Postingan Asli", url=original_url)]
    ])

    sent = await safe_send(message.copy(MAIN_CHANNEL_ID, caption=caption, reply_markup=btn))
    if sent:
        save_post(channel_id, message.id, sent.id)


# ── Hapus repost jika postingan asli dihapus ──────────────
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
