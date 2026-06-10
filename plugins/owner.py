from pyrogram import Client, filters
from db.mongo import partners

@Client.on_message(filters.command("pause") & filters.private)
async def pause(client, message):
    try:
        _, channel_id, reason = message.text.split(" ", 2)
        partners.update_one({"_id": int(channel_id)}, {"$set": {"paused": True, "reason": reason}})
        await message.reply(f"⏸ Channel {channel_id} dipause. Alasan: {reason}")
    except:
        await message.reply("Format salah. Gunakan: /pause <ID> <alasan>")

@Client.on_message(filters.command("run") & filters.private)
async def run(client, message):
    try:
        _, channel_id, reason = message.text.split(" ", 2)
        partners.update_one({"_id": int(channel_id)}, {"$set": {"paused": False, "reason": reason}})
        await message.reply(f"▶️ Channel {channel_id} dijalankan kembali. Alasan: {reason}")
    except:
        await message.reply("Format salah. Gunakan: /run <ID> <alasan>")
