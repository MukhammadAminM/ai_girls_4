import asyncio
import logging

from aiogram import Bot

from app.bot import setup_dispatcher
from app.config import settings
from app.db import engine
from app.models import Base
from app.repositories.girls import ensure_all_girls

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Добавляем колонку nsfw_enabled если её нет (миграция)
        from sqlalchemy import text
        try:
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
        except Exception as e:
            print(f"⚠️ Предупреждение при проверке/добавлении колонки nsfw_enabled: {e}")
        
        # Добавляем колонку clothing_description если её нет (миграция)
        try:
            # Проверяем, существует ли колонка
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='girls' AND column_name='clothing_description'
            """)
            result = await conn.execute(check_query)
            exists = result.fetchone() is not None
            
            if not exists:
                print("Добавляю колонку clothing_description в таблицу girls...")
                # Добавляем колонку
                alter_query = text("""
                    ALTER TABLE girls 
                    ADD COLUMN clothing_description TEXT
                """)
                await conn.execute(alter_query)
                print("✅ Колонка clothing_description успешно добавлена!")
        except Exception as e:
            print(f"⚠️ Предупреждение при проверке/добавлении колонки clothing_description: {e}")
        
        # Проверяем существование таблицы user_profiles (миграция)
        try:
            check_table_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name='user_profiles'
            """)
            result = await conn.execute(check_table_query)
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                print("Таблица user_profiles будет создана автоматически через Base.metadata.create_all()")
        except Exception as e:
            print(f"⚠️ Предупреждение при проверке таблицы user_profiles: {e}")
        
        # Проверяем существование таблицы payments (миграция)
        try:
            check_table_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name='payments'
            """)
            result = await conn.execute(check_table_query)
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                print("Таблица payments будет создана автоматически через Base.metadata.create_all()")
        except Exception as e:
            print(f"⚠️ Предупреждение при проверке таблицы payments: {e}")

    from app.db import get_session

    async with get_session() as session:
        await ensure_all_girls(session)


async def main() -> None:
    await on_startup()

    bot = Bot(settings.bot_token)
    dp = setup_dispatcher()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


