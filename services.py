import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

from pymongo import MongoClient
import google.generativeai as genai
from dotenv import load_dotenv

# ---- Load env ----
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "english_coach")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ---- MongoDB ----
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col   = db["users"]
lessons_col = db["lessons"]
reviews_col = db["reviews"]     # SRS items
events_col  = db["events"]      # Analytics

# Indexes (idempotent)
users_col.create_index("user_id", unique=True)
lessons_col.create_index([("user_id", 1), ("created_at", 1)])
reviews_col.create_index([("user_id", 1), ("next_due", 1)])
events_col.create_index([("user_id", 1), ("ts", 1)])

# ---- Gemini ----
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ---- Helpers ----
def _now_utc():
    return datetime.utcnow()

# ---- User Services ----
def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})

def save_user(user_id: int, data: dict):
    data = {**data, "user_id": user_id}
    users_col.update_one({"user_id": user_id}, {"$set": data}, upsert=True)

def update_user_field(user_id: int, field: str, value):
    users_col.update_one({"user_id": user_id}, {"$set": {field: value}})

# ---- Lesson Services ----
def save_lesson(user_id: int, lesson: str, exercise: str):
    doc = {
        "user_id": user_id,
        "lesson": lesson,
        "exercise": exercise,
        "created_at": _now_utc()
    }
    lessons_col.insert_one(doc)
    log_event(user_id, "lesson_created", {"exercise_id": f"ex_{abs(hash(exercise))}"})
    return doc

# ---- SRS Services ----
def seed_review_item(user_id: int, exercise: str, item_id: str | None = None):
    """افزودن آیتم مرور برای تمرین درس امروز (اگر وجود نداشته باشد)."""
    if not item_id:
        item_id = f"ex_{abs(hash(exercise))}"
    doc = reviews_col.find_one({"user_id": user_id, "item_id": item_id})
    if doc:
        return doc
    doc = {
        "user_id": user_id,
        "item_id": item_id,
        "exercise": exercise,
        "ease_factor": 2.5,
        "interval": 0,
        "reps": 0,
        "next_due": _now_utc(),
        "last_result": None,
        "updated_at": _now_utc(),
    }
    reviews_col.insert_one(doc)
    return doc

def get_due_reviews(user_id: int, limit: int = 1) -> List[Dict[str, Any]]:
    return list(
        reviews_col.find(
            {"user_id": user_id, "next_due": {"$lte": _now_utc()}}
        ).sort("next_due", 1).limit(limit)
    )

def update_review_result(user_id: int, item_id: str, correct: bool) -> Dict[str, Any]:
    doc = reviews_col.find_one({"user_id": user_id, "item_id": item_id})
    if not doc:
        return {}
    ef = float(doc.get("ease_factor", 2.5))
    interval = int(doc.get("interval", 0))
    reps = int(doc.get("reps", 0))

    if correct:
        reps += 1
        next_interval = 1 if interval == 0 else (2 if interval == 1 else int(round(interval * 1.6)))
        ef = max(1.3, ef + 0.05)
        interval = next_interval
    else:
        reps = 0
        ef = max(1.3, ef - 0.2)
        interval = 1  # مرور فردا

    next_due = _now_utc() + timedelta(days=interval)

    reviews_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "ease_factor": ef,
            "interval": interval,
            "reps": reps,
            "last_result": "correct" if correct else "wrong",
            "next_due": next_due,
            "updated_at": _now_utc(),
        }}
    )
    return {
        "item_id": doc["item_id"],
        "interval": interval,
        "reps": reps,
        "ease_factor": ef,
        "next_due": next_due,
        "last_result": "correct" if correct else "wrong",
    }

# ---- Analytics ----
def log_event(user_id: int, event: str, meta: dict | None = None):
    events_col.insert_one({
        "user_id": user_id,
        "event": event,
        "meta": meta or {},
        "ts": _now_utc()
    })

def progress_summary(user_id: int) -> dict:
    lessons_done = lessons_col.count_documents({"user_id": user_id})
    since = _now_utc() - timedelta(days=7)
    recent = list(events_col.find({"user_id": user_id, "ts": {"$gte": since}}))
    correct = sum(1 for e in recent if e.get("event") == "review_answered" and e.get("meta", {}).get("correct") is True)
    wrong   = sum(1 for e in recent if e.get("event") == "review_answered" and e.get("meta", {}).get("correct") is False)

    # streak ساده از روی روزهای lesson
    days = set()
    for d in lessons_col.find({"user_id": user_id}, {"created_at": 1}):
        if d.get("created_at"):
            days.add(d["created_at"].date())
    streak, today = 0, _now_utc().date()
    while today in days:
        streak += 1
        today = today - timedelta(days=1)

    return {
        "lessons_done": lessons_done,
        "reviews_correct_7d": correct,
        "reviews_wrong_7d": wrong,
        "streak_days": streak
    }

# ---- Gemini Service ----
async def ask_gemini(prompt: str) -> str:
    """ارسال پرامپت به Gemini و دریافت پاسخ"""
    try:
        response = await model.generate_content_async(prompt)
        return (response.text or "").strip()
    except Exception as e:
        return f"⚠️ خطا در ارتباط با Gemini: {e}"
