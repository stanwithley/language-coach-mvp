from telegram.ext import ConversationHandler, CallbackContext
from datetime import time as dtime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from services import (
    get_user, save_user, update_user_field,
    save_lesson, ask_gemini,
    log_event, seed_review_item, get_due_reviews,
    update_review_result, progress_summary
)

# ---- States ----
ASK_NAME, ASK_AGE, ASK_EMAIL, REG_LEVEL, REG_GOAL = range(5)
EDIT_FIELD, EDIT_VALUE = range(5, 7)
ASK_QUESTION = 7
ASK_EXERCISE = 8
REVIEW_ITEM = 9
SETTINGS_FIELD, SETTINGS_VALUE = 10, 11
PLACEMENT_Q = 20

# ---- Placement Questions (7 MCQ) ----
PLACEMENT_QUESTIONS = [
    {
        "q": "Choose the correct article: ___ apple a day keeps the doctor away.",
        "options": ["A", "An", "The", "No article"],
        "answer": 1,
        "tag": "grammar:articles"
    },
    {
        "q": "Fill in the blank: I ____ coffee every morning.",
        "options": ["drinks", "drink", "drank", "am drinking"],
        "answer": 1,
        "tag": "grammar:present-simple"
    },
    {
        "q": "Choose the correct preposition: I’m interested ___ music.",
        "options": ["on", "at", "in", "for"],
        "answer": 2,
        "tag": "grammar:prepositions"
    },
    {
        "q": "Vocabulary: What does 'daily routine' mean?",
        "options": ["A party", "Things you do every day", "An accident", "A holiday plan"],
        "answer": 1,
        "tag": "vocab:daily-life"
    },
    {
        "q": "Choose the correct past form: She ____ to school yesterday.",
        "options": ["go", "goes", "went", "going"],
        "answer": 2,
        "tag": "grammar:past-simple"
    },
    {
        "q": "Reading: 'He rarely eats meat.' What does 'rarely' mean?",
        "options": ["often", "never", "sometimes", "not often"],
        "answer": 3,
        "tag": "vocab:frequency"
    },
    {
        "q": "Choose the correct sentence:",
        "options": [
            "She don't like tea.",
            "She doesn't likes tea.",
            "She doesn't like tea.",
            "She not like tea."
        ],
        "answer": 2,
        "tag": "grammar:aux-does"
    },
]


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


def cancel_button():
    return ReplyKeyboardMarkup([["❌ لغو"]], resize_keyboard=True)


def _placement_keyboard(options):
    rows = []
    for i, opt in enumerate(options):
        label = f"{chr(65 + i)}) {opt}"
        if i % 2 == 0:
            rows.append([label])
        else:
            rows[-1].append(label)
    rows.append(["❌ لغو"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _render_question(idx: int):
    item = PLACEMENT_QUESTIONS[idx]
    text = f"سؤال {idx + 1}/{len(PLACEMENT_QUESTIONS)}:\n\n{item['q']}\n"
    for i, opt in enumerate(item["options"]):
        text += f"{chr(65 + i)}) {opt}\n"
    return text


# ---- Commands ----

def _intro_text():
    return (
        "👋 سلام!\n"
        "به ربات آموزش زبان انگلیسی خوش اومدی 🌱\n\n"
        "اینجا جاییه که می‌تونی بدون استرس و به صورت شخصی‌سازی شده زبانت رو تقویت کنی.\n\n"
        "✨ امکانات اصلی:\n"
        "• 📚 «میکرولسِن»‌های کوتاه و ساده، مخصوص سطح خودت\n"
        "• 📝 تمرین‌های کوچک با **فیدبک فوری** (درست/غلط و دلیل)\n"
        "• 🔁 مرور هوشمند (SRS) برای تثبیت مطالب در حافظه بلندمدت\n"
        "• ❓ بخش پرسش‌وپاسخ برای هر سوالی در مسیر یادگیری\n"
        "• ⏰ یادآور روزانه تا هیچ روزی تمرینت عقب نیفته\n"
        "• 📊 پیگیری پیشرفت و انگیزه با نمودار و استریک\n\n"
        "🚀 چطور شروع کنم؟\n"
        "1. «📋 ثبت‌نام» رو بزن تا پروفایل آموزشی‌ات ساخته بشه.\n"
        "2. با «🧪 تعیین سطح» جایگاه دقیق زبانت رو مشخص کن.\n"
        "3. «📚 شروع درس» رو بزن و اولین درس رو دریافت کن."
    )


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # نمایش حالت تایپ برای حس طبیعی‌تر
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    u = get_user(update.effective_user.id)
    is_registered = bool(u)

    # پیام اصلی معرفی
    await update.message.reply_text(
        _intro_text(),
        reply_markup=_quick_actions_menu(is_registered)
    )

    # پیام دوم با CTA متناسب با وضعیت کاربر
    if not is_registered:
        await update.message.reply_text(
            "برای شروع سریع:\n"
            "• اول «📋 ثبت‌نام» رو انجام بده\n"
            "• بعد «🧪 تعیین سطح» رو بزن\n"
            "• آماده‌ای؟ «📚 شروع درس» 😎"
        )
    else:
        await update.message.reply_text(
            "خوش برگشتی! ✨\n"
            "هر زمان آماده‌ای «📚 شروع درس» رو بزن یا با «🔁 مرور» آیتم‌های موعددار رو مرور کن."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ با منوی پایین می‌تونی عملیات رو انتخاب کنی.")


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ این ربات برای یادگیری زبان انگلیسی به صورت شخصی‌سازی شده ساخته شده.")


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

    # ⬇️ پروفایل موقت را همین‌جا ذخیره کن تا placement کار کند
    save_user(
        update.effective_user.id,
        {
            "name": context.user_data.get("name"),
            "age": context.user_data.get("age"),
            "email": context.user_data.get("email"),
            # اختیاری: اگر goal/level بعداً تعیین می‌شود، خالی بگذار
            "goal": context.user_data.get("goal"),
            "level": context.user_data.get("level"),
        },
    )

    await update.message.reply_text("📊 حالا یک تعیین سطح کوتاه انجام می‌دیم.")
    return await placement_start(update, context)


# اگر خواستی مسیر قدیمی level/goal را نگه داری:
async def register_set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["level"] = update.message.text
    await update.message.reply_text("🎯 هدف شما از یادگیری چیست؟ (Fun / Work / Travel ...)",
                                    reply_markup=cancel_button())
    return REG_GOAL


async def register_set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["goal"] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    log_event(update.effective_user.id, "register_completed", {})
    await update.message.reply_text("✅ ثبت‌نام با موفقیت انجام شد!", reply_markup=main_menu(True))
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
        f"📊 سطح: {u.get('level')}\n"
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
    answer = await ask_gemini(f"Answer this English learning question in simple terms: {question}")
    await update.message.reply_text(f"💡 پاسخ: {answer}", reply_markup=main_menu(True))
    return ConversationHandler.END


# ---- Lesson ----
async def generate_micro_lesson(level: str, goal: str, weaknesses: list | None = None):
    weak_hint = f"\nFocus on weaknesses: {', '.join(weaknesses)}" if weaknesses else ""
    system = (
        "Act as a friendly English teacher.\n"
        f"Level: {level}\n"
        f"Goal: {goal}{weak_hint}\n\n"
        "Write a SHORT micro-lesson with:\n"
        "- 3-4 simple sentences (topic appropriate for the student's level)\n"
        "- Then add a line starting with: Exercise:\n"
        "  - one tiny task (fill-in-the-blank OR short translation OR make-a-sentence)\n"
        "Keep it concise. Avoid long outputs."
    )
    text = await ask_gemini(system)

    if not text or text.startswith("⚠️"):
        lesson = (
            "Today's phrase: \"Nice to meet you!\"\n"
            "We use it when we meet someone for the first time.\n"
            "Example: \"Hi, I'm Alex. Nice to meet you!\""
        )
        exercise = "Exercise: Write a greeting using 'Nice to meet you'."
        return lesson, exercise

    parts = text.split("Exercise:")
    lesson_text = parts[0].strip()
    exercise = "Exercise:" + parts[1].strip() if len(
        parts) > 1 else "Exercise: Make one sentence using a new word from the lesson."
    return lesson_text, exercise


async def lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    await update.message.reply_text("📖 در حال ساخت درس شخصی‌سازی‌شده...")
    level = u.get("level", "Beginner")
    goal = u.get("goal", "Fun")
    weaknesses = u.get("weaknesses", [])
    lesson_text, exercise = await generate_micro_lesson(level, goal, weaknesses)
    save_lesson(u["user_id"], lesson_text, exercise)

    context.user_data["exercise"] = exercise
    seed_review_item(u["user_id"], exercise)  # آیتم مرور برای تمرین همین درس
    log_event(u["user_id"], "lesson_started", {})

    await update.message.reply_text(f"✨ درس امروز:\n\n{lesson_text}")
    await update.message.reply_text(f"📝 {exercise}")
    return ASK_EXERCISE


async def lesson_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    exercise = context.user_data.get("exercise", "")

    prompt = (
        f"You are an English teacher.\n"
        f"Here is the exercise: {exercise}\n"
        f"Student's answer: {answer}\n"
        "Return one word: CORRECT or WRONG. Then a short reason (<=15 words)."
    )
    feedback = await ask_gemini(prompt)
    item_id = f"ex_{abs(hash(exercise))}"
    is_correct = "correct" in (feedback or "").lower()

    stats = update_review_result(update.effective_user.id, item_id, is_correct)
    log_event(update.effective_user.id, "lesson_answered", {"correct": bool(is_correct)})

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
    feedback = await ask_gemini(prompt)
    is_correct = "correct" in (feedback or "").lower()

    stats = update_review_result(update.effective_user.id, item_id, is_correct)
    log_event(update.effective_user.id, "review_answered", {"correct": bool(is_correct)})

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

    # HH:MM parsing
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

    # ثبت Job روزانه (به وقت سرور/UTC)
    context.job_queue.run_daily(
        callback=send_daily_reminder,
        time=dtime(hour=hh, minute=mm),
        chat_id=uid,
        name=f"reminder_{uid}",
    )

    await update.message.reply_text(
        f"✅ یادآور روزانه با موفقیت روی ساعت {text} تنظیم شد.",
        reply_markup=main_menu(True)
    )
    return ConversationHandler.END


async def send_daily_reminder(context: CallbackContext):
    chat_id = context.job.chat_id
    await context.bot.send_message(chat_id=chat_id, text="🕒 وقت درسه! روی /lesson بزن 😊")


# ---- Placement ----
async def placement_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ ابتدا ثبت‌نام کنید.", reply_markup=main_menu(False))
        return ConversationHandler.END

    context.user_data["pl_idx"] = 0
    context.user_data["pl_score"] = 0
    context.user_data["pl_wrong_tags"] = {}

    q = _render_question(0)
    kb = _placement_keyboard(PLACEMENT_QUESTIONS[0]["options"])
    await update.message.reply_text("🧪 تعیین سطح شروع شد. لطفاً گزینه‌ی درست را انتخاب کنید.")
    await update.message.reply_text(q, reply_markup=kb)
    return PLACEMENT_Q


async def placement_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "❌ لغو":
        await update.message.reply_text("❌ تعیین سطح لغو شد.", reply_markup=main_menu(True))
        return ConversationHandler.END

    idx = context.user_data.get("pl_idx", 0)
    score = context.user_data.get("pl_score", 0)
    wrong_tags = context.user_data.get("pl_wrong_tags", {})

    item = PLACEMENT_QUESTIONS[idx]
    selected = None
    if len(text) >= 1 and text[0].upper() in "ABCD":
        selected = ord(text[0].upper()) - 65
    else:
        for i, opt in enumerate(item["options"]):
            if text.lower() == opt.lower():
                selected = i
                break

    if selected is None or not (0 <= selected < len(item["options"])):
        await update.message.reply_text("⛔️ لطفاً یکی از گزینه‌ها را انتخاب کنید (A/B/C/D).")
        q = _render_question(idx)
        kb = _placement_keyboard(item["options"])
        await update.message.reply_text(q, reply_markup=kb)
        return PLACEMENT_Q

    if selected == item["answer"]:
        score += 1
        await update.message.reply_text("✅ درست!")
    else:
        wrong_tags[item["tag"]] = wrong_tags.get(item["tag"], 0) + 1
        correct_letter = chr(65 + item["answer"])
        await update.message.reply_text(f"❌ غلط. پاسخ درست: {correct_letter}")

    idx += 1
    if idx < len(PLACEMENT_QUESTIONS):
        context.user_data["pl_idx"] = idx
        context.user_data["pl_score"] = score
        context.user_data["pl_wrong_tags"] = wrong_tags

        q = _render_question(idx)
        kb = _placement_keyboard(PLACEMENT_QUESTIONS[idx]["options"])
        await update.message.reply_text(q, reply_markup=kb)
        return PLACEMENT_Q

    # پایان آزمون – محاسبه سطح
    if score <= 2:
        level = "Beginner"
    elif score <= 5:
        level = "Intermediate"
    else:
        level = "Advanced"

    sorted_weak = sorted(wrong_tags.items(), key=lambda kv: kv[1], reverse=True)
    top3 = [t for t, c in sorted_weak[:3]]

    update_user_field(update.effective_user.id, "level", level)
    if top3:
        update_user_field(update.effective_user.id, "weaknesses", top3)

    try:
        log_event(update.effective_user.id, "placement_completed", {"score": score, "level": level, "weak": top3})
    except:
        pass

    weak_txt = ("ضعف‌ها: " + ", ".join(top3)) if top3 else "ضعف خاصی ثبت نشد."
    await update.message.reply_text(
        f"🏁 پایان تعیین سطح!\n"
        f"امتیاز: {score}/{len(PLACEMENT_QUESTIONS)}\n"
        f"سطح شما: {level}\n"
        f"{weak_txt}\n\n"
        f"حالا می‌تونی «📚 شروع درس» رو بزنی تا درس مناسب سطحت بیاد.",
        reply_markup=main_menu(True)
    )
    return ConversationHandler.END


# ---- Cancel ----
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=main_menu(True))
    return ConversationHandler.END
