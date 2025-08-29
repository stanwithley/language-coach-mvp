from pymongo import MongoClient, ASCENDING
from datetime import datetime
from config import MONGO_URI, DB_NAME

# اتصال به دیتابیس
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# کالکشن‌ها
users_col = db["users"]
lessons_col = db["lessons"]

# ایندکس‌ها برای بهبود عملکرد
users_col.create_index([("user_id", ASCENDING)], unique=True)
lessons_col.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])

# فانکشن‌های کاربردی
def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})

def create_user(doc: dict):
    users_col.insert_one(doc)

def update_user(user_id: int, updates: dict):
    users_col.update_one({"user_id": user_id}, {"$set": updates}, upsert=False)

def save_lesson(user_id: int, content: str, exercise: str):
    doc = {
        "user_id": user_id,
        "content": content,
        "exercise": exercise,
        "created_at": datetime.utcnow()
    }
    lessons_col.insert_one(doc)
    return doc
