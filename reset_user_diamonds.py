"""Скрипт для обнуления баланса алмазов и установки энергии пользователя."""
import asyncio
import logging

from app.db import get_session
from app.repositories.user_profile import get_user_profile, spend_diamonds, spend_energy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset_user_balance(user_id: int, target_energy: int = 2) -> None:
    """Обнуляет баланс алмазов и устанавливает энергию для пользователя."""
    async with get_session() as session:
        # Получаем текущий профиль пользователя
        profile = await get_user_profile(session, user_id=user_id)
        
        if not profile:
            logger.warning(f"Пользователь {user_id} не найден в базе данных")
            return
        
        current_diamonds = profile.diamonds
        current_energy = profile.energy
        logger.info(f"Текущий баланс для пользователя {user_id}:")
        logger.info(f"  💎 Алмазы: {current_diamonds}")
        logger.info(f"  ⚡ Энергия: {current_energy}")
        
        # Обнуляем алмазы
        if current_diamonds > 0:
            await spend_diamonds(session, user_id=user_id, amount=current_diamonds)
            logger.info(f"✅ Баланс алмазов обнулен (было: {current_diamonds})")
        else:
            logger.info(f"Баланс алмазов уже равен 0")
        
        # Устанавливаем энергию
        if current_energy != target_energy:
            # Если текущая энергия больше целевой, списываем разницу
            if current_energy > target_energy:
                await spend_energy(session, user_id=user_id, amount=current_energy - target_energy)
                logger.info(f"✅ Энергия установлена на {target_energy} (было: {current_energy})")
            else:
                # Если текущая энергия меньше целевой, добавляем разницу
                from app.repositories.user_profile import add_energy
                await add_energy(session, user_id=user_id, amount=target_energy - current_energy)
                logger.info(f"✅ Энергия установлена на {target_energy} (было: {current_energy})")
        else:
            logger.info(f"Энергия уже равна {target_energy}")
        
        await session.commit()
        
        # Проверяем результат
        profile = await get_user_profile(session, user_id=user_id)
        logger.info(f"📊 Итоговый баланс для пользователя {user_id}:")
        logger.info(f"  💎 Алмазы: {profile.diamonds}")
        logger.info(f"  ⚡ Энергия: {profile.energy}")


async def main() -> None:
    """Главная функция."""
    user_id = 7843988578
    target_energy = 2
    await reset_user_balance(user_id, target_energy=target_energy)


if __name__ == "__main__":
    asyncio.run(main())

