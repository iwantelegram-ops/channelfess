"""MongoDB connection & collections."""
from pymongo import MongoClient
from config import MONGO_URI
import dns.resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4']

client   = MongoClient(MONGO_URI)
db       = client["fessbot"]

partners      = db["partners"]
posts         = db["posts"]
users         = db["users"]
blacklist_col = db["blacklist"]
settings_col  = db["settings"]
broadcast_col = db["broadcasts"]
