"""MongoDB connection & semua collections."""
import dns.resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8", "8.8.4.4"]

from pymongo import MongoClient, DESCENDING, ASCENDING
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["fessbot"]

partners      = db["partners"]
posts         = db["posts"]
users         = db["users"]
blacklist_col = db["blacklist"]
settings_col  = db["settings"]
broadcast_col = db["broadcasts"]
activity_col  = db["activity"]
notif_col     = db["notifications"]
sessions_col  = db["sessions"]
peers_col     = db["peers"]
banned_col    = db["banned_users"]
rate_col      = db["rate_limits"]
templates_col = db["caption_templates"]
schedules_col = db["schedules"]


def ensure_indexes():
    posts.create_index([("partner_id", 1)])
    posts.create_index([("added_at", DESCENDING)])
    activity_col.create_index([("ts", DESCENDING)])
    activity_col.create_index([("partner_id", 1), ("ts", DESCENDING)])
    users.create_index([("joined", 1)])
    broadcast_col.create_index([("sent_at", DESCENDING)])
    peers_col.create_index([("username", 1)])
    peers_col.create_index([("phone", 1)])
    banned_col.create_index([("user_id", 1)])
    rate_col.create_index([("user_id", 1)])
    rate_col.create_index([("ts", ASCENDING)], expireAfterSeconds=60)
    partners.create_index([("owner_id", 1)])
    partners.create_index([("paused", 1)])


try:
    ensure_indexes()
except Exception:
    pass
