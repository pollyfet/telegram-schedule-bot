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
    
    def add_user(self, user_id, username):
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        self.conn.commit()
    
    def save_schedule(self, user_id, week_type, day, subject, time):
        self.cursor.execute("""
            INSERT INTO schedule (user_id, week_type, day, subject, time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, week_type, day, subject, time))
        self.conn.commit()
    
    def get_schedule(self, user_id, week_type, day):
        self.cursor.execute("""
            SELECT subject, time FROM schedule
            WHERE user_id = ? AND week_type = ? AND day = ?
            ORDER BY time
        """, (user_id, week_type, day))
        return self.cursor.fetchall()
    
    def get_all_schedule_for_user(self, user_id):
        self.cursor.execute("""
            SELECT id, week_type, day, subject, time FROM schedule
            WHERE user_id = ?
            ORDER BY week_type, day, time
        """, (user_id,))
        return self.cursor.fetchall()
    
    def save_homework(self, user_id, subject, task, deadline):
        self.cursor.execute("""
            INSERT INTO homework (user_id, subject, task, deadline, is_notified)
            VALUES (?, ?, ?, ?, 0)
        """, (user_id, subject, task, deadline))
        self.conn.commit()
    
    def get_all_homeworks_for_user(self, user_id):
        self.cursor.execute("""
            SELECT * FROM homework
            WHERE user_id = ?
            ORDER BY deadline ASC
        """, (user_id,))
        return self.cursor.fetchall()
