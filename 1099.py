import logging
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging (faqat xatolarni ko‘rsatadi)
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# =============================================
TOKEN = "8828629882:AAGPXxSrDtpP-uL1s0PpuUdrhIFs1Js5zVw"   # O‘zingiznikiga almashtiring
# =============================================

QUESTIONS_COUNT = 10
TIME_LIMIT = 20   # soniya


def generate_question():
    """10-99 oralig‘idagi tasodifiy son va uning kvadratini qaytaradi."""
    num = random.randint(10, 99)
    return num, num * num


def generate_options(correct):
    """To‘g‘ri javob + 4 ta noto‘g‘ri variant (5 ta) qaytaradi."""
    wrong = set()
    while len(wrong) < 4:
        offset = random.randint(-50, 50)
        if offset == 0:
            offset = random.randint(10, 30)
        candidate = correct + offset
        if candidate > 0 and candidate != correct:
            wrong.add(candidate)
    options = list(wrong) + [correct]
    random.shuffle(options)
    return options, correct


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start – testni boshlaydi."""
    # Foydalanuvchi ma'lumotlarini tozalash
    context.user_data.clear()

    # 10 ta savol tayyorlash
    questions = []
    for _ in range(QUESTIONS_COUNT):
        num, correct = generate_question()
        questions.append((num, correct))

    context.user_data["questions"] = questions
    context.user_data["current_index"] = 0
    context.user_data["score"] = 0
    context.user_data["answers"] = []
    context.user_data["timer_job"] = None

    await send_question(update, context)


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Joriy savolni yuboradi (xabar yoki callback orqali)."""
    data = context.user_data
    idx = data["current_index"]
    questions = data["questions"]

    if idx >= len(questions):
        await finish_test(update, context)
        return

    num, correct = questions[idx]
    options, correct_ans = generate_options(correct)

    # Tugmalar (5 ta variant)
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}) {opt}", callback_data=f"ans_{opt}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    data["correct_answer"] = correct_ans
    data["question_start"] = datetime.now()
    data["answered"] = False

    text = (
        f"📐 *{idx+1}/{len(questions)}-savol*\n\n"
        f"❓ *{num}* sonining kvadrati nechaga teng?\n\n"
        f"⏳ *Vaqt: {TIME_LIMIT} soniya*"
    )

    # Xabar yuborish (agar callback bo‘lsa, o‘sha xabarni tahrirlash yoki yangi)
    if update.callback_query:
        await update.callback_query.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    # Vaqt hisoblagichini ishga tushirish
    if data.get("timer_job"):
        data["timer_job"].schedule_removal()

    job = context.job_queue.run_once(
        timeout_callback,
        TIME_LIMIT,
        data={"user_id": update.effective_user.id, "chat_id": update.effective_chat.id}
    )
    data["timer_job"] = job


async def timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    """Vaqt tugaganda ishlaydi."""
    job_data = context.job.data
    user_id = job_data["user_id"]
    chat_id = job_data["chat_id"]

    user_data = context.application.user_data.get(user_id)
    if not user_data:
        return

    if user_data.get("answered", False):
        return

    idx = user_data["current_index"]
    questions = user_data["questions"]
    if idx >= len(questions):
        return

    correct_ans = user_data["correct_answer"]
    user_data["answers"].append((False, None, correct_ans))
    user_data["answered"] = True

    await context.bot.send_message(
        chat_id,
        f"⏰ *Vaqt tugadi!* To‘g‘ri javob: *{correct_ans}*\n\nKeyingi savolga o‘tamiz.",
        parse_mode="Markdown"
    )

    # Keyingi savolga o‘tish
    user_data["current_index"] += 1
    if user_data["current_index"] < len(user_data["questions"]):
        await send_question_by_user_id(context, user_id, chat_id)
    else:
        await finish_test_by_user_id(context, user_id, chat_id)


async def send_question_by_user_id(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    """Timer yoki boshqa joydan keyingi savolni yuborish."""
    user_data = context.application.user_data.get(user_id)
    if not user_data:
        return

    idx = user_data["current_index"]
    questions = user_data["questions"]
    if idx >= len(questions):
        await finish_test_by_user_id(context, user_id, chat_id)
        return

    num, correct = questions[idx]
    options, correct_ans = generate_options(correct)

    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}) {opt}", callback_data=f"ans_{opt}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    user_data["correct_answer"] = correct_ans
    user_data["question_start"] = datetime.now()
    user_data["answered"] = False

    text = (
        f"📐 *{idx+1}/{len(questions)}-savol*\n\n"
        f"❓ *{num}* sonining kvadrati nechaga teng?\n\n"
        f"⏳ *Vaqt: {TIME_LIMIT} soniya*"
    )

    await context.bot.send_message(
        chat_id, text, reply_markup=reply_markup, parse_mode="Markdown"
    )

    if user_data.get("timer_job"):
        user_data["timer_job"].schedule_removal()

    job = context.job_queue.run_once(
        timeout_callback,
        TIME_LIMIT,
        data={"user_id": user_id, "chat_id": chat_id}
    )
    user_data["timer_job"] = job


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Javob tugmasi bosilganda."""
    query = update.callback_query
    await query.answer()

    user_data = context.user_data

    # Agar allaqachon javob berilgan bo‘lsa
    if user_data.get("answered", False):
        await query.edit_message_text("Siz allaqachon javob berdingiz yoki vaqt tugadi.")
        return

    # Javobni olish
    try:
        user_answer = int(query.data[4:])  # "ans_3969" -> 3969
    except ValueError:
        await query.edit_message_text("Xatolik yuz berdi. /start bosing.")
        return

    correct_ans = user_data.get("correct_answer")
    if correct_ans is None:
        await query.edit_message_text("Xatolik. /start bosing.")
        return

    # Vaqtni tekshirish
    start_time = user_data.get("question_start")
    if not start_time:
        await query.edit_message_text("Xatolik. /start bosing.")
        return

    elapsed = (datetime.now() - start_time).total_seconds()
    if elapsed > TIME_LIMIT:
        await query.edit_message_text(
            f"⏰ Vaqt tugadi! To‘g‘ri javob: {correct_ans}"
        )
        user_data["answers"].append((False, None, correct_ans))
        user_data["answered"] = True
        # Timer jobni to‘xtatish
        if user_data.get("timer_job"):
            user_data["timer_job"].schedule_removal()
            user_data["timer_job"] = None
        # Keyingi savol
        user_data["current_index"] += 1
        if user_data["current_index"] < len(user_data["questions"]):
            await send_question(update, context)
        else:
            await finish_test(update, context)
        return

    # To‘g‘rilikni tekshirish
    correct = (user_answer == correct_ans)
    user_data["answers"].append((correct, user_answer, correct_ans))
    user_data["answered"] = True

    if correct:
        user_data["score"] += 1
        await query.edit_message_text(
            f"✅ *To‘g‘ri!* Javob: *{correct_ans}*",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"❌ *Xato.* To‘g‘ri javob: *{correct_ans}*\n\n📝 Siz: {user_answer}",
            parse_mode="Markdown"
        )

    # Timer jobni to‘xtatish
    if user_data.get("timer_job"):
        user_data["timer_job"].schedule_removal()
        user_data["timer_job"] = None

    # Keyingi savol
    user_data["current_index"] += 1
    if user_data["current_index"] < len(user_data["questions"]):
        await send_question(update, context)
    else:
        await finish_test(update, context)


async def finish_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test yakunida hisobotni ko‘rsatish."""
    user_data = context.user_data
    await send_report(update, context, user_data)


async def finish_test_by_user_id(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    """Timer tugagandan so‘ng hisobotni yuborish."""
    user_data = context.application.user_data.get(user_id)
    if not user_data:
        return
    # Bu yerda update yo‘q, shuning uchun bot.send_message dan foydalanamiz
    report = generate_report(user_data)
    keyboard = [[InlineKeyboardButton("🔄 Qayta boshlash", callback_data="restart")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id, report, parse_mode="Markdown", reply_markup=reply_markup
    )


async def send_report(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    """Hisobot matnini tayyorlab yuboradi."""
    report = generate_report(user_data)
    keyboard = [[InlineKeyboardButton("🔄 Qayta boshlash", callback_data="restart")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            report, parse_mode="Markdown", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            report, parse_mode="Markdown", reply_markup=reply_markup
        )


def generate_report(user_data: dict) -> str:
    """Hisobot matnini yaratadi."""
    total = len(user_data["answers"])
    correct_count = sum(1 for a in user_data["answers"] if a[0])

    report = f"🏆 *Test yakunlandi!*\n\n"
    report += f"📊 *Natijalar:*\n"
    report += f"✅ To‘g‘ri javoblar: *{correct_count}/{total}*\n"
    report += f"📈 Foiz: *{correct_count/total*100:.1f}%*\n\n"
    report += "📋 *Batafsil:*\n"
    for i, (is_correct, user_ans, correct_ans) in enumerate(user_data["answers"], 1):
        emoji = "✅" if is_correct else "❌"
        user_ans_str = user_ans if user_ans is not None else "(vaqt tugadi)"
        report += f"{i}. {emoji} Siz: {user_ans_str} | To‘g‘ri: {correct_ans}\n"
    return report


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qayta boshlash tugmasi."""
    query = update.callback_query
    await query.answer()
    await start(update, context)


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^ans_"))
    app.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))

    print("✅ Bot ishga tushdi. Telegramda /start yuboring.")
    app.run_polling()


if __name__ == "__main__":
    main()
