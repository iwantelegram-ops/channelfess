from pyrogram import Client, filters
from db.mongo import partners

@Client.on_message(filters.command("addpartner") & filters.private)
async def add_partner(client, message):
    try:
        _, channel_id, owner = message.text.split(" ", 2)
        partners.update_one({"_id": int(channel_id)}, {"$set": {"owner": owner, "paused": False}}, upsert=True)
        await message.reply(f"✅ Channel {channel_id} ditambahkan sebagai partner milik {owner}")
    except:
        await message.reply("Format salah. Gunakan: /addpartner <ID> <owner>")
