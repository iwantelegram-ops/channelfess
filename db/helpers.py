"""Helper functions for DB operations."""
from .mongo import partners, posts, users
from datetime import datetime

# ── Partners ──────────────────────────────────────────────
def get_partner(channel_id: int):
    return partners.find_one({"_id": channel_id})

def upsert_partner(channel_id: int, data: dict):
    partners.update_one({"_id": channel_id}, {"$set": data}, upsert=True)

def set_partner_paused(channel_id: int, paused: bool, reason: str = ""):
    partners.update_one({"_id": channel_id}, {"$set": {"paused": paused, "reason": reason}})

def get_all_partners():
    return list(partners.find())

def get_partners_by_owner(owner_id: int):
    return list(partners.find({"owner_id": owner_id}))

def count_partners():
    return partners.count_documents({})

# ── Posts ──────────────────────────────────────────────────
def make_post_id(partner_id: int, msg_id: int) -> str:
    return f"{partner_id}_{msg_id}"

def save_post(partner_id: int, partner_msg_id: int, main_msg_id: int):
    posts.insert_one({
        "_id":          make_post_id(partner_id, partner_msg_id),
        "partner_id":   partner_id,
        "partner_msg_id": partner_msg_id,
        "main_msg_id":  main_msg_id,
        "added_at":     datetime.utcnow()
    })

def get_post(partner_id: int, partner_msg_id: int):
    return posts.find_one({"_id": make_post_id(partner_id, partner_msg_id)})

def delete_post(partner_id: int, partner_msg_id: int):
    posts.delete_one({"_id": make_post_id(partner_id, partner_msg_id)})

# ── Users ──────────────────────────────────────────────────
def get_user(user_id: int):
    return users.find_one({"_id": user_id})

def upsert_user(user_id: int, data: dict):
    users.update_one({"_id": user_id}, {"$set": data}, upsert=True)

def is_joined(user_id: int) -> bool:
    u = get_user(user_id)
    return bool(u and u.get("joined"))
