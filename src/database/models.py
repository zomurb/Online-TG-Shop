import sqlite3
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.config import DB_NAME

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Корзина
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                size TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id, size)
            )
        ''')      
        
        # Заказы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone TEXT NOT NULL,       
                order_data TEXT NOT NULL,
                city TEXT NOT NULL,
                status TEXT DEFAULT 'new',
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                comment TEXT DEFAULT '',
                promo_code TEXT,
                discount REAL DEFAULT 0,
                total REAL DEFAULT 0
            )
        ''')

        # Товары
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                photo_id TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL
            )
        ''')
        
        # Медиа товаров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                kind TEXT CHECK(kind IN ('photo','video')) NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        ''')
        
        # Админы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                username TEXT PRIMARY KEY
            )
        ''')
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Промокоды
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                kind TEXT CHECK(kind IN ('percent','fixed')) NOT NULL,
                amount REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT
            )
        ''')

        # Избранное (НОВАЯ ФИЧА)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                UNIQUE(user_id, product_id),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        
        conn.commit()

def check_and_fix_db():
    # Эта функция сохранена для совместимости при миграции со старых версий
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.execute("PRAGMA table_info(orders)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'phone' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN phone TEXT DEFAULT 'не указан'")
            if 'comment' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN comment TEXT DEFAULT ''")
            if 'promo_code' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT")
            if 'discount' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0")
            if 'total' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN total REAL DEFAULT 0")
            
            cursor = conn.execute("PRAGMA table_info(promo_codes)")
            promo_columns = [column[1] for column in cursor.fetchall()]
            if 'expires_at' not in promo_columns:
                conn.execute("ALTER TABLE promo_codes ADD COLUMN expires_at TEXT")

            conn.commit()
    except Exception as e:
        logging.critical(f"Ошибка миграции: {str(e)}")

def format_dt_gmt_minus5(ts: str) -> str:
    try:
        if isinstance(ts, datetime):
            dt = ts
        else:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        local = dt - timedelta(hours=5)
        return local.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
