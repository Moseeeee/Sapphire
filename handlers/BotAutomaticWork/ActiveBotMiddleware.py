# handlers/BotAutomaticWork/Middleware/ActiveBotMiddleware.py
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.types import Update, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
import logging

from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
from handlers.BotAutomaticWork.active_bot_registry import registry

logger = logging.getLogger(__name__)


class ActiveBotMiddleware(BaseMiddleware):
    """
    Middleware для обновления active_bots.json
    """

    def __init__(self, current_bot_id: str):
        super().__init__()
        self.current_bot_id = current_bot_id
        logger.info(f"🔄 Middleware для бота {current_bot_id}")

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:

        # Обновляем active_bots.json при изменении статуса бота
        if event.my_chat_member:
            await self._update_bot_status(event.my_chat_member)

        # Пропускаем дальше
        return await handler(event, data)

    async def _update_bot_status(self, event: ChatMemberUpdated):
        """Обновить статус бота в active_bots.json"""
        chat_id = event.chat.id
        old_status = event.old_chat_member.status
        new_status = event.new_chat_member.status

        #logger.info(f"📝 Статус: {old_status} -> {new_status} в чате {chat_id}")

        # Бота ДОБАВИЛИ в чат
        if (old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and
                new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]):

            # Проверяем, есть ли уже бот в этом чате
            current_bot = registry.get_bot_for_chat(chat_id)

            if current_bot and current_bot != self.current_bot_id:
                # В чате уже другой бот - удаляем его
                registry.remove_chat(chat_id)
                #logger.info(f"🗑️ Удалён предыдущий бот {current_bot}")

            # Регистрируем текущего бота
            registry.set_bot_for_chat(chat_id, self.current_bot_id)

            # Приветствуем
            #try:
                #bot_config = MultiBotConfig.get_bot_by_id(self.current_bot_id)
                #bot_name = bot_config.get('name', 'Бот')

                #await event.bot.send_message(
                    #chat_id=chat_id,
                    #text=f"✅ {bot_name} активирован!\n"
                         #f"Теперь я обслуживаю этот чат."
                #)
            #except Exception as e:
                #logger.error(f"❌ Ошибка приветствия: {e}")

        # Бота УДАЛИЛИ из чата
        elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and
              new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]):

            # Удаляем только если это текущий бот
            current_bot = registry.get_bot_for_chat(chat_id)
            if current_bot == self.current_bot_id:
                registry.remove_chat(chat_id)
                #logger.info(f"👋 Бот {self.current_bot_id} удалён из чата {chat_id}")