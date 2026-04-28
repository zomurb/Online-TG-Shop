from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="❤️ Избранное")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои заказы")]
        ],
        resize_keyboard=True
    )

def city_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Душанбе", callback_data="city_Душанбе"),
        InlineKeyboardButton(text="Худжанд", callback_data="city_Худжанд"),
        InlineKeyboardButton(text="Истаравшан", callback_data="city_Истаравшан"),
        InlineKeyboardButton(text="Другой город", callback_data="city_other")
    )
    builder.adjust(2, 2)
    return builder.as_markup()

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="📝 Изменить товар", callback_data="admin_edit_product")],
        [InlineKeyboardButton(text="❌ Удалить товар", callback_data="admin_delete_product")],
        [InlineKeyboardButton(text="📦 Просмотреть заказы", callback_data="admin_view_orders")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👤 Добавить админа", callback_data="admin_add_user")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promos")]
    ])

def get_back_button(callback_data: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])

def product_keyboard(product_id, is_favorite=False):
    builder = InlineKeyboardBuilder()
    fav_text = "❤️ В избранном" if is_favorite else "🤍 В избранное"
    fav_data = f"unfav_{product_id}" if is_favorite else f"fav_{product_id}"
    
    builder.button(text="🛒 В корзину", callback_data=f"prd_{product_id}")
    builder.button(text=fav_text, callback_data=fav_data)
    builder.adjust(1)
    return builder.as_markup()
