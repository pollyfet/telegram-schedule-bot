import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name="schedule.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица расписания
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                week_type TEXT,
                day INTEGER,
                subject TEXT,
                time TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица домашних заданий
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT,
                task TEXT,
                deadline TIMESTAMP,
                is_notified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        self.conn.commit()
        print("✅ База данных инициализирована")
    
    def add_user(self, user_id, username):
        """Добавление или обновление пользователя"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, username, created_at)
            VALUES (?, ?, COALESCE((SELECT created_at FROM users WHERE user_id = ?), CURRENT_TIMESTAMP))
        """, (user_id, username, user_id))
        self.conn.commit()
    
    def save_schedule(self, user_id, week_type, day, subject, time):
        """Сохранение пары в расписание"""
        self.cursor.execute("""
            INSERT INTO schedule (user_id, week_type, day, subject, time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, week_type, day, subject, time))
        self.conn.commit()
    
    def get_schedule(self, user_id, week_type, day):
        """Получение расписания на конкретный день"""
        self.cursor.execute("""
            SELECT subject, time FROM schedule
            WHERE user_id = ? AND week_type = ? AND day = ?
            ORDER BY time
        """, (user_id, week_type, day))
        return self.cursor.fetchall()
    
    def get_all_schedule_for_user(self, user_id):
        """Получение всего расписания пользователя"""
        self.cursor.execute("""
            SELECT id, week_type, day, subject, time FROM schedule
            WHERE user_id = ?
            ORDER BY week_type, day, time
        """, (user_id,))
        return self.cursor.fetchall()
    
    def save_homework(self, user_id, subject, task, deadline):
        """Сохранение домашнего задания"""
        self.cursor.execute("""
            INSERT INTO homework (user_id, subject, task, deadline, is_notified)
            VALUES (?, ?, ?, ?, 0)
        """, (user_id, subject, task, deadline))
        self.conn.commit()
    
    def get_all_homeworks_for_user(self, user_id):
        """Получение всех домашних заданий пользователя"""
        self.cursor.execute("""
            SELECT * FROM homework
            WHERE user_id = ?
            ORDER BY deadline ASC
        """, (user_id,))
        return self.cursor.fetchall()
    
    def delete_schedule(self, schedule_id):
        """Удаление пары по ID"""
        self.cursor.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def get_schedule_by_id(self, schedule_id, user_id):
        """Получение пары по ID"""
        self.cursor.execute("""
            SELECT * FROM schedule WHERE id = ? AND user_id = ?
        """, (schedule_id, user_id))
        return self.cursor.fetchone()
    
    def close(self):
        """Закрытие соединения с БД"""
        self.conn.close()
