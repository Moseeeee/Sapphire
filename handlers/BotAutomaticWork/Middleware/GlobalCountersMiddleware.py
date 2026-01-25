import asyncio
import time
from typing import Dict, Any, List, Callable, Awaitable
import logging
from aiogram import BaseMiddleware
from aiogram.types import Update
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError, \
    TelegramConflictError

logger = logging.getLogger(__name__)


# --- АСИНХРОННЫЙ СЧЕТЧИК СОБЫТИЙ ---
class AsyncEventCounter:
    """
    Асинхронный счетчик, который хранит временные метки событий
    (ошибок, FloodWait) и предоставляет статистику за определенные периоды.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        # Реализация Singleton для глобального доступа
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        # Словарь для хранения событий: 'event_name' -> [timestamp1, timestamp2, ...]
        self.events: Dict[str, List[float]] = {
            'errors': [],
            'flood_wait': [],
        }
        self.start_time = time.time()

    async def add_event(self, event_name: str):
        """Добавляет временную метку события и очищает старые данные (за 1 час)."""
        if event_name not in self.events:
            self.events[event_name] = []

        async with self._lock:
            current_time = time.time()
            self.events[event_name].append(current_time)

            # Очистка: храним метки только за последние 3600 секунд (1 час)
            one_hour_ago = current_time - 3600

            # Очищаем только тот список, куда добавили
            self.events[event_name] = [
                t for t in self.events[event_name] if t >= one_hour_ago
            ]

    async def get_count(self, event_name: str, period_seconds: int) -> int:
        """Возвращает количество событий за указанный период (в секундах)."""
        if event_name not in self.events:
            return 0

        async with self._lock:
            current_time = time.time()
            time_limit = current_time - period_seconds
            count = sum(1 for t in self.events.get(event_name, []) if t >= time_limit)
            return count

    async def get_all_stats(self) -> Dict[str, Any]:
        """Возвращает статистику ошибок и FloodWait для команды /s."""
        return {
            'errors_1m': await self.get_count('errors', 60),
            'flood_wait_1h': await self.get_count('flood_wait', 3600),
        }


global_counter = AsyncEventCounter()


class GlobalCountersMiddleware(BaseMiddleware):
    """Middleware для подсчета глобальной статистики и обработки ошибок"""

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        try:
            # Статистика запросов
            bot = data.get("bot")
            if bot:
                bot_id = getattr(bot, "id", "unknown")
                # Здесь можно добавить логику подсчета запросов по ботам

            # Выполняем обработку
            result = await handler(event, data)
            return result

        except TelegramRetryAfter as e:
            # Обработка FloodWait
            await global_counter.add_event("flood_wait")
            logger.warning(f"FloodWait: {e}. Спим {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            # Повторяем запрос
            return await handler(event, data)

        except (TelegramNetworkError, TelegramServerError, TelegramConflictError) as e:
            # Обработка сетевых ошибок и ошибок сервера
            await global_counter.add_event("errors")
            logger.error(f"Сетевая ошибка или ошибка сервера: {e}")
            # Можно добавить логику повторных попыток

        except TelegramAPIError as e:
            # Обработка других ошибок API Telegram
            await global_counter.add_event("errors")
            logger.error(f"Ошибка API Telegram: {e}")

        except Exception as e:
            # Обработка всех остальных исключений
            await global_counter.add_event("errors")
            logger.exception(f"Необработанное исключение: {e}")
            # Можно отправить уведомление администратору