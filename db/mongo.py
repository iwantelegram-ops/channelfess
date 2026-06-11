"""MongoDB connection & semua collections."""
import dns.resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8", "8.8.4.4"]

from pymongo import MongoClient, DESCENDING
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
sessions_col  = db["sessions"]   # ← session bot
peers_col     = db["peers"]      # ← peer cache (resolusi ID Telegram)

# ── Indexes ────────────────────────────────────────────────
def ensure_indexes():
    posts.create_index([("partner_id", 1)])
    posts.create_index([("added_at", DESCENDING)])
    activity_col.create_index([("ts", DESCENDING)])
    activity_col.create_index([("partner_id", 1), ("ts", DESCENDING)])
    users.create_index([("joined", 1)])
    broadcast_col.create_index([("sent_at", DESCENDING)])
    peers_col.create_index([("username", 1)])   # ← untuk lookup @username
    peers_col.create_index([("phone", 1)])       # ← untuk lookup nomor HP

try:
    ensure_indexes()
except Exception:
    pass
