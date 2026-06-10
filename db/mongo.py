import dns.resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8", "8.8.4.4"]

from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db     = client["fessbot"]

# Koleksi
partners = db["partners"]   # channel partner { _id: channel_id, owner_id, owner_name, channel_name, username, paused, reason, added_at }
posts    = db["posts"]      # repost log       { _id: partner_msg_id+channel_id, partner_id, main_msg_id, added_at }
users    = db["users"]      # user             { _id: user_id, joined, joined_at }
