import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
import database
import re
import os

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Состояния для разговора с ботом
WEEK_TYPE, DAY, SUBJECT, TIME = range(4)
HW_SUBJECT, HW_TASK, HW_DEADLINE = range(4, 7)
BATCH_SCHEDULE = range(7, 8)
DELETE_SCHEDULE = range(8, 9)

DAYS_RU = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье"
}

DAYS_EN = {
    "Понедельник": 0,
    "Вторник": 1,
    "Среда": 2,
    "Четверг": 3,
    "Пятница": 4,
    "Суббота": 5,
    "Воскресенье": 6
}

class ScheduleBot:
    def __init__(self, token):
        self.token = token
        self.db = database.Database()
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("schedule", self.show_today_schedule))
        self.application.add_handler(CommandHandler("all_schedule", self.show_all_schedule))
        
        schedule_conv = ConversationHandler(
            entry_points=[CommandHandler("add_schedule", self.add_schedule_start)],
            states={
                WEEK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_week_type)],
                DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_day)],
                SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_subject)],
                TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_time)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(schedule_conv)
        
        batch_conv = ConversationHandler(
            entry_points=[CommandHandler("batch_schedule", self.batch_schedule_start)],
            states={
                BATCH_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_batch_schedule)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(batch_conv)
        
        delete_conv = ConversationHandler(
            entry_points=[CommandHandler("delete_schedule", self.delete_schedule_start)],
            states={
                DELETE_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_delete_schedule)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(delete_conv)
        
        hw_conv = ConversationHandler(
            entry_points=[CommandHandler("add_homework", self.add_homework_start)],
            states={
                HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_hw_subject)],
                HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_hw_task)],
                HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_hw_deadline)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(hw_conv)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.add_user(user.id, user.username)
        
        welcome_text = f"""Привет, {user.first_name}! 👋

Я бот-помощник для учёбы. Вот что я умею:

📚 /add_schedule - добавить одну пару
📚 /batch_schedule - добавить несколько пар за раз
🗑 /delete_schedule - удалить пару
📝 /add_homework - добавить домашнее задание
📅 /schedule - расписание на сегодня
📖 /all_schedule - всё расписание
❌ /cancel - отменить действие"""
        
        await update.message.reply_text(welcome_text)
    
    async def batch_schedule_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["Четная неделя", "Нечетная неделя"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери тип недели:", reply_markup=reply_markup)
        return BATCH_SCHEDULE
    
    async def process_batch_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if text == "Четная неделя":
            context.user_data['batch_week_type'] = "even"
            await update.message.reply_text(
                "Введи пары в формате:\nДЕНЬ ВРЕМЯ ПРЕДМЕТ\n\nПример:\nПонедельник 10:30 Математика\n\nКогда закончишь, напиши /done",
                reply_markup=ReplyKeyboardRemove()
            )
            return BATCH_SCHEDULE
        elif text == "Нечетная неделя":
            context.user_data['batch_week_type'] = "odd"
            await update.message.reply_text(
                "Введи пары в формате:\nДЕНЬ ВРЕМЯ ПРЕДМЕТ\n\nПример:\nПонедельник 10:30 Математика\n\nКогда закончишь, напиши /done",
                reply_markup=ReplyKeyboardRemove()
            )
            return BATCH_SCHEDULE
        elif text == "/done":
            await update.message.reply_text("✅ Добавление завершено!")
            context.user_data.clear()
            return ConversationHandler.END
        else:
            lines = text.strip().split('\n')
            saved = 0
            week_type = context.user_data.get('batch_week_type', 'even')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                match = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
                if match:
                    day_name = match.group(1)
                    time = match.group(2)
                    subject = match.group(3)
                    if day_name in DAYS_EN:
                        self.db.save_schedule(update.effective_user.id, week_type, DAYS_EN[day_name], subject, time)
                        saved += 1
            
            await update.message.reply_text(f"✅ Сохранено пар: {saved}\nМожешь добавить еще или напиши /done")
            return BATCH_SCHEDULE
    
    async def delete_schedule_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        items = self.db.get_all_schedule_for_user(user_id)
        
        if not items:
            await update.message.reply_text("📭 Нет пар для удаления!")
            return ConversationHandler.END
        
        context.user_data['delete_items'] = items
        
        week_names = {"even": "Четная", "odd": "Нечетная"}
        message = "🗑 Выбери пару для удаления:\n\n"
        
        for item in items:
            message += f"{item[0]}. {week_names[item[1]]} неделя, {DAYS_RU[item[2]]}, {item[4]} - {item[3]}\n"
        
        message += "\nВведи номер пары:"
        await update.message.reply_text(message)
        return DELETE_SCHEDULE
    
    async def process_delete_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            num = int(update.message.text)
            items = context.user_data.get('delete_items', [])
            
            for item in items:
                if item[0] == num:
                    self.db.cursor.execute("DELETE FROM schedule WHERE id = ?", (num,))
                    self.db.conn.commit()
                    await update.message.reply_text(f"✅ Удалена пара: {item[3]} в {item[4]}")
                    break
            else:
                await update.message.reply_text("❌ Пара не найдена!")
        except:
            await update.message.reply_text("❌ Введи номер цифрой!")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def add_schedule_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["Четная неделя", "Нечетная неделя"]]
        await update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return WEEK_TYPE
    
    async def get_week_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['week_type'] = "even" if update.message.text == "Четная неделя" else "odd"
        keyboard = [["Понедельник", "Вторник", "Среда"], ["Четверг", "Пятница", "Суббота"], ["Воскресенье"]]
        await update.message.reply_text("Выбери день:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return DAY
    
    async def get_day(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['day'] = DAYS_EN[update.message.text]
        await update.message.reply_text("Название предмета:", reply_markup=ReplyKeyboardRemove())
        return SUBJECT
    
    async def get_subject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['subject'] = update.message.text
        await update.message.reply_text("Время (например: 10:30):")
        return TIME
    
    async def get_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.db.save_schedule(
            update.effective_user.id,
            context.user_data['week_type'],
            context.user_data['day'],
            context.user_data['subject'],
            update.message.text
        )
        await update.message.reply_text(f"✅ Добавлено: {context.user_data['subject']}")
        context.user_data.clear()
        return ConversationHandler.END
    
    async def show_today_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        weekday = datetime.now().weekday()
        schedule = self.db.get_schedule(user_id, "even", weekday)
        
        if not schedule:
            await update.message.reply_text("📭 На сегодня пар нет")
            return
        
        msg = f"📚 {DAYS_RU[weekday]}:\n\n"
        for subj, time in schedule:
            msg += f"⏰ {time} - {subj}\n"
        await update.message.reply_text(msg)
    
    async def show_all_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        msg = "📖 РАСПИСАНИЕ\n\n"
        
        for week_type, week_name in [("even", "Четная"), ("odd", "Нечетная")]:
            msg += f"◾️ {week_name} неделя:\n"
            for day in range(7):
                items = self.db.get_schedule(user_id, week_type, day)
                if items:
                    msg += f"\n  📅 {DAYS_RU[day]}:\n"
                    for subj, time in items:
                        msg += f"     ⏰ {time} - {subj}\n"
            msg += "\n"
        
        await update.message.reply_text(msg)
    
    async def add_homework_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Название предмета:", reply_markup=ReplyKeyboardRemove())
        return HW_SUBJECT
    
    async def get_hw_subject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['hw_subject'] = update.message.text
        await update.message.reply_text("Что нужно сделать?")
        return HW_TASK
    
    async def get_hw_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['hw_task'] = update.message.text
        await update.message.reply_text("Дедлайн (ГГГГ-ММ-ДД ЧЧ:ММ) или 'завтра 18:00':")
        return HW_DEADLINE
    
    async def get_hw_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        try:
            if "завтра" in text:
                time_part = text.split()[-1]
                deadline = datetime.now() + timedelta(days=1)
                deadline = deadline.replace(hour=int(time_part.split(':')[0]), minute=int(time_part.split(':')[1]))
            else:
                deadline = datetime.strptime(text, "%Y-%m-%d %H:%M")
            
            self.db.save_homework(update.effective_user.id, context.user_data['hw_subject'], context.user_data['hw_task'], deadline.strftime("%Y-%m-%d %H:%M:%S"))
            await update.message.reply_text(f"✅ Добавлено! Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}")
        except:
            await update.message.reply_text("❌ Неправильный формат. Пример: 2025-05-20 23:59")
            return HW_DEADLINE
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Отменено", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END
    
    def run(self):
        print("=" * 40)
        print("🤖 БОТ ЗАПУЩЕН! 🚀")
        print("=" * 40)
        print("Команды:")
        print("  /start - приветствие")
        print("  /batch_schedule - добавить несколько пар")
        print("  /delete_schedule - удалить пару")
        print("  /add_homework - добавить задание")
        print("  /schedule - расписание на сегодня")
        print("  /all_schedule - всё расписание")
        print("=" * 40)
        self.application.run_polling()

if __name__ == "__main__":
    TOKEN = os.environ.get("TOKEN", "8278536077:AAG0GOWYolKbdEmy4sHMWCaa4SRsWfbg6wI")
    bot = ScheduleBot(TOKEN)
    bot.run()
