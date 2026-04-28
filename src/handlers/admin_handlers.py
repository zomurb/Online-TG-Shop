import logging
import sqlite3
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from zoneinfo import ZoneInfo

from src.database.models import get_db_connection, format_dt_gmt_minus5
from src.keyboards.builders import admin_menu, main_menu
from src.states.states import (
    AdminAddProductStates, AdminDeleteProductStates,
    AdminAddUserStates, AdminPromoStates,
    AdminOrderStates, AdminBroadcastStates,
    AdminEditProductStates
)

router = Router()

async def is_admin(username: str | None):
    if not username: return False
    username = username.lstrip('@').lower()
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT username FROM admins WHERE LOWER(TRIM(username, '@')) = ?",
            (username,)
        ).fetchone()
    return bool(result)

@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.username):
        return await msg.answer("❌ Доступ запрещен")
    await msg.answer("👮 Админ-панель:", reply_markup=admin_menu())

# --- НОВАЯ ФИЧА: СТАТИСТИКА ---

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.username): return
    try:
        with get_db_connection() as conn:
            total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            total_orders = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
            revenue = conn.execute('SELECT SUM(total) FROM orders WHERE status != "cancelled"').fetchone()[0] or 0
            delivered_orders = conn.execute('SELECT COUNT(*) FROM orders WHERE status = "delivered"').fetchone()[0]
            avg_order = round(revenue / total_orders, 2) if total_orders > 0 else 0

        text = (
            "📊 <b>Статистика магазина</b>\n\n"
            f"👤 Всего пользователей: {total_users}\n"
            f"📦 Всего заказов: {total_orders}\n"
            f"✅ Выполнено заказов: {delivered_orders}\n"
            f"💰 Общая выручка: {revenue} TJS\n"
            f"📈 Средний чек: {avg_order} TJS"
        )
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")

# --- НОВАЯ ФИЧА: ИЗМЕНЕНИЕ ТОВАРА ---

@router.callback_query(F.data == "admin_edit_product")
async def edit_product_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔢 Введите ID товара для редактирования:")
    await state.set_state(AdminEditProductStates.select_product)
    await callback.answer()

@router.message(AdminEditProductStates.select_product)
async def edit_product_select(msg: Message, state: FSMContext):
    try:
        pid = int(msg.text)
        with get_db_connection() as conn:
            p = conn.execute('SELECT * FROM products WHERE id = ?', (pid,)).fetchone()
        if not p: return await msg.answer("❌ Товар не найден")

        await state.update_data(pid=pid)
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Цена", callback_data="edit_price")
        builder.button(text="🔢 Количество", callback_data="edit_qty")
        builder.button(text="📝 Описание", callback_data="edit_desc")
        builder.adjust(2)

        await msg.answer(f"Редактирование: {p['description']}\nЧто изменить?", reply_markup=builder.as_markup())
        await state.set_state(AdminEditProductStates.select_field)
    except: await msg.answer("❌ Введите ID числом")

@router.callback_query(AdminEditProductStates.select_field, F.data.startswith("edit_"))
async def edit_field_select(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    await state.update_data(field=field)
    await callback.message.answer(f"Введите новое значение для {field}:")
    await state.set_state(AdminEditProductStates.new_value)
    await callback.answer()

@router.message(AdminEditProductStates.new_value)
async def edit_value_final(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data['pid']
    field = data['field']
    val = msg.text.strip()

    db_field = {
        'price': 'price',
        'qty': 'quantity',
        'desc': 'description'
    }.get(field)

    try:
        if field == 'price': val = float(val.replace(',', '.'))
        elif field == 'qty': val = int(val)

        with get_db_connection() as conn:
            conn.execute(f'UPDATE products SET {db_field} = ? WHERE id = ?', (val, pid))
            conn.commit()

        await msg.answer(f"✅ Товар {pid} обновлен. {field} -> {val}", reply_markup=admin_menu())
        await state.clear()
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")

# --- ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ---

@router.callback_query(F.data == "admin_add_product")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.username): return
    with get_db_connection() as conn:
        categories = conn.execute('SELECT DISTINCT category FROM products').fetchall()

    if categories:
        cats = "\n".join([f"• {c[0]}" for c in categories])
        await callback.message.answer(f"🌿 Существующие категории:\n{cats}\n\n✏️ Введите категорию:")
    else:
        await callback.message.answer("✏️ Введите название новой категории:")

    await state.set_state(AdminAddProductStates.category)
    await callback.answer()

@router.message(AdminAddProductStates.category)
async def process_category(msg: Message, state: FSMContext):
    await state.update_data(category=msg.text.strip())
    await msg.answer("📸 Отправьте фото товара. Когда закончите — напишите 'Готово'.")
    await state.update_data(media_list=[])
    await state.set_state(AdminAddProductStates.media)

@router.message(AdminAddProductStates.media, F.photo)
async def process_media_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    media_list.append({'file_id': msg.photo[-1].file_id, 'kind': 'photo'})
    await state.update_data(media_list=media_list)
    await msg.answer(f"✅ Фото добавлено ({len(media_list)}). Еще или 'Готово'?")

@router.message(AdminAddProductStates.media, F.text.lower() == "готово")
async def process_media_done(msg: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get('media_list'):
        return await msg.answer("❗ Добавьте хотя бы одно фото.")
    await msg.answer("📝 Введите описание товара:")
    await state.set_state(AdminAddProductStates.description)

@router.message(AdminAddProductStates.description)
async def process_description(msg: Message, state: FSMContext):
    await state.update_data(description=msg.text.strip())
    await msg.answer("💵 Введите цену (например 499.99):")
    await state.set_state(AdminAddProductStates.price)

@router.message(AdminAddProductStates.price)
async def process_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(',', '.'))
        await state.update_data(price=price)
        await msg.answer("🔢 Введите количество:")
        await state.set_state(AdminAddProductStates.quantity)
    except:
        await msg.answer("❌ Неверный формат цены.")

@router.message(AdminAddProductStates.quantity)
async def process_quantity(msg: Message, state: FSMContext):
    try:
        qty = int(msg.text)
        data = await state.get_data()
        with get_db_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO products (category, photo_id, description, price, quantity)
                VALUES (?, ?, ?, ?, ?)
            ''', (data['category'], data['media_list'][0]['file_id'], data['description'], data['price'], qty))
            product_id = cursor.lastrowid
            for idx, m in enumerate(data['media_list']):
                conn.execute('INSERT INTO product_media (product_id, file_id, kind, position) VALUES (?, ?, ?, ?)',
                             (product_id, m['file_id'], m['kind'], idx))
            conn.commit()
        await msg.answer(f"✅ Товар добавлен! ID: {product_id}", reply_markup=admin_menu())
        await state.clear()
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "admin_delete_product")
async def start_delete_product(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔢 Введите ID товара для удаления:")
    await state.set_state(AdminDeleteProductStates.select_product)
    await callback.answer()

@router.message(AdminDeleteProductStates.select_product)
async def process_delete_id(msg: Message, state: FSMContext):
    try:
        pid = int(msg.text)
        with get_db_connection() as conn:
            p = conn.execute('SELECT description FROM products WHERE id = ?', (pid,)).fetchone()
        if not p: return await msg.answer("❌ Не найден")
        await state.update_data(pid=pid)
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Удалить", callback_data="confirm_delete")
        builder.button(text="❌ Отмена", callback_data="cancel_delete")
        await msg.answer(f"Удалить '{p[0]}' (ID: {pid})?", reply_markup=builder.as_markup())
        await state.set_state(AdminDeleteProductStates.confirm)
    except: await msg.answer("❌ Введите число")

@router.callback_query(AdminDeleteProductStates.confirm, F.data == "confirm_delete")
async def confirm_delete_cb(callback: CallbackQuery, state: FSMContext):
    pid = (await state.get_data())['pid']
    with get_db_connection() as conn:
        conn.execute('DELETE FROM products WHERE id = ?', (pid,))
        conn.execute('DELETE FROM product_media WHERE product_id = ?', (pid,))
        conn.commit()
    await callback.message.answer("✅ Удалено")
    await state.clear()
    await callback.answer()

@router.callback_query(AdminDeleteProductStates.confirm, F.data == "cancel_delete")
async def cancel_delete_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Отменено", reply_markup=admin_menu())
    await callback.answer()

# --- ПРОМОКОДЫ ---

@router.callback_query(F.data == "admin_promos")
async def admin_promos_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🎟 Введите новый код:")
    await state.set_state(AdminPromoStates.code)
    await callback.answer()

@router.message(AdminPromoStates.code)
async def promo_code_step(msg: Message, state: FSMContext):
    await state.update_data(code=msg.text.strip())
    builder = InlineKeyboardBuilder()
    builder.button(text="%", callback_data="pk_percent")
    builder.button(text="Фикс (TJS)", callback_data="pk_fixed")
    await msg.answer("Тип скидки:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("pk_"))
async def promo_kind_step(callback: CallbackQuery, state: FSMContext):
    kind = "percent" if "percent" in callback.data else "fixed"
    await state.update_data(kind=kind)
    await callback.message.answer("Введите размер скидки:")
    await state.set_state(AdminPromoStates.amount)
    await callback.answer()

@router.message(AdminPromoStates.amount)
async def promo_amount_step(msg: Message, state: FSMContext):
    try:
        amt = float(msg.text)
        await state.update_data(amount=amt)
        await msg.answer("Срок (YYYY-MM-DD HH:MM) или 'Пропустить':")
        await state.set_state(AdminPromoStates.expires)
    except: await msg.answer("❌ Число!")

@router.message(AdminPromoStates.expires)
async def promo_final_step(msg: Message, state: FSMContext):
    data = await state.get_data()
    exp = msg.text.strip()
    if exp.lower() == 'пропустить': exp = None
    else:
        try: exp = datetime.strptime(exp, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
        except: return await msg.answer("❌ Формат!")

    with get_db_connection() as conn:
        conn.execute('INSERT INTO promo_codes (code, kind, amount, expires_at) VALUES (?, ?, ?, ?)',
                     (data['code'], data['kind'], data['amount'], exp))
        conn.commit()
    await msg.answer(f"✅ Промокод {data['code']} создан")
    await state.clear()

# --- РАССЫЛКА ---

@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📨 Текст рассылки:")
    await state.set_state(AdminBroadcastStates.content)
    await callback.answer()

@router.message(AdminBroadcastStates.content)
async def broadcast_send(msg: Message, state: FSMContext, bot: Bot):
    text = msg.text
    with get_db_connection() as conn:
        users = conn.execute('SELECT user_id FROM users').fetchall()

    ok, err = 0, 0
    for u in users:
        try:
            await bot.send_message(u[0], text)
            ok += 1
        except: err += 1
    await msg.answer(f"✅ Готово. Успешно: {ok}, Ошибок: {err}")
    await state.clear()

# --- ЗАКАЗЫ ---

@router.callback_query(F.data == "admin_view_orders")
async def view_orders_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    for s in ["new", "processing", "delivered", "cancelled"]:
        builder.button(text=s.capitalize(), callback_data=f"as_{s}")
    builder.adjust(2)
    await callback.message.answer("Статус заказов:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("as_"))
async def list_orders_by_status(callback: CallbackQuery):
    status = callback.data.split("_")[1]
    with get_db_connection() as conn:
        orders = conn.execute('SELECT * FROM orders WHERE status = ? ORDER BY order_date DESC LIMIT 10', (status,)).fetchall()

    if not orders: return await callback.message.answer("Пусто")

    for o in orders:
        txt = f"🆔 №{o['id']} | 📞 {o['phone']}\n🏙 {o['city']} | 💰 {o['total']} TJS\n📊 {o['status']}"
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Статус", callback_data=f"chs_{o['id']}")
        await callback.message.answer(txt, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("chs_"))
async def change_status_start(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split("_")[1])
    await state.update_data(oid=oid)
    builder = InlineKeyboardBuilder()
    for s in ["new", "processing", "delivered", "cancelled"]:
        builder.button(text=s, callback_data=f"set_{s}")
    await callback.message.answer(f"Новый статус для №{oid}:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("set_"))
async def set_status_final(callback: CallbackQuery, state: FSMContext, bot: Bot):
    status = callback.data.split("_")[1]
    oid = (await state.get_data())['oid']
    with get_db_connection() as conn:
        conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, oid))
        user = conn.execute('SELECT user_id FROM orders WHERE id = ?', (oid,)).fetchone()
        conn.commit()

    await callback.message.answer(f"✅ №{oid} -> {status}")
    try: await bot.send_message(user[0], f"📦 Статус вашего заказа №{oid} изменен на: {status}")
    except: pass
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "admin_add_user")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 Введите username (без @):")
    await state.set_state(AdminAddUserStates.username)
    await callback.answer()

@router.message(AdminAddUserStates.username)
async def add_admin_final(msg: Message, state: FSMContext):
    uname = msg.text.strip().lower()
    with get_db_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO admins (username) VALUES (?)', (uname,))
        conn.commit()
    await msg.answer(f"✅ {uname} теперь админ")
    await state.clear()
