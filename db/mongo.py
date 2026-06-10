from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["telegram_bot"]

partners = db["partners"]
posts = db["posts"]
users = db["users"]
