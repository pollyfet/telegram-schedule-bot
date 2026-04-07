import os
import logging
import re
import asyncio
import datetime
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import database

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Состояния
(
    ADD_SCHEDULE_WEEK, ADD_SCHEDULE_DAY, ADD_SCHEDULE_SUBJECT, ADD_SCHEDULE_TIME,
    BATCH_WEEK, BATCH_ADD,
    DELETE_CHOOSE,
    HW_SUBJECT, HW_TASK, HW_DEADLINE
) = range(10)

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}
DAYS_EN = {v: k for k, v in DAYS_RU.items()}

class ScheduleBot:
    def __init__(self, token):
        self.db = database.Database()
        self.app = Application.builder().token(token).build()
        self.setup_handlers()

    def setup_handlers(self):
        # Общий fallback для всех диалогов
        common_fallbacks = [
            CommandHandler("cancel", self.cancel),
            CommandHandler("start", self.start),
        ]
        
        # Простые команды
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("schedule", self.schedule_today))
        self.app.add_handler(CommandHandler("all_schedule", self.all_schedule))
        self.app.add_handler(CommandHandler("all_homework", self.all_homework))

        # Добавление одной пары
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("add_schedule", self.add_schedule_start)],
            states={
                ADD_SCHEDULE_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_week)],
                ADD_SCHEDULE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_day)],
                ADD_SCHEDULE_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_subject)],
                ADD_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_time)],
            },
            fallbacks=common_fallbacks,
            allow_reentry=True
        ))

        # Добавление нескольких пар
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("batch_schedule", self.batch_start)],
            states={
                BATCH_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.batch_week)],
                BATCH_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.batch_add)],
            },
            fallbacks=common_fallbacks,
            allow_reentry=True
        ))

        # Удаление пары
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("delete_schedule", self.delete_start)],
            states={DELETE_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.delete_choose)]},
            fallbacks=common_fallbacks,
            allow_reentry=True
        ))

        # Добавление домашнего задания
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("add_homework", self.hw_start)],
            states={
                HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_subject)],
                HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_task)],
                HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_deadline)],
            },
            fallbacks=common_fallbacks,
            allow_reentry=True
        ))

    async def start(self, update, context):
        """Обработчик команды /start - сбрасывает любой диалог"""
        # Очищаем данные пользователя
        context.user_data.clear()
        
        # Добавляем пользователя в БД
        self.db.add_user(update.effective_user.id, update.effective_user.username)
        
        text = """🤖 *Бот-помощник для учёбы*

📚 /add_schedule - добавить одну пару
📚 /batch_schedule - добавить несколько пар за раз
🗑 /delete_schedule - удалить пару
📝 /add_homework - добавить домашнее задание
📋 /all_homework - все домашние задания
📅 /schedule - расписание на сегодня
📖 /all_schedule - всё расписание
❌ /cancel - отменить действие

_Бот автоматически напомнит о дедлайнах за сутки_"""
        
        await update.message.reply_text(text, parse_mode="Markdown")

    async def schedule_today(self, update, context):
        """Расписание на сегодня"""
        user_id = update.effective_user.id
        weekday = datetime.now().weekday()
        week_type = "even" if (datetime.now().isocalendar()[1] % 2 == 0) else "odd"
        
        rows = self.db.get_schedule(user_id, week_type, weekday)
        
        if not rows:
            await update.message.reply_text("📭 На сегодня пар нет")
        else:
            msg = f"📚 *{DAYS_RU[weekday]}*:\n"
            msg += "\n".join([f"⏰ {t} - {s}" for s, t in rows])
            await update.message.reply_text(msg, parse_mode="Markdown")

    async def all_schedule(self, update, context):
        """Всё расписание"""
        user_id = update.effective_user.id
        msg = "📖 *ПОЛНОЕ РАСПИСАНИЕ*\n"
        
        for wt, wn in [("even", "Четная"), ("odd", "Нечетная")]:
            msg += f"\n◾ *{wn} неделя:*\n"
            has_any = False
            for d in range(7):
                rows = self.db.get_schedule(user_id, wt, d)
                if rows:
                    has_any = True
                    msg += f"\n📅 *{DAYS_RU[d]}*:\n"
                    msg += "\n".join([f"   {t} - {s}" for s, t in rows]) + "\n"
            if not has_any:
                msg += "   (нет пар)\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def all_homework(self, update, context):
        """Все домашние задания"""
        user_id = update.effective_user.id
        homeworks = self.db.get_all_homeworks_for_user(user_id)
        
        if not homeworks:
            await update.message.reply_text("📭 Нет текущих домашних заданий")
            return
        
        msg = "📋 *ВСЕ ДОМАШНИЕ ЗАДАНИЯ*\n\n"
        
        for hw in homeworks:
            hw_id, user_id, subject, task, deadline_str, is_notified = hw
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            
            if deadline < now:
                status = "❌ *ПРОСРОЧЕНО*"
            elif (deadline - now).days == 0:
                status = "⚠️ *СЕГОДНЯ*"
            elif (deadline - now).days == 1:
                status = "⚠️ *ЗАВТРА*"
            else:
                status = f"📅 {deadline.strftime('%d.%m.%Y')}"
            
            msg += f"*{subject}*\n"
            msg += f"📝 {task}\n"
            msg += f"⏰ {status} {deadline.strftime('%H:%M')}\n"
            msg += "\n" + "─"*20 + "\n\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ========== ДОБАВЛЕНИЕ ОДНОЙ ПАРЫ ==========
    async def add_schedule_start(self, update, context):
        kb = [["Четная неделя", "Нечетная неделя"]]
        await update.message.reply_text(
            "Выбери тип недели:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return ADD_SCHEDULE_WEEK

    async def add_schedule_week(self, update, context):
        text = update.message.text
        if text == "Четная неделя":
            context.user_data['week'] = "even"
        elif text == "Нечетная неделя":
            context.user_data['week'] = "odd"
        else:
            await update.message.reply_text("Пожалуйста, нажми на кнопку")
            return ADD_SCHEDULE_WEEK
        
        kb = [[d] for d in DAYS_RU.values()]
        await update.message.reply_text(
            "Выбери день:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return ADD_SCHEDULE_DAY

    async def add_schedule_day(self, update, context):
        context.user_data['day'] = DAYS_EN[update.message.text]
        await update.message.reply_text(
            "Название предмета:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_SCHEDULE_SUBJECT

    async def add_schedule_subject(self, update, context):
        context.user_data['subject'] = update.message.text
        await update.message.reply_text("Время (например: 10:30):")
        return ADD_SCHEDULE_TIME

    async def add_schedule_time(self, update, context):
        self.db.save_schedule(
            update.effective_user.id,
            context.user_data['week'],
            context.user_data['day'],
            context.user_data['subject'],
            update.message.text
        )
        await update.message.reply_text(f"✅ Добавлено: {context.user_data['subject']}")
        context.user_data.clear()
        return ConversationHandler.END

    # ========== ДОБАВЛЕНИЕ НЕСКОЛЬКИХ ПАР ==========
    async def batch_start(self, update, context):
        kb = [["Четная неделя", "Нечетная неделя"]]
        await update.message.reply_text(
            "Выбери тип недели:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return BATCH_WEEK

    async def batch_week(self, update, context):
        text = update.message.text
        if text == "Четная неделя":
            context.user_data['batch_week'] = "even"
        elif text == "Нечетная неделя":
            context.user_data['batch_week'] = "odd"
        else:
            await update.message.reply_text("Пожалуйста, нажми на кнопку")
            return BATCH_WEEK
        
        await update.message.reply_text(
            "📝 *Введи пары в формате:*\n"
            "`ДЕНЬ ВРЕМЯ ПРЕДМЕТ`\n\n"
            "*Пример:*\n"
            "`Понедельник 10:30 Математика`\n"
            "`Вторник 14:00 Физика`\n\n"
            "Можно ввести несколько строк сразу.\n\n"
            "✅ Когда закончишь - напиши `/done`\n"
            "❌ Чтобы отменить - `/cancel`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return BATCH_ADD

    async def batch_add(self, update, context):
        text = update.message.text.strip()
        
        # Выход из режима
        if text.lower() == "/done":
            await update.message.reply_text("✅ Добавление пар завершено!")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Отмена
        if text.lower() == "/cancel":
            await update.message.reply_text("❌ Добавление пар отменено.")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Защита от других команд
        if text.startswith("/"):
            await update.message.reply_text(
                f"⚠️ Вы в режиме добавления пар.\n\n"
                f"Доступно:\n"
                f"• `/done` - завершить\n"
                f"• `/cancel` - отменить\n\n"
                f"Или введите пары в формате:\n"
                f"`Понедельник 10:30 Математика`",
                parse_mode="Markdown"
            )
            return BATCH_ADD
        
        lines = text.split('\n')
        saved = 0
        week = context.user_data.get('batch_week', 'even')
        errors = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Регулярное выражение для парсинга
            match = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
            if match and match.group(1) in DAYS_EN:
                day_name = match.group(1)
                time = match.group(2)
                subject = match.group(3)
                self.db.save_schedule(
                    update.effective_user.id,
                    week,
                    DAYS_EN[day_name],
                    subject,
                    time
                )
                saved += 1
            else:
                errors.append(line)
        
        if saved == 0:
            await update.message.reply_text(
                f"❌ *Не распознано ни одной пары*\n\n"
                f"*Правильный формат:*\n"
                f"`ДЕНЬ ВРЕМЯ ПРЕДМЕТ`\n\n"
                f"*Пример:*\n"
                f"`Понедельник 10:30 Математика`\n\n"
                f"Ты ввёл:\n`{text[:100]}`\n\n"
                f"✅ Напиши `/done` для выхода\n"
                f"❌ Или `/cancel` для отмены",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"✅ *Сохранено пар: {saved}*\n\n"
                f"Можно добавить ещё или написать `/done` для завершения.",
                parse_mode="Markdown"
            )
        
        return BATCH_ADD

    # ========== УДАЛЕНИЕ ПАРЫ ==========
    async def delete_start(self, update, context):
        user_id = update.effective_user.id
        rows = self.db.get_all_schedule_for_user(user_id)
        
        if not rows:
            await update.message.reply_text("📭 Нет пар для удаления")
            return ConversationHandler.END

        context.user_data['delete_list'] = rows
        msg = "🗑 *Выбери пару для удаления:*\n\n"
        
        for r in rows:
            week_name = "Четная" if r[1] == "even" else "Нечетная"
            msg += f"`{r[0]}.` {week_name} неделя, {DAYS_RU[r[2]]}, {r[4]} - {r[3]}\n"
        
        msg += "\nВведи номер пары:"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return DELETE_CHOOSE

    async def delete_choose(self, update, context):
        try:
            num = int(update.message.text.strip())
            deleted = False
            
            for r in context.user_data.get('delete_list', []):
                if r[0] == num:
                    self.db.cursor.execute("DELETE FROM schedule WHERE id = ?", (num,))
                    self.db.conn.commit()
                    await update.message.reply_text(f"✅ Удалена пара: {r[3]} в {r[4]}")
                    deleted = True
                    break
            
            if not deleted:
                await update.message.reply_text("❌ Пара с таким номером не найдена")
        except ValueError:
            await update.message.reply_text("❌ Введи номер цифрой")
        
        context.user_data.clear()
        return ConversationHandler.END

    # ========== ДОМАШНЕЕ ЗАДАНИЕ ==========
    async def hw_start(self, update, context):
        await update.message.reply_text(
            "📝 *Добавление домашнего задания*\n\nВведи название предмета:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return HW_SUBJECT

    async def hw_subject(self, update, context):
        if update.message.text.startswith('/'):
            await update.message.reply_text("❌ Команда не доступна в режиме добавления. Напиши /cancel для выхода.")
            return HW_SUBJECT
        
        context.user_data['hw_subj'] = update.message.text
        await update.message.reply_text(
            "📖 Опиши задание (что нужно сделать):"
        )
        return HW_TASK

    async def hw_task(self, update, context):
        if update.message.text.startswith('/'):
            await update.message.reply_text("❌ Команда не доступна. Напиши /cancel для выхода.")
            return HW_TASK
        
        context.user_data['hw_task'] = update.message.text
        await update.message.reply_text(
            "⏰ *Введи дедлайн:*\n\n"
            "Варианты:\n"
            "• `2025-05-20 23:59`\n"
            "• `завтра 18:00`\n"
            "• `20.05.2025 23:59`",
            parse_mode="Markdown"
        )
        return HW_DEADLINE

    async def hw_deadline(self, update, context):
        text = update.message.text.strip().lower()
        
        try:
            # Обработка "завтра"
            if "завтра" in text:
                parts = text.split()
                time_str = parts[-1]
                time_parts = time_str.split(':')
                d = datetime.now() + timedelta(days=1)
                deadline = d.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=0,
                    microsecond=0
                )
            else:
                # Попробуем разные форматы
                for fmt in ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        deadline = datetime.strptime(text, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError("Неверный формат даты")
            
            # Сохраняем в БД
            self.db.save_homework(
                update.effective_user.id,
                context.user_data['hw_subj'],
                context.user_data['hw_task'],
                deadline.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            await update.message.reply_text(
                f"✅ *Домашнее задание добавлено!*\n\n"
                f"📚 Предмет: {context.user_data['hw_subj']}\n"
                f"📝 Задание: {context.user_data['hw_task']}\n"
                f"⏰ Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Посмотреть все задания: /all_homework",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ *Ошибка:* неправильный формат даты.\n\n"
                f"*Правильные примеры:*\n"
                f"• `2025-05-20 23:59`\n"
                f"• `20.05.2025 23:59`\n"
                f"• `завтра 18:00`",
                parse_mode="Markdown"
            )
            return HW_DEADLINE
        
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel(self, update, context):
        """Отмена текущего действия"""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Действие отменено",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    async def check_deadlines(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверка дедлайнов (запускается каждый день в 9:00)"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # Ищем задания с дедлайном завтра
        self.db.cursor.execute("""
            SELECT user_id, subject, task, deadline 
            FROM homework 
            WHERE date(deadline) = date(?, 'localtime')
            AND is_notified = 0
        """, (tomorrow.strftime("%Y-%m-%d"),))
        
        homeworks = self.db.cursor.fetchall()
        
        for hw in homeworks:
            user_id, subject, task, deadline = hw
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ *НАПОМИНАНИЕ О ДЕДЛАЙНЕ!* ⚠️\n\n"
                         f"📚 Предмет: {subject}\n"
                         f"📝 Задание: {task}\n"
                         f"⏰ Дедлайн: {deadline_dt.strftime('%d.%m.%Y в %H:%M')}\n\n"
                         f"❕ Остался 1 день!",
                    parse_mode="Markdown"
                )
                
                # Помечаем как уведомленное
                self.db.cursor.execute("""
                    UPDATE homework 
                    SET is_notified = 1 
                    WHERE user_id = ? AND subject = ? AND deadline = ?
                """, (user_id, subject, deadline))
                self.db.conn.commit()
                
                logging.info(f"Уведомление отправлено пользователю {user_id} о задании {subject}")
                
            except Exception as e:
                logging.error(f"Ошибка отправки уведомления: {e}")

    def run(self):
        """Запуск бота"""
        async def post_init(application):
            # Удаляем webhook
            await application.bot.delete_webhook(drop_pending_updates=True)
            logging.info("✅ Webhook удалён")
            
            # Настраиваем планировщик уведомлений
            job_queue = application.job_queue
            if job_queue:
                # Запускаем проверку каждый день в 9:00
                job_queue.run_daily(
                    self.check_deadlines,
                    time=datetime.time(hour=9, minute=0),
                    days=tuple(range(7))
                )
                logging.info("✅ Планировщик уведомлений запущен (каждый день в 9:00)")
                
                # Также запускаем проверку через 10 секунд после старта (для теста)
                job_queue.run_once(self.check_deadlines, when=10)
        
        # Устанавливаем post_init
        self.app.post_init = post_init
        
        # Запускаем бота
        logging.info("=" * 50)
        logging.info("🤖 БОТ ЗАПУЩЕН! 🚀")
        logging.info("=" * 50)
        logging.info("Команды:")
        logging.info("  /start - приветствие и сброс")
        logging.info("  /add_schedule - добавить одну пару")
        logging.info("  /batch_schedule - добавить несколько пар")
        logging.info("  /delete_schedule - удалить пару")
        logging.info("  /add_homework - добавить задание")
        logging.info("  /all_homework - все домашние задания")
        logging.info("  /schedule - расписание на сегодня")
        logging.info("  /all_schedule - всё расписание")
        logging.info("=" * 50)
        
        self.app.run_polling()

if __name__ == "__main__":
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        print("❌ Ошибка: токен не найден")
        print("Установи переменную окружения TOKEN")
    else:
        bot = ScheduleBot(TOKEN)
        bot.run()
