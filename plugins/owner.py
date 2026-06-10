import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import database as db

OWNER_ID = int(os.getenv("OWNER_ID"))

# Filter Khusus Owner
def owner_filter(func):
    async def wrapper(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return
        return await func(client, message)
    return wrapper

@Client.on_message(filters.command("start") & filters.private)
async def owner_start(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    
    text = (
        "👑 **Halo Owner! Selamat Datang di Control Panel Bot**\n\n"
        "**Daftar Perintah Owner:**\n"
        "• `/pause [ID_CHANNEL] [Alasan]` - Hentikan paksa forward dari channel tertentu.\n"
        "• `/run [ID_CHANNEL] [Alasan]` - Jalankan kembali forward channel yang ditangguhkan.\n\n"
        "Gunakan tombol di bawah untuk melihat statistik channel partner."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Lihat Statistik Channel", callback_data="stats_0")]])
    await message.reply_text(text, reply_markup=markup)

# Callback Pagination Statistik
@Client.on_callback_query(filters.regex(r"^stats_"))
async def stats_callback(client: Client, callback_query):
    if callback_query.from_user.id != OWNER_ID:
        return await callback_query.answer("Akses ditolak!", show_alert=True)
        
    page = int(callback_query.data.split("_")[1])
    channels = await db.get_all_channels()
    
    if not channels:
        return await callback_query.message.edit_text("📊 Belum ada channel partner yang terdaftar.")
        
    limit = 15
    start = page * limit
    end = start + limit
    paginated_ch = channels[start:end]
    
    text = f"📊 **Daftar Channel Partner (Halaman {page + 1}):**\n\n"
    for idx, ch in enumerate(paginated_ch, start=start+1):
        status_ico = "🟢" if ch["status"] == "active" else "🔴"
        text += f"{idx}. {status_ico} **{ch['title']}**\n   └ ID Unik: `{ch['channel_id']}`\n   └ Owner ID: `{ch['owner_id']}`\n\n"
        
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"stats_{page - 1}"))
    if end < len(channels):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"stats_{page + 1}"))
        
    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    await callback_query.message.edit_text(text, reply_markup=markup)

# Perintah Owner: /pause [ID] [Alasan]
@Client.on_message(filters.command("pause") & filters.private)
@owner_filter
async def force_pause(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text("❌ **Format Salah!**\nGunakan: `/pause [ID_Channel] [Alasan Anda]`")
        
    ch_id = int(message.command[1])
    reason = " ".join(message.command[2:])
    
    ch = await db.get_channel(ch_id)
    if not ch:
        return await message.reply_text("❌ ID Channel tidak ditemukan di database.")
        
    await db.update_channel_status(ch_id, "force_paused")
    await message.reply_text(f"🛑 Channel **{ch['title']}** berhasil di-**PAUSE PAKSA**.")
    
    # Kirim alasan ke Owner Channel Partner
    try:
        await client.send_message(
            ch["owner_id"],
            f"⚠️ **Pemberitahuan dari Admin Utama:**\n\n"
            f"Channel Anda **{ch['title']}** telah dinonaktifkan sementara dari sistem forwarder.\n"
            f"💬 **Alasan:** {reason}"
        )
    except Exception:
        pass

# Perintah Owner: /run [ID] [Alasan]
@Client.on_message(filters.command("run") & filters.private)
@owner_filter
async def force_run(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text("❌ **Format Salah!**\nGunakan: `/run [ID_Channel] [Alasan Anda]`")
        
    ch_id = int(message.command[1])
    reason = " ".join(message.command[2:])
    
    ch = await db.get_channel(ch_id)
    if not ch:
        return await message.reply_text("❌ ID Channel tidak ditemukan di database.")
        
    await db.update_channel_status(ch_id, "active")
    await message.reply_text(f"▶️ Channel **{ch['title']}** diizinkan kembali untuk meneruskan postingan.")
    
    # Kirim alasan ke Owner Channel Partner
    try:
        await client.send_message(
            ch["owner_id"],
            f"✅ **Pemberitahuan dari Admin Utama:**\n\n"
            f"Channel Anda **{ch['title']}** telah diaktifkan kembali dalam sistem forwarder.\n"
            f"💬 **Keterangan:** {reason}"
        )
    except Exception:
        pass
