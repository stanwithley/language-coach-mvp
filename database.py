from pymongo import MongoClient, ASCENDING
from datetime import datetime
from config import MONGO_URI, DB_NAME
from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "language_coach")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]
lessons_col = db["lessons"]

client = MongoClient(MONGO_URI)
db = client[DB_NAME]


# Indexes for performance (idempotent)
users_col.create_index([("user_id", ASCENDING)], unique=True)
lessons_col.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])

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
