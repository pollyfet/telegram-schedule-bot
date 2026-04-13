import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

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
    result = []
    for s in schedule_store[user_id]:
        result.append((s['id'], s['week_type'], s['day'], s['subject'], s['time']))
    return result

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

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    week_type = get_current_week()
    week_name = "ЧЕТНАЯ" if week_type == "even" else "НЕЧЕТНАЯ"
    
    text = f"""🤖 БОТ-ПОМОЩНИК ДЛЯ УЧЁБЫ

Сейчас {week_name} неделя

📚 /even [список пар] - добавить пары на ЧЕТНУЮ неделю
📚 /odd [список пар] - добавить пары на НЕЧЕТНУЮ неделю
📝 /hw [предмет] | [задание] | [дедлайн] - добавить домашку
📋 /all_hw - все активные задания
✅ /done [номер] - отметить задание выполненным
📅 /today - расписание на сегодня
📖 /all_schedule - всё расписание
🗑 /delete [номер] - удалить пару
❌ /cancel - отмена

ПРИМЕРЫ:
/even Понедельник 10:30 Математика; Вторник 14:00 Физика
/hw Математика | решить задачи | 2025-05-20 23:59
/done 1
/delete 3"""
    await update.message.reply_text(text)

# ==================== РАСПИСАНИЕ ====================

async def add_even(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить пары на четную неделю: /even Понедельник 10:30 Математика; Вторник 14:00 Физика"""
    if not context.args:
        await update.message.reply_text("❌ Пример: /even Понедельник 10:30 Математика; Вторник 14:00 Физика")
        return
    
    text = ' '.join(context.args)
    await parse_and_save(update, text, "even")

async def add_odd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить пары на нечетную неделю: /odd Понедельник 10:30 Математика; Вторник 14:00 Физика"""
    if not context.args:
        await update.message.reply_text("❌ Пример: /odd Понедельник 10:30 Математика; Вторник 14:00 Физика")
        return
    
    text = ' '.join(context.args)
    await parse_and_save(update, text, "odd")

async def parse_and_save(update, text, week_type):
    """Парсит и сохраняет пары (разделитель ; или новая строка)"""
    user_id = update.effective_user.id
    week_name = "ЧЕТНУЮ" if week_type == "even" else "НЕЧЕТНУЮ"
    
    # Разделяем по ; или по переводу строки
    if ';' in text:
        lines = text.split(';')
    else:
        lines = text.split('\n')
    
    saved = 0
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = re.match(r'^([А-Яа-я]+)\s+(\d{1,2}:\d{2})\s+(.+)$', line)
        if match and match.group(1) in DAYS_EN:
            day = DAYS_EN[match.group(1)]
            time = match.group(2)
            subject = match.group(3)
            save_schedule(user_id, week_type, day, subject, time)
            saved += 1
        else:
            errors.append(line[:40])
    
    if saved == 0:
        await update.message.reply_text(
            f"❌ Не распознано ни одной пары\n\n"
            f"Формат: ДЕНЬ ВРЕМЯ ПРЕДМЕТ\n"
            f"Пример: Понедельник 10:30 Математика"
        )
    else:
        msg = f"✅ Сохранено {saved} пар на {week_name} неделю"
        if errors:
            msg += f"\n\n⚠️ Не распознано:\n" + "\n".join(errors[:3])
        await update.message.reply_text(msg)

async def today_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    if len(msg) > 4000:
        msg = msg[:3500] + "\n\n... (слишком много пар, используй /today)"
    await update.message.reply_text(msg)

async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить пару по номеру: /delete 5"""
    if not context.args:
        await update.message.reply_text("❌ Пример: /delete 5 (номер пары из /all_schedule)")
        return
    
    try:
        num = int(context.args[0])
        user_id = update.effective_user.id
        
        if user_id not in schedule_store:
            await update.message.reply_text("Нет пар для удаления")
            return
        
        for i, s in enumerate(schedule_store[user_id]):
            if s['id'] == num:
                del schedule_store[user_id][i]
                await update.message.reply_text(f"✅ Удалена пара: {s['subject']} в {s['time']}")
                return
        
        await update.message.reply_text(f"❌ Пара с номером {num} не найдена")
    except ValueError:
        await update.message.reply_text("❌ Введи номер цифрой")

# ==================== ДОМАШНЕЕ ЗАДАНИЕ ====================

async def add_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить домашку: /hw Предмет | Задание | 2025-05-20 23:59"""
    if not context.args:
        await update.message.reply_text(
            "❌ Пример: /hw Математика | решить задачи | 2025-05-20 23:59\n\n"
            "Или: /hw Физика | подготовиться | завтра 18:00"
        )
        return
    
    text = ' '.join(context.args)
    parts = text.split('|')
    
    if len(parts) < 3:
        await update.message.reply_text("❌ Используй разделитель | \nПример: /hw Предмет | Задание | 2025-05-20 23:59")
        return
    
    subject = parts[0].strip()
    task = parts[1].strip()
    deadline_str = parts[2].strip().lower()
    
    try:
        if "завтра" in deadline_str:
            time_match = re.search(r'(\d{1,2}:\d{2})', deadline_str)
            if time_match:
                time_parts = time_match.group(1).split(':')
                d = datetime.now() + timedelta(days=1)
                deadline = d.replace(hour=int(time_parts[0]), minute=int(time_parts[1]), second=0)
            else:
                deadline = datetime.now() + timedelta(days=1)
                deadline = deadline.replace(hour=23, minute=59, second=0)
        else:
            for fmt in ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"]:
                try:
                    deadline = datetime.strptime(deadline_str, fmt)
                    break
                except:
                    continue
            else:
                raise ValueError()
        
        save_homework(update.effective_user.id, subject, task, deadline.strftime("%Y-%m-%d %H:%M:%S"))
        await update.message.reply_text(
            f"✅ Домашнее задание добавлено!\n\n"
            f"📚 {subject}\n"
            f"📝 {task}\n"
            f"⏰ {deadline.strftime('%d.%m.%Y %H:%M')}"
        )
    except:
        await update.message.reply_text("❌ Неправильный формат дедлайна\nПримеры: 2025-05-20 23:59 или завтра 18:00")

async def all_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    homeworks = get_homeworks(user_id, show_completed=False)
    
    if not homeworks:
        await update.message.reply_text("📭 Нет активных домашних заданий")
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
        msg += f"⏰ {status} {deadline.strftime('%H:%M')}\n\n"
    
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
        msg += f"📚 {hw['subject']}\n📝 {hw['task']}\n⏰ {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await update.message.reply_text(msg)

async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Пример: /done 1")
        return
    
    try:
        hw_id = int(context.args[0])
        if complete_homework(update.effective_user.id, hw_id):
            await update.message.reply_text(f"✅ Задание #{hw_id} отмечено как выполненное!")
        else:
            await update.message.reply_text(f"❌ Задание #{hw_id} не найдено")
    except ValueError:
        await update.message.reply_text("❌ Введи номер цифрой")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено", reply_markup=ReplyKeyboardRemove())

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
                            text = f"❌ ПРОСРОЧЕНО!\n\n{hw['subject']}\n{hw['task']}"
                        
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
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("even", add_even))
    app.add_handler(CommandHandler("odd", add_odd))
    app.add_handler(CommandHandler("today", today_schedule))
    app.add_handler(CommandHandler("all_schedule", all_schedule))
    app.add_handler(CommandHandler("delete", delete_schedule))
    app.add_handler(CommandHandler("hw", add_homework))
    app.add_handler(CommandHandler("all_hw", all_homework))
    app.add_handler(CommandHandler("completed_hw", completed_homework))
    app.add_handler(CommandHandler("done", done_task))
    app.add_handler(CommandHandler("cancel", cancel))
    
    if app.job_queue:
        app.job_queue.run_repeating(check_deadlines, interval=3600, first=10)
    
    app.post_init = post_init
    
    print("🤖 БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
