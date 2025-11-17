"""Скрипт для добавления колонки nsfw_enabled в таблицу dialogs."""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def migrate() -> None:
    """Добавляет колонку nsfw_enabled в таблицу dialogs."""
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        # Проверяем, существует ли колонка
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='dialogs' AND column_name='nsfw_enabled'
        """)
        result = await conn.execute(check_query)
        exists = result.fetchone() is not None
        
        if not exists:
            print("Добавляю колонку nsfw_enabled в таблицу dialogs...")
            # Добавляем колонку
            alter_query = text("""
                ALTER TABLE dialogs 
                ADD COLUMN nsfw_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """)
            await conn.execute(alter_query)
            print("✅ Колонка nsfw_enabled успешно добавлена!")
        else:
            print("✅ Колонка nsfw_enabled уже существует.")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())

