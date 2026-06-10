from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
import importlib
import os

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Load plugins
for file in os.listdir("plugins"):
    if file.endswith(".py"):
        importlib.import_module(f"plugins.{file[:-3]}")

print("Bot started...")
app.run()
