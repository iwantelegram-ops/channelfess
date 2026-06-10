from pyrogram import Client, filters
from config import OWNER_ID
from db.mongo import partners

def is_owner(user_id):
    return user_id == OWNER_ID

@Client.on_message(filters.command("pause") & filters.private)
async def pause(client, message):
    if not is_owner(message.from_user.id):
        return await message.reply("❌ Kamu bukan owner bot.")
    try:
        _, channel_id, reason = message.text.split(" ", 2)
        partners.update_one({"_id": int(channel_id)}, {"$set": {"paused": True, "reason": reason}})
        await message.reply(f"⏸ Channel {channel_id} dipause. Alasan: {reason}")
    except:
        await message.reply("Format salah. Gunakan: /pause <ID> <alasan>")

@Client.on_message(filters.command("run") & filters.private)
async def run(client, message):
    if not is_owner(message.from_user.id):
        return await message.reply("❌ Kamu bukan owner bot.")
    try:
        _, channel_id, reason = message.text.split(" ", 2)
        partners.update_one({"_id": int(channel_id)}, {"$set": {"paused": False, "reason": reason}})
        await message.reply(f"▶️ Channel {channel_id} dijalankan kembali. Alasan: {reason}")
    except:
        await message.reply("Format salah. Gunakan: /run <ID> <alasan>")
