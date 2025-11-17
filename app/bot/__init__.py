from aiogram import Dispatcher

from app.bot.admin_handlers import admin_router
from app.bot.handlers import router


def setup_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # Админ-роутер должен быть первым, чтобы команды админа обрабатывались до общих обработчиков
    dp.include_router(admin_router)
    dp.include_router(router)
    return dp



