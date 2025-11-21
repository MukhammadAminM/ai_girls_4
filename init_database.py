"""
Скрипт для инициализации базы данных.
Создает все таблицы и выполняет необходимые миграции.

Использование:
    python init_database.py
"""

import asyncio
import logging
import sys

from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.models import Base

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_column_exists(conn, table_name: str, column_name: str) -> bool:
    """Проверяет существование колонки в таблице."""
    check_query = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = :table_name AND column_name = :column_name
    """)
    result = await conn.execute(check_query, {"table_name": table_name, "column_name": column_name})
    return result.fetchone() is not None


async def check_table_exists(conn, table_name: str) -> bool:
    """Проверяет существование таблицы."""
    check_query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = :table_name
    """)
    result = await conn.execute(check_query, {"table_name": table_name})
    return result.fetchone() is not None


async def run_migrations(conn) -> None:
    """Выполняет миграции базы данных."""
    logger.info("Проверка и выполнение миграций...")
    
    # Миграция 1: Добавление колонки nsfw_enabled в dialogs
    if await check_table_exists(conn, "dialogs"):
        if not await check_column_exists(conn, "dialogs", "nsfw_enabled"):
            logger.info("Добавляю колонку nsfw_enabled в таблицу dialogs...")
            try:
                alter_query = text("""
                    ALTER TABLE dialogs 
                    ADD COLUMN nsfw_enabled BOOLEAN NOT NULL DEFAULT FALSE
                """)
                await conn.execute(alter_query)
                logger.info("✅ Колонка nsfw_enabled успешно добавлена!")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при добавлении колонки nsfw_enabled: {e}")
        else:
            logger.info("✓ Колонка nsfw_enabled уже существует")
    
    # Миграция 2: Добавление колонки clothing_description в girls
    if await check_table_exists(conn, "girls"):
        if not await check_column_exists(conn, "girls", "clothing_description"):
            logger.info("Добавляю колонку clothing_description в таблицу girls...")
            try:
                alter_query = text("""
                    ALTER TABLE girls 
                    ADD COLUMN clothing_description TEXT
                """)
                await conn.execute(alter_query)
                logger.info("✅ Колонка clothing_description успешно добавлена!")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при добавлении колонки clothing_description: {e}")
        else:
            logger.info("✓ Колонка clothing_description уже существует")
    
    # Миграция 3: Проверка существования таблиц
    required_tables = [
        "girls",
        "dialogs",
        "chat_messages",
        "user_selected_girls",
        "user_retention",
        "user_activity",
        "user_profiles",
        "payments"
    ]
    
    logger.info("\nПроверка существования таблиц:")
    for table_name in required_tables:
        if await check_table_exists(conn, table_name):
            logger.info(f"  ✓ Таблица {table_name} существует")
        else:
            logger.warning(f"  ⚠️ Таблица {table_name} не найдена (будет создана)")


async def init_database() -> None:
    """Инициализирует базу данных: создает все таблицы и выполняет миграции."""
    logger.info("=" * 60)
    logger.info("Инициализация базы данных")
    logger.info("=" * 60)
    logger.info(f"Подключение к БД: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'скрыто'}")
    
    try:
        async with engine.begin() as conn:
            # Создаем все таблицы на основе моделей
            logger.info("Создание таблиц...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Все таблицы созданы успешно!")
            
            # Выполняем миграции
            await run_migrations(conn)
            
            # Выводим список созданных таблиц
            logger.info("\n" + "=" * 60)
            logger.info("Список таблиц в базе данных:")
            logger.info("=" * 60)
            
            tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            result = await conn.execute(tables_query)
            tables = result.fetchall()
            
            for table in tables:
                table_name = table[0]
                # Получаем количество записей в таблице
                count_query = text(f'SELECT COUNT(*) FROM "{table_name}"')
                count_result = await conn.execute(count_query)
                count = count_result.scalar()
                logger.info(f"  • {table_name}: {count} записей")
            
            logger.info("=" * 60)
            logger.info("✅ Инициализация базы данных завершена успешно!")
            logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации базы данных: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await engine.dispose()


async def main() -> None:
    """Главная функция."""
    await init_database()


if __name__ == "__main__":
    asyncio.run(main())

