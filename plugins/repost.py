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
from config import MAIN_CHANNEL_ID, MAIN_CHANNEL_USERNAME
from db.helpers import (
    get_partner, upsert_partner, save_post, get_post, delete_post
)
from datetime import datetime, timezone

def build_caption(original_caption: str, channel_title: str,
                  channel_username: str, owner_name: str, post_id: int) -> str:
    now  = datetime.now(timezone.utc)
    date = now.strftime("%d %b %Y")
    time = now.strftime("%H:%M UTC")
    uname = f"@{channel_username}" if channel_username else "—"

    cap = f"""**{channel_title}**  {uname}

{original_caption or ""}

━━━━━━━━━━━━━━━━━━━━
👤  **Owner**  :  {owner_name}
📅  **Tanggal** :  {date}
🕒  **Jam**     :  {time}
🆔  **Post ID** :  `{post_id}`
━━━━━━━━━━━━━━━━━━━━
🔁  _via FessBot_"""
    return cap.strip()

# ── Bot dijadikan admin di channel baru ───────────────────
@Client.on_my_chat_member()
async def on_bot_admin(client: Client, update: ChatMemberUpdated):
    """Tangkap saat bot di-promote jadi admin di sebuah channel."""
    if update.chat.type != ChatType.CHANNEL:
        return

    new_status = update.new_chat_member.status
    old_status = update.old_chat_member.status if update.old_chat_member else None

    channel_id = update.chat.id

    # Bot baru dijadikan admin
    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        if old_status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            inviter    = update.from_user
            owner_id   = inviter.id if inviter else 0
            owner_name = inviter.first_name if inviter else "Unknown"

            upsert_partner(channel_id, {
                "owner_id":      owner_id,
                "owner_name":    owner_name,
                "channel_name":  update.chat.title,
                "username":      update.chat.username or "",
                "paused":        False,
                "reason":        "",
                "added_at":      datetime.utcnow()
            })

            # Notif ke user
            if inviter:
                try:
                    await client.send_message(
                        owner_id,
                        f"✅ **Channel terdaftar sebagai partner!**\n\n"
                        f"📡 **{update.chat.title}** kini terhubung ke channel utama.\n"
                        f"Setiap foto/video yang kamu post akan diteruskan secara otomatis.\n\n"
                        f"Gunakan tombol **My Channel** di menu bot untuk mengatur channel kamu.",
                    )
                except Exception:
                    pass

    # Bot dikeluarkan / dicopot admin
    elif new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        # Tandai sebagai paused tapi jangan hapus riwayat
        existing = get_partner(channel_id)
        if existing:
            upsert_partner(channel_id, {"paused": True, "reason": "Bot dicopot dari admin channel"})

# ── Repost dari channel partner ───────────────────────────
@Client.on_message(filters.channel & (filters.photo | filters.video))
async def repost(client: Client, message: Message):
    channel_id = message.chat.id
    partner    = get_partner(channel_id)

    if not partner:
        return
    if partner.get("paused"):
        return

    caption = build_caption(
        original_caption = message.caption or "",
        channel_title    = partner.get("channel_name", message.chat.title),
        channel_username = partner.get("username", ""),
        owner_name       = partner.get("owner_name", "Unknown"),
        post_id          = message.id
    )

    chan_uname = partner.get("username", "")
    if chan_uname:
        original_url = f"https://t.me/{chan_uname}/{message.id}"
    else:
        # Channel private: gunakan format t.me/c/
        cid_str      = str(channel_id).replace("-100", "")
        original_url = f"https://t.me/c/{cid_str}/{message.id}"

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Lihat Postingan Asli", url=original_url)]
    ])

    try:
        sent = await message.copy(
            MAIN_CHANNEL_ID,
            caption   = caption,
            reply_markup = btn
        )
        save_post(channel_id, message.id, sent.id)
    except Exception as e:
        print(f"[repost] Gagal copy ke main channel: {e}")

# ── Hapus repost jika postingan asli dihapus ──────────────
@Client.on_deleted_messages(filters.channel)
async def delete_repost(client: Client, messages):
    for msg in messages:
        # messages bisa berupa list of Message atau Message tunggal
        channel_id = getattr(msg.chat, "id", None) if hasattr(msg, "chat") and msg.chat else None
        if not channel_id:
            continue
        post = get_post(channel_id, msg.id)
        if post:
            try:
                await client.delete_messages(MAIN_CHANNEL_ID, post["main_msg_id"])
            except Exception:
                pass
            delete_post(channel_id, msg.id)
