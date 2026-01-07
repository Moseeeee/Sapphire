# handlers/BotAutomaticWork/Middleware/BotDetailedStats.py
import time
import logging
import asyncio
from typing import Dict, Optional, Tuple
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class BotDetailedStats:
    """Детальная статистика для одного бота"""

    def __init__(self, bot_id: str, bot_name: str):
        self.bot_id = bot_id
        self.bot_name = bot_name

        # Статистика запросов (1 человек = 1 RPS)
        self.total_users = set()  # Все уникальные пользователи
        self.users_last_second = deque(maxlen=1000)  # Пользователи за последнюю секунду
        self.users_per_second = deque(maxlen=3600)  # Исторические данные за час

        # Время ответа
        self.response_times = deque(maxlen=1000)
        self.best_response_time = float('inf')
        self.worst_response_time = 0

        # Ошибки
        self.error_count = 0
        self.errors_last_hour = deque(maxlen=100)

        # Очередь
        self.queue_times = deque(maxlen=1000)
        self.current_queue_time = 0  # Время с последнего ответа

        # Чаты
        self.chat_count = 0

        # Ping к Telegram API
        self.ping_times = deque(maxlen=100)
        self.best_ping = float('inf')
        self.worst_ping = 0

        # Статус
        self.last_activity = time.time()
        self.is_online = True

        # Блокировка для потокобезопасности
        self.lock = asyncio.Lock()

        logger.info(f"📊 Детальная статистика для {bot_name} ({bot_id}) инициализирована")

    def record_user(self, user_id: int):
        """Учесть пользователя (1 человек = 1 RPS)"""
        current_time = time.time()

        self.total_users.add(user_id)
        self.users_last_second.append((current_time, user_id))
        self.users_per_second.append((current_time, user_id))
        self.last_activity = current_time

    def record_response_time(self, response_time: float):
        """Учесть время ответа"""
        self.response_times.append(response_time)

        if response_time < self.best_response_time:
            self.best_response_time = response_time
        if response_time > self.worst_response_time:
            self.worst_response_time = response_time

        # Сбрасываем текущее время очереди
        self.current_queue_time = 0
        self.last_activity = time.time()

    def record_error(self):
        """Учесть ошибку"""
        self.error_count += 1
        self.errors_last_hour.append(time.time())

    def record_ping(self, ping_time: float):
        """Учесть пинг к Telegram API"""
        self.ping_times.append(ping_time)

        if ping_time < self.best_ping:
            self.best_ping = ping_time
        if ping_time > self.worst_ping:
            self.worst_ping = ping_time

    def update_queue_time(self):
        """Обновить время очереди (сколько времени бот не отвечал)"""
        self.current_queue_time = time.time() - self.last_activity

    def update_chat_count(self, count: int):
        """Обновить количество чатов"""
        self.chat_count = count

    def calculate_users_rps(self, window_seconds: float = 1.0) -> float:
        """Рассчитать RPS уникальных пользователей"""
        if not self.users_last_second:
            return 0.0

        cutoff = time.time() - window_seconds
        unique_users = set()

        for timestamp, user_id in reversed(self.users_last_second):
            if timestamp >= cutoff:
                unique_users.add(user_id)
            else:
                break

        return len(unique_users) / window_seconds

    def calculate_historical_rps(self, window_minutes: int = 5) -> float:
        """Рассчитать RPS за исторический период"""
        cutoff = time.time() - (window_minutes * 60)
        unique_users = set()

        for timestamp, user_id in self.users_per_second:
            if timestamp >= cutoff:
                unique_users.add(user_id)

        return len(unique_users) / (window_minutes * 60)

    def get_avg_response_time(self) -> float:
        """Среднее время ответа"""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)

    def get_ping_stats(self) -> Tuple[float, float, float]:
        """Статистика пинга: средний, лучший, худший"""
        if not self.ping_times:
            return 0.0, 0.0, 0.0

        avg_ping = statistics.mean(self.ping_times)
        return avg_ping, self.best_ping, self.worst_ping

    def get_error_rate_last_hour(self) -> float:
        """Процент ошибок за последний час"""
        cutoff = time.time() - 3600
        recent_errors = sum(1 for t in self.errors_last_hour if t >= cutoff)
        total_requests = len([t for t, _ in self.users_per_second if t >= cutoff])

        if total_requests == 0:
            return 0.0
        return (recent_errors / total_requests) * 100

    def get_load_percentage(self, max_users_per_second: float = 50.0) -> float:
        """Загрузка бота в % (относительно максимальной пропускной способности)"""
        current_rps = self.calculate_users_rps()
        load = min(100.0, (current_rps / max_users_per_second) * 100)
        return load

    def get_stats_summary(self) -> Dict:
        """Получить сводную статистику"""
        users_rps_1s = self.calculate_users_rps(1.0)
        users_rps_5min = self.calculate_historical_rps(5)
        avg_response_time = self.get_avg_response_time()
        avg_ping, best_ping, worst_ping = self.get_ping_stats()
        error_rate = self.get_error_rate_last_hour()
        load = self.get_load_percentage()

        self.update_queue_time()

        return {
            'bot_id': self.bot_id,
            'bot_name': self.bot_name,
            'users_rps_1s': round(users_rps_1s, 2),
            'users_rps_5min': round(users_rps_5min, 2),
            'total_unique_users': len(self.total_users),
            'chat_count': self.chat_count,
            'avg_response_time': round(avg_response_time, 2),
            'response_time_range': f"{self.best_response_time:.0f} | {self.worst_response_time:.0f}",
            'avg_ping': round(avg_ping, 2),
            'ping_range': f"{best_ping:.0f} | {worst_ping:.0f}",
            'current_queue_time': round(self.current_queue_time, 2),
            'error_rate': round(error_rate, 2),
            'error_count': self.error_count,
            'load_percentage': round(load, 2),
            'is_online': self.is_online,
            'last_activity_seconds': round(time.time() - self.last_activity, 2),
            'display': self._format_display(users_rps_1s, avg_response_time, load)
        }

    def _format_display(self, users_rps: float, avg_response: float, load: float) -> str:
        """Форматировать отображение для командной строки"""
        status = "🟢" if self.is_online else "🔴"
        return (
            f"{status} {self.bot_name}: "
            f"RPS: {users_rps:.1f} 👤/с | "
            f"Ответ: {avg_response:.0f}мс | "
            f"Загрузка: {load:.1f}% | "
            f"Чаты: {self.chat_count}"
        )

    def reset_stats(self):
        """Сбросить статистику (кроме чатов)"""
        self.total_users.clear()
        self.users_last_second.clear()
        self.users_per_second.clear()
        self.response_times.clear()
        self.error_count = 0
        self.errors_last_hour.clear()
        self.ping_times.clear()
        self.best_response_time = float('inf')
        self.worst_response_time = 0
        self.best_ping = float('inf')
        self.worst_ping = 0
        self.current_queue_time = 0

        logger.info(f"📊 Статистика сброшена для {self.bot_name}")


class BotStatsManager:
    """Менеджер статистики всех ботов"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.bot_stats: Dict[str, BotDetailedStats] = {}
        self._lock = asyncio.Lock()
        self._initialized = True

        logger.info("📊 Менеджер детальной статистики ботов инициализирован")

    def get_or_create_bot_stats(self, bot_id: str, bot_name: str) -> BotDetailedStats:
        """Получить или создать статистику для бота"""
        if bot_id not in self.bot_stats:
            self.bot_stats[bot_id] = BotDetailedStats(bot_id, bot_name)
            logger.info(f"📊 Создана детальная статистика для {bot_name}")

        return self.bot_stats[bot_id]

    async def record_bot_user(self, bot_id: str, user_id: int, bot_name: str = None):
        """Записать пользователя для бота"""
        stats = self.get_or_create_bot_stats(bot_id, bot_name or bot_id)
        stats.record_user(user_id)

    async def record_bot_response(self, bot_id: str, response_time: float):
        """Записать время ответа бота"""
        if bot_id in self.bot_stats:
            self.bot_stats[bot_id].record_response_time(response_time)

    async def record_bot_error(self, bot_id: str):
        """Записать ошибку бота"""
        if bot_id in self.bot_stats:
            self.bot_stats[bot_id].record_error()

    async def record_bot_ping(self, bot_id: str, ping_time: float):
        """Записать пинг бота"""
        if bot_id in self.bot_stats:
            self.bot_stats[bot_id].record_ping(ping_time)

    async def update_bot_chat_count(self, bot_id: str, chat_count: int):
        """Обновить количество чатов бота"""
        if bot_id in self.bot_stats:
            self.bot_stats[bot_id].update_chat_count(chat_count)

    async def get_bot_stats(self, bot_id: str) -> Optional[Dict]:
        """Получить статистику конкретного бота"""
        if bot_id in self.bot_stats:
            return self.bot_stats[bot_id].get_stats_summary()
        return None

    async def get_all_bots_stats(self) -> Dict[str, Dict]:
        """Получить статистику всех ботов"""
        result = {}
        for bot_id, stats in self.bot_stats.items():
            result[bot_id] = stats.get_stats_summary()
        return result

    async def get_aggregated_stats(self) -> Dict:
        """Получить агрегированную статистику по всем ботам"""
        all_stats = await self.get_all_bots_stats()

        if not all_stats:
            return {
                'total_bots': 0,
                'online_bots': 0,
                'total_chats': 0,
                'total_users': 0,
                'total_rps': 0,
                'avg_response_time': 0,
                'avg_ping': 0,
                'total_errors': 0
            }

        total_bots = len(all_stats)
        online_bots = sum(1 for s in all_stats.values() if s['is_online'])
        total_chats = sum(s['chat_count'] for s in all_stats.values())
        total_users = sum(s['total_unique_users'] for s in all_stats.values())
        total_rps = sum(s['users_rps_1s'] for s in all_stats.values())
        avg_response = statistics.mean([s['avg_response_time'] for s in all_stats.values()
                                        if s['avg_response_time'] > 0])
        avg_ping = statistics.mean([s['avg_ping'] for s in all_stats.values()
                                    if s['avg_ping'] > 0])
        total_errors = sum(s['error_count'] for s in all_stats.values())

        return {
            'total_bots': total_bots,
            'online_bots': online_bots,
            'total_chats': total_chats,
            'total_users': total_users,
            'total_rps': round(total_rps, 2),
            'avg_response_time': round(avg_response, 2),
            'avg_ping': round(avg_ping, 2),
            'total_errors': total_errors
        }

    async def reset_bot_stats(self, bot_id: str):
        """Сбросить статистику бота"""
        if bot_id in self.bot_stats:
            self.bot_stats[bot_id].reset_stats()

    async def reset_all_stats(self):
        """Сбросить статистику всех ботов"""
        for bot_id in list(self.bot_stats.keys()):
            await self.reset_bot_stats(bot_id)


# Глобальный экземпляр менеджера
bot_stats_manager = BotStatsManager()


# Функции для обратной совместимости
async def record_bot_user_request(bot_id: str, user_id: int):
    await bot_stats_manager.record_bot_user(bot_id, user_id)


async def record_bot_handled_user(bot_id: str, user_id: int):
    # Используем ту же функцию, что и для запроса (1 человек = 1 RPS)
    await bot_stats_manager.record_bot_user(bot_id, user_id)


async def record_bot_response_time(bot_id: str, response_time: float):
    await bot_stats_manager.record_bot_response(bot_id, response_time)


async def record_bot_error(bot_id: str):
    await bot_stats_manager.record_bot_error(bot_id)


async def get_bot_detailed_stats(bot_id: str) -> Optional[Dict]:
    return await bot_stats_manager.get_bot_stats(bot_id)


async def get_all_bots_detailed_stats() -> Dict[str, Dict]:
    return await bot_stats_manager.get_all_bots_stats()


async def get_aggregated_bots_stats() -> Dict:
    return await bot_stats_manager.get_aggregated_stats()