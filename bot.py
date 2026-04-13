import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

# Состояния - УНИКАЛЬНЫЕ ДЛЯ КАЖДОГО ДИАЛОГА
ADD_SCHEDULE_WEEK, ADD_SCHEDULE_DAY, ADD_SCHEDULE_SUBJECT, ADD_SCHEDULE_TIME = range(4)
BATCH_WEEK, BATCH_ADD = range(10, 12)
DELETE_CHOOSE = 20
HW_SUBJECT, HW_TASK, HW_DEADLINE = range(30, 33)
COPY_WEEK = 40

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}
DAYS_EN = {v: k for k, v in DAYS_RU.items()}

# Хранилища
schedule_store = {}
homework_store = {}

def get_current_week():
    today = datetime.now()
    start = datetime(2026, 4, 6)
    days_since_monday = today.weekday()
    current_monday = today - timedelta(days=days_since_monday)
    days_diff = (current_monday - start).days
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
        'is_completed': False,
        'is_notified': False
    })

def get_homeworks(user_id, show_completed=False):
    if user_id not in homework_store:
        return []
    if show_completed:
        return homework_store[user_id]
    return [hw for hw in homework_store[user_id] if not hw['is_completed']]

def complete_homework(user_id, hw_id):
    if user_id in homework_store:
        for hw in homework_store[user_id]:
            if hw['id'] == hw_id:
                hw['is_completed'] = True
                return True
    return False

def copy_week_schedule(user_id, from_week, to_week):
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

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    week_type = get_current_week()
    week_name = "ЧЕТНАЯ" if week_type == "even" else "НЕЧЕТНАЯ"
    
    text = f"""🤖 БОТ-ПОМОЩНИК ДЛЯ УЧЁБЫ

Сейчас {week_name} неделя

Доступные команды:

/add_schedule - добавить одну пару
/batch_schedule - добавить несколько пар
/copy_schedule - скопировать расписание
/delete_schedule - удалить пару
/add_homework - добавить домашнее задание
/all_homework - все активные задания
/completed_homework - выполненные задания
/schedule - расписание на сегодня
/all_schedule - всё расписание
/cancel - отменить действие"""
    await update.message.reply_text(text)

async def schedule_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    weekday = datetime.now().weekday()
    week_type = get_current_week()
    week_name = "ЧЕТНАЯ" if week_type == "even" else "НЕЧЕТНАЯ"
    
    rows = get_schedule(user_id, week_type, weekday)
    if not rows:
        await update.message.reply_text(f"На сегодня ({week_name} неделя) пар нет")
    else:
        msg = f"📚 {DAYS_RU[weekday]} ({week_name} неделя):\n"
        for subject, time in rows:
            msg += f"⏰ {time} - {subject}\n"
        await update.message.reply_text(msg)

async def all_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_week = get_current_week()
    current_week_name = "ЧЕТНАЯ" if current_week == "even" else "НЕЧЕТНАЯ"
    
    msg = f"📖 ПОЛНОЕ РАСПИСАНИЕ\n\n⭐ Сейчас {current_week_name} неделя\n"
    
    for wt, wn in [("even", "Четная"), ("odd", "Нечетная")]:
        msg += f"\n◾ {wn} неделя:\n"
        has_any = False
        for d in range(7):
            rows = get_schedule(user_id, wt, d)
            if rows:
                has_any = True
                msg += f"\n📅 {DAYS_RU[d]}:\n"
                for subject, time in rows:
                    msg += f"   {time} - {subject}\n"
        if not has_any:
            msg += "   (нет пар)\n"
    await update.message.reply_text(msg)

async def all_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    homeworks = get_homeworks(user_id, show_completed=False)
    
    if not homeworks:
        await update.message.reply_text("📭 Нет активных домашних заданий\n\n✅ Выполненные задания: /completed_homework")
        return
    
    msg = "📋 АКТИВНЫЕ ДОМАШНИЕ ЗАДАНИЯ\n\n"
    now = datetime.now()
    
    for hw in homeworks:
        deadline = datetime.strptime(hw['deadline'], "%Y-%m-%d %H:%M:%S")
        if deadline < now:
            status = "❌ ПРОСРОЧЕНО"
        elif (deadline - now).days == 0:
            status = "⚠️ СЕГОДНЯ"
        elif (deadline - now).days == 1:
            status = "⚠️ ЗАВТРА"
        else:
            status = f"📅 {deadline.strftime('%d.%m.%Y')}"
        
        msg += f"📌 #{hw['id']}\n"
        msg += f"📚 {hw['subject']}\n"
        msg += f"📝 {hw['task']}\n"
        msg += f"⏰ {status} {deadline.strftime('%H:%M')}\n"
        msg += f"✅ Чтобы отметить выполненным, напиши: /done {hw['id']}\n"
        msg += "\n" + "─"*30 + "\n\n"
    
    await update.message.reply_text(msg)

async def completed_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    homeworks = get_homeworks(user_id, show_completed=True)
    completed = [hw for hw in homeworks if hw['is_completed']]
    
    if not completed:
        await update.message.reply_text("📭 Нет выполненных заданий")
        return
    
    msg = "✅ ВЫПОЛНЕННЫЕ ЗАДАНИЯ\n\n"
    for hw in completed:
        deadline = datetime.strptime(hw['deadline'], "%Y-%m-%d %H:%M:%S")
        msg += f"📚 {hw['subject']}\n"
        msg += f"📝 {hw['task']}\n"
        msg += f"⏰ Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await update.message.reply_text(msg)

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        hw_id = int(context.args[0])
        if complete_homework(user_id, hw_id):
            await update.message.reply_text(f"✅ Задание #{hw_id} отмечено как выполненное!")
        else:
            await update.message.reply_text(f"❌ Задание #{hw_id} не найдено")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используй: /done <номер>")

# ==================== ДОБАВЛЕНИЕ ОДНОЙ ПАРЫ ====================
async def add_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = [["Четная неделя", "Нечетная неделя"]]
    await update.message.reply_text(
        "Выбери тип недели:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
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
    await update.message.reply_text(
        "Выбери день:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return ADD_SCHEDULE_DAY

async def add_schedule_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['day'] = DAYS_EN[update.message.text]
    await update.message.reply_text(
        "Название предмета:",
        reply_markup=ReplyKeyboardRemove()
    )
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

# ==================== ДОБАВЛЕНИЕ НЕСКОЛЬКИХ ПАР ====================
async def batch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = [["Четная неделя", "Нечетная неделя"]]
    await update.message.reply_text(
        "Выбери тип недели:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return BATCH_WEEK

async def batch_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Четная неделя":
        context.user_data['batch_week'] = "even"
        week_name = "ЧЕТНУЮ"
    elif text == "Нечетная неделя":
        context.user_data['batch_week'] = "odd"
        week_name = "НЕЧЕТНУЮ"
    else:
        await update.message.reply_text("Пожалуйста, нажми на кнопку")
        return BATCH_WEEK
    
    await update.message.reply_text(
        f"📝 ДОБАВЛЕНИЕ ПАР НА {week_name.upper()} НЕДЕЛЮ\n\n"
        "Введи ВСЕ пары ОДНИМ СООБЩЕНИЕМ, КАЖДУЮ С НОВОЙ СТРОКИ:\n\n"
        "Пример:\n"
        "Понедельник 10:30 Математика\n"
        "Вторник 14:00 Физика\n"
        "Среда 12:00 Химия\n\n"
        "Когда закончишь, напиши /stop\n"
        "Чтобы отменить, напиши /cancel",
        reply_markup=ReplyKeyboardRemove()
    )
    return BATCH_ADD

async def batch_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.lower() == "/stop":
        week_type = context.user_data.get('batch_week', 'even')
        week_name = "ЧЕТНУЮ" if week_type == "even" else "НЕЧЕТНУЮ"
        await update.message.reply_text(f"✅ Добавление пар на {week_name} неделю завершено!")
        context.user_data.clear()
        return ConversationHandler.END
    
    if text.lower() == "/cancel":
        await update.message.reply_text("❌ Добавление отменено")
        context.user_data.clear()
        return ConversationHandler.END
    
    if text.startswith("/"):
        await update.message.reply_text("Напиши /stop для завершения или /cancel для отмены")
        return BATCH_ADD
    
    # Разбиваем на строки - поддерживаем несколько пар за раз
    lines = text.split('\n')
    week = context.user_data.get('batch_week', 'even')
    week_name = "ЧЕТНУЮ" if week == "even" else "НЕЧЕТНУЮ"
    
    saved = 0
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
        if match and match.group(1) in DAYS_EN:
            save_schedule(update.effective_user.id, week, DAYS_EN[match.group(1)], match.group(3), match.group(2))
            saved += 1
        else:
            errors.append(line[:40])
    
    if saved == 0:
        await update.message.reply_text(
            "❌ Не распознано ни одной пары\n\n"
            "Формат каждой строки: ДЕНЬ ВРЕМЯ ПРЕДМЕТ\n"
            "Пример: Понедельник 10:30 Математика\n\n"
            "Напиши /stop для завершения"
        )
    else:
        msg = f"✅ Сохранено {saved} пар на {week_name} неделю"
        if errors:
            msg += f"\n\n⚠️ Не распознано:\n" + "\n".join(errors[:3])
        msg += "\n\nМожно добавить ещё или напиши /stop"
        await update.message.reply_text(msg)
    
    return BATCH_ADD

# ==================== УДАЛЕНИЕ ПАРЫ ====================
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
    msg += "\nВведи номер:"
    await update.message.reply_text(msg)
    return DELETE_CHOOSE

async def delete_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = int(update.message.text.strip())
        rows = context.user_data.get('delete_list', [])
        for i, r in enumerate(rows):
            if r[0] == num:
                del schedule_store[update.effective_user.id][i]
                await update.message.reply_text(f"✅ Удалена пара: {r[3]}")
                break
        else:
            await update.message.reply_text("❌ Не найдено")
    except:
        await update.message.reply_text("❌ Введи номер цифрой")
    context.user_data.clear()
    return ConversationHandler.END

# ==================== КОПИРОВАНИЕ ====================
async def copy_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = [["Четная → Нечетная", "Нечетная → Четная"]]
    await update.message.reply_text(
        "Выбери направление:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return COPY_WEEK

async def copy_schedule_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "Четная → Нечетная":
        from_week, to_week = "even", "odd"
        from_name, to_name = "Четной", "Нечетную"
    elif text == "Нечетная → Четная":
        from_week, to_week = "odd", "even"
        from_name, to_name = "Нечетной", "Четную"
    else:
        await update.message.reply_text("Нажми на кнопку")
        return COPY_WEEK
    
    copied = copy_week_schedule(user_id, from_week, to_week)
    
    if copied == 0:
        await update.message.reply_text(f"❌ На {from_name} неделе нет пар для копирования")
    else:
        await update.message.reply_text(f"✅ Скопировано {copied} пар с {from_name} на {to_name} неделю")
    
    context.user_data.clear()
    return ConversationHandler.END

# ==================== ДОМАШНЕЕ ЗАДАНИЕ ====================
async def hw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 ДОБАВЛЕНИЕ ДОМАШНЕГО ЗАДАНИЯ\n\nВведи название предмета:",
        reply_markup=ReplyKeyboardRemove()
    )
    return HW_SUBJECT

async def hw_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Напиши /cancel для выхода")
        return HW_SUBJECT
    context.user_data['hw_subj'] = update.message.text
    await update.message.reply_text("📖 Опиши задание:")
    return HW_TASK

async def hw_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Напиши /cancel для выхода")
        return HW_TASK
    context.user_data['hw_task'] = update.message.text
    await update.message.reply_text("⏰ Введи дедлайн:\n\n• 2025-05-20 23:59\n• завтра 18:00")
    return HW_DEADLINE

async def hw_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    try:
        if "завтра" in text:
            parts = text.split()
            time_parts = parts[-1].split(':')
            d = datetime.now() + timedelta(days=1)
            deadline = d.replace(hour=int(time_parts[0]), minute=int(time_parts[1]), second=0)
        else:
            for fmt in ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"]:
                try:
                    deadline = datetime.strptime(text, fmt)
                    break
                except:
                    continue
            else:
                raise ValueError()
        
        save_homework(
            update.effective_user.id,
            context.user_data['hw_subj'],
            context.user_data['hw_task'],
            deadline.strftime("%Y-%m-%d %H:%M:%S")
        )
        await update.message.reply_text(
            f"✅ Домашнее задание добавлено!\n\n"
            f"📚 {context.user_data['hw_subj']}\n"
            f"📝 {context.user_data['hw_task']}\n"
            f"⏰ {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Чтобы отметить выполненным: /done (номер из /all_homework)"
        )
    except:
        await update.message.reply_text("❌ Неправильный формат\nПримеры:\n• 2025-05-20 23:59\n• завтра 18:00")
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
            if not hw['is_notified'] and not hw['is_completed']:
                deadline = datetime.strptime(hw['deadline'], "%Y-%m-%d %H:%M:%S")
                days_left = (deadline - now).days
                if days_left <= 1:
                    try:
                        if days_left == 1:
                            text = f"⚠️ НАПОМИНАНИЕ!\n\nДедлайн по \"{hw['subject']}\" ЗАВТРА!\n{hw['task']}"
                        elif days_left == 0:
                            text = f"⚠️ СРОЧНО!\n\nДедлайн по \"{hw['subject']}\" СЕГОДНЯ!\n{hw['task']}"
                        else:
                            text = f"❌ ПРОСРОЧЕНО!\n\n\"{hw['subject']}\"\n{hw['task']}"
                        
                        await context.bot.send_message(chat_id=user_id, text=text)
                        hw['is_notified'] = True
                    except:
                        pass

async def post_init(application: Application):
    await application.bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен")
    await check_deadlines(application)

def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("❌ Токен не найден")
        return
    
    app = Application.builder().token(token).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", schedule_today))
    app.add_handler(CommandHandler("all_schedule", all_schedule))
    app.add_handler(CommandHandler("all_homework", all_homework))
    app.add_handler(CommandHandler("completed_homework", completed_homework))
    app.add_handler(CommandHandler("done", complete_task))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Копирование
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("copy_schedule", copy_schedule_start)],
        states={COPY_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, copy_schedule_choose)]},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    ))
    
    # Добавление одной пары
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_schedule", add_schedule_start)],
        states={
            ADD_SCHEDULE_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_week)],
            ADD_SCHEDULE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_day)],
            ADD_SCHEDULE_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_subject)],
            ADD_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    ))
    
    # Добавление нескольких пар
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("batch_schedule", batch_start)],
        states={
            BATCH_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_week)],
            BATCH_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_add)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True
    ))
    
    # Удаление пары
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_schedule", delete_start)],
        states={DELETE_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_choose)]},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    ))
    
    # Добавление домашнего задания
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_homework", hw_start)],
        states={
            HW_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_subject)],
            HW_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_task)],
            HW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, hw_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    ))
    
    # Планировщик
    if app.job_queue:
        app.job_queue.run_repeating(check_deadlines, interval=3600, first=10)
    
    app.post_init = post_init
    
    print("🤖 БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
