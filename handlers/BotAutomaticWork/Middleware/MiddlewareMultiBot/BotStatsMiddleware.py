# handlers/BotAutomaticWork/Middleware/BotStatsMiddleware.py
import time
import logging
from typing import Callable, Awaitable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Update

from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotDetailedStats import record_bot_user_request, \
    record_bot_handled_user, record_bot_response_time, record_bot_error
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.SuperBotLoadEstimator import super_bot_load_estimator

logger = logging.getLogger(__name__)


class BotStatsMiddleware(BaseMiddleware):
    """Middleware для сбора статистики ботов"""

    def __init__(self, bot_id: str):
        super().__init__()
        self.bot_id = bot_id
        logger.debug(f"📊 BotStatsMiddleware для {bot_id}")

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Извлекаем user_id
        user_id = self._extract_user_id(event)

        # === ЗАПИСЬ ЗАПРОСА И УНИКАЛЬНОГО ПОЛЬЗОВАТЕЛЯ ===
        if user_id:
            try:
                await record_bot_user_request(self.bot_id, user_id)
                bot_rps_manager.record_unique_user(self.bot_id, user_id)
            except Exception as e:
                logger.error(f"Ошибка записи запроса: {e}")

        # === НОВОЕ: замер времени выполнения хендлера ===
        start_time = time.time()
        try:
            result = await handler(event, data)
            handler_time_ms = (time.time() - start_time) * 1000  # мс

            # Записываем в метрики
            metrics = super_bot_load_estimator._get_metrics(self.bot_id)
            metrics.record_handler_time(handler_time_ms)

            if user_id:
                try:
                    await record_bot_handled_user(self.bot_id, user_id)
                    if handler_time_ms < 10000:
                        await record_bot_response_time(self.bot_id, handler_time_ms)
                        bot_rps_manager.get_or_create_bot_stats(self.bot_id).record_ping(handler_time_ms)
                except Exception as e:
                    logger.error(f"Ошибка записи статистики: {e}")
            return result

        except Exception as e:
            # === НОВОЕ: запись ошибки + счётчик в PerBotRPS ===
            try:
                await record_bot_error(self.bot_id)
                bot_rps_manager.get_or_create_bot_stats(self.bot_id).record_error()
            except Exception as err:
                logger.error(f"Ошибка записи ошибки: {err}")
            raise e

    def _extract_user_id(self, event: Update) -> int:
        try:
            if event.message:
                return event.message.from_user.id
            elif event.callback_query:
                return event.callback_query.from_user.id
            elif event.chat_member:
                return event.chat_member.new_chat_member.user.id
            elif event.my_chat_member:
                return event.my_chat_member.new_chat_member.user.id
            elif event.chat_join_request:
                return event.chat_join_request.from_user.id
            elif event.inline_query:
                return event.inline_query.from_user.id
        except Exception as e:
            logger.debug(f"Не удалось извлечь user_id: {e}")
        return None