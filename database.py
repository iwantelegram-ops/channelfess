import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
client = AsyncIOMotorClient(MONGO_URL)
db = client["telegram_forwarder_bot"]

# Koleksi
users_col = db["users"]
channels_col = db["channels"]
posts_col = db["posts"]

# --- Manajemen User ---
async def add_user(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

# --- Manajemen Channel ---
async def add_channel(channel_id, title, owner_id):
    await channels_col.update_one(
        {"channel_id": channel_id},
        {"$set": {"title": title, "owner_id": owner_id, "status": "active"}},
        upsert=True
    )

async def get_channel(channel_id):
    return await channels_col.find_one({"channel_id": channel_id})

async def get_user_channels(owner_id):
    return await channels_col.find({"owner_id": owner_id}).to_list(length=100)

async def update_channel_status(channel_id, status):
    await channels_col.update_one({"channel_id": channel_id}, {"$set": {"status": status}})

async def get_all_channels():
    return await channels_col.find({}).to_list(length=1000)

# --- Manajemen Postingan (Mapping ID) ---
async def save_post_map(partner_ch_id, partner_msg_id, main_msg_id):
    await posts_col.insert_one({
        "partner_channel_id": partner_ch_id,
        "partner_message_id": partner_msg_id,
        "main_message_id": main_msg_id
    })

async def get_main_msg_id(partner_ch_id, partner_msg_id):
    res = await posts_col.find_one({"partner_channel_id": partner_ch_id, "partner_message_id": partner_msg_id})
    return res["main_message_id"] if res else None
