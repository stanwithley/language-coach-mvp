# handlers.py
from __future__ import annotations
import re
from datetime import time as dtime
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ConversationHandler, CallbackContext, ContextTypes

from services import (
    get_user, save_user, update_user_field, update_user,
    save_lesson, ask_gemini, log_event,
    seed_review_item, get_due_reviews, update_review_result, progress_summary,
    generate_micro_lesson_json, generate_placement_questions, score_to_cefr
)

# ---- States ----
ASK_NAME, ASK_AGE, ASK_EMAIL, REG_LEVEL, REG_GOAL = range(5)
EDIT_FIELD, EDIT_VALUE = range(5, 7)
ASK_QUESTION = 7
ASK_EXERCISE = 8
REVIEW_ITEM = 9
SETTINGS_FIELD, SETTINGS_VALUE = 10, 11
PLACEMENT_Q = 20


# ---- Keyboards ----
def main_menu(is_registered: bool):
    if is_registered:
        buttons = [
            ["📖 مشاهده اطلاعات", "✏️ ویرایش اطلاعات"],
            ["📚 شروع درس", "🔁 مرور"],
            ["🧪 تعیین سطح", "📊 پیشرفت"],
            ["❓ پرسش‌وپاسخ", "⚙️ تنظیمات"]
        ]
    else:
        buttons = [["📋 ثبت‌نام"]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def _quick_actions_menu(is_registered: bool):
    if is_registered:
        buttons = [
            ["📚 شروع درس", "🔁 مرور"],
            ["🧪 تعیین سطح", "📊 پیشرفت"],
            ["❓ پرسش‌وپاسخ", "⚙️ تنظیمات"],
            ["📖 مشاهده اطلاعات", "✏️ ویرایش اطلاعات"],
        ]
    else:
        buttons = [["📋 ثبت‌نام"], ["🧪 تعیین سطح"]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def cancel_button():
    return ReplyKeyboardMarkup([["❌ لغو"]], resize_keyboard=True)


def _placement_keyboard(options):
    if not options:
        return cancel_button()
    rows = []
    for i, opt in enumerate(options):
        label = f"{chr(65 + i)}) {opt}"
        if i % 2 == 0:
            rows.append([label])
        else:
            rows[-1].append(label)
    rows.append(["❌ لغو"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _render_question_dyn(item: dict, idx: int, total: int) -> str:
    title = f"سؤال {idx + 1}/{total}:\n\n"
    body = item.get("q", "")
    t = (item.get("type") or "").lower()
    txt = title + body + "\n"
    if t in ("listening", "reading") and item.get("transcript"):
        txt += f"\n(Passage/Transcript): {item['transcript']}\n"
    opts = item.get("options") or []
    if opts:
        for i, opt in enumerate(opts):
            txt += f"{chr(65 + i)}) {opt}\n"
    return txt


# ---- Intro/Help/About ----
def _intro_text():
    return (
        "👋 سلام!\n"
        "به ربات آموزش زبان انگلیسی خوش اومدی 🌱\n\n"
        "✨ امکانات اصلی:\n"
        "• 📚 «میکرولسن»‌های کوتاه و ساده، مخصوص سطح خودت\n"
        "• 📝 تمرین‌های کوچک با فیدبک فوری\n"
        "• 🔁 مرور هوشمند (SRS)\n"
        "• ❓ بخش پرسش‌وپاسخ\n"
        "• ⏰ یادآور روزانه\n"
        "• 📊 پیگیری پیشرفت\n\n"
        "🚀 شروع سریع:\n"
        "1) «📋 ثبت‌نام»  2) «🧪 تعیین سطح»  3) «📚 شروع درس»"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    u = get_user(update.effective_user.id)
    is_registered = bool(u)
    await update.message.reply_text(_intro_text(), reply_markup=_quick_actions_menu(is_registered))
    if not is_registered:
        await update.message.reply_text("برای شروع سریع: «📋 ثبت‌نام» سپس «🧪 تعیین سطح» و بعد «📚 شروع درس».")
    else:
        await update.message.reply_text(
            "خوش برگشتی! با «📚 شروع درس» ادامه بده یا «🔁 مرور» آیتم‌های موعددار رو انجام بده.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ از منوی پایین گزینه‌ات رو انتخاب کن.")


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ ربات یادگیری زبان انگلیسی با محتوای شخصی‌سازی‌شده و مرور هوشمند.")


# ---- Register ----
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 نام خود را وارد کنید:", reply_markup=cancel_button())
    return ASK_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("📅 سن خود را وارد کنید:", reply_markup=cancel_button())
    return ASK_AGE


async def register_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text
    await update.message.reply_text("📧 ایمیل خود را وارد کنید:", reply_markup=cancel_button())
    return ASK_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text
    save_user(update.effective_user.id, {
        "name": context.user_data.get("name"),
        "age": context.user_data.get("age"),
        "email": context.user_data.get("email"),
        "goal": context.user_data.get("goal"),
        "level": context.user_data.get("level"),
    })
    await update.message.reply_text("📊 حالا یک تعیین سطح کوتاه انجام می‌دیم.")
    return await placement_start(update, context)


async def register_set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["level"] = update.message.text
    await update.message.reply_text("🎯 هدف شما از یادگیری چیست؟ (Fun / Work / Travel ...)",
                                    reply_markup=cancel_button())
    return REG_GOAL


async def register_set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["goal"] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    log_event(update.effective_user.id, "register_completed", {})
    await update.message.reply_text("✅ ثبت‌نام انجام شد!", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- Edit Info ----
async def edit_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ کدام بخش را می‌خواهید ویرایش کنید؟ (name / age / email / level / goal)",
                                    reply_markup=cancel_button())
    return EDIT_FIELD


async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["field"] = update.message.text
    await update.message.reply_text("🔄 مقدار جدید را وارد کنید:", reply_markup=cancel_button())
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data["field"]
    value = update.message.text
    update_user_field(update.effective_user.id, field, value)
    await update.message.reply_text("✅ بروزرسانی انجام شد!", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- View Info ----
async def view_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return
    text = (
        f"👤 نام: {u.get('name')}\n"
        f"📅 سن: {u.get('age')}\n"
        f"📧 ایمیل: {u.get('email')}\n"
        f"📊 سطح: {u.get('level') or u.get('cefr')}\n"
        f"🎯 هدف: {u.get('goal')}\n"
        f"🧩 ضعف‌ها: {', '.join(u.get('weaknesses', [])) if u.get('weaknesses') else '—'}\n"
    )
    await update.message.reply_text(text)


# ---- Q&A ----
async def qa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ سوال خود را بنویسید:", reply_markup=cancel_button())
    return ASK_QUESTION


async def qa_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    log_event(update.effective_user.id, "qa_asked", {"q": question})
    answer = await ask_gemini(
        f"Answer this English learning question in simple terms: {question}") or "Sorry, try again later."
    await update.message.reply_text(f"💡 پاسخ: {answer}", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- Lesson ----
def _render_lesson_from_json(j: dict) -> tuple[str, str]:
    parts = ["📌 واژگان:\n"]
    for v in (j.get("vocab") or [])[:3]:
        line = f"- {v.get('word')} /{v.get('ipa', '')}/ = {v.get('meaning_fa', '')}\n  e.g. {v.get('example', '')}"
        parts.append(line)
    parts.append("\n🧩 جمله‌ها:\n")
    for s in (j.get("sentences") or []):
        parts.append(f"- {s}")
    content = "\n".join(parts).strip()

    ex = (j.get("exercises") or [])
    if not ex:
        return content, "Exercise: Make one sentence using a new word."
    first = ex[0]
    if first.get("type") == "mcq":
        t = f"{first['prompt']}\n"
        for i, opt in enumerate(first.get("options") or []):
            t += f"{chr(65 + i)}) {opt}\n"
        exercise_text = "Exercise: " + t.strip()
    else:
        exercise_text = "Exercise: " + (first.get("prompt") or "")
    return content, exercise_text


async def lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    await update.message.reply_text("📖 در حال ساخت درس شخصی‌سازی‌شده...")
    level = u.get("cefr") or u.get("level") or "A1"
    goal = u.get("goal", "General")
    weaknesses = u.get("weaknesses", [])

    j = generate_micro_lesson_json(level, goal, weaknesses)
    content, exercise = _render_lesson_from_json(j)
    save_lesson(u["user_id"], content, exercise, json_payload=j)

    context.user_data["exercise"] = exercise
    seed_review_item(u["user_id"], exercise)
    log_event(u["user_id"], "lesson_started", {"cefr": level})

    await update.message.reply_text(f"✨ درس امروز:\n\n{content}")
    ex0 = (j.get("exercises") or [None])[0] or {}
    if (ex0.get("type") == "listening") and ex0.get("media_url"):
        try:
            await update.message.reply_audio(audio=ex0["media_url"])
        except:
            pass
    await update.message.reply_text(f"📝 {exercise}")
    return ASK_EXERCISE


async def lesson_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    exercise = context.user_data.get("exercise", "")
    u = get_user(update.effective_user.id)
    weaknesses = u.get("weaknesses", []) if u else []

    prompt = (
        f"You are an English teacher.\n"
        f"Exercise: {exercise}\n"
        f"Student's answer: {answer}\n"
        f"Weakness hints: {', '.join(weaknesses)}\n"
        "Return one word: CORRECT or WRONG. Then a short reason (<=15 words) + a tiny tip."
    )
    feedback = await ask_gemini(prompt) or ""
    item_id = f"ex_{abs(hash(exercise))}"
    is_correct = "correct" in feedback.lower()

    stats = update_review_result(update.effective_user.id, item_id, is_correct)
    log_event(update.effective_user.id, "review_answered_correct" if is_correct else "review_answered_wrong", {})

    await update.message.reply_text(f"✅ جواب دریافت شد:\n\n{answer}")
    extra = f"\n(نوبت بعدی مرور: {stats.get('interval', 1)} روز دیگر)" if stats else ""
    await update.message.reply_text(f"🔎 فیدبک: {feedback}{extra}", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- Review (SRS) ----
async def review_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    due = get_due_reviews(u["user_id"], limit=1)
    if not due:
        await update.message.reply_text("🎉 فعلاً آیتم موعددار نداری. بعداً برگرد!", reply_markup=main_menu(True))
        return ConversationHandler.END

    item = due[0]
    context.user_data["review_item_id"] = item["item_id"]
    context.user_data["review_exercise"] = item["exercise"]

    await update.message.reply_text(f"🔁 مرور:\n\n{item['exercise']}", reply_markup=cancel_button())
    return REVIEW_ITEM


async def review_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    exercise = context.user_data.get("review_exercise")
    item_id = context.user_data.get("review_item_id")

    prompt = (
        f"You are an English teacher.\n"
        f"Exercise: {exercise}\n"
        f"Student's answer: {answer}\n"
        "Return one word: CORRECT or WRONG. Then a short reason (<=15 words)."
    )
    feedback = await ask_gemini(prompt) or ""
    is_correct = "correct" in feedback.lower()

    stats = update_review_result(update.effective_user.id, item_id, is_correct)
    log_event(update.effective_user.id, "review_answered_correct" if is_correct else "review_answered_wrong", {})

    result = "✅ درست" if is_correct else "❌ غلط"
    extra = f"\n(نوبت بعدی: {stats.get('interval', 1)} روز دیگر)" if stats else ""
    await update.message.reply_text(f"{result}\n{feedback}{extra}", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- Progress ----
async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return
    summary = progress_summary(u["user_id"])
    txt = (
        f"📊 پیشرفت شما\n"
        f"• درس‌های انجام‌شده: {summary['lessons_done']}\n"
        f"• مرور صحیح (۷ روز گذشته): {summary['reviews_correct_7d']}\n"
        f"• مرور غلط (۷ روز گذشته): {summary['reviews_wrong_7d']}\n"
        f"• استریک: {summary['streak_days']} روز\n"
    )
    await update.message.reply_text(txt, reply_markup=main_menu(True))


# ---- Settings + Reminder ----
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ تنظیمات:\n"
        "برای فعال‌سازی یادآور روزانه، ساعت را به صورت HH:MM بفرست (مثلاً 20:30)\n"
        "برای خاموش: OFF",
        reply_markup=cancel_button()
    )
    return SETTINGS_FIELD


async def settings_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id

    if text.upper() == "OFF":
        update_user_field(uid, "reminder_enabled", False)
        update_user_field(uid, "reminder_time", None)
        await update.message.reply_text("⏰ یادآور خاموش شد.", reply_markup=main_menu(True))
        return ConversationHandler.END

    try:
        hh, mm = map(int, text.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        await update.message.reply_text("⛔️ فرمت ساعت نادرست است. نمونه: 20:30", reply_markup=cancel_button())
        return SETTINGS_FIELD

    update_user_field(uid, "reminder_time", text)
    update_user_field(uid, "reminder_enabled", True)

    # حذف jobهای قبلی با همین نام
    for old in context.job_queue.get_jobs_by_name(f"reminder_{uid}"):
        old.schedule_removal()

    # توجه: run_daily به وقت سرور/UTC است
    context.job_queue.run_daily(
        callback=send_daily_reminder,
        time=dtime(hour=hh, minute=mm),
        chat_id=uid,
        name=f"reminder_{uid}",
    )

    await update.message.reply_text(
        f"✅ یادآور روزانه روی {text} تنظیم شد.",
        reply_markup=main_menu(True)
    )
    return ConversationHandler.END


async def send_daily_reminder(context: CallbackContext):
    chat_id = context.job.chat_id
    await context.bot.send_message(chat_id=chat_id, text="🕒 وقت درسه! روی /lesson بزن 😊")


# ---- Placement (Dynamic) ----
async def placement_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    level_hint = u.get("level") or u.get("cefr") or "Beginner"
    qs = generate_placement_questions(level_hint)
    if not qs:
        await update.message.reply_text("⛔️ فعلاً نتوانستم سؤال‌های تعیین‌سطح بسازم. بعداً دوباره تلاش کن.")
        return ConversationHandler.END

    context.user_data["pl_qs"] = qs
    context.user_data["pl_idx"] = 0
    context.user_data["pl_score"] = 0
    context.user_data["pl_wrong_tags"] = {}

    item = qs[0]
    kb = _placement_keyboard(item.get("options"))
    await update.message.reply_text("🧪 تعیین‌سطح شروع شد. لطفاً پاسخ بده.")
    if item.get("type") == "listening" and item.get("media_url"):
        try:
            await update.message.reply_audio(audio=item["media_url"])
        except:
            pass
    await update.message.reply_text(_render_question_dyn(item, 0, len(qs)), reply_markup=kb)
    return PLACEMENT_Q


async def placement_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "❌ لغو":
        await update.message.reply_text("❌ تعیین سطح لغو شد.", reply_markup=main_menu(True))
        return ConversationHandler.END

    qs = context.user_data.get("pl_qs", [])
    idx = context.user_data.get("pl_idx", 0)
    score = context.user_data.get("pl_score", 0)
    wrong_tags = context.user_data.get("pl_wrong_tags", {})

    if idx >= len(qs):
        await update.message.reply_text("پایان آزمون.", reply_markup=main_menu(True))
        return ConversationHandler.END

    item = qs[idx]
    t = (item.get("type") or "").lower()
    options = item.get("options") or []
    correct = False

    if options:
        selected = None
        if len(text) >= 1 and text[0].upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            pos = ord(text[0].upper()) - 65
            if 0 <= pos < len(options):
                selected = pos
        if selected is None:
            for i, opt in enumerate(options):
                if text.lower() == (opt or "").lower():
                    selected = i
                    break
        if selected is None:
            await update.message.reply_text("⛔️ لطفاً یکی از گزینه‌ها را انتخاب کنید.")
            kb = _placement_keyboard(options)
            await update.message.reply_text(_render_question_dyn(item, idx, len(qs)), reply_markup=kb)
            return PLACEMENT_Q
        correct = (selected == item.get("answer_index"))
    else:
        ans = (item.get("answer_text") or "").strip().lower()
        user_ans = text.strip().lower()
        norm = lambda s: re.sub(r"[^a-z0-9 ']", "", s)
        correct = norm(user_ans) == norm(ans)

    if correct:
        score += 1
        await update.message.reply_text("✅ درست!")
    else:
        tag = item.get("tag") or "general"
        wrong_tags[tag] = wrong_tags.get(tag, 0) + 1
        if options and item.get("answer_index") is not None:
            correct_letter = chr(65 + item["answer_index"])
            await update.message.reply_text(f"❌ غلط. پاسخ درست: {correct_letter}")
        elif item.get("answer_text"):
            await update.message.reply_text(f"❌ غلط. پاسخ نمونه: {item['answer_text']}")

    idx += 1
    if idx < len(qs):
        context.user_data["pl_idx"] = idx
        context.user_data["pl_score"] = score
        context.user_data["pl_wrong_tags"] = wrong_tags

        nxt = qs[idx]
        kb = _placement_keyboard(nxt.get("options"))
        if nxt.get("type") == "listening" and nxt.get("media_url"):
            try:
                await update.message.reply_audio(audio=nxt["media_url"])
            except:
                pass
        await update.message.reply_text(_render_question_dyn(nxt, idx, len(qs)), reply_markup=kb)
        return PLACEMENT_Q

    # پایان آزمون
    cefr = score_to_cefr(score, len(qs))
    update_user_field(update.effective_user.id, "cefr", cefr)
    update_user_field(update.effective_user.id, "level", cefr)  # برای سازگاری با کدهای دیگر

    sorted_weak = sorted(wrong_tags.items(), key=lambda kv: kv[1], reverse=True)
    top3 = [t for t, c in sorted_weak[:3]]
    if top3:
        update_user_field(update.effective_user.id, "weaknesses", top3)

    try:
        log_event(update.effective_user.id, "placement_completed",
                  {"score": score, "total": len(qs), "cefr": cefr, "weak": top3})
    except:
        pass

    weak_txt = ("ضعف‌ها: " + ", ".join(top3)) if top3 else "ضعف خاصی ثبت نشد."
    await update.message.reply_text(
        f"🏁 پایان تعیین سطح!\n"
        f"امتیاز: {score}/{len(qs)}\n"
        f"سطح (CEFR): {cefr}\n"
        f"{weak_txt}\n\n"
        f"حالا «📚 شروع درس» رو بزن تا درس مناسب سطحت بیاد.",
        reply_markup=main_menu(True)
    )
    return ConversationHandler.END


# ---- Cancel ----
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=main_menu(True))
    return ConversationHandler.END
