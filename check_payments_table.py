"""Скрипт для проверки существования таблицы payments."""
import asyncio

from sqlalchemy import text

from app.db import engine


async def check_payments_table() -> None:
    """Проверяет существование таблицы payments."""
    async with engine.begin() as conn:
        # Проверяем существование таблицы
        check_table_query = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name='payments'
        """)
        result = await conn.execute(check_table_query)
        table_exists = result.fetchone() is not None
        
        if table_exists:
            print("✅ Таблица 'payments' существует!")
            
            # Проверяем количество записей
            count_query = text("SELECT COUNT(*) FROM payments")
            count_result = await conn.execute(count_query)
            count = count_result.scalar()
            print(f"📊 Количество записей в таблице: {count}")
            
            # Показываем структуру таблицы
            columns_query = text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'payments'
                ORDER BY ordinal_position
            """)
            columns_result = await conn.execute(columns_query)
            columns = columns_result.fetchall()
            
            print("\n📋 Структура таблицы 'payments':")
            for col_name, data_type, is_nullable in columns:
                nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
                print(f"  - {col_name}: {data_type} ({nullable})")
            
            # Показываем последние 5 записей, если они есть
            if count > 0:
                print("\n📝 Последние 5 записей:")
                recent_query = text("""
                    SELECT id, user_id, payment_type, amount_stars, diamonds_received, energy_received, created_at
                    FROM payments
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                recent_result = await conn.execute(recent_query)
                recent_records = recent_result.fetchall()
                
                for record in recent_records:
                    print(f"  ID: {record[0]}, User: {record[1]}, Type: {record[2]}, Stars: {record[3]}, "
                          f"Diamonds: {record[4]}, Energy: {record[5]}, Date: {record[6]}")
        else:
            print("❌ Таблица 'payments' НЕ существует!")
            print("💡 Таблица должна быть создана автоматически при запуске main.py")
            print("   Попробуйте запустить: python main.py")


if __name__ == "__main__":
    asyncio.run(check_payments_table())

