import asyncio
import logging
from typing import Dict
from datetime import datetime, timedelta

from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotDetailedStats import bot_stats_manager
from handlers.BotAutomaticWork.active_bot_registry import registry
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

logger = logging.getLogger(__name__)


class BotChatStatsService:
    """Сервис для обновления статистики чатов ботов"""

    def __init__(self, update_interval: int = 60):
        self.update_interval = update_interval
        self.running = False
        self.task = None

        logger.info("📊 Сервис статистики чатов инициализирован")

    async def start(self):
        """Запустить сервис"""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self._update_loop())
        logger.info("✅ Сервис статистики чатов запущен")

    async def stop(self):
        """Остановить сервис"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("🛑 Сервис статистики чатов остановлен")

    async def _update_loop(self):
        """Цикл обновления статистики"""
        while self.running:
            try:
                await self.update_all_bots_chat_stats()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обновления статистики: {e}")
                await asyncio.sleep(10)

    async def update_all_bots_chat_stats(self):
        """Обновить статистику чатов для всех ботов"""
        try:
            # Получаем конфигурации всех ботов
            for bot_config in MultiBotConfig.BOTS:
                bot_id = bot_config.get('id')
                bot_name = bot_config.get('name', bot_id)

                if not bot_id:
                    continue

                # Получаем количество чатов для этого бота
                chat_count = registry.get_chat_count(bot_id)

                # Обновляем статистику
                await bot_stats_manager.update_bot_chat_count(bot_id, chat_count)

                # Получаем и обновляем имя бота в статистике
                stats = bot_stats_manager.get_or_create_bot_stats(bot_id, bot_name)
                if stats.bot_name != bot_name:
                    stats.bot_name = bot_name

            logger.debug(f"📊 Обновлена статистика чатов для всех ботов")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики чатов: {e}")

    async def get_bots_with_chats(self) -> Dict[str, Dict]:
        """Получить список ботов с информацией о чатах"""
        result = {}

        for bot_config in MultiBotConfig.BOTS:
            bot_id = bot_config.get('id')
            bot_name = bot_config.get('name', bot_id)

            if not bot_id:
                continue

            # Получаем статистику бота
            stats = await bot_stats_manager.get_bot_stats(bot_id)
            if not stats:
                stats = {}

            # Получаем чаты бота
            chat_ids = registry.get_all_chats_for_bot(bot_id)

            result[bot_id] = {
                'name': bot_name,
                'chat_count': len(chat_ids),
                'chat_ids': chat_ids[:10],  # Только первые 10
                'total_chats': len(chat_ids),
                'stats': stats
            }

        return result

    async def get_bot_chat_details(self, bot_id: str) -> Dict:
        """Получить детальную информацию о чатах бота"""
        try:
            bot_config = MultiBotConfig.get_bot_by_id(bot_id)
            if not bot_config:
                return {}

            chat_ids = registry.get_all_chats_for_bot(bot_id)
            stats = await bot_stats_manager.get_bot_stats(bot_id) or {}

            return {
                'bot_id': bot_id,
                'bot_name': bot_config.get('name', bot_id),
                'total_chats': len(chat_ids),
                'chat_ids': chat_ids,
                'stats': stats,
                'active_chats': len(chat_ids),
                'inactive_chats': 0,  # Можно добавить логику определения
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения деталей чатов: {e}")
            return {}


# Глобальный экземпляр
chat_stats_service = BotChatStatsService()