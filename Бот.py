import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import sqlite3
from sqlite3 import Error
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
BOT_TOKEN = "7887719821:AAFA4DzCv4GL8Wax-JJPVyBPvdQU-uyGlGA"
ADMIN_IDS = {5237959867, 927652138, 728292764}
DB_FILE = 'school.db'
user_data = {}


async def get_classes():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT class FROM students ORDER BY class')
        classes = [row[0] for row in cursor.fetchall()]
        logger.info(f"Available classes: {classes}")
        return classes
    except Error as e:
        logger.error(f"Database error in get_classes: {e}")
        return []
    finally:
        if conn:
            conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} ({user.full_name}) started the bot")
    classes = await get_classes()

    if not classes:
        await update.message.reply_text("В базе данных нет классов.")
        return

    keyboard = [[cls] for cls in classes]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Выберите класс:", reply_markup=reply_markup)


async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    class_name = update.message.text.strip()
    logger.info(f"User {user.id} selected class: {class_name}")
    classes = await get_classes()
    if class_name not in classes:
        await update.message.reply_text(f"Класс {class_name} не найден. Выберите класс из списка.")
        return

    user_data[user.id] = {'class': class_name}
    await show_students(update, context, class_name)


async def show_students(update: Update, context: ContextTypes.DEFAULT_TYPE, class_name: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, full_name FROM students WHERE class = ? ORDER BY full_name',
            (class_name,)
        )
        students = cursor.fetchall()

        logger.info(f"Found {len(students)} students in class {class_name}")

        if not students:
            await update.message.reply_text(f"В классе {class_name} нет учеников.")
            return

        keyboard = [[student[1]] for student in students]
        if update.effective_user.id in ADMIN_IDS:
            keyboard.append(["Сбросить оценки", "Вывести все оценки"])

        keyboard.append(["Назад"])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(
            f"Ученики класса {class_name}:",
            reply_markup=reply_markup
        )
    except Error as e:
        logger.error(f"Database error in show_students: {e}")
        await update.message.reply_text("Произошла ошибка при загрузке данных.")
    finally:
        if conn:
            conn.close()


async def handle_student_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    student_name = update.message.text.strip()

    logger.info(f"User {user.id} selected student: {student_name}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, plus_count, minus_count FROM students WHERE full_name = ?',
            (student_name,)
        )
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text("Ученик не найден.")
            return

        student_id, plus, minus = result

        if user.id in ADMIN_IDS:
            keyboard = [
                [
                    InlineKeyboardButton("+", callback_data=f"plus_{student_id}"),
                    InlineKeyboardButton("-", callback_data=f"minus_{student_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"{student_name}\n'+' = {plus}\n'-' = {minus}",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"{student_name}:\n+ {plus}\n- {minus}"
            )
    except Error as e:
        logger.error(f"Database error in handle_student_selection: {e}")
        await update.message.reply_text("Произошла ошибка при загрузке данных.")
    finally:
        if conn:
            conn.close()


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if user.id not in ADMIN_IDS:
        logger.warning(f"Unauthorized button click by user {user.id}")
        await query.edit_message_text("У вас нет прав для этого действия.")
        return

    action, student_id = query.data.split('_')
    student_id = int(student_id)

    logger.info(f"Admin {user.id} clicked {action} for student {student_id}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if action == "plus":
            cursor.execute('UPDATE students SET plus_count = plus_count + 1 WHERE id = ?', (student_id,))
        elif action == "minus":
            cursor.execute('UPDATE students SET minus_count = minus_count + 1 WHERE id = ?', (student_id,))
        conn.commit()
        cursor.execute(
            'SELECT full_name, plus_count, minus_count FROM students WHERE id = ?',
            (student_id,)
        )
        student = cursor.fetchone()

        if not student:
            await query.edit_message_text("Ученик не найден.")
            return

        keyboard = [
            [
                InlineKeyboardButton("+", callback_data=f"plus_{student_id}"),
                InlineKeyboardButton("-", callback_data=f"minus_{student_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"{student[0]}\n'+' = {student[1]}\n'-' = {student[2]}",
            reply_markup=reply_markup
        )
    except Error as e:
        logger.error(f"Database error in handle_button_click: {e}")
        await query.edit_message_text("Произошла ошибка при обновлении оценки.")
    finally:
        if conn:
            conn.close()


async def handle_reset_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        logger.warning(f"Unauthorized reset attempt by user {user.id}")
        await update.message.reply_text("У вас нет прав для этого действия.")
        return
    class_name = user_data.get(user.id, {}).get('class')
    if not class_name:
        await update.message.reply_text("Сначала выберите класс.")
        return

    logger.info(f"Admin {user.id} requested reset for class {class_name}")

    keyboard = [["Сбросить", "Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"Вы уверены, что хотите сбросить оценки для класса {class_name}?",
        reply_markup=reply_markup
    )


async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    class_name = user_data.get(user.id, {}).get('class')

    if not class_name:
        await update.message.reply_text("Сначала выберите класс.")
        return

    logger.info(f"Admin {user.id} confirmed reset for class {class_name}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE students SET plus_count = 0, minus_count = 0 WHERE class = ?',
            (class_name,)
        )
        conn.commit()

        await update.message.reply_text(
            f"Оценки для класса {class_name} сброшены."
        )
        await show_students(update, context, class_name)
    except Error as e:
        logger.error(f"Database error in confirm_reset: {e}")
        await update.message.reply_text("Произошла ошибка при сбросе оценок.")
    finally:
        if conn:
            conn.close()


async def show_all_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        logger.warning(f"Unauthorized grades view attempt by user {user.id}")
        await update.message.reply_text("У вас нет прав для этого действия.")
        return

    class_name = user_data.get(user.id, {}).get('class')
    if not class_name:
        await update.message.reply_text("Сначала выберите класс.")
        return

    logger.info(f"Admin {user.id} requested all grades for class {class_name}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT full_name, plus_count, minus_count FROM students WHERE class = ? ORDER BY full_name',
            (class_name,)
        )
        students = cursor.fetchall()

        if not students:
            await update.message.reply_text("В этом классе нет учеников.")
            return

        message = f"Оценки класса {class_name}:\n\n"
        for student in students:
            message += f"{student[0]}: '+' = {student[1]}, '-' = {student[2]}\n"

        await update.message.reply_text(message)
    except Error as e:
        logger.error(f"Database error in show_all_grades: {e}")
        await update.message.reply_text("Произошла ошибка при загрузке данных.")
    finally:
        if conn:
            conn.close()


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    application.add_handler(MessageHandler(filters.Regex(r'^Назад$'), back_to_start))
    application.add_handler(MessageHandler(filters.Regex(r'^Сбросить оценки$'), handle_reset_request))
    application.add_handler(MessageHandler(filters.Regex(r'^Вывести все оценки$'), show_all_grades))
    application.add_handler(MessageHandler(filters.Regex(r'^Сбросить$'), confirm_reset))

    class_filter = filters.TEXT & ~filters.COMMAND
    application.add_handler(MessageHandler(
        class_filter & filters.Regex(r'^(10Г|11И)$'),
        handle_class_selection
    ))

    application.add_handler(MessageHandler(
        class_filter,
        handle_student_selection
    ))

    application.add_handler(CallbackQueryHandler(handle_button_click))

    logger.info("Starting bot...")
    application.run_polling()


if __name__ == '__main__':
    main()