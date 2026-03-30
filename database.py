import sqlite3
from datetime import datetime

class Database:
    def __init__(self):
        # Создаем подключение к базе данных
        self.conn = sqlite3.connect('schedule_bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        # Создаем таблицы, если их нет
        self.create_tables()
    
    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                state TEXT DEFAULT 'main'
            )
        ''')
        
        # Таблица расписания
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                week_type TEXT,
                weekday INTEGER,
                subject TEXT,
                start_time TEXT
            )
        ''')
        
        # Таблица домашних заданий
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT,
                task TEXT,
                deadline TEXT,
                is_notified INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username):
        """Добавляем нового пользователя"""
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        self.conn.commit()
    
    def save_schedule(self, user_id, week_type, weekday, subject, start_time):
        """Сохраняем пару в расписание"""
        self.cursor.execute('''
            INSERT INTO schedule (user_id, week_type, weekday, subject, start_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, week_type, weekday, subject, start_time))
        self.conn.commit()
    
    def get_schedule(self, user_id, week_type, weekday):
        """Получаем расписание на конкретный день"""
        self.cursor.execute('''
            SELECT subject, start_time FROM schedule
            WHERE user_id = ? AND week_type = ? AND weekday = ?
            ORDER BY start_time
        ''', (user_id, week_type, weekday))
        return self.cursor.fetchall()
    
    def get_all_schedule_for_user(self, user_id):
        """Получаем всё расписание пользователя для удаления"""
        self.cursor.execute('''
            SELECT id, week_type, weekday, subject, start_time 
            FROM schedule 
            WHERE user_id = ?
            ORDER BY weekday, start_time
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def save_homework(self, user_id, subject, task, deadline):
        """Сохраняем домашнее задание"""
        self.cursor.execute('''
            INSERT INTO homework (user_id, subject, task, deadline)
            VALUES (?, ?, ?, ?)
        ''', (user_id, subject, task, deadline))
        self.conn.commit()
    
    def get_homeworks_by_deadline(self):
        """Получаем задания, у которых дедлайн скоро"""
        self.cursor.execute('''
            SELECT * FROM homework 
            WHERE is_notified = 0 AND deadline > datetime('now')
            ORDER BY deadline
        ''')
        return self.cursor.fetchall()
    
    def mark_notified(self, hw_id):
        """Отмечаем задание как уведомленное"""
        self.cursor.execute(
            "UPDATE homework SET is_notified = 1 WHERE id = ?",
            (hw_id,)
        )
        self.conn.commit()