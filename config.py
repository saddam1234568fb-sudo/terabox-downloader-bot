import os
import urllib.parse

API_ID = int(os.environ.get("API_ID", "123456")) 
API_HASH = os.environ.get("API_HASH", "আপনার_এপিআই_হ্যাশ") 
BOT_TOKEN = os.environ.get("BOT_TOKEN", "আপনার_বট_টোকেন") 

# REDIS CONFIG FOR RENDER
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
parsed = urllib.parse.urlparse(REDIS_URL)
HOST = parsed.hostname or "localhost"
PORT = parsed.port or 6379
PASSWORD = parsed.password or ""

PRIVATE_CHAT_ID = int(os.environ.get("PRIVATE_CHAT_ID", "-1001234567890")) 
COOKIE = os.environ.get("COOKIE", "")
ADMINS = [int(x) for x in os.environ.get("ADMINS", "1317173146").split(",")]

BOT_USERNAME = os.environ.get("BOT_USERNAME", "teraboxdown_bot")
FORCE_LINK = os.environ.get("FORCE_LINK", "@RoldexVerse")
PUBLIC_EARN_API = os.environ.get("PUBLIC_EARN_API", "")
