import logging
import sqlite3
import datetime
import pytz

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

#BOT_TOKEN = "8534911818:AAGtLGMxPiT1aa6ocj1lJJoRkyc-3yLznO0"  # ← এখানে তোমার বট টোকেন দাও
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_USERNAMES = ['mrx_46x', 'cr_username']  # ← @ ছাড়া, ছোট হাত–বড় হাত মিলিয়ে নাও
DB_NAME = "simple_uni.db"

# Timezone Setup (Bangladesh)
BD_TZ = pytz.timezone('Asia/Dhaka')

# --- HARDCODED TEACHER LIST (Edit Here) ---
TEACHER_LIST_TEXT = """
👨‍🏫 *University Teacher List*

1️⃣ *Asad Sir*
   📚 Subject: Mathematics
   📞 Contact: 013xxxxxxxx
   📧 Email: asad@example.com

2️⃣ *Moni Khan*
   📚 Subject: CSE
   📞 Contact: 017xxxxxxxx
   📧 Email: moni@example.com

3️⃣ *Rahim Uddin*
   📚 Subject: Physics
   📞 Contact: 018xxxxxxxx
   📧 Email: rahim@example.com

*(Contact CR/ACR for updates)*
"""

# Conversation States
(
    ADD_CLASS_TIME,
    ADD_CLASS_COURSE,
    ADD_CLASS_ROOM,
    ADD_CLASS_TEACHER,
    ADD_NOTICE_TITLE,
    ADD_NOTICE_BODY,
    BROADCAST_MSG,
    ADD_RESOURCE_FILE,
) = range(8)

# Logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 2. DATABASE
# ---------------------------------------------------------------------------


def init_db() -> None:
    """প্রথমবার রান করলে প্রয়োজনীয় টেবিলগুলো তৈরি করবে।"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Users
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id   INTEGER PRIMARY KEY,
            username  TEXT,
            first_name TEXT
        )
        """
    )

    # Daily Classes
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_classes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            course   TEXT,
            room     TEXT,
            teacher  TEXT
        )
        """
    )

    # Notices
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS notices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            body       TEXT,
            created_at TIMESTAMP
        )
        """
    )

    # Resources
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id    TEXT,
            file_type  TEXT,
            caption    TEXT,
            created_at TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    """প্রতি কলের জন্য নতুন কানেকশন (এভাবে লিকের ঝামেলা কম থাকে)।"""
    return sqlite3.connect(DB_NAME)


def is_admin(username: str | None) -> bool:
    """
    ইউজার অ্যাডমিন কি না চেক করে।
    - None হলে False
    - case-insensitive চেক করে
    """
    if not username:
        return False
    username = username.lstrip("@").lower()
    admin_list = [u.lower() for u in ADMIN_USERNAMES]
    return username in admin_list


def get_bd_time() -> datetime.datetime:
    return datetime.datetime.now(BD_TZ)


# ---------------------------------------------------------------------------
# 3. HELPERS (Validation)
# ---------------------------------------------------------------------------


def validate_and_format_time(time_text: str) -> str | None:
    """
    সময় validate করে এবং HH:MM ফরম্যাটে রিটার্ন করে।
    যেমন: 9:30 → 09:30, 14:05 → 14:05
    """
    time_text = time_text.strip()
    try:
        dt = datetime.datetime.strptime(time_text, "%H:%M")
        return dt.strftime("%H:%M")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 4. COMMANDS & NAVIGATION
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    # User কে DB তে সেভ করা
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (chat_id, username, first_name) VALUES (?, ?, ?)",
                (user.id, user.username, user.first_name),
            )
    except Exception as e:
        logger.error("Error inserting user: %s", e)

    welcome = f"স্বাগতম {user.first_name}! 👋\nইউনিভার্সিটি হেল্পার বটের মেনু নিচে দেওয়া হলো:"

    # User Buttons
    buttons: list[list[KeyboardButton]] = [
        [KeyboardButton("📅 Full Routine"), KeyboardButton("🗓 Today Classes")],
        [KeyboardButton("📢 Notices"), KeyboardButton("👨‍🏫 Teachers")],
        [KeyboardButton("📂 View Resources")],
    ]

    # Admin Buttons
    if is_admin(user.username):
        welcome += "\n\n🔰 *ADMIN PANEL*"
        buttons.append(
            [KeyboardButton("⚙ Add Today Class"), KeyboardButton("⚙ Add Notice")]
        )
        buttons.append(
            [KeyboardButton("⚙ Add Resources"), KeyboardButton("⚙ Broadcast")]
        )

    await update.message.reply_text(
        welcome,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True),
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে।")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# 5. USER FEATURES (VIEW)
# ---------------------------------------------------------------------------


async def show_full_routine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    routine = """
📅 *সাপ্তাহিক রুটিন*

*রবিবার:*
• CSE 101 (09:30 - 10:45) | Room: 301
• MAT 102 (11:00 - 12:50) | Room: 502

*সোমবার:*
• PHY 103 (09:30 - 10:45) | Room: Lab 2

*বৃহস্পতিবার:*
• LAB FINAL (10:00 - 01:00) | Room: Lab 1
"""
    await update.message.reply_text(routine, parse_mode="Markdown")


async def show_today_classes(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT time_str, course, room, teacher FROM daily_classes ORDER BY time_str ASC"
            )
            classes = c.fetchall()
    except Exception as e:
        logger.error("Error fetching classes: %s", e)
        await update.message.reply_text("❌ ক্লাস ডেটা লোড করতে সমস্যা হচ্ছে।")
        return

    if not classes:
        await update.message.reply_text("✅ আজকে কোনো ক্লাস শিডিউল করা নেই।")
        return

    msg = "🗓 *আজকের ক্লাস রুটিন:*\n\n"
    for time_str, course, room, teacher in classes:
        try:
            time_obj = datetime.datetime.strptime(time_str, "%H:%M")
            time_display = time_obj.strftime("%I:%M %p")
        except ValueError:
            time_display = time_str

        msg += (
            f"⏰ `{time_display}`\n"
            f"📘 *{course}*\n"
            f"📍 Room: {room}\n"
            f"👨‍🏫 {teacher}\n"
            f"{'-' * 20}\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def show_teachers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEACHER_LIST_TEXT, parse_mode="Markdown")


async def view_resources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT file_id, file_type, caption, created_at
                FROM resources
                ORDER BY id DESC
                LIMIT 5
                """
            )
            files = c.fetchall()
    except Exception as e:
        logger.error("Error fetching resources: %s", e)
        await update.message.reply_text("❌ রিসোর্স লোড করতে সমস্যা হচ্ছে।")
        return

    if not files:
        await update.message.reply_text("📂 কোনো রিসোর্স ফাইল নেই।")
        return

    await update.message.reply_text("📂 *সর্বশেষ রিসোর্স ফাইলসমূহ:*", parse_mode="Markdown")

    for file_id, f_type, caption, created in files:
        try:
            try:
                date_str = datetime.datetime.strptime(
                    created, "%Y-%m-%d %H:%M:%S"
                ).strftime("%d %b")
            except Exception:
                date_str = ""

            msg_cap = caption or "Resource File"
            if date_str:
                msg_cap += f"\n📅 {date_str}"

            if f_type == "photo":
                await update.message.reply_photo(photo=file_id, caption=msg_cap)
            else:
                await update.message.reply_document(document=file_id, caption=msg_cap)
        except Exception as e:
            logger.error("Failed to send resource: %s", e)


async def show_notices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT title, body, created_at FROM notices ORDER BY created_at DESC LIMIT 5"
            )
            notices = c.fetchall()
    except Exception as e:
        logger.error("Error fetching notices: %s", e)
        await update.message.reply_text("❌ নোটিশ লোড করতে সমস্যা হচ্ছে।")
        return

    if not notices:
        await update.message.reply_text("📭 কোনো নোটিশ নেই।")
        return

    msg = "📢 *নোটিশ বোর্ড:*\n\n"
    for title, body, created_at in notices:
        msg += f"📌 *{title}*\n{body}\n\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# 6. ADMIN HANDLERS (WRITE)
# ---------------------------------------------------------------------------

# ------- Add Class ---------


async def add_class_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("⛔ শুধুমাত্র এডমিনদের জন্য।")
        return ConversationHandler.END

    await update.message.reply_text("🕒 ক্লাসের সময় দিন (২৪ ঘন্টা ফরম্যাট, Ex: 09:30 বা 14:00):")
    return ADD_CLASS_TIME


async def add_class_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    raw_time = update.message.text.strip()
    formatted_time = validate_and_format_time(raw_time)

    if not formatted_time:
        await update.message.reply_text(
            "❌ ভুল সময়! HH:MM ফরম্যাট ব্যবহার করুন (Ex: 09:30 বা 14:00)।"
        )
        return ADD_CLASS_TIME

    context.user_data["time"] = formatted_time
    await update.message.reply_text("📘 কোর্সের নাম লিখুন:")
    return ADD_CLASS_COURSE


async def add_class_course(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["course"] = update.message.text.strip()
    await update.message.reply_text("📍 রুম নম্বর লিখুন:")
    return ADD_CLASS_ROOM


async def add_class_room(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["room"] = update.message.text.strip()
    await update.message.reply_text("👨‍🏫 শিক্ষকের নাম লিখুন:")
    return ADD_CLASS_TEACHER


async def add_class_finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    teacher = update.message.text.strip()
    time_str = context.user_data.get("time")
    course = context.user_data.get("course")
    room = context.user_data.get("room")

    if not (time_str and course and room):
        await update.message.reply_text("❌ ডেটায় সমস্যা হয়েছে, আবার চেষ্টা করুন।")
        return ConversationHandler.END

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO daily_classes (time_str, course, room, teacher) VALUES (?, ?, ?, ?)",
                (time_str, course, room, teacher),
            )
        await update.message.reply_text(
            f"✅ ক্লাস যুক্ত হয়েছে:\n⏰ {time_str} | 📘 {course} | 📍 {room} | 👨‍🏫 {teacher}"
        )
    except Exception as e:
        logger.error("Error inserting class: %s", e)
        await update.message.reply_text("❌ ক্লাস সেভ করতে সমস্যা হয়েছে।")

    return ConversationHandler.END


# ------- Add Resources ---------


async def add_res_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("⛔ শুধুমাত্র এডমিনদের জন্য।")
        return ConversationHandler.END

    await update.message.reply_text("📂 ফাইল বা ছবি আপলোড করুন (PDF/Doc/Photo):")
    return ADD_RESOURCE_FILE


async def add_res_finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    msg = update.message
    file_id = None
    file_type = "doc"

    if msg.document:
        file_id = msg.document.file_id
        file_type = "doc"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    else:
        await update.message.reply_text("❌ ফাইল বা ছবি দিন।")
        return ADD_RESOURCE_FILE

    caption = msg.caption if msg.caption else "Resource File"
    created = get_bd_time().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO resources (file_id, file_type, caption, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, file_type, caption, created),
            )
        await update.message.reply_text(
            "✅ আপলোড সফল। আরও দিতে পারেন অথবা /cancel লিখে বের হতে পারেন।"
        )
    except Exception as e:
        logger.error("Error inserting resource: %s", e)
        await update.message.reply_text("❌ রিসোর্স সেভ করতে সমস্যা হয়েছে।")

    return ADD_RESOURCE_FILE


# ------- Add Notice ---------


async def add_notice_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("⛔ শুধুমাত্র এডমিনদের জন্য।")
        return ConversationHandler.END

    await update.message.reply_text("📝 নোটিশের শিরোনাম লিখুন:")
    return ADD_NOTICE_TITLE


async def add_notice_title(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("❌ শিরোনাম ফাঁকা হতে পারে না, আবার লিখুন।")
        return ADD_NOTICE_TITLE

    context.user_data["notice_title"] = title
    await update.message.reply_text("📄 নোটিশের বিস্তারিত লিখুন:")
    return ADD_NOTICE_BODY


async def add_notice_body(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    body = update.message.text.strip()
    title = context.user_data.get("notice_title", "Untitled")
    created_at = get_bd_time().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO notices (title, body, created_at) VALUES (?, ?, ?)",
                (title, body, created_at),
            )
        await update.message.reply_text("✅ নোটিশ সংরক্ষণ করা হয়েছে।")
    except Exception as e:
        logger.error("Error inserting notice: %s", e)
        await update.message.reply_text("❌ নোটিশ সেভ করতে সমস্যা হয়েছে।")

    return ConversationHandler.END


# ------- Broadcast ---------


async def broadcast_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("⛔ শুধুমাত্র এডমিনদের জন্য।")
        return ConversationHandler.END

    await update.message.reply_text("📢 ব্রডকাস্ট মেসেজ/ফাইল পাঠান:")
    return BROADCAST_MSG


async def broadcast_finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        with get_db() as conn:
            users = conn.execute("SELECT chat_id FROM users").fetchall()
    except Exception as e:
        logger.error("Error fetching users for broadcast: %s", e)
        await update.message.reply_text("❌ ইউজার লিস্ট লোড করতে সমস্যা হয়েছে।")
        return ConversationHandler.END

    total = len(users)
    await update.message.reply_text(f"⏳ {total} জনকে পাঠানো হচ্ছে...")

    sent = 0
    for (chat_id,) in users:
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
            sent += 1
        except Exception as e:
            logger.warning("Failed to send broadcast to %s: %s", chat_id, e)

    await update.message.reply_text(f"✅ ব্রডকাস্ট সম্পন্ন হয়েছে। (সফল: {sent}/{total})")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# 7. JOBS & AUTOMATION
# ---------------------------------------------------------------------------


async def class_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    প্রতি মিনিটে চেক করবে: এখন থেকে ৫ মিনিট পর কোনো ক্লাস আছে কি না।
    থাকলে সব ইউজারকে রিমাইন্ডার পাঠাবে।
    """
    now = get_bd_time()
    target_time_obj = now + datetime.timedelta(minutes=5)
    target_time_str = target_time_obj.strftime("%H:%M")

    logger.info(
        "Checking class alerts at %s for Target: %s",
        now.strftime("%H:%M:%S"),
        target_time_str,
    )

    try:
        with get_db() as conn:
            classes = conn.execute(
                "SELECT course, room, teacher FROM daily_classes WHERE time_str = ?",
                (target_time_str,),
            ).fetchall()
            users = conn.execute("SELECT chat_id FROM users").fetchall()
    except Exception as e:
        logger.error("Error in class_reminder_job DB: %s", e)
        return

    if not classes:
        return

    logger.info("Found %d class(es). Sending alerts...", len(classes))

    for course, room, teacher in classes:
        text = (
            "⏰ *ক্লাস রিমাইন্ডার (৫ মিনিট বাকি)!*\n\n"
            f"বিষয়: *{course}*\n"
            f"সময়: {target_time_str}\n"
            f"রুম: {room}\n"
            f"শিক্ষক: {teacher}"
        )
        for (chat_id,) in users:
            try:
                await context.bot.send_message(
                    chat_id, text, parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning("Failed to send reminder to %s: %s", chat_id, e)


async def midnight_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """প্রতিদিন রাত ১২ টায় আজকের daily_classes ফাঁকা করে দেয়।"""
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM daily_classes")
        logger.info("[System] Daily classes reset.")
    except Exception as e:
        logger.error("Error in midnight_cleanup: %s", e)


# ---------------------------------------------------------------------------
# 8. TEXT HANDLER (MENU BUTTONS)
# ---------------------------------------------------------------------------


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if text == "📅 Full Routine":
        await show_full_routine(update, context)
    elif text == "🗓 Today Classes":
        await show_today_classes(update, context)
    elif text == "📢 Notices":
        await show_notices(update, context)
    elif text == "👨‍🏫 Teachers":
        await show_teachers(update, context)
    elif text == "📂 View Resources":
        await view_resources(update, context)
    elif "⚙" in text:
        # যদি নন-অ্যাডমিন হয়, ব্লক করবে
        if not is_admin(update.effective_user.username):
            await update.message.reply_text("⛔ শুধুমাত্র এডমিনদের জন্য।")
    else:
        await update.message.reply_text("❗ মেনু থেকে একটি অপশন সিলেক্ট করুন অথবা /start দিন।")


# ---------------------------------------------------------------------------
# 9. MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    jq = app.job_queue

    # Jobs: প্রতি ৬০ সেকেন্ডে রিমাইন্ডার চেক
    jq.run_repeating(class_reminder_job, interval=60, first=10)

    # Midnight Cleanup
    jq.run_daily(
        midnight_cleanup,
        time=datetime.time(0, 0, tzinfo=BD_TZ),
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))

    # Add Today Class Flow
    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^⚙ Add Today Class$"), add_class_start
                )
            ],
            states={
                ADD_CLASS_TIME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_class_time)
                ],
                ADD_CLASS_COURSE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_class_course)
                ],
                ADD_CLASS_ROOM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_class_room)
                ],
                ADD_CLASS_TEACHER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_class_finish)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )

    # Add Notice Flow
    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^⚙ Add Notice$"), add_notice_start
                )
            ],
            states={
                ADD_NOTICE_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_notice_title)
                ],
                ADD_NOTICE_BODY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_notice_body)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )

    # Broadcast Flow
    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^⚙ Broadcast$"), broadcast_start
                )
            ],
            states={
                BROADCAST_MSG: [
                    MessageHandler(
                        filters.ALL & ~filters.COMMAND, broadcast_finish
                    )
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )

    # Add Resources Flow
    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^⚙ Add Resources$"), add_res_start
                )
            ],
            states={
                ADD_RESOURCE_FILE: [
                    MessageHandler(
                        (filters.Document.ALL | filters.PHOTO)
                        & ~filters.COMMAND,
                        add_res_finish,
                    )
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )

    # General text handler
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    logger.info("Bot is running... (Upgraded)")
    app.run_polling()


if __name__ == "__main__":
    main()

