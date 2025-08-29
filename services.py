# services.py
from __future__ import annotations
import os, json, re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, UTC
from pymongo import MongoClient, ASCENDING, ReturnDocument
from config import MONGO_URI, DB_NAME

# ---------- DB ----------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]

users_col   = db["users"]
lessons_col = db["lessons"]
reviews_col = db["reviews"]
events_col  = db["events"]
gen_col     = db["generated_cache"]  # cache for LLM outputs

# ---------- Indexes ----------
users_col.create_index([("user_id", ASCENDING)], unique=True)
users_col.create_index([("level", ASCENDING)])
users_col.create_index([("cefr", ASCENDING)])
lessons_col.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])
reviews_col.create_index([("user_id", ASCENDING), ("next_due", ASCENDING)])
events_col.create_index([("user_id", ASCENDING), ("ts", ASCENDING)])
gen_col.create_index([("key", ASCENDING)], unique=True)

# ---------- Users ----------
def get_user(user_id: int) -> Optional[dict]:
    return users_col.find_one({"user_id": user_id})

def save_user(user_id: int, doc: Dict[str, Any]) -> dict:
    now = datetime.now(UTC)
    doc["user_id"] = user_id
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    return users_col.find_one_and_update(
        {"user_id": user_id},
        {"$setOnInsert": doc},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

def update_user_field(user_id: int, field: str, value: Any) -> None:
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {field: value, "updated_at": datetime.now(UTC)}},
        upsert=True
    )

def update_user(user_id: int, updates: dict) -> None:
    updates["updated_at"] = datetime.now(UTC)
    users_col.update_one({"user_id": user_id}, {"$set": updates}, upsert=True)

# ---------- Lessons ----------
def save_lesson(user_id: int, content: str, exercise: str, json_payload: Optional[dict]=None) -> dict:
    doc = {
        "user_id": user_id,
        "content": content,
        "exercise": exercise,
        "json": json_payload,
        "created_at": datetime.now(UTC),
    }
    lessons_col.insert_one(doc)
    return doc

# ---------- Events / Logs ----------
def log_event(user_id: int, name: str, data: Dict[str, Any]) -> None:
    events_col.insert_one({
        "user_id": user_id,
        "name": name,
        "data": data or {},
        "ts": datetime.now(UTC)
    })

# ---------- LLM (Gemini) ----------
def ask_gemini(prompt: str, system: Optional[str]=None, json_mode: bool=False) -> Optional[str]:
    """
    Wrapper ساده برای Gemini (sync). اگر API key یا پکیج نبود → None.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai  # pip install google-generativeai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        parts = []
        if system:
            parts.append({"role": "system", "parts": [system]})
        parts.append({"role": "user", "parts": [prompt]})

        resp = model.generate_content(parts)
        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            return None
        if json_mode:
            m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
            return m.group(1) if m else text
        return text
    except ModuleNotFoundError:
        return None
    except Exception:
        return None

# ---------- CEFR Mapping ----------
def score_to_cefr(score: int, total: int) -> str:
    pct = (score / max(1, total)) * 100
    if pct < 20:   return "A1"
    if pct < 40:   return "A2"
    if pct < 60:   return "B1"
    if pct < 75:   return "B2"
    if pct < 90:   return "C1"
    return "C2"

# ---------- Dynamic Placement (with cache) ----------
def _validate_questions(payload: dict) -> List[dict]:
    out: List[dict] = []
    items = (payload or {}).get("questions") or []
    for it in items:
        t = (it.get("type") or "").lower()
        if t == "mcq":
            if not it.get("options") or it.get("answer_index") is None:
                continue
        elif t in ("fill", "dialog"):
            if not it.get("answer_text"):
                continue
        # listening/reading: می‌تواند options+answer_index یا answer_text داشته باشد
        out.append(it)
    return out[:10]

def generate_placement_questions(level_hint: str = "Beginner") -> List[dict]:
    cache_key = f"placement:{level_hint.lower()}"
    cached = gen_col.find_one({"key": cache_key})
    if cached and cached.get("expires_at") and cached["expires_at"] > datetime.now(UTC):
        return cached["value"]

    sys = (
        "You are an expert English placement-test writer. "
        "Create short, level-discriminating questions mixing grammar/vocab/listening/reading. "
        "Keep questions concise and culturally neutral. Questions in EN."
    )
    prompt = f"""
Return STRICT JSON:
{{
 "questions":[
   {{"q":"...", "type":"mcq|fill|dialog|listening|reading", "options":["A","B","C","D"], "answer_index":1, "answer_text":"...", "tag":"...", "media_url":"", "transcript":""}}
 ]
}}
Target level hint: {level_hint}.
Include 7–8 questions, at least one listening (short transcript) and one reading.
For MCQ include 'answer_index'; for non-MCQ include 'answer_text'.
"""
    raw = ask_gemini(prompt, system=sys, json_mode=True)

    if raw:
        try:
            payload = json.loads(raw)
            qs = _validate_questions(payload)
            if qs:
                gen_col.find_one_and_update(
                    {"key": cache_key},
                    {"$set": {"key": cache_key, "value": qs, "expires_at": datetime.now(UTC)+timedelta(hours=12)}},
                    upsert=True
                )
                return qs
        except (ValueError, TypeError):
            pass

    # --- fallback ---
    return [
        {"q": "Choose the correct article: ___ apple a day keeps the doctor away.",
         "type": "mcq", "options": ["A", "An", "The", "—"], "answer_index": 1, "tag": "grammar:articles"},
        {"q": "I ____ coffee every morning.", "type": "mcq",
         "options": ["drinks", "drink", "drank", "am drinking"], "answer_index": 1, "tag": "grammar:present-simple"},
        {"q": "Complete: I'm interested ___ music.", "type": "mcq",
         "options": ["on", "at", "in", "for"], "answer_index": 2, "tag": "grammar:prepositions"},
        {"q": "Fill: She ____ to school yesterday.", "type": "fill",
         "answer_text": "went", "tag": "grammar:past-simple"},
        {"q": "Dialog: A: Do you like tea? B: Yes, I ____.", "type": "dialog",
         "answer_text": "do", "tag": "grammar:aux-do"},
        {"q": "Listening: Identify the adverb meaning 'not often'.", "type": "listening",
         "media_url": "", "transcript": "He rarely eats meat.",
         "options": ["often", "never", "sometimes", "rarely"], "answer_index": 3, "tag": "vocab:frequency"},
        {"q": "Reading: What is 'daily routine'?", "type": "reading",
         "media_url": "", "transcript": "Daily routine means the things you do every day.",
         "options": ["A party", "An accident", "Daily activities", "A holiday"], "answer_index": 2, "tag": "vocab:daily-life"},
    ]

# ---------- Micro-lesson JSON ----------
def generate_micro_lesson_json(level: str, goal: str, weaknesses: Optional[List[str]]=None) -> dict:
    weak = ", ".join(weaknesses or [])
    sys = "You are a friendly English teacher. Return compact JSON for a micro-lesson. All content in English."
    prompt = f"""
Return STRICT JSON with keys:
{{
 "meta": {{"level":"{level}","goal":"{goal}","weaknesses":"{weak}","version":"1.0"}},
 "vocab": [{{"word":"...","ipa":"...","meaning_fa":"...","example":"...","audio_url":""}}],
 "sentences": ["...", "..."],
 "exercises": [
    {{
      "type": "fill|mcq|dialog|listening|reading",
      "prompt": "...",
      "options": ["A","B","C","D"],
      "answer_index": 1,
      "answer_text": "...",
      "media_url": "",
      "transcript": ""
    }}
 ],
 "tips": ["short tip 1", "short tip 2"]
}}
Keep it short and {level}-appropriate for goal "{goal}".
"""
    raw = ask_gemini(prompt, system=sys, json_mode=True)
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            pass
    # fallback
    return {
        "meta": {"level": level, "goal": goal, "weaknesses": weak, "version": "1.0"},
        "vocab": [
            {"word": "greet", "ipa": "ɡriːt", "meaning_fa": "سلام کردن", "example": "I greet my classmates.", "audio_url": ""},
            {"word": "meet", "ipa": "miːt", "meaning_fa": "ملاقات کردن", "example": "Nice to meet you.", "audio_url": ""},
            {"word": "daily", "ipa": "ˈdeɪli", "meaning_fa": "روزانه", "example": "My daily routine is simple.", "audio_url": ""},
        ],
        "sentences": ["Hello! Nice to meet you.", "I study English every day."],
        "exercises": [
            {"type": "fill", "prompt": "Fill: Nice to ____ you.", "answer_text": "meet"},
            {"type": "mcq", "prompt": "Choose: I ____ English.", "options": ["studies","study","studied","studying"], "answer_index": 1},
            {"type": "listening", "prompt": "What did you hear?", "media_url": "", "transcript": "Good morning!", "answer_text": "Good morning"},
        ],
        "tips": ["Practice speaking out loud.", "Keep sentences short and clear."]
    }

# ---------- SRS (SM2-lite) ----------
DEFAULT_EASE = 2.5
MIN_EASE = 1.3

def _sm2_next(interval: int, ease: float, was_correct: bool) -> Tuple[int, float]:
    if was_correct:
        ease = max(MIN_EASE, ease + 0.1)
        interval = 1 if interval == 0 else int(round(interval * ease))
    else:
        ease = max(MIN_EASE, ease - 0.2)
        interval = 1
    return interval, ease

def seed_review_item(user_id: int, exercise: str, item_id: Optional[str]=None) -> dict:
    if not item_id:
        item_id = f"ex_{abs(hash(exercise))}"
    now = datetime.now(UTC)
    return reviews_col.find_one_and_update(
        {"user_id": user_id, "item_id": item_id},
        {"$setOnInsert": {
            "user_id": user_id, "item_id": item_id, "exercise": exercise,
            "interval": 0, "ease": DEFAULT_EASE, "next_due": now,
            "created_at": now, "updated_at": now, "stats": {"correct": 0, "wrong": 0}
        }},
        upsert=True, return_document=ReturnDocument.AFTER
    )

def get_due_reviews(user_id: int, limit: int=1) -> List[dict]:
    now = datetime.now(UTC)
    cur = reviews_col.find({"user_id": user_id, "next_due": {"$lte": now}})\
                     .sort("next_due", ASCENDING).limit(limit)
    return list(cur)

def update_review_result(user_id: int, item_id: str, was_correct: bool) -> Optional[dict]:
    doc = reviews_col.find_one({"user_id": user_id, "item_id": item_id})
    if not doc:
        return None
    interval = doc.get("interval", 0)
    ease     = doc.get("ease", DEFAULT_EASE)
    interval, ease = _sm2_next(interval, ease, was_correct)
    next_due = datetime.now(UTC) + timedelta(days=interval)
    inc = {"stats.correct": 1} if was_correct else {"stats.wrong": 1}
    reviews_col.update_one({"_id": doc["_id"]}, {
        "$set": {"interval": interval, "ease": ease, "next_due": next_due, "updated_at": datetime.now(UTC)},
        "$inc": inc
    })
    return {"interval": interval, "ease": ease, "next_due": next_due}

def progress_summary(user_id: int) -> dict:
    lessons_done = lessons_col.count_documents({"user_id": user_id})
    since = datetime.now(UTC) - timedelta(days=7)
    pipeline = [
        {"$match": {"user_id": user_id, "ts": {"$gte": since}}},
        {"$group": {"_id": "$name", "cnt": {"$sum": 1}}}
    ]
    events = {e["_id"]: e["cnt"] for e in events_col.aggregate(pipeline)}
    return {
        "lessons_done": lessons_done,
        "reviews_correct_7d": events.get("review_answered_correct", 0),
        "reviews_wrong_7d": events.get("review_answered_wrong", 0),
        "streak_days": _compute_streak(user_id)
    }

def _compute_streak(user_id: int) -> int:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$project": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}}}},
        {"$group": {"_id": "$d"}},
        {"$sort": {"_id": -1}}
    ]
    days = [r["_id"] for r in events_col.aggregate(pipeline)]
    today = datetime.now(UTC).date()
    streak = 0
    while (today - timedelta(days=streak)).isoformat() in days:
        streak += 1
    return streak
