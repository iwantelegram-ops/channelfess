import os
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ChatMemberUpdated
from pyrogram.errors import UserNotParticipant
import database as db

MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID"))

# Decorator untuk cek Force Join
def cb_force_join(func):
    async def wrapper(client, message: Message):
        user_id = message.from_user.id
        try:
            member = await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
            if member.status in ["kicked", "left"]:
                raise UserNotParticipant
        except UserNotParticipant:
            ch_info = await client.get_chat(MAIN_CHANNEL_ID)
            invite_link = ch_info.invite_link or f"https://t.me/{ch_info.username}"
            await message.reply_text(
                "❌ **Akses Ditolak!**\n\nAnda harus bergabung ke Channel Utama terlebih dahulu sebelum menggunakan bot ini.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Gabung Channel", url=invite_link)]])
            )
            return
        return await func(client, message)
    return wrapper

# /start Command
@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    
    # Cek status join untuk tampilan menu awal
    try:
        await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
        # Jika sudah join, kasih tombol menu utama
        keyboard = ReplyKeyboardMarkup([[KeyboardButton("🗂 My Channel")], [KeyboardButton("ℹ️ Panduan")]], resize_keyboard=True)
        await message.reply_text(
            "👋 **Halo Partner!**\n\nBot siap digunakan. Tambahkan bot ke channel Anda sebagai admin untuk mulai meneruskan postingan.",
            reply_markup=keyboard
        )
    except UserNotParticipant:
        ch_info = await client.get_chat(MAIN_CHANNEL_ID)
        invite_link = ch_info.invite_link or f"https://t.me/{ch_info.username}"
        await message.reply_text(
            "👋 **Selamat Datang di Auto Forwarder Bot**\n\n"
            "Bot ini berfungsi untuk me-repost postingan foto/video dari channel Anda ke Channel Utama secara otomatis.\n\n"
            "⚠️ **Kunci Akses:** Anda wajib bergabung ke channel utama terlebih dahulu.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel Utama", url=invite_link)]])
        )

# Deteksi otomatis saat User Join ke Channel Utama (Chat Member Updated)
@Client.on_chat_member_updated()
async def welcome_new_member(client: Client, update: ChatMemberUpdated):
    if update.chat.id == MAIN_CHANNEL_ID and update.new_chat_member:
        user_id = update.new_chat_member.user.id
        if update.old_chat_member and update.old_chat_member.status in ["left", "kicked"]:
            bot_username = (await client.get_me()).username
            try:
                await client.send_message(
                    user_id,
                    "🎉 **Terima kasih telah bergabung di Channel Utama!**\n\n"
                    "**Cara Menautkan Channel Anda:**\n"
                    "1. Tambahkan bot ini ke Channel Anda sebagai Admin.\n"
                    "2. Berikan hak akses mengirim & menghapus pesan.\n"
                    "3. Postingan foto/video baru Anda akan otomatis diteruskan!\n\n"
                    "**Kelebihan:** Menaikkan impresi konten secara otomatis.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ Tambahkan Bot ke Channel", url=f"https://t.me/{bot_username}?startchannel=true&admin=post_messages+delete_messages")
                    ]])
                )
            except Exception:
                pass

# Deteksi Bot ditambahkan sebagai Admin di Channel Partner
@Client.on_chat_member_updated()
async def bot_added_as_admin(client: Client, update: ChatMemberUpdated):
    if update.new_chat_member and update.new_chat_member.user.is_self:
        if update.new_chat_member.status == "administrator":
            chat = update.chat
            # Mencari siapa yang menambahkan bot (dianggap owner channel oleh sistem bot)
            creator_id = None
            async for member in client.get_chat_members(chat.id, filter="administrators"):
                if member.status == "creator":
                    creator_id = member.user.id
                    break
            
            if creator_id:
                await db.add_channel(chat.id, chat.title, creator_id)
                try:
                    await client.send_message(creator_id, f"✅ Channel **{chat.title}** berhasil terdaftar sebagai **Channel Partner**!")
                except Exception:
                    pass

# Tombol "My Channel" dan Panduan via Bottom Buttons
@Client.on_message(filters.text & filters.private)
@cb_force_join
async def handle_text_buttons(client: Client, message: Message):
    user_id = message.from_user.id
    if message.text == "🗂 My Channel":
        channels = await db.get_user_channels(user_id)
        if not channels:
            return await message.reply_text("❌ Anda belum mengaitkan channel apapun.")
        
        for ch in channels:
            status_text = "🟢 Aktif (Meneruskan)" if ch["status"] == "active" else "🔴 Berhenti (Pause)"
            btn_text = "⏸ Pause" if ch["status"] == "active" else "▶️ Teruskan"
            callback_data = f"toggle_{ch['channel_id']}"
            
            await message.reply_text(
                f"📢 **Nama Channel:** {ch['title']}\n"
                f"🆔 **ID:** `{ch['channel_id']}`\n"
                f"📊 **Status:** {status_text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=callback_data)]])
            )
            
    elif message.text == "ℹ️ Panduan":
        await message.reply_text("📖 **Panduan Bot:**\n\nCukup jadikan bot sebagai admin di channel Anda. Pastikan bot memiliki hak kirim dan hapus pesan.")

# Handler untuk Klik Tombol Pause/Teruskan oleh User
@Client.on_callback_query(filters.regex(r"^toggle_"))
async def toggle_channel_user(client: Client, callback_query):
    ch_id = int(callback_query.data.split("_")[1])
    ch = await db.get_channel(ch_id)
    
    if ch["owner_id"] != callback_query.from_user.id:
        return await callback_query.answer("Akses ditolak!", show_alert=True)
        
    new_status = "paused" if ch["status"] == "active" else "active"
    await db.update_channel_status(ch_id, new_status)
    
    btn_text = "⏸ Pause" if new_status == "active" else "▶️ Teruskan"
    status_text = "🟢 Aktif (Meneruskan)" if new_status == "active" else "🔴 Berhenti (Pause)"
    
    await callback_query.message.edit_text(
        f"📢 **Nama Channel:** {ch['title']}\n"
        f"🆔 **ID:** `{ch['channel_id']}`\n"
        f"📊 **Status:** {status_text}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=callback_data)]])
    )
    await callback_query.answer("Status channel diperbarui.")

# --- INTI FORWARDER LOGIC ---
@Client.on_message((filters.photo | filters.video) & filters.channel)
async def auto_forwarder(client: Client, message: Message):
    ch_id = message.chat.id
    ch_data = await db.get_channel(ch_id)
    
    # Validasi jika channel partner terdaftar dan berstatus aktif
    if not ch_data or ch_data["status"] != "active":
        return

    # Ambil info owner channel partner
    try:
        owner_member = await client.get_chat_member(ch_id, ch_data["owner_id"])
        owner_name = owner_member.user.first_name
    except Exception:
        owner_name = "Undisclosed Owner"

    now = datetime.datetime.now()
    tanggal = now.strftime("%d-%m-%Y")
    jam = now.strftime("%H:%M WIB")
    
    caption_asli = message.caption if message.caption else ""
    post_link = f"https://t.me/c/{str(ch_id)[4:]}/{message.id}"
    
    # Desain Rapi, Minimalis, dan Detail sesuai permintaan
    caption_baru = (
        f"{caption_asli}\n\n"
        f"─── **DETAIL REPOST** ───\n"
        f"📢 **Partner:** {message.chat.title}\n"
        f"👤 **Owner:** {owner_name}\n"
        f"📆 **Tanggal:** `{tanggal}`\n"
        f"⏰ **Waktu:** `{jam}`\n"
        f"🆔 **Post ID:** `{message.id}`"
    )
    
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Lihat Postingan Asli", url=post_link)]])
    
    # Kirim ke channel utama
    if message.photo:
        sent_msg = await client.send_photo(MAIN_CHANNEL_ID, message.photo.file_id, caption=caption_baru, reply_markup=reply_markup)
    else:
        sent_msg = await client.send_video(MAIN_CHANNEL_ID, message.video.file_id, caption=caption_baru, reply_markup=reply_markup)
        
    # Simpan mapping ID ke MongoDB untuk fungsi hapus otomatis nanti
    await db.save_post_map(ch_id, message.id, sent_msg.id)

# --- DETEKSI HAPUS OTOMATIS ---
@Client.on_deleted_messages(filters.channel)
async def deleted_posts_handler(client: Client, messages):
    for msg in messages:
        main_msg_id = await db.get_main_msg_id(msg.chat.id, msg.id)
        if main_msg_id:
            try:
                await client.delete_messages(MAIN_CHANNEL_ID, main_msg_id)
            except Exception:
                pass
