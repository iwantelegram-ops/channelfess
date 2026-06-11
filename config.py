import os
from dotenv import load_dotenv

load_dotenv()

API_ID                = int(os.getenv("API_ID", "0"))
API_HASH              = os.getenv("API_HASH", "")
BOT_TOKEN             = os.getenv("BOT_TOKEN", "")
MONGO_URI             = os.getenv("MONGO_URI", "")
MAIN_CHANNEL_ID       = int(os.getenv("MAIN_CHANNEL_ID", "0"))
MAIN_CHANNEL_USERNAME = os.getenv("MAIN_CHANNEL_USERNAME", "")
OWNER_ID              = int(os.getenv("OWNER_ID", "0"))
BOT_USERNAME          = os.getenv("BOT_USERNAME", "")
OWNER_USERNAME        = os.getenv("OWNER_USERNAME", "")
OWNER_NAME            = os.getenv("OWNER_NAME", "Owner")
BOT_NAME              = os.getenv("BOT_NAME", "FessBot")
BOT_DESC              = os.getenv("BOT_DESC", "Auto Repost Bot")

FLOOD_SLEEP_THRESHOLD = 60
BROADCAST_DELAY       = 0.05
RATE_LIMIT_PER_MINUTE = 20
