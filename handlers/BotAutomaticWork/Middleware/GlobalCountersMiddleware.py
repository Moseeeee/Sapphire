import time
import asyncio
from typing import Dict, Any, List


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