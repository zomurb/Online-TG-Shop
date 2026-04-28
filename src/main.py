import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from src.config import BOT_TOKEN, INITIAL_ADMINS
from src.database.models import init_db, check_and_fix_db, get_db_connection
from src.handlers import user_handlers, admin_handlers

async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    # Инициализация БД
    init_db()
    check_and_fix_db()

    # Добавление начальных админов
    with get_db_connection() as conn:
        for admin in INITIAL_ADMINS:
            conn.execute('INSERT OR IGNORE INTO admins (username) VALUES (?)', (admin.lower(),))
        conn.commit()

    # Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация роутеров
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # Запуск поллинга
    logging.info("Bot started!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
