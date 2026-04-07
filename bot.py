import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import database

logging.basicConfig(level=logging.INFO)

# Состояния — ОНИ ДОЛЖНЫ БЫТЬ УНИКАЛЬНЫМИ
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
        # Простые команды
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("schedule", self.schedule_today))
        self.app.add_handler(CommandHandler("all_schedule", self.all_schedule))
        self.app.add_handler(CommandHandler("all_homework", self.all_homework))

        # Добавление ОДНОЙ пары
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("add_schedule", self.add_schedule_start)],
            states={
                ADD_SCHEDULE_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_week)],
                ADD_SCHEDULE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_day)],
                ADD_SCHEDULE_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_subject)],
                ADD_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_schedule_time)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True
        ))

        # Добавление НЕСКОЛЬКИХ пар
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("batch_schedule", self.batch_start)],
            states={
                BATCH_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.batch_week)],
                BATCH_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.batch_add)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True
        ))

        # Удаление пары
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("delete_schedule", self.delete_start)],
            states={DELETE_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.delete_choose)]},
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True
        ))

        # ДОМАШНЕЕ ЗАДАНИЕ
        self.app.add_handler(ConversationHandler(
            entry_points=[CommandHandler("add_homework", self.hw_start)],
            states={
                HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_subject)],
                HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_task)],
                HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.hw_deadline)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True
        ))

    async def start(self, update, context):
        self.db.add_user(update.effective_user.id, update.effective_user.username)
        text = """🤖 Бот-помощник для учёбы

📚 /add_schedule - добавить одну пару
📚 /batch_schedule - добавить несколько пар за раз
🗑 /delete_schedule - удалить пару
📝 /add_homework - добавить домашнее задание
📋 /all_homework - все домашние задания
📅 /schedule - расписание на сегодня
📖 /all_schedule - всё расписание
❌ /cancel - отменить действие"""
        await update.message.reply_text(text)

    async def schedule_today(self, update, context):
        user_id = update.effective_user.id
        weekday = datetime.now().weekday()
        week_type = "even"
        rows = self.db.get_schedule(user_id, week_type, weekday)
        if not rows:
            await update.message.reply_text("📭 На сегодня пар нет")
        else:
            msg = f"📚 {DAYS_RU[weekday]}:\n" + "\n".join([f"⏰ {t} - {s}" for s, t in rows])
            await update.message.reply_text(msg)

    async def all_schedule(self, update, context):
        user_id = update.effective_user.id
        msg = "📖 ПОЛНОЕ РАСПИСАНИЕ\n"
        for wt, wn in [("even", "Четная"), ("odd", "Нечетная")]:
            msg += f"\n◾ {wn} неделя:\n"
            has_any = False
            for d in range(7):
                rows = self.db.get_schedule(user_id, wt, d)
                if rows:
                    has_any = True
                    msg += f"\n📅 {DAYS_RU[d]}:\n"
                    msg += "\n".join([f"   {t} - {s}" for s, t in rows]) + "\n"
            if not has_any:
                msg += "   (нет пар)\n"
        await update.message.reply_text(msg)

    async def all_homework(self, update, context):
        user_id = update.effective_user.id
        homeworks = self.db.get_all_homeworks_for_user(user_id)
        
        if not homeworks:
            await update.message.reply_text("📭 Нет текущих домашних заданий")
            return
        
        msg = "📋 **ВСЕ ДОМАШНИЕ ЗАДАНИЯ**\n\n"
        
        for hw in homeworks:
            hw_id, user_id, subject, task, deadline_str, is_notified = hw
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            
            if deadline < now:
                status = "❌ ПРОСРОЧЕНО"
            elif (deadline - now).days == 0:
                status = "⚠️ СЕГОДНЯ"
            elif (deadline - now).days == 1:
                status = "⚠️ ЗАВТРА"
            else:
                status = f"📅 {deadline.strftime('%d.%m.%Y')}"
            
            msg += f"**{subject}**\n"
            msg += f"📝 {task}\n"
            msg += f"⏰ {status} {deadline.strftime('%H:%M')}\n"
            msg += "\n" + "─"*20 + "\n\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ========== ДОБАВЛЕНИЕ ОДНОЙ ПАРЫ ==========
    async def add_schedule_start(self, update, context):
        kb = [["Четная неделя", "Нечетная неделя"]]
        await update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return ADD_SCHEDULE_WEEK

    async def add_schedule_week(self, update, context):
        context.user_data['week'] = "even" if update.message.text == "Четная неделя" else "odd"
        kb = [[d] for d in DAYS_RU.values()]
        await update.message.reply_text("Выбери день:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return ADD_SCHEDULE_DAY

    async def add_schedule_day(self, update, context):
        context.user_data['day'] = DAYS_EN[update.message.text]
        await update.message.reply_text("Название предмета:", reply_markup=ReplyKeyboardRemove())
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
        await update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
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
            "Введи пары в формате:\nДЕНЬ ВРЕМЯ ПРЕДМЕТ\n\nПример:\nПонедельник 10:30 Математика\n\nКогда закончишь, напиши /done",
            reply_markup=ReplyKeyboardRemove()
        )
        return BATCH_ADD

    async def batch_add(self, update, context):
        text = update.message.text
        
        if text == "/done":
            await update.message.reply_text("✅ Готово!")
            context.user_data.clear()
            return ConversationHandler.END

        lines = text.strip().split('\n')
        saved = 0
        week = context.user_data.get('batch_week', 'even')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
            if m and m.group(1) in DAYS_EN:
                self.db.save_schedule(update.effective_user.id, week, DAYS_EN[m.group(1)], m.group(3), m.group(2))
                saved += 1
        
        await update.message.reply_text(f"✅ Сохранено пар: {saved}\n\nЕсли закончил — напиши /done")
        return BATCH_ADD

    # ========== УДАЛЕНИЕ ПАРЫ ==========
    async def delete_start(self, update, context):
        user_id = update.effective_user.id
        rows = self.db.get_all_schedule_for_user(user_id)
        if not rows:
            await update.message.reply_text("📭 Нет пар для удаления")
            return ConversationHandler.END

        context.user_data['delete_list'] = rows
        msg = "🗑 Выбери пару для удаления:\n\n"
        for r in rows:
            week_name = "Четная" if r[1] == "even" else "Нечетная"
            msg += f"{r[0]}. {week_name} неделя, {DAYS_RU[r[2]]}, {r[4]} - {r[3]}\n"
        msg += "\nВведи номер пары:"
        await update.message.reply_text(msg)
        return DELETE_CHOOSE

    async def delete_choose(self, update, context):
        try:
            num = int(update.message.text.strip())
            for r in context.user_data.get('delete_list', []):
                if r[0] == num:
                    self.db.cursor.execute("DELETE FROM schedule WHERE id = ?", (num,))
                    self.db.conn.commit()
                    await update.message.reply_text(f"✅ Удалена пара: {r[3]} в {r[4]}")
                    break
            else:
                await update.message.reply_text("❌ Пара не найдена")
        except:
            await update.message.reply_text("❌ Введи номер цифрой")
        context.user_data.clear()
        return ConversationHandler.END

    # ========== ДОМАШНЕЕ ЗАДАНИЕ ==========
    async def hw_start(self, update, context):
        await update.message.reply_text("📝 Введи название предмета:", reply_markup=ReplyKeyboardRemove())
        return HW_SUBJECT

    async def hw_subject(self, update, context):
        context.user_data['hw_subj'] = update.message.text
        await update.message.reply_text("📖 Опиши задание (что нужно сделать):")
        return HW_TASK

    async def hw_task(self, update, context):
        context.user_data['hw_task'] = update.message.text
        await update.message.reply_text("⏰ Введи дедлайн:\n\nГГГГ-ММ-ДД ЧЧ:ММ\nНапример: 2025-05-20 23:59\n\nИли: завтра 18:00")
        return HW_DEADLINE

    async def hw_deadline(self, update, context):
        text = update.message.text
        try:
            if "завтра" in text.lower():
                parts = text.split()
                time_parts = parts[-1].split(':')
                d = datetime.now() + timedelta(days=1)
                deadline = d.replace(hour=int(time_parts[0]), minute=int(time_parts[1]), second=0, microsecond=0)
            else:
                deadline = datetime.strptime(text, "%Y-%m-%d %H:%M")
            
            self.db.save_homework(
                update.effective_user.id,
                context.user_data['hw_subj'],
                context.user_data['hw_task'],
                deadline.strftime("%Y-%m-%d %H:%M:%S")
            )
            await update.message.reply_text(
                f"✅ Домашнее задание добавлено!\n\n"
                f"📚 Предмет: {context.user_data['hw_subj']}\n"
                f"📝 Задание: {context.user_data['hw_task']}\n"
                f"⏰ Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Посмотреть все задания: /all_homework"
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: неправильный формат даты.\n\n"
                f"Попробуй так: 2025-05-20 23:59\n"
                f"Или: завтра 18:00"
            )
            return HW_DEADLINE
        
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel(self, update, context):
        await update.message.reply_text("❌ Отменено", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END

    def run(self):
        print("=" * 40)
        print("🤖 БОТ ЗАПУЩЕН! 🚀")
        print("=" * 40)
        print("Команды:")
        print("  /start - приветствие")
        print("  /add_schedule - добавить одну пару")
        print("  /batch_schedule - добавить несколько пар")
        print("  /delete_schedule - удалить пару")
        print("  /add_homework - добавить задание")
        print("  /all_homework - все домашние задания")
        print("  /schedule - расписание на сегодня")
        print("  /all_schedule - всё расписание")
        print("=" * 40)
        self.app.run_polling()

if __name__ == "__main__":
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        print("❌ Ошибка: токен не найден")
    else:
        bot = ScheduleBot(TOKEN)
        bot.run()
