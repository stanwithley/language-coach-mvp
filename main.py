# main.py
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    JobQueue,
)
from config import BOT_TOKEN
import handlers

def main():
    app = Application.builder()\
        .token(BOT_TOKEN)\
        .job_queue(JobQueue())\
        .build()

    # --- Register conversation ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📋 ثبت‌نام$"), handlers.register_start)],
        states={
            handlers.ASK_NAME: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.register_name)],
            handlers.ASK_AGE: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.register_age)],
            handlers.ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.register_email)],
            handlers.REG_LEVEL: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.register_set_level)],
            handlers.REG_GOAL: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.register_set_goal)],
            handlers.PLACEMENT_Q: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.placement_answer)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="register_conv",
        persistent=False,
    )

    # --- Edit conversation ---
    edit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✏️ ویرایش اطلاعات$"), handlers.edit_info)],
        states={
            handlers.EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.edit_field)],
            handlers.EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.edit_value)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="edit_conv",
        persistent=False,
    )

    # --- Q&A conversation ---
    qa_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^❓ پرسش‌وپاسخ$"), handlers.qa_start)],
        states={handlers.ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.qa_answer)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="qa_conv",
        persistent=False,
    )

    # --- Lesson conversation ---
    lesson_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📚 شروع درس$"), handlers.lesson_start)],
        states={handlers.ASK_EXERCISE: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.lesson_answer)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="lesson_conv",
        persistent=False,
    )

    # --- Review conversation ---
    review_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔁 مرور$"), handlers.review_start)],
        states={handlers.REVIEW_ITEM: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.review_answer)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="review_conv",
        persistent=False,
    )

    # --- Settings conversation ---
    settings_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ تنظیمات$"), handlers.settings)],
        states={handlers.SETTINGS_FIELD: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.settings_handle)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="settings_conv",
        persistent=False,
    )

    # --- Placement conversation ---
    placement_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧪 تعیین سطح$"), handlers.placement_start)],
        states={handlers.PLACEMENT_Q: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ لغو$"), handlers.placement_answer)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ لغو$"), handlers.cancel)],
        name="placement_conv",
        persistent=False,
    )

    # --- Commands ---
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("about", handlers.about))
    app.add_handler(CommandHandler("review", handlers.review_start))
    app.add_handler(CommandHandler("progress", handlers.progress))
    app.add_handler(CommandHandler("settings", handlers.settings))
    app.add_handler(CommandHandler("placement", handlers.placement_start))

    # --- Menus & flows ---
    app.add_handler(reg_conv)
    app.add_handler(edit_conv)
    app.add_handler(qa_conv)
    app.add_handler(lesson_conv)
    app.add_handler(review_conv)
    app.add_handler(settings_conv)
    app.add_handler(placement_conv)

    # main menu items
    app.add_handler(MessageHandler(filters.Regex("^📖 مشاهده اطلاعات$"), handlers.view_info))
    app.add_handler(MessageHandler(filters.Regex("^📊 پیشرفت$"), handlers.progress))

    # --- Error handler ---
    app.add_error_handler(handlers.error_handler)

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
