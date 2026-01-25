import logging
from typing import Dict, Optional
import asyncio

from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.PerBotRPS import PerBotRPS

logger = logging.getLogger(__name__)


class BotRPSManager:
    """
    Менеджер для отслеживания RPS статистики всех ботов
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.bot_stats: Dict[str, PerBotRPS] = {}
        self._lock = asyncio.Lock()
        self._initialized = True

        logger.info("📊 Менеджер RPS статистики инициализирован")

    def get_or_create_bot_stats(self, bot_id: str) -> PerBotRPS:
        """Получить или создать статистику для бота"""
        if bot_id not in self.bot_stats:
            self.bot_stats[bot_id] = PerBotRPS(bot_id)
            logger.info(f"📊 Создана статистика для бота {bot_id}")

        return self.bot_stats[bot_id]

    def record_request(self, bot_id: str):
        """Учесть запрос для бота"""
        stats = self.get_or_create_bot_stats(bot_id)
        stats.record_request()

    def record_handled(self, bot_id: str):
        """Учесть обработанный запрос для бота"""
        stats = self.get_or_create_bot_stats(bot_id)
        stats.record_handled()

    def record_unique_user(self, bot_id: str, user_id: int):
        """Учесть уникального пользователя для бота"""
        stats = self.get_or_create_bot_stats(bot_id)
        stats.record_unique_user(user_id)

    async def get_bot_stats_detailed(self, bot_id: str) -> Optional[Dict]:
        """Получить детальную статистику бота"""
        if bot_id in self.bot_stats:
            stats = self.bot_stats[bot_id]
            return await stats.get_stats_detailed_async()
        return None

    async def get_all_bots_stats(self) -> Dict[str, Dict]:
        """Получить статистику всех ботов"""
        async with self._lock:
            result = {}
            for bot_id, stats in self.bot_stats.items():
                result[bot_id] = await stats.get_stats_detailed_async()
            return result

    async def get_aggregated_stats(self) -> Dict:
        """Получить агрегированную статистику по всем ботам"""
        all_stats = await self.get_all_bots_stats()

        if not all_stats:
            return {
                "total_requests": 0,
                "handled_requests": 0,
                "total_unique": 0,
                "percent": 100.0,
                "percent_info": "0 | 0",
                "handled_rps_1s": 0.0,
                "handled_rps_5min": 0.0,
                "handled_rps_1h": 0.0,
                "display": "(0/0) → 100.0% | RPS: 0.0/0.0/s | 👤 0 (0.0/s)"
            }

        # Агрегируем данные
        total_requests = sum(stats.get('total', 0) for stats in all_stats.values())
        handled_requests = sum(stats.get('handled', 0) for stats in all_stats.values())
        total_unique = sum(stats.get('total_unique', 0) for stats in all_stats.values())

        # Суммируем RPS
        handled_rps_1s = sum(stats.get('handled_rps_1s', 0) for stats in all_stats.values())
        handled_rps_5min = sum(stats.get('handled_rps_5min', 0) for stats in all_stats.values())
        handled_rps_1h = sum(stats.get('handled_rps_1h', 0) for stats in all_stats.values())

        # Также RPS входящих запросов
        rps_1s = sum(stats.get('rps_1s', 0) for stats in all_stats.values())

        # Рассчитываем общий процент
        percent = (handled_requests / total_requests * 100) if total_requests > 0 else 100.0
        percent_info = f"{handled_requests} | {total_requests}"

        # UPS (уникальные пользователи в секунду)
        ups_1s = sum(stats.get('ups_1s', 0) for stats in all_stats.values())

        display = f"({handled_requests}/{total_requests}) → {percent:.1f}% | RPS: {handled_rps_1s:.1f}/{rps_1s:.1f}/s | 👤 {total_unique} ({ups_1s:.1f}/s)"

        return {
            "total": total_requests,
            "handled": handled_requests,
            "total_unique": total_unique,
            "percent": round(percent, 2),
            "percent_info": percent_info,
            "handled_rps_1s": round(handled_rps_1s, 2),
            "handled_rps_5min": round(handled_rps_5min, 2),
            "handled_rps_1h": round(handled_rps_1h, 2),
            "rps_1s": round(rps_1s, 2),
            "ups_1s": round(ups_1s, 2),
            "display": display,
            "bot_count": len(all_stats),
            "bots": {bot_id: stats.get('display', '') for bot_id, stats in all_stats.items()}
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
bot_rps_manager = BotRPSManager()


# Функции для обратной совместимости со старым кодом
async def get_rps_detailed_async() -> Dict:
    """Получить агрегированную статистику по всем ботам"""
    return await bot_rps_manager.get_aggregated_stats()


async def get_all_bots_rps_stats() -> Dict[str, Dict]:
    """Получить статистику всех ботов отдельно"""
    return await bot_rps_manager.get_all_bots_stats()


async def get_bot_rps_stats(bot_id: str) -> Optional[Dict]:
    """Получить статистику конкретного бота"""
    return await bot_rps_manager.get_bot_stats_detailed(bot_id)