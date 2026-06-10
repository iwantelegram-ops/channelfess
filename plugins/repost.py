from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import MAIN_CHANNEL_ID
from db.mongo import posts, partners
from datetime import datetime

@Client.on_message(filters.channel)
async def repost(client, message):
    chat_id = message.chat.id
    partner = partners.find_one({"_id": chat_id})
    if not partner or partner.get("paused"): return

    if message.photo or message.video:
        caption = f"""
📌 Channel: {message.chat.title}
👤 Owner: {partner['owner']}
🕒 {datetime.now().strftime('%d-%m-%Y %H:%M')}
🆔 Post ID: {message.id}
        """
        sent = await message.copy(MAIN_CHANNEL_ID, caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Lihat Asli", url=f"https://t.me/{message.chat.username}/{message.id}")]
            ])
        )
        posts.insert_one({
            "_id": message.id,
            "partner_id": chat_id,
            "main_id": sent.id
        })

@Client.on_deleted_messages(filters.channel)
async def delete_repost(client, messages):
    for msg in messages:
        post = posts.find_one({"_id": msg.id})
        if post:
            try:
                await client.delete_messages(MAIN_CHANNEL_ID, post["main_id"])
            except: pass
            posts.delete_one({"_id": msg.id})
