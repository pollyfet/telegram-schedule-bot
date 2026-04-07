import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    ConversationHandler, CallbackContext, filters
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Состояния
ADD_SCHEDULE_WEEK, ADD_SCHEDULE_DAY, ADD_SCHEDULE_SUBJECT, ADD_SCHEDULE_TIME = range(4)
BATCH_WEEK, BATCH_ADD = range(4, 6)
DELETE_CHOOSE = 6
HW_SUBJECT, HW_TASK, HW_DEADLINE = range(7, 10)

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}
DAYS_EN = {v: k for k, v in DAYS_RU.items()}

# Хранилища данных
user_data_store = {}
schedule_store = {}
homework_store = {}

def get_user_data(user_id):
    if user_id not in user_data_store:
        user_data_store[user_id] = {}
    return user_data_store[user_id]

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
        'deadline': deadline
    })

def get_homeworks(user_id):
    if user_id not in homework_store:
        return []
    return homework_store[user_id]

# Команды
def start(update, context):
    text = """🤖 Бот-помощник для учёбы

📚 /add_schedule - добавить одну пару
📚 /batch_schedule - добавить несколько пар за раз
🗑 /delete_schedule - удалить пару
📝 /add_homework - добавить домашнее задание
📋 /all_homework - все домашние задания
📅 /schedule - расписание на сегодня
📖 /all_schedule - всё расписание
❌ /cancel - отменить действие"""
    update.message.reply_text(text)

def schedule_today(update, context):
    user_id = update.effective_user.id
    weekday = datetime.now().weekday()
    week_type = "even" if (datetime.now().isocalendar()[1] % 2 == 0) else "odd"
    rows = get_schedule(user_id, week_type, weekday)
    if not rows:
        update.message.reply_text("📭 На сегодня пар нет")
    else:
        msg = f"📚 {DAYS_RU[weekday]}:\n" + "\n".join([f"⏰ {t} - {s}" for s, t in rows])
        update.message.reply_text(msg)

def all_schedule(update, context):
    user_id = update.effective_user.id
    msg = "📖 ПОЛНОЕ РАСПИСАНИЕ\n"
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
    update.message.reply_text(msg)

def all_homework(update, context):
    user_id = update.effective_user.id
    homeworks = get_homeworks(user_id)
    if not homeworks:
        update.message.reply_text("📭 Нет домашних заданий")
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
    update.message.reply_text(msg)

# Добавление одной пары
def add_schedule_start(update, context):
    kb = [["Четная неделя", "Нечетная неделя"]]
    update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADD_SCHEDULE_WEEK

def add_schedule_week(update, context):
    text = update.message.text
    if text == "Четная неделя":
        context.user_data['week'] = "even"
    elif text == "Нечетная неделя":
        context.user_data['week'] = "odd"
    else:
        update.message.reply_text("Пожалуйста, нажми на кнопку")
        return ADD_SCHEDULE_WEEK
    kb = [[d] for d in DAYS_RU.values()]
    update.message.reply_text("Выбери день:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADD_SCHEDULE_DAY

def add_schedule_day(update, context):
    context.user_data['day'] = DAYS_EN[update.message.text]
    update.message.reply_text("Название предмета:", reply_markup=ReplyKeyboardRemove())
    return ADD_SCHEDULE_SUBJECT

def add_schedule_subject(update, context):
    context.user_data['subject'] = update.message.text
    update.message.reply_text("Время (например: 10:30):")
    return ADD_SCHEDULE_TIME

def add_schedule_time(update, context):
    save_schedule(
        update.effective_user.id,
        context.user_data['week'],
        context.user_data['day'],
        context.user_data['subject'],
        update.message.text
    )
    update.message.reply_text(f"✅ Добавлено: {context.user_data['subject']}")
    context.user_data.clear()
    return ConversationHandler.END

# Добавление нескольких пар
def batch_start(update, context):
    kb = [["Четная неделя", "Нечетная неделя"]]
    update.message.reply_text("Выбери тип недели:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return BATCH_WEEK

def batch_week(update, context):
    text = update.message.text
    if text == "Четная неделя":
        context.user_data['batch_week'] = "even"
    elif text == "Нечетная неделя":
        context.user_data['batch_week'] = "odd"
    else:
        update.message.reply_text("Пожалуйста, нажми на кнопку")
        return BATCH_WEEK
    update.message.reply_text(
        "Введи пары в формате:\nДЕНЬ ВРЕМЯ ПРЕДМЕТ\n\nПример:\nПонедельник 10:30 Математика\n\nКогда закончишь, напиши /done",
        reply_markup=ReplyKeyboardRemove()
    )
    return BATCH_ADD

def batch_add(update, context):
    text = update.message.text.strip()
    if text == "/done":
        update.message.reply_text("✅ Готово!")
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
        update.message.reply_text("❌ Не распознано ни одной пары\nФормат: ДЕНЬ ВРЕМЯ ПРЕДМЕТ\nПример: Понедельник 10:30 Математика")
    else:
        update.message.reply_text(f"✅ Сохранено пар: {saved}\n\nЕсли закончил — напиши /done")
    return BATCH_ADD

# Удаление пары
def delete_start(update, context):
    user_id = update.effective_user.id
    rows = get_all_schedule(user_id)
    if not rows:
        update.message.reply_text("📭 Нет пар для удаления")
        return ConversationHandler.END
    context.user_data['delete_list'] = rows
    msg = "🗑 Выбери пару для удаления:\n\n"
    for r in rows:
        week_name = "Четная" if r[1] == "even" else "Нечетная"
        msg += f"{r[0]}. {week_name} неделя, {DAYS_RU[r[2]]}, {r[4]} - {r[3]}\n"
    msg += "\nВведи номер пары:"
    update.message.reply_text(msg)
    return DELETE_CHOOSE

def delete_choose(update, context):
    try:
        num = int(update.message.text.strip())
        rows = context.user_data.get('delete_list', [])
        for i, r in enumerate(rows):
            if r[0] == num:
                del schedule_store[update.effective_user.id][i]
                update.message.reply_text(f"✅ Удалена пара: {r[3]} в {r[4]}")
                break
        else:
            update.message.reply_text("❌ Пара не найдена")
    except:
        update.message.reply_text("❌ Введи номер цифрой")
    context.user_data.clear()
    return ConversationHandler.END

# Домашнее задание
def hw_start(update, context):
    update.message.reply_text("📝 Введи название предмета:", reply_markup=ReplyKeyboardRemove())
    return HW_SUBJECT

def hw_subject(update, context):
    context.user_data['hw_subj'] = update.message.text
    update.message.reply_text("📖 Опиши задание:")
    return HW_TASK

def hw_task(update, context):
    context.user_data['hw_task'] = update.message.text
    update.message.reply_text("⏰ Введи дедлайн в формате: ГГГГ-ММ-ДД ЧЧ:ММ\nПример: 2025-05-20 23:59\n\nИли напиши: завтра 18:00")
    return HW_DEADLINE

def hw_deadline(update, context):
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
        update.message.reply_text(f"✅ Домашнее задание добавлено!\n\n📚 {context.user_data['hw_subj']}\n📝 {context.user_data['hw_task']}\n⏰ {deadline.strftime('%d.%m.%Y %H:%M')}")
    except:
        update.message.reply_text("❌ Неправильный формат. Попробуй: 2025-05-20 23:59")
        return HW_DEADLINE
    context.user_data.clear()
    return ConversationHandler.END

def cancel(update, context):
    update.message.reply_text("❌ Отменено", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("❌ Ошибка: токен не найден")
        return
    
    updater = Updater(token)
    dp = updater.dispatcher
    
    # Команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("schedule", schedule_today))
    dp.add_handler(CommandHandler("all_schedule", all_schedule))
    dp.add_handler(CommandHandler("all_homework", all_homework))
    
    # Диалоги
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_schedule", add_schedule_start)],
        states={
            ADD_SCHEDULE_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_week)],
            ADD_SCHEDULE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_day)],
            ADD_SCHEDULE_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_subject)],
            ADD_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("batch_schedule", batch_start)],
        states={
            BATCH_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_week)],
            BATCH_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_add)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_schedule", delete_start)],
        states={DELETE_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_choose)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_homework", hw_start)],
        states={
            HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_subject)],
            HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_task)],
            HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    
    print("🤖 БОТ ЗАПУЩЕН!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
