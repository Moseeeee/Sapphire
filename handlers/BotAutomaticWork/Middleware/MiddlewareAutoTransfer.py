from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import Update, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
import logging
import asyncio

from handlers.BotAutomaticWork.BotCreatedGlobal import get_all_bots
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

logger = logging.getLogger(__name__)


class AutoTransferMiddleware(BaseMiddleware):
    """
    Middleware для автоматической передачи чата при добавлении нового бота.
    """

    def __init__(self, current_bot_token: str):
        super().__init__()
        self.current_bot_token = current_bot_token
        self.current_bot_config = MultiBotConfig.get_bot_by_token(current_bot_token)
        self.lock = asyncio.Lock()

        if self.current_bot_config:
            logger.info(f"✅ AutoTransferMiddleware для бота {self.current_bot_config.get('name', 'Unknown')}")
        else:
            logger.error(f"❌ Не удалось получить конфигурацию для токена {current_bot_token[:10]}...")

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        try:
            # Обрабатываем ChatMemberUpdated (добавление/удаление ботов)
            if event.my_chat_member:
                await self._handle_my_chat_member(event.my_chat_member)
            elif event.chat_member:
                # Это события для других пользователей, не обрабатываем
                pass

            # Для обычных событий проверяем, активен ли наш бот в этом чате
            chat_id = self._extract_chat_id(event)
            if chat_id:
                active_bot = MultiBotConfig.get_active_bot_for_chat(chat_id)

                if active_bot and active_bot['id'] != self.current_bot_config['id']:
                    # Этот чат обслуживает другой бот - игнорируем события
                    #logger.debug(f"🚫 Чат {chat_id} обслуживается ботом {active_bot.get('name')}, игнорирую")
                    return None

            # Пропускаем дальше
            return await handler(event, data)

        except Exception as e:
            logger.error(f"❌ Ошибка в AutoTransferMiddleware: {e}", exc_info=True)
            return await handler(event, data)

    async def _handle_my_chat_member(self, event: ChatMemberUpdated):
        """Обработка событий изменения статуса текущего бота в чате"""
        try:
            if not self.current_bot_config:
                return

            chat = event.chat
            old_status = event.old_chat_member.status
            new_status = event.new_chat_member.status

           # logger.info(
                #f"🤖 Статус бота {self.current_bot_config['name']} изменился в чате {chat.id}: {old_status} -> {new_status}")

            # Бота ДОБАВИЛИ в чат
            if (old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, None] and
                    new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]):

                async with self.lock:
                    # Проверяем, есть ли уже активный бот в этом чате
                    active_bot = MultiBotConfig.get_active_bot_for_chat(chat.id)

                    if active_bot:
                        # В чате уже есть активный бот - просим его выйти
                        await self._ask_old_bot_to_leave(chat.id, active_bot['id'])

                    # Текущий бот становится активным
                    MultiBotConfig.set_active_bot_for_chat(chat.id, self.current_bot_config['id'])

                    #logger.info(f"🎯 Бот {self.current_bot_config['name']} стал активным в чате {chat.id}")

                    # Отправляем приветственное сообщение
                    await self._send_welcome_message(event)

            # Бота УДАЛИЛИ из чата
            elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and
                  new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]):

                # Удаляем бота из активных
                MultiBotConfig.remove_bot_from_chat(chat.id, self.current_bot_config['id'])

                #logger.info(f"👋 Бот {self.current_bot_config['name']} покинул чат {chat.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки my_chat_member: {e}", exc_info=True)

    async def _ask_old_bot_to_leave(self, chat_id: int, old_bot_id: str):
        """Попросить старого бота выйти из чата"""
        try:
            old_bot_config = MultiBotConfig.get_bot_by_id(old_bot_id)
            if not old_bot_config:
                return

            # Получаем экземпляр старого бота
            all_bots = get_all_bots()
            old_bot_token = old_bot_config['TOKEN']
            old_bot = all_bots.get(old_bot_token)

            if not old_bot:
                return

            # Отправляем команду старому боту выйти
            try:
                await old_bot.leave_chat(chat_id)
                #logger.info(f"🚶 Старый бот {old_bot_config['name']} вышел из чата {chat_id}")

                # Удаляем из активных
                MultiBotConfig.remove_bot_from_chat(chat_id, old_bot_id)

            except Exception as e:
                logger.warning(f"⚠️ Не удалось выгнать старого бота: {e}")

                # Все равно меняем активного бота
                #logger.info(f"📝 Чат {chat_id} передан новому боту, несмотря на ошибку")

        except Exception as e:
            logger.error(f"❌ Ошибка в _ask_old_bot_to_leave: {e}")

    async def _send_welcome_message(self, event: ChatMemberUpdated):
        """Отправить приветственное сообщение при добавлении бота"""
        try:
            if not self.current_bot_config:
                return

            chat = event.chat

            welcome_text = (
                f"🤖 <b>Бот {self.current_bot_config['name']} активирован!</b>\n\n"
                f"✅ Теперь я обслуживаю этот чат.\n"
                f"🔧 Все предыдущие боты были автоматически отключены.\n\n"
                f"<i>Для смены бота просто добавьте другого бота из этой же системы.</i>"
            )

            #await event.bot.send_message(
                #chat_id=chat.id,
                #text=welcome_text,
                #parse_mode='HTML'
            #)

        except Exception as e:
            logger.error(f"❌ Ошибка отправки welcome сообщения: {e}")

    def _extract_chat_id(self, event: Update) -> int:
        """Извлечь chat_id из события"""
        try:
            if event.message:
                return event.message.chat.id
            elif event.callback_query and event.callback_query.message:
                return event.callback_query.message.chat.id
            elif event.chat_member:
                return event.chat_member.chat.id
            elif event.my_chat_member:
                return event.my_chat_member.chat.id
            elif event.chat_join_request:
                return event.chat_join_request.chat.id
        except:
            pass
        return None

    async def on_startup(self):
        """Запуск middleware"""
        if self.current_bot_config:
            logger.info(f"🚀 AutoTransferMiddleware запущен для {self.current_bot_config.get('name')}")

            # При старте бота, проверяем в каких чатах он администратор
            # и обновляем статус
            await self._sync_bot_status()
        else:
            logger.error("❌ Не удалось запустить AutoTransferMiddleware - нет конфигурации бота")

    async def _sync_bot_status(self):
        """Синхронизировать статус бота при запуске"""
        try:
            # Здесь можно добавить логику проверки чатов,
            # но это требует дополнительных прав бота
            logger.info(f"🔄 Синхронизация статуса бота {self.current_bot_config.get('name')}")

            # Пока просто логируем
            bot = next((b for b in get_all_bots().values()
                        if b.token == self.current_bot_token), None)
            if bot:
                try:
                    bot_info = await bot.get_me()
                    logger.info(f"🤖 Бот {self.current_bot_config.get('name')} запущен как @{bot_info.username}")
                except:
                    pass

        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации статуса: {e}")

    async def on_shutdown(self):
        """Остановка middleware"""
        if self.current_bot_config:
            logger.info(f"🛑 AutoTransferMiddleware остановлен для {self.current_bot_config.get('name')}")
