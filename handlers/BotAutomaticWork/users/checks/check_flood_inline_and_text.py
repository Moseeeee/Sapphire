import asyncio
import time
from functools import wraps
from random import random, choice
from typing import Dict, OrderedDict

from aiogram.types import CallbackQuery

random_text = ["Пальчики будут бобо 😣", "СТОП! 🖐🏻 Мне не приятно", "Так и кнопку можно сломать! 😡",
               "🥱 Я тебя игнорирую", "🫵🏻 себя тыкни", "Мишка фредди уже рядом....", "😬 Ну и настырный же ты...",
               ""]

# Альтернативная версия с очисткой старых записей (для долгоживущих ботов)
def rate_limit_with_cleanup(limit: float = 1.0, max_users: int = 1000, cleanup_interval: int = 3600):
    def decorator(func):
        last_called_by_user: Dict[int, float] = OrderedDict()
        last_cleanup: float = 0
        lock = asyncio.Lock()  # Защита от race conditions

        async def cleanup_old_users(current_time: float):
            """Асинхронная очистка старых записей"""
            nonlocal last_cleanup

            cutoff_time = current_time - cleanup_interval
            # Используем OrderedDict для быстрого удаления устаревших
            while last_called_by_user:
                user_id, timestamp = next(iter(last_called_by_user.items()))
                if timestamp < cutoff_time:
                    del last_called_by_user[user_id]
                else:
                    break
            last_cleanup = current_time

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal last_cleanup

            callback = next((arg for arg in args if isinstance(arg, CallbackQuery)), None)
            if not callback:
                return await func(*args, **kwargs)

            user_id = callback.from_user.id
            current_time = time.time()

            # Используем lock для thread-safe операций
            async with lock:
                # Очистка только если нужно
                if current_time - last_cleanup > cleanup_interval:
                    await cleanup_old_users(current_time)

                # Проверяем ограничение
                if user_id in last_called_by_user:
                    time_passed = current_time - last_called_by_user[user_id]
                    if time_passed < limit:
                        send_random_text = choice(random_text)
                        await callback.answer(send_random_text, show_alert=False)
                        return

                # Обновляем время вызова
                last_called_by_user[user_id] = current_time
                # Удаляем самую старую запись если превышен лимит
                if len(last_called_by_user) > max_users:
                    last_called_by_user.popitem()

            return await func(*args, **kwargs)

        return wrapper

    return decorator


random_text_inline = [
    "⚠️ Кажется, что кнопочка то не ваша!",
    "😬 Ты же шутишь?",
    "🚁 Лечу к тебе, чтобы наказать за шалость!",
    "🆘 ЧС! ЧС! ЧС! ЧС! ЧС! ЧС! ЧС! ЧС!",
    "🦥 Обрабатываю... Со скоростью ленивца",
    "🎯 Промах! Попробуй ещё раз... но не сейчас"
]

def get_random_text() -> str:
    """Возвращает случайный текст из списка"""
    return choice(random_text_inline)