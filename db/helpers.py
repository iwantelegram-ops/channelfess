"""Helper functions untuk semua operasi database."""
from .mongo import (
    partners, posts, users, blacklist_col,
    settings_col, broadcast_col, activity_col, notif_col,
    banned_col, rate_col, templates_col,
)
from datetime import datetime, timezone, timedelta
import re


# ═══════════════════════════════════════════════════════════
#  PARTNERS
# ═══════════════════════════════════════════════════════════

def get_partner(channel_id: int):
    return partners.find_one({"_id": channel_id})

def upsert_partner(channel_id: int, data: dict):
    partners.update_one({"_id": channel_id}, {"$set": data}, upsert=True)

def remove_partner(channel_id: int):
    partners.delete_one({"_id": channel_id})

def increment_partner_posts(channel_id: int):
    partners.update_one({"_id": channel_id}, {"$inc": {"total_posts": 1}})

def get_all_partners():
    return list(partners.find().sort("total_posts", -1))

def get_active_partners():
    return list(partners.find({"paused": False}))

def get_partners_by_owner(owner_id: int):
    return list(partners.find({"owner_id": owner_id}))

def count_partners():
    return partners.count_documents({})

def search_partners(query: str):
    rgx = re.compile(re.escape(query), re.IGNORECASE)
    return list(partners.find({"$or": [
        {"channel_name": {"$regex": rgx}},
        {"username":     {"$regex": rgx}},
    ]}))

def get_top_partners(limit: int = 5):
    return list(partners.find({"paused": False}).sort("total_posts", -1).limit(limit))

def get_partner_media_filter(channel_id: int) -> str:
    partner = get_partner(channel_id)
    if partner:
        return partner.get("media_filter", "all")
    return "all"


# ═══════════════════════════════════════════════════════════
#  POSTS
# ═══════════════════════════════════════════════════════════

def _post_id(partner_id: int, msg_id: int) -> str:
    return f"{partner_id}_{msg_id}"

def save_post(partner_id: int, partner_msg_id: int, main_msg_id: int):
    try:
        posts.insert_one({
            "_id":            _post_id(partner_id, partner_msg_id),
            "partner_id":     partner_id,
            "partner_msg_id": partner_msg_id,
            "main_msg_id":    main_msg_id,
            "added_at":       datetime.now(timezone.utc),
        })
    except Exception:
        pass

def get_post(partner_id: int, partner_msg_id: int):
    return posts.find_one({"_id": _post_id(partner_id, partner_msg_id)})

def delete_post(partner_id: int, partner_msg_id: int):
    posts.delete_one({"_id": _post_id(partner_id, partner_msg_id)})

def get_all_tracked_posts() -> list:
    return list(posts.find({}, {"partner_id": 1, "partner_msg_id": 1, "main_msg_id": 1}))

def count_posts_by_partner(partner_id: int) -> int:
    return posts.count_documents({"partner_id": partner_id})

def get_posts_today() -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return posts.count_documents({"added_at": {"$gte": start}})

def get_posts_this_week() -> int:
    start = datetime.now(timezone.utc) - timedelta(days=7)
    return posts.count_documents({"added_at": {"$gte": start}})

def get_posts_this_month() -> int:
    start = datetime.now(timezone.utc) - timedelta(days=30)
    return posts.count_documents({"added_at": {"$gte": start}})

def get_recent_posts_by_partner(partner_id: int, limit: int = 5):
    return list(posts.find({"partner_id": partner_id}).sort("added_at", -1).limit(limit))

def get_posts_by_msg_id(partner_msg_id: int) -> list:
    return list(posts.find({"partner_msg_id": partner_msg_id}))


# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════

def get_user(user_id: int):
    return users.find_one({"_id": user_id})

def upsert_user(user_id: int, data: dict):
    users.update_one({"_id": user_id}, {"$set": data}, upsert=True)

def is_joined(user_id: int) -> bool:
    u = get_user(user_id)
    return bool(u and u.get("joined"))

def get_all_user_ids():
    return [u["_id"] for u in users.find({}, {"_id": 1})]

def count_users() -> int:
    return users.count_documents({})

def count_active_users() -> int:
    return users.count_documents({"joined": True})


# ═══════════════════════════════════════════════════════════
#  BANNED USERS
# ═══════════════════════════════════════════════════════════

def is_banned(user_id: int) -> bool:
    return banned_col.count_documents({"_id": user_id}) > 0

def ban_user(user_id: int, reason: str = "", banned_by: int = 0):
    banned_col.update_one(
        {"_id": user_id},
        {"$set": {
            "reason":    reason,
            "banned_by": banned_by,
            "banned_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )

def unban_user(user_id: int):
    banned_col.delete_one({"_id": user_id})

def get_banned_list() -> list:
    return list(banned_col.find().sort("banned_at", -1))

def count_banned() -> int:
    return banned_col.count_documents({})


# ═══════════════════════════════════════════════════════════
#  RATE LIMITING (per user, 1 menit window via TTL index)
# ═══════════════════════════════════════════════════════════

def check_rate_limit(user_id: int, limit: int = 20) -> bool:
    """Return True jika user masih dalam batas rate limit."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=60)
    count = rate_col.count_documents({
        "user_id": user_id,
        "ts": {"$gte": window_start},
    })
    return count < limit

def record_rate_hit(user_id: int):
    rate_col.insert_one({
        "user_id": user_id,
        "ts": datetime.now(timezone.utc),
    })


# ═══════════════════════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════════════════════

def get_blacklist() -> list:
    doc = blacklist_col.find_one({"_id": "global"})
    return doc.get("words", []) if doc else []

def add_blacklist(word: str):
    blacklist_col.update_one(
        {"_id": "global"},
        {"$addToSet": {"words": word.lower().strip()}},
        upsert=True,
    )

def remove_blacklist(word: str):
    blacklist_col.update_one(
        {"_id": "global"},
        {"$pull": {"words": word.lower().strip()}},
    )

def contains_blacklisted(text: str):
    words = get_blacklist()
    text_lower = text.lower()
    for w in words:
        if w in text_lower:
            return w
    return None


# ═══════════════════════════════════════════════════════════
#  MAINTENANCE MODE
# ═══════════════════════════════════════════════════════════

def set_maintenance(active: bool, reason: str = ""):
    settings_col.update_one(
        {"_id": "maintenance"},
        {"$set": {"active": active, "reason": reason, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

def get_maintenance() -> dict:
    doc = settings_col.find_one({"_id": "maintenance"})
    return doc or {"active": False, "reason": ""}


# ═══════════════════════════════════════════════════════════
#  BOT SETTINGS
# ═══════════════════════════════════════════════════════════

def get_bot_setting(key: str, default=None):
    doc = settings_col.find_one({"_id": f"setting_{key}"})
    return doc.get("value", default) if doc else default

def set_bot_setting(key: str, value):
    settings_col.update_one(
        {"_id": f"setting_{key}"},
        {"$set": {"value": value, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


# ═══════════════════════════════════════════════════════════
#  CAPTION TEMPLATE
# ═══════════════════════════════════════════════════════════

DEFAULT_CAPTION_TEMPLATE = (
    "{channel_link}\n"
    "{original_caption}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤  Owner   :  {owner_link}\n"
    "📅  Tanggal :  {date}\n"
    "🕒  Jam     :  {time}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🔁  via {bot_link}"
)

def get_caption_template() -> str:
    doc = templates_col.find_one({"_id": "global"})
    return doc.get("template", DEFAULT_CAPTION_TEMPLATE) if doc else DEFAULT_CAPTION_TEMPLATE

def set_caption_template(template: str):
    templates_col.update_one(
        {"_id": "global"},
        {"$set": {"template": template, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

def reset_caption_template():
    templates_col.delete_one({"_id": "global"})


# ═══════════════════════════════════════════════════════════
#  ACTIVITY LOG
# ═══════════════════════════════════════════════════════════

def log_activity(event: str, partner_id: int = None, extra: dict = None):
    doc = {
        "event":      event,
        "partner_id": partner_id,
        "ts":         datetime.now(timezone.utc),
    }
    if extra:
        doc.update(extra)
    activity_col.insert_one(doc)

def get_recent_activity(limit: int = 10, partner_id: int = None):
    query = {}
    if partner_id:
        query["partner_id"] = partner_id
    return list(activity_col.find(query).sort("ts", -1).limit(limit))

def count_activity_today() -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return activity_col.count_documents({"ts": {"$gte": start}})


# ═══════════════════════════════════════════════════════════
#  NOTIFICATION SETTINGS (per user)
# ═══════════════════════════════════════════════════════════

def get_notif_setting(user_id: int, key: str, default: bool = True) -> bool:
    doc = notif_col.find_one({"_id": user_id})
    return doc.get(key, default) if doc else default

def set_notif_setting(user_id: int, key: str, value: bool):
    notif_col.update_one(
        {"_id": user_id},
        {"$set": {key: value}},
        upsert=True,
    )


# ═══════════════════════════════════════════════════════════
#  BROADCAST HISTORY
# ═══════════════════════════════════════════════════════════

def save_broadcast(sender_id: int, target: str, message: str, success: int, fail: int):
    broadcast_col.insert_one({
        "sender_id": sender_id,
        "target":    target,
        "message":   message[:200],
        "success":   success,
        "fail":      fail,
        "sent_at":   datetime.now(timezone.utc),
    })

def get_broadcast_history(limit: int = 5):
    return list(broadcast_col.find().sort("sent_at", -1).limit(limit))
