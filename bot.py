import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import db
from handlers import start, game, profile, night_actions

logging.basicConfig(level=logging.INFO)


async def main():
    if BOT_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Укажи BOT_TOKEN в файле .env (см. .env.example)")
        sys.exit(1)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher(storage=MemoryStorage())
    await db.init()

    # Порядок важен: game (deep-link /start join_..., модерация чата) идёт первым,
    # общий обработчик /start — последним.
    dp.include_router(game.router)
    dp.include_router(night_actions.router)
    dp.include_router(profile.router)
    dp.include_router(start.router)

    await bot.set_my_commands([
        BotCommand(command="game", description="🎮 Начать игру"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="shop", description="🛒 Магазин"),
        BotCommand(command="top", description="🏆 Рейтинг"),
        BotCommand(command="roles", description="🎭 Роли"),
        BotCommand(command="leave", description="🚪 Выйти из игры"),
        BotCommand(command="stop", description="🛑 Остановить игру"),
        BotCommand(command="help", description="📖 Помощь"),
    ])

    me = await bot.me()
    print(f"🎭 Wox Mafia запущен! @{me.username}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
