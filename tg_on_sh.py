# --------- Часть 1/3: Настройка бота ---------
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import sqlite3
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties  # <-- Добавлено
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage  # <-- Добавлено
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery,
    ReplyKeyboardRemove,
    ContentType,
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Настройка бота
TOKEN = "YOUUR_BOT_TOKEN"
router = Router()
bot = Bot(
    token=TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)  
)
dp = Dispatcher(storage=MemoryStorage())  
dp.include_router(router)


class AdminAddProductStates(StatesGroup):
    category = State()
    media = State()
    description = State()
    price = State()
    quantity = State()
class AdminDeleteProductStates(StatesGroup):
    select_product = State()
    confirm = State()
class AdminAddUserStates(StatesGroup):
    username = State()
class AdminPromoStates(StatesGroup):
    code = State()
    kind = State()
    amount = State()
    expires = State()
class OrderStates(StatesGroup):
    wait_custom_city = State()  
    wait_phone = State() 
    wait_city = State()
    wait_comment = State()
    wait_promo = State()
class AdminOrderStates(StatesGroup):
    select_order = State()
    change_status = State()
class AdminBroadcastStates(StatesGroup):
    content = State()
    

def init_db():
    with sqlite3.connect('TG_ON_SH.db') as conn:
        cursor = conn.cursor()
        

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id)
            )
        ''')      
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone TEXT NOT NULL,       
                order_data TEXT NOT NULL,
                city TEXT NOT NULL,
                status TEXT DEFAULT 'new',
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                username TEXT PRIMARY KEY
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                kind TEXT CHECK(kind IN ('percent','fixed')) NOT NULL,
                amount REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT
            )
        ''')
        
        conn.commit()
init_db()



def check_and_fix_db():
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            # Проверяем наличие колонки phone
            cursor = conn.execute("PRAGMA table_info(orders)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'phone' not in columns:
                # Экстренное исправление структуры
                conn.execute('''
                    ALTER TABLE orders 
                    ADD COLUMN phone TEXT DEFAULT 'не указан'
                ''')
                conn.commit()
                logging.info("Колонка phone добавлена в таблицу orders")

            # Добавляем колонку comment, если отсутствует
            cursor = conn.execute("PRAGMA table_info(orders)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'comment' not in columns:
                conn.execute("""
                    ALTER TABLE orders
                    ADD COLUMN comment TEXT DEFAULT ''
                """)
                conn.commit()
                logging.info("Колонка comment добавлена в таблицу orders")

            # Добавляем колонки для промокода/скидки/итога
            cursor = conn.execute("PRAGMA table_info(orders)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'promo_code' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT")
            if 'discount' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0")
            if 'total' not in columns:
                conn.execute("ALTER TABLE orders ADD COLUMN total REAL DEFAULT 0")
            conn.commit()

            # Добавляем expires_at в promo_codes при необходимости
            cursor = conn.execute("PRAGMA table_info(promo_codes)")
            promo_columns = [column[1] for column in cursor.fetchall()]
            if 'expires_at' not in promo_columns:
                conn.execute("ALTER TABLE promo_codes ADD COLUMN expires_at TEXT")
                conn.commit()

            # Проверяем таблицу cart на наличие size и корректного UNIQUE
            cursor = conn.execute("PRAGMA table_info(cart)")
            cart_columns = [column[1] for column in cursor.fetchall()]
            need_cart_migration = 'size' not in cart_columns

            if need_cart_migration:
                logging.info("Миграция таблицы cart для поддержки размера")
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS cart_new (
                        user_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        size TEXT,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        UNIQUE(user_id, product_id, size)
                    )
                ''')
                # Переносим старые данные, размер будет NULL
                conn.execute('''
                    INSERT OR IGNORE INTO cart_new (user_id, product_id, quantity)
                    SELECT user_id, product_id, quantity FROM cart
                ''')
                conn.execute('DROP TABLE cart')
                conn.execute('ALTER TABLE cart_new RENAME TO cart')
                conn.commit()
                logging.info("Таблица cart мигрирована")
                
    except Exception as e:
        logging.critical(f"Ошибка миграции: {str(e)}")

# Форматирование даты в GMT-5
def format_dt_gmt_minus5(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        local = dt - timedelta(hours=5)
        return local.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ts

# Главное меню (должно быть объявлено ПЕРЕД использованием)
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Каталог"), KeyboardButton(text="Корзина")],
            [KeyboardButton(text="Мои заказы")]
        ],
        resize_keyboard=True
    )

# Обработчик старта с меню 
@router.message(Command("start"))
async def start_handler(msg: Message):
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.execute('''
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name
            ''', (
                msg.from_user.id,
                msg.from_user.username,
                msg.from_user.first_name,
                msg.from_user.last_name
            ))
            conn.commit()
    except Exception as e:
        logging.error(f"Не удалось сохранить пользователя: {e}")
    await msg.answer(
        "👟 Добро пожаловать в магазин обуви!",
        reply_markup=main_menu()  # <-- Теперь функция доступна
    )

# Остальной код Части 2/3...

@router.message(F.text == "Каталог")
async def show_categories(msg: Message):
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row  # Добавлено для удобства
            categories = conn.execute('''
                SELECT DISTINCT category 
                FROM products 
                WHERE quantity > 0  
            ''').fetchall()

        if not categories:
            return await msg.answer("😢 Каталог пуст. Зайдите позже!")
        
        builder = InlineKeyboardBuilder()
        for category in categories:
            builder.add(InlineKeyboardButton(
                text=category["category"],
                callback_data=f"cat_{category['category']}"  # Убедитесь в правильности префикса
            ))
        
        builder.adjust(2)
        await msg.answer(
            "👟 Выберите категорию:", 
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка каталога: {e}")
        await msg.answer("⚠️ Произошла ошибка. Попробуйте позже.") 
        
@router.callback_query(F.data.startswith("cat_"))  # Обработчик категорий
async def show_products(callback: CallbackQuery):
    try:
        category = callback.data.split("cat_")[1]
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            products = conn.execute('''
                SELECT id, description, price 
                FROM products 
                WHERE category = ? AND quantity > 0
            ''', (category,)).fetchall()
        
        builder = InlineKeyboardBuilder()
        for product in products:
            # Используем префикс "prd_" для товаров ▼
            builder.button(
                text=f"{product['description']} - {product['price']} TJS",
                callback_data=f"prd_{product['id']}"  # <- Единый префикс
            )
        
        builder.adjust(1)
        await callback.message.edit_text(
            f"Товары в категории {category}:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        await callback.answer("❌ Ошибка загрузки товаров")

@router.callback_query(F.data.startswith("prd_"))
async def show_product(callback: CallbackQuery):
    try:
        product_id = int(callback.data.split("prd_")[1])
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            product = conn.execute('''
                SELECT * FROM products WHERE id = ?
            ''', (product_id,)).fetchone()

        # Кнопки выбора размера
        builder = InlineKeyboardBuilder()
        for size in ["36","37","38","39","40","41","42","43","44","45"]:
            builder.button(text=f"Размер {size}", callback_data=f"size_{product_id}_{size}")
        builder.adjust(3, 3, 4)
        
        # Загружаем дополнительные медиа
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            media_items = conn.execute('''
                SELECT file_id, kind FROM product_media
                WHERE product_id = ?
                ORDER BY position ASC
            ''', (product_id,)).fetchall()

        # Отправляем главное изображение и галерею
        await callback.message.answer_photo(
            photo=product['photo_id'],
            caption=f"👟 Модель: {product['description']}\n💰 Цена: {product['price']} TJS",
            reply_markup=builder.as_markup()
        )
        # Остальные медиа без подписи
        for m in media_items[1:]:
            if m['kind'] == 'photo':
                await callback.message.answer_photo(photo=m['file_id'])
            else:
                await callback.message.answer_video(video=m['file_id'])
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка товара: {str(e)}")
        await callback.answer("⚠️ Ошибка загрузки")
        
@router.callback_query(F.data.startswith("size_"))
async def add_to_cart_with_size(callback: CallbackQuery):
    try:
        _, product_id_str, size = callback.data.split("_", 2)
        product_id = int(product_id_str)
        user_id = callback.from_user.id
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            # Проверяем существование товара
            product = conn.execute('''
                SELECT id FROM products 
                WHERE id = ? AND quantity > 0
            ''', (product_id,)).fetchone()
            
            if not product:
                return await callback.answer("❌ Товар закончился", show_alert=True)
            
            # Добавляем в корзину
            conn.execute('''
                INSERT INTO cart (user_id, product_id, size, quantity)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, product_id, size) 
                DO UPDATE SET quantity = quantity + 1
            ''', (user_id, product_id, size))
            conn.commit()
        
        await callback.answer(f"✅ Добавлено: размер {size}")
    except Exception as e:
        logging.error(f"Ошибка корзины: {str(e)}")
        await callback.answer("⚠️ Не удалось добавить товар")

# Корзина: исправленный код
@router.message(F.text == "Корзина")
async def show_cart(msg: Message):
    try:
        user_id = msg.from_user.id
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            items = conn.execute('''
                SELECT p.id, p.description, p.price, c.quantity, c.size 
                FROM cart c 
                JOIN products p ON c.product_id = p.id 
                WHERE c.user_id = ?
            ''', (user_id,)).fetchall()
        
        if not items:
            return await msg.answer("🛒 Корзина пуста")
        
        total = 0
        response = ["📦 Ваша корзина:"]
        for item in items:
            line_total = item['price'] * item['quantity']
            response.append(
                f"{item['description']} (р. {item['size'] or '-'} ) x{item['quantity']} = {line_total} TJS"
            )
            total += line_total
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")
        ]])
        
        await msg.answer(
            "\n".join(response) + f"\n\n💵 Итого: {total}TJS",
            reply_markup=kb
        )
    except Exception as e:
        await msg.answer("🚫 Не удалось загрузить корзину")
        
@router.callback_query(F.data == "checkout")
async def process_checkout(callback: CallbackQuery, state: FSMContext):
    try:
        # 1. Получаем данные корзины
        user_id = callback.from_user.id
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            cart_items = conn.execute('''
                SELECT product_id, size, quantity 
                FROM cart 
                WHERE user_id = ?
            ''', (user_id,)).fetchall()

            if not cart_items:
                await callback.answer("🛒 Корзина пуста!")
                return

        # 1.1 Сохраняем состав заказа в состояние, чтобы не терять
        order_data = ";".join([f"{row['product_id']}:{row['quantity']}:{row['size'] or ''}" for row in cart_items])
        await state.update_data(order_data=order_data)

        # 2. Запрашиваем контакт
        await callback.message.answer(
            "📞 Для оформления заказа поделитесь контактом:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Отправить контакт", request_contact=True)],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        await state.set_state(OrderStates.wait_phone)
        await callback.answer()

    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        await callback.answer("⚠️ Ошибка оформления")

# --------- Часть 3/3: Обработчик контакта ---------
@router.message(OrderStates.wait_phone, F.contact)
async def process_contact(msg: Message, state: FSMContext):
    try:
        logging.info(f"Начало обработки контакта для user_id={msg.from_user.id}")
        
        phone = msg.contact.phone_number
        logging.info(f"Получен номер: {phone}")
        await state.update_data(phone=phone)
        
        # Тестовая отправка сообщения
        await msg.answer("🔄 Тестовое сообщение после контакта", reply_markup=ReplyKeyboardRemove())
        logging.info("Тестовое сообщение отправлено")
        
        # Отправка клавиатуры городов
        await msg.answer("🏙 Выберите город:", reply_markup=city_keyboard())
        logging.info("Клавиатура городов отправлена")
        
        await state.set_state(OrderStates.wait_city)
        logging.info(f"Установлено состояние: wait_city")
        
    except Exception as e:
        logging.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
        await msg.answer("🚫 Техническая неполадка, попробуйте позже")
        await state.clear()

@router.message(
    StateFilter(OrderStates),
    F.text.func(lambda t: (t or '').strip().lower() in {"отмена", "❌ отмена", "отменить оформление", "❌ отменить оформление"})
)
async def cancel_checkout_anytime(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Оформление отменено", reply_markup=main_menu())

# --------- Часть 2/3: Проверка клавиатуры городов ---------
def city_keyboard():
    try:
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="Душанбе", callback_data="city_Душанбе"),
            InlineKeyboardButton(text="Худжанд", callback_data="city_Худжанд"),
            InlineKeyboardButton(text="Истаравшан", callback_data="city_Истаравшан"),
            InlineKeyboardButton(text="Другой город", callback_data="city_other")
        )
        builder.adjust(2, 2)
        return builder.as_markup()
    except Exception as e:
        logging.error(f"Ошибка создания клавиатуры: {str(e)}")
        return None

# Проверка данных в БД:
# 1. Убедитесь, что в таблице products есть записи:
# SELECT * FROM products;

# 2. Проверьте корзину для вашего user_id:
# SELECT * FROM cart WHERE user_id = YOUR_ID;



# Обработка выбора города
@router.callback_query(OrderStates.wait_city, F.data.startswith("city_"))
async def handle_city_selection(callback: CallbackQuery, state: FSMContext):
    try:
        # Обработка кастомного города
        if callback.data == "city_other":
            await callback.message.answer("🏙 Введите свой город текстом:")
            await state.set_state(OrderStates.wait_custom_city)
            await callback.answer()
            return

        city = callback.data.split("_", 1)[1]
        await state.update_data(city=city)
        # Запрашиваем промокод
        await callback.message.answer(
            "🏷 Введите промокод или напишите 'Пропустить'"
        )
        await state.set_state(OrderStates.wait_promo)
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        await callback.answer("⚠️ Ошибка оформления")
        
@router.message(OrderStates.wait_custom_city)
async def process_custom_city(msg: Message, state: FSMContext):
    try:
        user_id = msg.from_user.id
        city = msg.text.strip()
        await state.update_data(city=city)
        await msg.answer("🏷 Введите промокод или напишите 'Пропустить'")
        await state.set_state(OrderStates.wait_promo)
        
    except Exception as e:
        await msg.answer("⚠️ Ошибка сохранения, попробуйте снова")
        logging.error(f"Custom city error: {str(e)}")

@router.message(OrderStates.wait_promo)
async def process_promo(msg: Message, state: FSMContext):
    code = (msg.text or '').strip()
    if code.lower() == 'пропустить' or not code:
        await msg.answer(
            "📝 Оставьте комментарий к заказу (адрес, пожелания).\nЕсли не нужно — напишите 'Пропустить'."
        )
        await state.set_state(OrderStates.wait_comment)
        return

    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT code, kind, amount, active, expires_at FROM promo_codes WHERE code = ?',
                (code,)
            ).fetchone()
        if not row or not row['active']:
            await msg.answer("❌ Промокод не найден или не активен. Попробуйте другой или напишите 'Пропустить'.")
            return
        # проверяем срок (по часовому поясу Душанбе)
        expires_at = row['expires_at']
        if expires_at:
            try:
                # expires_at хранится как локальное время Душанбе (Asia/Dushanbe, UTC+5)
                expires_dt_local = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Dushanbe"))
                now_dushanbe = datetime.now(ZoneInfo("Asia/Dushanbe"))
                if now_dushanbe > expires_dt_local:
                    await msg.answer("⌛ Срок действия промокода истёк. Введите другой или 'Пропустить'.")
                    return
            except Exception:
                pass
        await state.update_data(promo_code=row['code'], promo_kind=row['kind'], promo_amount=float(row['amount']))
        await msg.answer("✅ Промокод применён. Теперь добавьте комментарий или напишите 'Пропустить'.")
        await state.set_state(OrderStates.wait_comment)
    except Exception as e:
        logging.error(f"Промокод ошибка: {e}")
        await msg.answer("⚠️ Ошибка проверки промокода. Напишите 'Пропустить' или попробуйте позже.")

@router.message(OrderStates.wait_comment)
async def process_order_comment(msg: Message, state: FSMContext):
    try:
        user_id = msg.from_user.id
        comment_text = msg.text.strip()
        if comment_text.lower() == 'пропустить':
            comment_text = ''

        data = await state.get_data()
        city = data.get('city', '')
        phone = data.get('phone', 'не указан')
        order_data = data.get('order_data', '')

        with sqlite3.connect('TG_ON_SH.db') as conn:
            # если order_data нет в состоянии — соберем из корзины
            if not order_data:
                conn.row_factory = sqlite3.Row
                cart_items = conn.execute('''
                    SELECT product_id, size, quantity FROM cart WHERE user_id = ?
                ''', (user_id,)).fetchall()
                order_data = ";".join([f"{row['product_id']}:{row['quantity']}:{row['size'] or ''}" for row in cart_items])

            # Считаем сумму корзины
            subtotal = conn.execute('''
                SELECT COALESCE(SUM(p.price * c.quantity), 0)
                FROM cart c JOIN products p ON p.id = c.product_id
                WHERE c.user_id = ?
            ''', (user_id,)).fetchone()[0] or 0.0

            # Применяем промокод, если есть
            promo_code = data.get('promo_code')
            promo_kind = data.get('promo_kind')
            promo_amount = float(data.get('promo_amount', 0) or 0)
            discount = 0.0
            if promo_code and promo_kind in ('percent','fixed') and promo_amount > 0:
                if promo_kind == 'percent':
                    discount = round(subtotal * (promo_amount / 100.0), 2)
                else:
                    discount = float(promo_amount)
                if discount > subtotal:
                    discount = subtotal
            total = round(subtotal - discount, 2)

            conn.execute('''
                INSERT INTO orders (user_id, phone, city, order_data, comment, promo_code, discount, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, phone, city, order_data or '', comment_text, promo_code, discount, total))
            new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
            conn.commit()

        await msg.answer(
            f"✅ Заказ оформлен!\n🆔 Номер: {new_id}\n"
            f"💵 Сумма: {subtotal} TJS\n"
            f"🔖 Скидка: {discount} TJS\n"
            f"🧾 Итого к оплате: {total} TJS\n"
            f"📊 Статус: new\nМы свяжемся с вами для уточнения доставки."
        )
        await state.clear()
    except Exception as e:
        logging.error(f"Ошибка сохранения заказа: {str(e)}")
        await msg.answer("⚠️ Не удалось оформить заказ, попробуйте снова")

# Удален дубликат функции city_keyboard() ниже
# История заказов
@router.message(F.text == "Мои заказы")
async def show_orders(msg: Message):
    try:
        user_id = msg.from_user.id
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            orders = conn.execute('''
                SELECT id, order_date, city, status 
                FROM orders 
                WHERE user_id = ?
                ORDER BY order_date DESC
            ''', (user_id,)).fetchall()
        
        if not orders:
            return await msg.answer("📭 У вас пока нет заказов")
        
        response = []
        for order in orders:
            date = format_dt_gmt_minus5(order['order_date'])
            response.append(
                f"🆔 Заказ #{order['id']}\n"
                f"📅 {date}\n"
                f"🏙 {order['city']}\n"
                f"📊 Статус: {order['status']}\n"
            )
        
        await msg.answer("\n\n".join(response))
        
    except Exception as e:
        logging.error(f"Ошибка заказов: {str(e)}")
        await msg.answer("⚠️ Ошибка загрузки заказов")
        
        
init_db()  # Создает таблицу заново
check_and_fix_db()  # Дополнительная проверка
    
    

# Проверка прав админа
async def is_admin(username: str | None):
    if not username:
        return False
    
    # Приводим к нижнему регистру и добавляем @ если отсутствует
    username = username.lstrip('@').lower()
    
    with sqlite3.connect('TG_ON_SH.db') as conn:
        cursor = conn.cursor()
        result = cursor.execute(
            "SELECT username FROM admins WHERE LOWER(TRIM(username, '@')) = ?", 
            (username,)
        ).fetchone()
    
    return bool(result)
    
# Админ-меню
def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить товар", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="Удалить товар", callback_data="admin_delete_product")],
        [InlineKeyboardButton(text="Просмотреть заказы", callback_data="admin_view_orders")],
        [InlineKeyboardButton(text="Добавить админа", callback_data="admin_add_user")],
        [InlineKeyboardButton(text="Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="Промокоды", callback_data="admin_promos")]
    ])

# Обработчик /admin
@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.username):
        return await msg.answer("❌ Доступ запрещен")
    await msg.answer("👮 Админ-панель:", reply_markup=admin_menu())
    
# Добавление админа через callback
@router.callback_query(F.data == "admin_add_user")
async def add_admin_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите username нового админа:")
    await state.set_state(AdminAddUserStates.username)
@router.callback_query(F.data == "admin_promos")
async def admin_promos_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.username):
        await callback.answer("⛔️ Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("🏷 Введите код промокода (латиница/цифры, без пробелов):")
    await state.set_state(AdminPromoStates.code)
    await callback.answer()

@router.message(AdminPromoStates.code)
async def admin_promos_set_code(msg: Message, state: FSMContext):
    code = (msg.text or '').strip()
    if not code or ' ' in code or len(code) > 32:
        await msg.answer("❌ Неверный код. Введите без пробелов, до 32 символов.")
        return
    await state.update_data(code=code)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="% (проценты)", callback_data="promo_kind_percent")],
        [InlineKeyboardButton(text="–N TJS (фикс)", callback_data="promo_kind_fixed")]
    ])
    await msg.answer("Выберите тип скидки:", reply_markup=kb)

@router.callback_query(F.data.startswith("promo_kind_"))
async def admin_promos_set_kind(callback: CallbackQuery, state: FSMContext):
    kind = callback.data.split("promo_kind_")[1]
    await state.update_data(kind=kind)
    await callback.message.answer("Введите размер скидки (число). Для % — 5,10,15 и т.д.; для фикса — сумма в TJS.")
    await state.set_state(AdminPromoStates.amount)
    await callback.answer()

@router.message(AdminPromoStates.amount)
async def admin_promos_save(msg: Message, state: FSMContext):
    try:
        amount = float((msg.text or '').replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except Exception:
        await msg.answer("❌ Введите корректное положительное число.")
        return
    data = await state.get_data()
    code = data.get('code')
    kind = data.get('kind')
    if kind not in ('percent','fixed'):
        await msg.answer("❌ Сначала выберите тип скидки.")
        return
    await state.update_data(amount=amount)
    await msg.answer(
        "⏳ Введите срок действия в формате YYYY-MM-DD HH:MM (или напишите 'Пропустить' для бессрочного)"
    )
    await state.set_state(AdminPromoStates.expires)

@router.message(AdminPromoStates.expires)
async def admin_promos_save_with_expiry(msg: Message, state: FSMContext):
    text = (msg.text or '').strip()
    expires_at = None
    if text.lower() != 'пропустить':
        try:
            # ожидаем локальный формат без таймзоны
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
            expires_at = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            await msg.answer("❌ Неверный формат. Пример: 2025-12-31 23:59. Или напишите 'Пропустить'.")
            return
    data = await state.get_data()
    code = data.get('code')
    kind = data.get('kind')
    amount = data.get('amount')
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.execute('''
                INSERT INTO promo_codes (code, kind, amount, active, expires_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(code) DO UPDATE SET kind=excluded.kind, amount=excluded.amount, active=1, expires_at=excluded.expires_at
            ''', (code, kind, amount, expires_at))
            conn.commit()
        exp_text = expires_at or 'бессрочно'
        await msg.answer(f"✅ Промокод сохранён: {code} / {kind} / {amount} / действует до: {exp_text}")
    except Exception as e:
        await msg.answer(f"⚠️ Ошибка сохранения: {e}")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.username):
        await callback.answer("⛔️ Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("📨 Введите текст рассылки (будет отправлен всем пользователям):")
    await state.set_state(AdminBroadcastStates.content)
    await callback.answer()

@router.message(AdminBroadcastStates.content)
async def admin_broadcast_send(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.username):
        await msg.answer("⛔️ Доступ запрещен")
        await state.clear()
        return
    text = msg.text.strip()
    sent = 0
    failed = 0
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            users = conn.execute('SELECT user_id FROM users').fetchall()
        for row in users:
            try:
                await bot.send_message(chat_id=row[0], text=text)
                sent += 1
            except Exception:
                failed += 1
        await msg.answer(f"✅ Рассылка завершена. Успешно: {sent}, ошибок: {failed}")
    except Exception as e:
        await msg.answer(f"⚠️ Ошибка рассылки: {e}")
    finally:
        await state.clear()



@router.message(AdminAddUserStates.username)
async def process_add_admin(msg: Message, state: FSMContext):
    username = msg.text.strip().lower()
    if not username.startswith("@"):
        username = "@" + username
    
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admins VALUES (?)",
                (username,)
            )
            conn.commit()
        await msg.answer(f"✅ Админ {username} добавлен!")
    except Exception as e:
        await msg.answer("❌ Ошибка добавления!")
    finally:
        await state.clear()
        
@router.callback_query(F.data == "admin_delete_product")
async def start_delete_product(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔢 Введите ID товара для удаления:")
    await state.set_state(AdminDeleteProductStates.select_product)
    
# Обработка ID товара
@router.message(AdminDeleteProductStates.select_product)
async def process_product_id(msg: Message, state: FSMContext):
    try:
        product_id = int(msg.text)
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row  # Добавьте эту строку
            product = conn.execute('''
                SELECT * FROM products WHERE id = ?
            ''', (product_id,)).fetchone()
            
            if not product:
                return await msg.answer("❌ Товар не найден")
            
            await state.update_data(product_id=product_id)
            
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Подтвердить", callback_data="delete_confirm")
            kb.button(text="❌ Отмена", callback_data="delete_cancel")
            
            await msg.answer(
                f"Удалить товар?\n"
                f"ID: {product_id}\n"
                f"Название: {product['description']}",  # Теперь работает
                reply_markup=kb.as_markup()
            )
            await state.set_state(AdminDeleteProductStates.confirm)
    except ValueError:
        await msg.answer("❌ Неверный формат ID")

# Подтверждение удаления
@router.callback_query(AdminDeleteProductStates.confirm, F.data == "delete_confirm")
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data['product_id']
    
    try:
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
            conn.commit()
        
        await callback.message.answer("✅ Товар успешно удален")
        await state.clear()
    except Exception as e:
        await callback.message.answer("❌ Ошибка удаления")
    
    await callback.answer()

# Отмена удаления
@router.callback_query(AdminDeleteProductStates.confirm, F.data == "delete_cancel")
async def cancel_delete(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Удаление отменено")
    await callback.answer()

# Начало добавления товара
@router.callback_query(F.data == "admin_add_product")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    try:
        # 1. Проверка прав администратора (дополнительная защита)
        if not await is_admin(callback.from_user.username):
            await callback.answer("⛔️ Доступ запрещен!", show_alert=True)
            return

        # 2. Логирование действия
        logging.info(f"Админ @{callback.from_user.username} начал добавление товара")

        # 3. Загрузка существующих категорий для подсказки
        with sqlite3.connect('TG_ON_SH.db') as conn:
            categories = conn.execute('''
                SELECT DISTINCT category FROM products
            ''').fetchall()

        # 4. Отправка списка существующих категорий
        if categories:
            categories_list = "\n".join([f"• {cat[0]}" for cat in categories])
            await callback.message.answer(
                f"🌿 Существующие категории:\n{categories_list}\n\n"
                "✏️ Введите новую категорию или выберите из списка:"
            )
        else:
            await callback.message.answer("✏️ Введите название категории:")

        # 5. Установка состояния
        await state.set_state(AdminAddProductStates.category)
        await callback.answer()

    except sqlite3.Error as e:
        logging.error(f"Ошибка БД: {str(e)}")
        await callback.message.answer("⚠️ Ошибка доступа к базе данных")
        await state.clear()

    except Exception as e:
        logging.error(f"Ошибка: {str(e)}", exc_info=True)
        await callback.message.answer("❌ Неизвестная ошибка")
        await state.clear()

@router.message(AdminAddProductStates.category)
async def process_category(msg: Message, state: FSMContext):
    try:
        if not msg.text or len(msg.text) > 50:
            raise ValueError("Некорректная категория")
        
        await state.update_data(category=msg.text.strip())
        await msg.answer(
            "📸 Отправьте фото/видео товара. Можно несколько сообщениями.\n"
            "Когда закончите — отправьте слово ‘Готово’."
        )
        await state.update_data(media_list=[])
        await state.set_state(AdminAddProductStates.media)
    except Exception as e:
        await msg.answer("❌ Ошибка: " + str(e))
        await state.clear()

@router.message(AdminAddProductStates.media, F.photo)
async def process_media_photo(msg: Message, state: FSMContext):
    try:
        photo = msg.photo[-1]
        data = await state.get_data()
        media_list = data.get('media_list', [])
        media_list.append({
            'file_id': photo.file_id,
            'kind': 'photo'
        })
        await state.update_data(media_list=media_list)
        await msg.answer(f"✅ Фото добавлено. Всего: {len(media_list)}. Отправьте ещё или ‘Готово’.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка загрузки: {str(e)}")

@router.message(AdminAddProductStates.media, F.video)
async def process_media_video(msg: Message, state: FSMContext):
    try:
        video = msg.video
        data = await state.get_data()
        media_list = data.get('media_list', [])
        media_list.append({
            'file_id': video.file_id,
            'kind': 'video'
        })
        await state.update_data(media_list=media_list)
        await msg.answer(f"✅ Видео добавлено. Всего: {len(media_list)}. Отправьте ещё или ‘Готово’.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка загрузки: {str(e)}")

@router.message(AdminAddProductStates.media)
async def process_media_done_or_text(msg: Message, state: FSMContext):
    # Переход по слову Готово
    if msg.text and msg.text.strip().lower() == 'готово':
        data = await state.get_data()
        media_list = data.get('media_list', [])
        if not media_list:
            await msg.answer("❗ Сначала добавьте хотя бы одно фото или видео.")
            return
        await msg.answer("📝 Введите описание товара (макс. 200 символов):")
        await state.set_state(AdminAddProductStates.description)
        return
    else:
        await msg.answer("📎 Отправьте фото/видео или ‘Готово’ для продолжения.")

@router.message(AdminAddProductStates.description)
async def process_description(msg: Message, state: FSMContext):
    try:
        if len(msg.text) > 200 or not msg.text.strip():
            raise ValueError("Неверное описание")
        
        await state.update_data(description=msg.text.strip())
        await msg.answer("💵 Введите цену в формате 999.99:")
        await state.set_state(AdminAddProductStates.price)
    except Exception as e:
        await msg.answer("❌ Ошибка: " + str(e))
        await state.clear()

@router.message(AdminAddProductStates.price)
async def process_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(',', '.'))
        if price <= 0 or price > 1000000:
            raise ValueError("Недопустимая цена")
        
        await state.update_data(price=round(price, 2))
        await msg.answer("🔢 Введите количество товара:")
        await state.set_state(AdminAddProductStates.quantity)
    except Exception as e:
        await msg.answer("❌ Ошибка: " + str(e))
        await state.clear()

@router.message(AdminAddProductStates.quantity)
async def process_quantity(msg: Message, state: FSMContext):
    try:
        quantity = int(msg.text)
        if quantity <= 0 or quantity > 10000:
            raise ValueError("Недопустимое количество")
        
        data = await state.get_data()
        
        # Полная валидация данных
        required = {
            'category': str,
            'description': str,
            'price': float
        }
        
        for field, field_type in required.items():
            if field not in data:
                raise ValueError(f"Отсутствует поле {field}")
            if not isinstance(data[field], field_type):
                raise TypeError(f"Неверный тип {field}")
        
        # SQL-запрос с проверкой
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.execute('''
                INSERT INTO products 
                (category, photo_id, description, price, quantity)
        VALUES (?, ?, ?, ?, ?)
            ''', (
                data['category'],
                (data.get('media_list') or [{}])[0].get('file_id', ''),
                data['description'],
                data['price'],
                quantity
            ))
            conn.commit()
            new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Сохраняем медиагалерею
            media_list = data.get('media_list', [])
            for idx, m in enumerate(media_list):
                conn.execute('''
                    INSERT INTO product_media (product_id, file_id, kind, position)
                    VALUES (?, ?, ?, ?)
                ''', (new_id, m['file_id'], m['kind'], idx))
            conn.commit()
        
        await msg.answer(f"""
            ✅ Товар успешно добавлен!
            ID: {new_id}
            📸 Медиа: {len(data.get('media_list', []))} шт.
            📝 Описание: {data['description']}
            💵 Цена: {data['price']} TJS
            🧮 Количество: {quantity} шт.
        """)
    except Exception as e:
        error_msg = f"⛔️ Критическая ошибка: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await msg.answer(error_msg)
    finally:
        await state.clear()


# Просмотр заказов
@router.callback_query(F.data == "admin_view_orders")
async def admin_view_orders(callback: CallbackQuery):
    try:
        # Только для админов
        if not await is_admin(callback.from_user.username):
            await callback.answer("⛔️ Доступ запрещен", show_alert=True)
            return
        # Показ меню выбора статуса вместо полной выдачи
        kb = InlineKeyboardBuilder()
        for s in ["new", "processing", "delivered", "cancelled"]:
            kb.button(text=s.capitalize(), callback_data=f"admin_orders_status_{s}")
        kb.adjust(2, 2)
        await callback.message.answer("Выберите статус заказов для просмотра:", reply_markup=kb.as_markup())
        await callback.answer()

    except Exception as e:
        logging.error(f"Ошибка заказов: {str(e)}", exc_info=True)
        await callback.answer("⚠️ Ошибка загрузки")
            
@router.callback_query(F.data.startswith("admin_orders_status_"))
async def admin_orders_by_status(callback: CallbackQuery):
    try:
        if not await is_admin(callback.from_user.username):
            await callback.answer("⛔️ Доступ запрещен", show_alert=True)
            return
        status = callback.data.split("admin_orders_status_")[1]
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            orders = conn.execute('''
                SELECT id, user_id, phone, city, status, order_date, comment, promo_code, discount, total
                FROM orders WHERE status = ?
                ORDER BY order_date DESC LIMIT 20
            ''', (status,)).fetchall()

        if not orders:
            await callback.message.answer("📭 Нет заказов с таким статусом")
            await callback.answer()
            return

        for order in orders:
            order_date_raw = order['order_date'] if 'order_date' in order.keys() else 'N/A'
            try:
                formatted_date = format_dt_gmt_minus5(order_date_raw)
            except Exception:
                formatted_date = order_date_raw
            phone = order['phone'] if order['phone'] else 'Не указан'
            city = order['city'] if order['city'] else 'Не указан'
            promo = order['promo_code'] or '—'
            discount = order['discount'] or 0
            total = order['total'] or 0

            text = (
                f"🆔 Заказ #{order['id']}\n"
                f"👤 User ID: {order['user_id']}\n"
                f"📞 Телефон: {phone}\n"
                f"🏙 Город: {city}\n"
                f"📅 Дата: {formatted_date}\n"
                f"📊 Статус: {order['status']}\n"
                f"🏷 Промо: {promo}\n"
                f"🔖 Скидка: {discount} TJS\n"
                f"🧾 Итого: {total} TJS\n"
            )

            kb = InlineKeyboardBuilder()
            kb.button(text="Показать", callback_data=f"order_{order['id']}")
            kb.button(text="Изменить статус", callback_data=f"change_status_{order['id']}")
            kb.adjust(2)
            await callback.message.answer(text, reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка списка по статусу: {e}")
        await callback.answer("⚠️ Ошибка загрузки")

@router.callback_query(F.data.startswith("order_"))
async def show_order_details(callback: CallbackQuery, state: FSMContext):
    try:  # Добавляем блок try для обработки исключений
        order_id = int(callback.data.split("_")[1])
        
        with sqlite3.connect('TG_ON_SH.db') as conn:
            conn.row_factory = sqlite3.Row
            order = conn.execute('''
                SELECT * FROM orders WHERE id = ?
            ''', (order_id,)).fetchone()
            
            if not order:
                await callback.answer("Заказ не найден")
                return

            products = []
            order_items_str = order['order_data'] or ''
            order_items = [x for x in order_items_str.split(';') if x]
            for item in order_items:
                try:
                    product_id_str, quantity_and_maybe_size = item.split(':', 1)
                    if ':' in quantity_and_maybe_size:
                        quantity_str, size_str = quantity_and_maybe_size.split(':', 1)
                    else:
                        quantity_str, size_str = quantity_and_maybe_size, ''
                    product_id = int(product_id_str)
                    quantity = int(quantity_str)
                except Exception:
                    continue

                product = conn.execute('''
                    SELECT description, price, photo_id 
                    FROM products 
                    WHERE id = ?
                ''', (product_id,)).fetchone()

                if product:
                    size_note = f" (р. {size_str})" if size_str else ''
                    products.append(
                        f"{product['description']}{size_note} x{quantity} - {product['price'] * quantity} TJS"
                    )

            # Отправка фото первого товара и деталей заказа
            if products:
                first_product = conn.execute(
                    'SELECT photo_id FROM products WHERE id = ?',
                    (int(order_items[0].split(':', 1)[0]),)
                ).fetchone()

                if first_product:
                    await callback.message.answer_photo(
                        photo=first_product['photo_id'],
                        caption=(
                            f"📦 Заказ #{order['id']}\n"
                            f"👤 Клиент: {order['phone']}\n"
                            f"🏙 Город: {order['city']}\n"
                            f"📝 Коммент: {order['comment'] if 'comment' in order.keys() and order['comment'] else '—'}\n"
                            f"📊 Статус: {order['status']}\n"
                            f"📦 Товары:\n" + "\n".join(products)
                        )
                    )

        # Кнопки изменения статуса
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Изменить статус", callback_data=f"change_status_{order_id}")
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()

    except Exception as e:  # Добавляем блок except
        logging.error(f"Ошибка в show_order_details: {str(e)}")
        await callback.answer("⚠️ Ошибка при загрузке заказа")

@router.callback_query(F.data.startswith("change_status_"))
async def change_order_status(callback: CallbackQuery, state: FSMContext):
    # Проверка прав администратора
    if not await is_admin(callback.from_user.username):
        await callback.answer("⛔️ Доступ запрещен", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    await state.update_data(order_id=order_id)

    builder = InlineKeyboardBuilder()
    for status in ["new", "processing", "delivered", "cancelled"]:
        builder.button(text=status.capitalize(), callback_data=f"set_status_{status}")

    await callback.message.answer(
        "Выберите новый статус:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()
    await state.set_state(AdminOrderStates.change_status)
    
@router.callback_query(F.data.startswith("set_status_"))
async def set_new_status(callback: CallbackQuery, state: FSMContext):
    # Проверка прав администратора
    if not await is_admin(callback.from_user.username):
        await callback.answer("⛔️ Доступ запрещен", show_alert=True)
        return

    new_status = callback.data.split("_")[2]
    data = await state.get_data()

    with sqlite3.connect('TG_ON_SH.db') as conn:
        # Проверим, что заказ существует
        existing = conn.execute('SELECT id, user_id FROM orders WHERE id = ?', (data.get('order_id'),)).fetchone()
        if not existing:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        conn.execute('''
            UPDATE orders 
            SET status = ? 
            WHERE id = ?
        ''', (new_status, data['order_id']))
        conn.commit()

    await callback.message.answer(f"✅ Статус обновлен на: {new_status}")
    # Уведомляем клиента
    try:
        await bot.send_message(existing[1], f"📦 Ваш заказ #{data['order_id']} обновлен: {new_status}")
    except Exception as e:
        logging.error(f"Не удалось уведомить пользователя: {e}")
    await callback.answer()
    await state.clear()

# 2. Убедитесь, что кнопка в админ-меню имеет правильный callback_data
# Удален дублирующийся admin_menu ниже

# Обработка ошибок FSM
@router.message(StateFilter(AdminAddProductStates))
async def handle_fsm_errors(msg: Message):
    await msg.answer("❌ Неверный ввод! Используйте кнопки или отправьте корректные данные.")

# Завершающий код для запуска
import asyncio

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
