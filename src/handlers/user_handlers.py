import logging
import sqlite3
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardRemove,
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from zoneinfo import ZoneInfo

from src.database.models import get_db_connection, format_dt_gmt_minus5
from src.keyboards.builders import main_menu, city_keyboard, product_keyboard, get_back_button
from src.states.states import OrderStates, SearchStates

router = Router()

# --- СУЩЕСТВУЮЩИЕ ХЕНДЛЕРЫ ---

@router.message(Command("start"))
async def start_handler(msg: Message):
    try:
        with get_db_connection() as conn:
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
        "👟 Добро пожаловать в наш обновленный магазин!",
        reply_markup=main_menu()
    )

@router.message(F.text == "🛍 Каталог")
async def show_categories(msg: Message):
    try:
        with get_db_connection() as conn:
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
                callback_data=f"cat_{category['category']}"
            ))

        builder.adjust(2)
        await msg.answer(
            "👟 Выберите категорию:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка каталога: {e}")
        await msg.answer("⚠️ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data.startswith("cat_"))
async def show_products(callback: CallbackQuery):
    try:
        category = callback.data.split("cat_")[1]

        with get_db_connection() as conn:
            products = conn.execute('''
                SELECT id, description, price
                FROM products
                WHERE category = ? AND quantity > 0
            ''', (category,)).fetchall()

        builder = InlineKeyboardBuilder()
        for product in products:
            builder.button(
                text=f"{product['description']} - {product['price']} TJS",
                callback_data=f"view_{product['id']}"
            )

        builder.adjust(1)
        # Добавляем кнопку назад к категориям
        builder.row(InlineKeyboardButton(text="🔙 К категориям", callback_data="back_to_categories"))

        await callback.message.edit_text(
            f"Товары в категории {category}:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        await callback.answer("❌ Ошибка загрузки товаров")

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories_cb(callback: CallbackQuery):
    await show_categories(callback.message)
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data.startswith("view_"))
async def show_product(callback: CallbackQuery):
    try:
        product_id = int(callback.data.split("view_")[1])
        user_id = callback.from_user.id

        with get_db_connection() as conn:
            product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            is_fav = conn.execute('SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?', (user_id, product_id)).fetchone()

        if not product:
            return await callback.answer("Товар не найден")

        # Кнопки выбора размера
        builder = InlineKeyboardBuilder()
        for size in ["36","37","38","39","40","41","42","43","44","45"]:
            builder.button(text=f"Размер {size}", callback_data=f"size_{product_id}_{size}")

        # Кнопка избранного
        fav_text = "❤️ В избранном" if is_fav else "🤍 В избранное"
        fav_data = f"unfav_{product_id}" if is_fav else f"fav_{product_id}"
        builder.row(InlineKeyboardButton(text=fav_text, callback_data=fav_data))

        builder.adjust(3, 3, 4, 1)

        with get_db_connection() as conn:
            media_items = conn.execute('''
                SELECT file_id, kind FROM product_media
                WHERE product_id = ?
                ORDER BY position ASC
            ''', (product_id,)).fetchall()

        await callback.message.answer_photo(
            photo=product['photo_id'],
            caption=f"👟 Модель: {product['description']}\n💰 Цена: {product['price']} TJS",
            reply_markup=builder.as_markup()
        )

        for m in media_items[1:]:
            if m['kind'] == 'photo':
                await callback.message.answer_photo(photo=m['file_id'])
            else:
                await callback.message.answer_video(video=m['file_id'])
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка товара: {str(e)}")
        await callback.answer("⚠️ Ошибка загрузки")

# --- НОВАЯ ФИЧА: ИЗБРАННОЕ ---

@router.callback_query(F.data.startswith("fav_"))
async def add_to_favorites(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)', (user_id, product_id))
            conn.commit()
        await callback.answer("✅ Добавлено в избранное")
        # Обновляем кнопку
        await show_product(callback)
        await callback.message.delete()
    except Exception as e:
        await callback.answer("❌ Ошибка")

@router.callback_query(F.data.startswith("unfav_"))
async def remove_from_favorites(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    try:
        with get_db_connection() as conn:
            conn.execute('DELETE FROM favorites WHERE user_id = ? AND product_id = ?', (user_id, product_id))
            conn.commit()
        await callback.answer("❌ Удалено из избранного")
        await show_product(callback)
        await callback.message.delete()
    except Exception as e:
        await callback.answer("❌ Ошибка")

@router.message(F.text == "❤️ Избранное")
async def show_favorites(msg: Message):
    user_id = msg.from_user.id
    try:
        with get_db_connection() as conn:
            products = conn.execute('''
                SELECT p.id, p.description, p.price
                FROM favorites f
                JOIN products p ON f.product_id = p.id
                WHERE f.user_id = ?
            ''', (user_id,)).fetchall()

        if not products:
            return await msg.answer("❤️ Список избранного пуст")

        builder = InlineKeyboardBuilder()
        for p in products:
            builder.button(text=f"{p['description']} - {p['price']} TJS", callback_data=f"view_{p['id']}")
        builder.adjust(1)

        await msg.answer("❤️ Ваши избранные товары:", reply_markup=builder.as_markup())
    except Exception as e:
        await msg.answer("⚠️ Ошибка загрузки избранного")

# --- НОВАЯ ФИЧА: ПОИСК ---

@router.message(F.text == "🔍 Поиск")
async def search_start(msg: Message, state: FSMContext):
    await msg.answer("🔍 Введите название или описание товара для поиска:")
    await state.set_state(SearchStates.waiting_for_query)

@router.message(SearchStates.waiting_for_query)
async def search_process(msg: Message, state: FSMContext):
    query = msg.text.strip()
    if len(query) < 2:
        return await msg.answer("❗ Слишком короткий запрос. Введите минимум 2 символа.")

    try:
        with get_db_connection() as conn:
            products = conn.execute('''
                SELECT id, description, price FROM products
                WHERE (description LIKE ? OR category LIKE ?) AND quantity > 0
            ''', (f'%{query}%', f'%{query}%')).fetchall()

        if not products:
            await msg.answer("🔎 По вашему запросу ничего не найдено.")
        else:
            builder = InlineKeyboardBuilder()
            for p in products:
                builder.button(text=f"{p['description']} - {p['price']} TJS", callback_data=f"view_{p['id']}")
            builder.adjust(1)
            await msg.answer(f"🔎 Результаты поиска для '{query}':", reply_markup=builder.as_markup())

        await state.clear()
    except Exception as e:
        await msg.answer("⚠️ Ошибка поиска")
        await state.clear()

# --- НОВАЯ ФИЧА: ПРОФИЛЬ ---

@router.message(F.text == "👤 Профиль")
async def show_profile(msg: Message):
    user_id = msg.from_user.id
    try:
        with get_db_connection() as conn:
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            orders_count = conn.execute('SELECT COUNT(*) FROM orders WHERE user_id = ?', (user_id,)).fetchone()[0]
            total_spent = conn.execute('SELECT SUM(total) FROM orders WHERE user_id = ? AND status != "cancelled"', (user_id,)).fetchone()[0] or 0

        if not user:
            return await msg.answer("👤 Профиль не найден. Нажмите /start")

        text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {user['first_name']} {user['last_name'] or ''}\n"
            f"🏷 Username: @{user['username'] or '—'}\n"
            f"📅 Дата регистрации: {format_dt_gmt_minus5(user['created_at'])}\n\n"
            f"📦 Всего заказов: {orders_count}\n"
            f"💰 Всего потрачено: {total_spent} TJS"
        )
        await msg.answer(text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Profile error: {e}")
        await msg.answer("⚠️ Ошибка загрузки профиля")

# --- КОРЗИНА И ОФОРМЛЕНИЕ (ПОВТОРНО ДЛЯ ПОЛНОТЫ) ---

@router.callback_query(F.data.startswith("size_"))
async def add_to_cart_with_size(callback: CallbackQuery):
    try:
        _, product_id_str, size = callback.data.split("_", 2)
        product_id = int(product_id_str)
        user_id = callback.from_user.id

        with get_db_connection() as conn:
            product = conn.execute('SELECT id FROM products WHERE id = ? AND quantity > 0', (product_id,)).fetchone()
            if not product:
                return await callback.answer("❌ Товар закончился", show_alert=True)

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

@router.message(F.text == "🛒 Корзина")
async def show_cart(msg: Message):
    try:
        user_id = msg.from_user.id
        with get_db_connection() as conn:
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

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Оформить заказ", callback_data="checkout")
        builder.button(text="🗑 Очистить корзину", callback_data="clear_cart")
        builder.adjust(1)

        await msg.answer(
            "\n".join(response) + f"\n\n💵 Итого: {total} TJS",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await msg.answer("🚫 Не удалось загрузить корзину")

@router.callback_query(F.data == "clear_cart")
async def clear_cart_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    with get_db_connection() as conn:
        conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
        conn.commit()
    await callback.message.edit_text("🛒 Корзина очищена")
    await callback.answer()

@router.callback_query(F.data == "checkout")
async def process_checkout(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    with get_db_connection() as conn:
        cart_items = conn.execute('SELECT product_id, size, quantity FROM cart WHERE user_id = ?', (user_id,)).fetchall()
        if not cart_items:
            return await callback.answer("🛒 Корзина пуста!", show_alert=True)

    order_data = ";".join([f"{row['product_id']}:{row['quantity']}:{row['size'] or ''}" for row in cart_items])
    await state.update_data(order_data=order_data)

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

@router.message(OrderStates.wait_phone, F.contact)
async def process_contact(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.contact.phone_number)
    await msg.answer("🏙 Выберите город:", reply_markup=city_keyboard())
    await state.set_state(OrderStates.wait_city)

@router.callback_query(OrderStates.wait_city, F.data.startswith("city_"))
async def handle_city_selection(callback: CallbackQuery, state: FSMContext):
    if callback.data == "city_other":
        await callback.message.answer("🏙 Введите свой город текстом:")
        await state.set_state(OrderStates.wait_custom_city)
        return

    city = callback.data.split("_", 1)[1]
    await state.update_data(city=city)
    await callback.message.answer("🏷 Введите промокод или напишите 'Пропустить'")
    await state.set_state(OrderStates.wait_promo)
    await callback.answer()

@router.message(OrderStates.wait_custom_city)
async def process_custom_city(msg: Message, state: FSMContext):
    await state.update_data(city=msg.text.strip())
    await msg.answer("🏷 Введите промокод или напишите 'Пропустить'")
    await state.set_state(OrderStates.wait_promo)

@router.message(OrderStates.wait_promo)
async def process_promo(msg: Message, state: FSMContext):
    code = (msg.text or '').strip()
    if code.lower() == 'пропустить' or not code:
        await msg.answer("📝 Оставьте комментарий к заказу или напишите 'Пропустить'.")
        await state.set_state(OrderStates.wait_comment)
        return

    with get_db_connection() as conn:
        row = conn.execute('SELECT code, kind, amount, active, expires_at FROM promo_codes WHERE code = ?', (code,)).fetchone()

    if not row or not row['active']:
        return await msg.answer("❌ Промокод не найден или не активен. Попробуйте другой или напишите 'Пропустить'.")

    if row['expires_at']:
        try:
            expires_dt = datetime.strptime(row['expires_at'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Dushanbe"))
            if datetime.now(ZoneInfo("Asia/Dushanbe")) > expires_dt:
                return await msg.answer("⌛ Срок действия промокода истёк.")
        except: pass

    await state.update_data(promo_code=row['code'], promo_kind=row['kind'], promo_amount=float(row['amount']))
    await msg.answer("✅ Промокод применён. Добавьте комментарий или напишите 'Пропустить'.")
    await state.set_state(OrderStates.wait_comment)

@router.message(OrderStates.wait_comment)
async def process_order_comment(msg: Message, state: FSMContext):
    user_id = msg.from_user.id
    comment = msg.text.strip()
    if comment.lower() == 'пропустить': comment = ''

    data = await state.get_data()

    with get_db_connection() as conn:
        subtotal = conn.execute('''
            SELECT COALESCE(SUM(p.price * c.quantity), 0)
            FROM cart c JOIN products p ON p.id = c.product_id
            WHERE c.user_id = ?
        ''', (user_id,)).fetchone()[0] or 0.0

        promo_kind = data.get('promo_kind')
        promo_amount = data.get('promo_amount', 0)
        discount = 0.0
        if promo_kind == 'percent':
            discount = round(subtotal * (promo_amount / 100.0), 2)
        elif promo_kind == 'fixed':
            discount = float(promo_amount)

        total = max(0, subtotal - discount)

        conn.execute('''
            INSERT INTO orders (user_id, phone, city, order_data, comment, promo_code, discount, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, data['phone'], data['city'], data['order_data'], comment, data.get('promo_code'), discount, total))

        new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
        conn.commit()

    await msg.answer(
        f"✅ Заказ №{new_id} оформлен!\n💰 Итого к оплате: {total} TJS\nМы свяжемся с вами в ближайшее время.",
        reply_markup=main_menu()
    )
    await state.clear()

@router.message(F.text == "📦 Мои заказы")
async def show_orders_history(msg: Message):
    user_id = msg.from_user.id
    with get_db_connection() as conn:
        orders = conn.execute('SELECT id, order_date, status, total FROM orders WHERE user_id = ? ORDER BY order_date DESC LIMIT 10', (user_id,)).fetchall()

    if not orders:
        return await msg.answer("📭 У вас пока нет заказов")

    resp = ["📜 Ваши последние заказы:"]
    for o in orders:
        date = format_dt_gmt_minus5(o['order_date'])
        resp.append(f"🆔 №{o['id']} | 📅 {date}\n💰 {o['total']} TJS | 📊 {o['status']}")

    await msg.answer("\n\n".join(resp))

@router.message(StateFilter(OrderStates), F.text.lower().contains("отмена"))
async def cancel_checkout_anytime(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Оформление отменено", reply_markup=main_menu())
