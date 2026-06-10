"""Helper functions for DB operations — extended for advanced features."""
from .mongo import partners, posts, users, blacklist_col, broadcast_col
from datetime import datetime

# ── Partners ──────────────────────────────────────────────
def get_partner(channel_id: int):
    return partners.find_one({"_id": channel_id})

def upsert_partner(channel_id: int, data: dict):
    partners.update_one({"_id": channel_id}, {"$set": data}, upsert=True)

def increment_partner_posts(channel_id: int):
    partners.update_one({"_id": channel_id}, {"$inc": {"total_posts": 1}})

def set_partner_paused(channel_id: int, paused: bool, reason: str = ""):
    partners.update_one({"_id": channel_id}, {"$set": {"paused": paused, "reason": reason}})

def get_all_partners():
    return list(partners.find())

def get_active_partners():
    return list(partners.find({"paused": False}))

def get_partners_by_owner(owner_id: int):
    return list(partners.find({"owner_id": owner_id}))

def count_partners():
    return partners.count_documents({})

def search_partners(query: str):
    """Cari partner by nama channel atau username (case-insensitive)."""
    import re
    rgx = re.compile(query, re.IGNORECASE)
    return list(partners.find({"$or": [
        {"channel_name": {"$regex": rgx}},
        {"username": {"$regex": rgx}}
    ]}))

# ── Posts ──────────────────────────────────────────────────
def make_post_id(partner_id: int, msg_id: int) -> str:
    return f"{partner_id}_{msg_id}"

def save_post(partner_id: int, partner_msg_id: int, main_msg_id: int):
    posts.insert_one({
        "_id":            make_post_id(partner_id, partner_msg_id),
        "partner_id":     partner_id,
        "partner_msg_id": partner_msg_id,
        "main_msg_id":    main_msg_id,
        "added_at":       datetime.utcnow()
    })

def get_post(partner_id: int, partner_msg_id: int):
    return posts.find_one({"_id": make_post_id(partner_id, partner_msg_id)})

def delete_post(partner_id: int, partner_msg_id: int):
    posts.delete_one({"_id": make_post_id(partner_id, partner_msg_id)})

def count_posts_by_partner(partner_id: int) -> int:
    return posts.count_documents({"partner_id": partner_id})

def get_posts_today() -> int:
    from datetime import timezone
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return posts.count_documents({"added_at": {"$gte": start}})

# ── Users ──────────────────────────────────────────────────
def get_user(user_id: int):
    return users.find_one({"_id": user_id})

def upsert_user(user_id: int, data: dict):
    users.update_one({"_id": user_id}, {"$set": data}, upsert=True)

def is_joined(user_id: int) -> bool:
    u = get_user(user_id)
    return bool(u and u.get("joined"))

def get_all_user_ids():
    return [u["_id"] for u in users.find({}, {"_id": 1})]

# ── Blacklist ──────────────────────────────────────────────
def get_blacklist() -> list:
    doc = blacklist_col.find_one({"_id": "global"})
    return doc.get("words", []) if doc else []

def add_blacklist(word: str):
    blacklist_col.update_one(
        {"_id": "global"},
        {"$addToSet": {"words": word.lower()}},
        upsert=True
    )

def remove_blacklist(word: str):
    blacklist_col.update_one(
        {"_id": "global"},
        {"$pull": {"words": word.lower()}}
    )

def contains_blacklisted(text: str) -> str | None:
    """Return matched word if text contains blacklisted word, else None."""
    words = get_blacklist()
    text_lower = text.lower()
    for w in words:
        if w in text_lower:
            return w
    return None

# ── Maintenance mode ───────────────────────────────────────
def set_maintenance(active: bool, reason: str = ""):
    from .mongo import settings_col
    settings_col.update_one(
        {"_id": "maintenance"},
        {"$set": {"active": active, "reason": reason, "updated_at": datetime.utcnow()}},
        upsert=True
    )

def get_maintenance() -> dict:
    from .mongo import settings_col
    doc = settings_col.find_one({"_id": "maintenance"})
    return doc or {"active": False, "reason": ""}
