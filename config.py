import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "english_coach")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
PROXY_URL = os.getenv("PROXY_URL", "")        # مثلا: socks5://127.0.0.1:1080 یا http://127.0.0.1:8080
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "40"))  # تایم‌اوت کلی ثانیه
