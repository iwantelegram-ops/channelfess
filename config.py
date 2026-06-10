import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID"))
MAIN_CHANNEL_USERNAME = os.getenv("MAIN_CHANNEL_USERNAME")
OWNER_ID = int(os.getenv("OWNER_ID"))
