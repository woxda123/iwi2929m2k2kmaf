import asyncio
import html
import logging

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)


def esc(value) -> str:
    return html.escape(str(value))


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{esc(name)}</a>'


async def safe_send(bot, chat_id, text, **kwargs):
    """Отправка сообщения без падения, если пользователь не запускал бота."""
    for _ in range(2):
        try:
            return await bot.send_message(chat_id, text, **kwargs)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logging.warning("Не удалось отправить сообщение %s: %s", chat_id, e)
            return None
    return None


async def safe_edit(message, text, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass
