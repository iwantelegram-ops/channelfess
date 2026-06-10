"""
Auto-repost dari channel partner ke channel utama.
Deteksi bot dijadikan admin → daftarkan sebagai partner.
"""
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.enums import ChatMemberStatus, ChatType
from config import MAIN_CHANNEL_ID
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post
)
from datetime import datetime, timezone


def build_caption(original_caption, channel_title, channel_username, owner_name, post_id):
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
🆔  **Post ID** :  `{post_id}`
━━━━━━━━━━━━━━━━━━━━
🔁  _via FessBot_""".strip()


# ── Deteksi bot dijadikan/dicopot admin di channel ────────
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
                "paused":       False,
                "reason":       "",
                "added_at":     datetime.utcnow()
            })

            if inviter:
                try:
                    await client.send_message(
                        owner_id,
                        f"✅ **Channel terdaftar sebagai partner!**\n\n"
                        f"📡 **{update.chat.title}** kini terhubung ke channel utama.\n"
                        f"Setiap foto/video yang kamu post akan diteruskan otomatis.\n\n"
                        f"Gunakan tombol **My Channel** di menu bot untuk mengatur channel kamu."
                    )
                except Exception:
                    pass

    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin channel"})


# ── /daftarkan — fallback manual jika event tidak tertangkap ──
@Client.on_message(filters.command("daftarkan") & filters.private)
async def cmd_daftarkan(client: Client, message: Message):
    """
    User forward pesan dari channelnya, bot akan cek apakah
    bot sudah jadi admin di channel tersebut, lalu daftarkan.

    Cara pakai: forward sembarang pesan dari channel kamu ke bot,
    lalu ketik /daftarkan
    """
    # Cek apakah user mereply sebuah forward dari channel
    reply = message.reply_to_message
    if not reply or not reply.forward_from_chat:
        await message.reply(
            "📋 **Cara mendaftarkan channel:**\n\n"
            "1. Buka channel kamu\n"
            "2. Forward (teruskan) salah satu postingan dari channel kamu ke chat ini\n"
            "3. Reply pesan forward itu dengan `/daftarkan`\n\n"
            "Bot akan otomatis mengecek dan mendaftarkan channel kamu."
        )
        return

    chat = reply.forward_from_chat
    if chat.type != ChatType.CHANNEL:
        await message.reply("❌ Pesan yang di-forward harus berasal dari channel, bukan grup.")
        return

    channel_id = chat.id
    user_id    = message.from_user.id

    # Verifikasi bot sudah jadi admin di channel tersebut
    try:
        me      = await client.get_me()
        member  = await client.get_chat_member(channel_id, me.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply(
                f"❌ Bot belum dijadikan **admin** di channel **{chat.title}**.\n\n"
                f"Jadikan bot admin dulu, lalu ulangi langkah ini."
            )
            return
    except Exception as e:
        await message.reply(
            f"❌ Bot tidak bisa mengakses channel **{chat.title}**.\n"
            f"Pastikan bot sudah dijadikan admin.\n\nError: `{e}`"
        )
        return

    # Verifikasi user adalah admin/owner channel tersebut
    try:
        user_member = await client.get_chat_member(channel_id, user_id)
        if user_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await message.reply("❌ Kamu harus menjadi admin channel tersebut untuk mendaftarkannya.")
            return
    except Exception:
        await message.reply("❌ Tidak bisa memverifikasi status kamu di channel tersebut.")
        return

    # Daftarkan
    upsert_partner(channel_id, {
        "owner_id":     user_id,
        "owner_name":   message.from_user.first_name or "Unknown",
        "channel_name": chat.title,
        "username":     chat.username or "",
        "paused":       False,
        "reason":       "",
        "added_at":     datetime.utcnow()
    })

    await message.reply(
        f"✅ **Channel berhasil didaftarkan!**\n\n"
        f"📡 **{chat.title}** kini terhubung ke channel utama.\n"
        f"Setiap foto/video yang kamu post akan diteruskan otomatis.\n\n"
        f"Gunakan tombol **My Channel** untuk mengatur channel kamu."
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
        post_id          = message.id
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

    try:
        sent = await message.copy(MAIN_CHANNEL_ID, caption=caption, reply_markup=btn)
        save_post(channel_id, message.id, sent.id)
    except Exception as e:
        print(f"[repost] Gagal: {e}")


# ── Hapus repost jika postingan asli dihapus ──────────────
@Client.on_deleted_messages(filters.channel)
async def delete_repost(client: Client, messages):
    for msg in messages:
        channel_id = getattr(getattr(msg, "chat", None), "id", None)
        if not channel_id:
            continue
        post = get_post(channel_id, msg.id)
        if post:
            try:
                await client.delete_messages(MAIN_CHANNEL_ID, post["main_msg_id"])
            except Exception:
                pass
            delete_post(channel_id, msg.id)
