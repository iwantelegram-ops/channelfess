from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import MAIN_CHANNEL_ID
from db.mongo import users

@Client.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    users.update_one({"_id": user_id}, {"$set": {"joined": False}}, upsert=True)

    try:
        member = await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            users.update_one({"_id": user_id}, {"$set": {"joined": True}})
            await message.reply(
                "✅ Kamu sudah join channel utama.\n"
                "Gunakan tombol di bawah untuk menautkan bot ke channelmu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Admin-kan Bot", url="https://t.me/your_bot?start=link")]
                ])
            )
        else:
            await message.reply(
                "⚠️ Kamu harus join channel utama dulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Join Channel Utama", url="https://t.me/your_main_channel")]
                ])
            )
    except:
        await message.reply("⚠️ Kamu harus join channel utama dulu.")
