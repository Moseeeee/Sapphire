# handlers/BotAutomaticWork/Middleware/ResponseTimeMiddleware.py
import time
import logging
from typing import Callable, Dict, Any, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import Update


logger = logging.getLogger(__name__)


class ResponseTimeMiddleware(BaseMiddleware):
    """Middleware для отслеживания времени ответа ботов"""

    def __init__(self, bot_id: str):
        super().__init__()
        self.bot_id = bot_id
        logger.info(f"⏱️ ResponseTimeMiddleware для бота {bot_id}")

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        start_time = time.time()

        try:
            # Выполняем обработчик
            result = await handler(event, data)

            # Рассчитываем время ответа
            response_time = (time.time() - start_time) * 1000  # в мс

            # Извлекаем user_id из события
            user_id = self._extract_user_id(event)
            if user_id:
                # Записываем время ответа
                bot_stats_manager.record_handled(self.bot_id, user_id, response_time)

                # Также записываем как пинг к Telegram (если это ответ на API вызов)
                if response_time < 10000:  # Игнорируем слишком большие значения
                    bot_stats_manager.record_telegram_ping(self.bot_id, response_time)

            return result

        except Exception as e:
            # При ошибке также записываем время
            response_time = (time.time() - start_time) * 1000
            logger.error(f"❌ Ошибка в ResponseTimeMiddleware: {e}, время: {response_time:.0f}мс")

            # Записываем ошибку в статистику
            bot_stats_manager.get_or_create_bot_stats(self.bot_id).record_error()

            raise

    def _extract_user_id(self, event: Update) -> Optional[int]:
        """Извлечь user_id из события"""
        try:
            if event.message and event.message.from_user:
                return event.message.from_user.id
            elif event.callback_query and event.callback_query.from_user:
                return event.callback_query.from_user.id
            elif event.chat_member and event.chat_member.new_chat_member:
                return event.chat_member.new_chat_member.user.id
            elif event.my_chat_member and event.my_chat_member.new_chat_member:
                return event.my_chat_member.new_chat_member.user.id
        except:
            pass
        return None