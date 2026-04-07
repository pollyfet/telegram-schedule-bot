import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Состояния
ADD_SCHEDULE_WEEK, ADD_SCHEDULE_DAY, ADD_SCHEDULE_SUBJECT, ADD_SCHEDULE_TIME = range(4)
BATCH_WEEK, BATCH_ADD = range(4, 6)
DELETE_CHOOSE = 6
HW_SUBJECT, HW_TASK, HW_DEADLINE = range(7, 10)
COPY_WEEK = 10

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}
DAYS_EN = {v: k for k, v in DAYS_RU.items()}

# Хранилища данных
schedule_store = {}
homework_store = {}

# НАЧАЛО ОТСЧЕТА: понедельник этой недели (6 апреля 2026) - ЧЕТНАЯ неделя
START_DATE = datetime(2026, 4, 6)  # ЧЕТНАЯ неделя

def get_current_week_type():
    """Определяет четная или нечетная неделя от START_DATE"""
    today = datetime.now()
    days_diff = (today - START_DATE).days
    week_number = days_diff // 7
    return "even" if week_number % 2 == 0 else "odd"

def save_schedule(user_id, week_type, day, subject, time):
    if user_id not in schedule_store:
        schedule_store[user_id] = []
    schedule_store[user_id].append({
        'id': len(schedule_store[user_id]) + 1,
        'week_type': week_type,
        'day': day,
        'subject': subject,
        'time': time
    })

def get_schedule(user_id, week_type, day):
    if user_id not in schedule_store:
        return []
    return [(s['subject'], s['time']) for s in schedule_store[user_id] 
            if s['week_type'] == week_type and s['day'] == day]

def get_all_schedule(user_id):
    if user_id not in schedule_store:
        return []
    return [(s['id'], s['week_type'], s['day'], s['subject'], s['time']) 
            for s in schedule_store[user_id]]

def save_homework(user_id, subject, task, deadline):
    if user_id not in homework_store:
        homework_store[user_id] = []
    homework_store[user_id].append({
        'id': len(homework_store[user_id]) + 1,
        'subject': subject,
        'task': task,
        'deadline': deadline,
        'is_notified': False
    })

def get_homeworks(user_id):
    if user_id not in homework_store:
        return []
    return homework_store[user_id]

def copy_week_schedule(user_id, from_week, to_week):
    """Копирует расписание с одной недели на другую"""
    if user_id not in schedule_store:
        return 0
    
    copied = 0
    for s in schedule_store[user_id]:
        if s['week_type'] == from_week:
            exists = False
            for existing in schedule_store[user_id]:
                if (existing['week_type'] == to_week and 
                    existing['day'] == s['day'] and 
                    existing['time'] == s['time'] and 
                    existing['subject'] == s['subject']):
                    exists = True
                    break
            if not exists:
                save_schedule(user_id, to_week, s['day'], s['subject'], s['time'])
                copied += 1
    return copied

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    text = """🤖 Бот-помощник для учёбы

📚 /add_schedule - добавить одну пару
📚 /batch_schedule - добавить несколько пар за раз
📋 /copy_schedule - скопировать расписание с одной недели на другую
🗑 /delete_schedule - удалить пару
📝 /add_homework - добавить домашнее задание
📋 /all_homework - все домашние задания
📅 /schedule - расписание на сегодня
📖 /all_schedule - всё расписание
❌ /cancel - отменить действие"""
    await update.message.reply_text(text)

async def schedule_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    weekday = datetime.now().weekday()
    week_type = get_current_week_type()
    
    week_name = "Четная" if week_type == "even" else "Нечетная"
    
    rows = get_schedule(user_id, week_type, weekday)
    if not rows:
        await update.message.reply_text(f"📭 На сегодня ({week_name} неделя) пар нет")
    else:
        msg = f"📚 {DAYS_RU[weekday]} ({week_name} неделя):\n" + "\n".join([f"⏰ {t} - {s}" for s, t in rows])
        await update.message.reply_text(msg)

async def all_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_week = get_current_week_type()
    current_week_name = "Четная" if current_week == "even" else "Нечетная"
    
    msg = f"📖 ПОЛНОЕ РАСПИСАНИЕ\n\n⭐ Сейчас {current_week_name} неделя\n"
    
    for wt, wn in [("even", "Четная"), ("odd", "Нечетная")]:
        msg += f"\n◾ {wn} неделя:\n"
        has_any = False
        for d in range(7):
            rows = get_schedule(user_id, wt, d)
            if rows:
                has_any = True
                msg += f"\n📅 {DAYS_RU[d]}:\n"
                msg += "\n".join([f"   {t} - {s}" for s, t in rows]) + "\n"
        if not has_any:
            msg += "   (нет пар)\n"
    await update.message.reply_text(msg)

async def all_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    homeworks = get_homeworks(user_id)
    if not homeworks:
        await update.message.reply_text("📭 Нет домашних заданий")
        return
    msg = "📋 ВСЕ ДОМАШНИЕ ЗАДАНИЯ\n\n"
    for hw in homeworks:
        deadline = datetime.strptime(hw['deadline'], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if deadline < now:
            status = "❌ ПРОСРОЧЕНО"
        elif (deadline - now).days == 0:
            status = "⚠️ СЕГОДНЯ"
        elif (deadline - now).days == 1:
            status = "⚠️ ЗАВТРА"
        else:
            status = f"📅 {deadline.strftime('%d.%m.%Y')}"
        msg += f"📚 {hw['subject']}\n📝 {hw['task']}\n⏰ {status} {deadline.strftime('%H:%M')}\n\n"
    await update.message.reply_text(msg)

async def copy_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Четная → Нечетная", "Нечетная → Четная"]]
    await update.message.reply_text(
        "Выбери направление копирования:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return COPY_WEEK

async def copy_schedule_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "Четная → Нечетная":
        from_week = "even"
        to_week = "odd"
        from_name = "Четной"
        to_name = "Нечетную"
    elif text == "Нечетная → Четная":
        from_week = "odd"
        to_week = "even"
        from_name = "Нечетной"
        to_name = "Четную"
    else:
        await update.message.reply_text("Пожалуйста, нажми на кнопку")
        return COPY_WEEK
    
    copied = copy_week_schedule(user_id, from_week, to_week)
    
    if copied == 0:
        has_pairs = False
        for d in range(7):
            if get_schedule(user_id, from_week, d):
                has_pairs = True
                break
        
        if not has_pairs:
            await update.message.reply_text(f"❌ На {from_name} неделе нет пар для копирования.")
        else:
            await update.message.reply_text(f"ℹ️ Все пары с {from_name} недели уже есть на {to_name} неделе.")
    else:
        await update.message.reply_text(
            f"✅ Скопировано {copied} пар(ы) с {from_name} недели на {to_name} неделю.\n\n"
            f"Посмотреть результат: /all_schedule"
        )
    
    context.user_data.clear()
    return ConversationHandler.END

# Добавление одной пары
async def add_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Четная неделя", "Нечетная неделя"]]
    await update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADD_SCHEDULE_WEEK

async def add_schedule_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Четная неделя":
        context.user_data['week'] = "even"
    elif text == "Нечетная неделя":
        context.user_data['week'] = "odd"
    else:
        await update.message.reply_text("Пожалуйста, нажми на кнопку")
        return ADD_SCHEDULE_WEEK
    kb = [[d] for d in DAYS_RU.values()]
    await update.message.reply_text("Выбери день:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADD_SCHEDULE_DAY

async def add_schedule_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['day'] = DAYS_EN[update.message.text]
    await update.message.reply_text("Название предмета:", reply_markup=ReplyKeyboardRemove())
    return ADD_SCHEDULE_SUBJECT

async def add_schedule_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['subject'] = update.message.text
    await update.message.reply_text("Время (например: 10:30):")
    return ADD_SCHEDULE_TIME

async def add_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_schedule(
        update.effective_user.id,
        context.user_data['week'],
        context.user_data['day'],
        context.user_data['subject'],
        update.message.text
    )
    await update.message.reply_text(f"✅ Добавлено: {context.user_data['subject']}")
    context.user_data.clear()
    return ConversationHandler.END

# Добавление нескольких пар
async def batch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Четная неделя", "Нечетная неделя"]]
    await update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return BATCH_WEEK

async def batch_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def batch_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/done":
        await update.message.reply_text("✅ Готово!")
        context.user_data.clear()
        return ConversationHandler.END
    lines = text.split('\n')
    saved = 0
    week = context.user_data.get('batch_week', 'even')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
        if match and match.group(1) in DAYS_EN:
            save_schedule(update.effective_user.id, week, DAYS_EN[match.group(1)], match.group(3), match.group(2))
            saved += 1
    if saved == 0:
        await update.message.reply_text("❌ Не распознано ни одной пары\nФормат: ДЕНЬ ВРЕМЯ ПРЕДМЕТ\nПример: Понедельник 10:30 Математика")
    else:
        await update.message.reply_text(f"✅ Сохранено пар: {saved}\n\nЕсли закончил — напиши /done")
    return BATCH_ADD

# Удаление пары
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_all_schedule(user_id)
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

async def delete_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = int(update.message.text.strip())
        rows = context.user_data.get('delete_list', [])
        for i, r in enumerate(rows):
            if r[0] == num:
                del schedule_store[update.effective_user.id][i]
                await update.message.reply_text(f"✅ Удалена пара: {r[3]} в {r[4]}")
                break
        else:
            await update.message.reply_text("❌ Пара не найдена")
    except:
        await update.message.reply_text("❌ Введи номер цифрой")
    context.user_data.clear()
    return ConversationHandler.END

# Домашнее задание
async def hw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи название предмета:", reply_markup=ReplyKeyboardRemove())
    return HW_SUBJECT

async def hw_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hw_subj'] = update.message.text
    await update.message.reply_text("📖 Опиши задание:")
    return HW_TASK

async def hw_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hw_task'] = update.message.text
    await update.message.reply_text("⏰ Введи дедлайн в формате: ГГГГ-ММ-ДД ЧЧ:ММ\nПример: 2025-05-20 23:59\n\nИли напиши: завтра 18:00")
    return HW_DEADLINE

async def hw_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    try:
        if "завтра" in text:
            parts = text.split()
            time_str = parts[-1]
            time_parts = time_str.split(':')
            d = datetime.now() + timedelta(days=1)
            deadline = d.replace(hour=int(time_parts[0]), minute=int(time_parts[1]), second=0, microsecond=0)
        else:
            deadline = datetime.strptime(text, "%Y-%m-%d %H:%M")
        save_homework(
            update.effective_user.id,
            context.user_data['hw_subj'],
            context.user_data['hw_task'],
            deadline.strftime("%Y-%m-%d %H:%M:%S")
        )
        await update.message.reply_text(f"✅ Домашнее задание добавлено!\n\n📚 {context.user_data['hw_subj']}\n📝 {context.user_data['hw_task']}\n⏰ {deadline.strftime('%d.%m.%Y %H:%M')}")
    except:
        await update.message.reply_text("❌ Неправильный формат. Попробуй: 2025-05-20 23:59")
        return HW_DEADLINE
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def check_deadlines(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for user_id, homeworks in homework_store.items():
        for hw in homeworks:
            if not hw['is_notified']:
                deadline = datetime.strptime(hw['deadline'], "%Y-%m-%d %H:%M:%S")
                days_left = (deadline - now).days
                if days_left == 1:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ НАПОМИНАНИЕ!\n\nДедлайн по заданию \"{hw['subject']}\" завтра!\n{hw['task']}"
                        )
                        hw['is_notified'] = True
                    except:
                        pass

def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("❌ Ошибка: токен не найден")
        return
    
    app = Application.builder().token(token).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", schedule_today))
    app.add_handler(CommandHandler("all_schedule", all_schedule))
    app.add_handler(CommandHandler("all_homework", all_homework))
    
    # Копирование расписания
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("copy_schedule", copy_schedule_start)],
        states={COPY_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, copy_schedule_choose)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    # Диалоги
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_schedule", add_schedule_start)],
        states={
            ADD_SCHEDULE_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_week)],
            ADD_SCHEDULE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_day)],
            ADD_SCHEDULE_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_subject)],
            ADD_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("batch_schedule", batch_start)],
        states={
            BATCH_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_week)],
            BATCH_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_add)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_schedule", delete_start)],
        states={DELETE_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_choose)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_homework", hw_start)],
        states={
            HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_subject)],
            HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_task)],
            HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    # Планировщик уведомлений
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(check_deadlines, time=datetime.time(hour=9, minute=0))
    
    print("🤖 БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
