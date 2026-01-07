import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Awaitable, Dict, Any

import pytz
from aiogram import BaseMiddleware
from aiogram.enums import ChatMemberStatus
from aiogram.types import Update, CallbackQuery, ChatMemberUpdated

from handlers.BotAutomaticWork.Middleware.MiddlewareCache import is_user_ignored_cached
from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import enqueue_user_update
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager
from handlers.BotAutomaticWork.Middleware.MiddlewareUtils import extract_user_info
from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import update_user_activity
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import increment_message
#from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_and_add_user_rang
from handlers.AdminsTools.ChatSettings.welcome.check_join_left import handle_join, handle_leave
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


class UpdateChatUserMiddleware(BaseMiddleware):
    """Middleware для обработки обновлений пользователей и чатов"""

    def __init__(self, bot_token: str):
        super().__init__()
        self.bot_token = bot_token
        self.bot = get_bot_by_token(bot_token) if bot_token else None
        self.bot_id = self._get_bot_id_from_token(bot_token)
        self.processed_events = set()

        if not self.bot:
            logger.warning(f"⚠️ Bot not found for token {bot_token[:20]}...")
        else:
            logger.info(f"✅ UpdateChatUserMiddleware initialized for bot {self.bot_id}")

    def _get_bot_id_from_token(self, token: str) -> str:
        """Получить bot_id из токена"""
        for bot_config in MultiBotConfig.BOTS:
            if bot_config.get('TOKEN') == token:
                return bot_config.get('id', f"bot_{token[:10]}")
        return f"bot_{token[:10]}"

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        """
        Основной метод middleware.
        """
        update_id = event.update_id

        if update_id in self.processed_events:
            #logger.debug(f"🔄 Event {update_id} already processed, skipping")
            return await handler(event, data)

        self.processed_events.add(update_id)
        if len(self.processed_events) > 1000:
            self.processed_events.clear()

        # Записываем запрос для этого бота
        bot_rps_manager.record_request(self.bot_id)

        start_time = time.time()

        try:
            # Извлекаем информацию о пользователе
            info = extract_user_info(event)

            if info:
                user_id, name, username, chat, chat_id = info

                # Записываем уникального пользователя для RPS
                bot_rps_manager.record_unique_user(self.bot_id, user_id)

                # Для ChatMemberUpdated - обрабатываем СРАЗУ и полностью
                if event.chat_member:
                    #logger.info(f"🔄 Processing ChatMemberUpdated for user {user_id}")
                    result = await self._process_chat_member_update(event, user_id, name, username, chat, chat_id)
                    # Записываем успешную обработку
                    bot_rps_manager.record_handled(self.bot_id)
                    return result

                # Для обычных событий
                result = await self._process_regular_event(handler, event, data, user_id, name, username, chat, chat_id)

                # Обновляем статистику сообщений и ранги (в фоне)
                if chat and hasattr(chat, 'type') and chat.type != 'private':
                    asyncio.create_task(self._update_additional_stats(user_id, chat))

                # Записываем успешную обработку
                bot_rps_manager.record_handled(self.bot_id)

                # Логируем статус очереди каждые 50 запросов
                if update_id % 50 == 0:
                    from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import log_queue_stats
                    await log_queue_stats()

                return result
            else:
                logger.debug(f"⚠️ Could not extract user info from update {update_id}")
                # Все равно записываем как обработанное
                bot_rps_manager.record_handled(self.bot_id)
                return await handler(event, data)

        except Exception as e:
            logger.error(f"❌ Middleware error processing update {update_id}: {e}", exc_info=True)
            # При ошибке все равно записываем как обработанное
            bot_rps_manager.record_handled(self.bot_id)
            return await handler(event, data)
        finally:
            processing_time = time.time() - start_time
            if processing_time > 0.3:
                logger.warning(f"⏱️ SLOW Middleware: {processing_time:.3f}s for update {update_id}")

    async def _process_chat_member_update(self, event: Update, user_id: int, name: str,
                                          username: str, chat: Any, chat_id: int) -> Any:
        """Обработка ChatMemberUpdated СРАЗУ (без фоновой очереди)"""
        chat_member_event = event.chat_member

        # Игнорируем ботов
        if chat_member_event.new_chat_member.user.is_bot:
            #logger.debug(f"  Skipping bot user: {user_id}")
            return "ok"

        #old_status = chat_member_event.old_chat_member.status
        #new_status = chat_member_event.new_chat_member.status

        #logger.info(f"  Processing ChatMemberUpdated: user={user_id}, {old_status} -> {new_status}")

        # 1. Обрабатываем вход/выход СРАЗУ
        await self._process_chat_member_status(chat_member_event)

        # 2. НЕМЕДЛЕННО обновляем данные пользователя в БД
        await self._update_user_data_immediately(user_id, name, username, chat, chat_id)

        return "ok"

    async def _update_user_data_immediately(self, user_id: int, name: str, username: str,
                                            chat: Any, chat_id: int):
        """Немедленно обновить данные пользователя в БД"""
        try:
            pool = get_db_pool()

            async with pool.acquire() as conn:
                now = datetime.now(MOSCOW_TZ).isoformat()

                # Обновление пользователя
                await conn.execute('''
                    INSERT INTO users (user_id, name, username, first_seen, last_activity)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        username = EXCLUDED.username,
                        last_activity = EXCLUDED.last_activity
                ''', user_id, name, username, now, now)

                #logger.debug(f"✅ Updated user {user_id} in DB")

                # Привязка к чату (только для групповых чатов)
                if chat_id and chat_id < 0:
                    await conn.execute('''
                        INSERT INTO users_chats (chat_id, user_id)
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id, user_id) DO NOTHING
                    ''', chat_id, user_id)

                    #logger.debug(f"✅ Linked user {user_id} to chat {chat_id}")

                    # Обновление информации о чате (в фоне)
                    if chat and hasattr(chat, 'title'):
                        asyncio.create_task(self._update_chat_info_in_background(chat_id, chat.title,
                                                                                 getattr(chat, 'username', None)))

                # Обновление кэша игнора
                ignored = await conn.fetchval('SELECT 1 FROM ignore_users WHERE user_id = $1', user_id)
                from handlers.BotAutomaticWork.Middleware.MiddlewareCache import update_ignore_cache
                await update_ignore_cache(user_id, ignored is not None)

        except Exception as e:
            logger.error(f"❌ Error updating user data immediately for {user_id}: {e}", exc_info=True)

    async def _update_chat_info_in_background(self, chat_id: int, title: str, username: str):
        """Обновить информацию о чате в фоне"""
        try:
            from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import _update_chat_info_smart
            pool = get_db_pool()
            async with pool.acquire() as conn:
                await _update_chat_info_smart(conn, chat_id, title, username)
        except Exception as e:
            logger.error(f"Error updating chat info in background: {e}")

    async def _process_chat_member_status(self, event: ChatMemberUpdated):
        """Обработка статусов участника чата"""
        try:
            old_status = event.old_chat_member.status
            new_status = event.new_chat_member.status
            user = event.new_chat_member.user

            #logger.info(f"    Status change: {old_status} -> {new_status}")

            is_join = False
            is_leave = False

            # Присоединение
            if (old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, None] and
                    new_status == ChatMemberStatus.MEMBER):
                is_join = True

            # Выход
            elif (old_status == ChatMemberStatus.MEMBER and
                  new_status == ChatMemberStatus.LEFT):
                is_leave = True

            # Кик
            elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED,
                                 ChatMemberStatus.ADMINISTRATOR] and
                  new_status == ChatMemberStatus.KICKED):
                is_leave = True

            # Администратор вышел
            elif (old_status == ChatMemberStatus.ADMINISTRATOR and
                  new_status == ChatMemberStatus.LEFT):
                is_leave = True

            # Изменение restricted статуса
            elif old_status == ChatMemberStatus.RESTRICTED and new_status == ChatMemberStatus.RESTRICTED:
                old_is_member = getattr(event.old_chat_member, 'is_member', False)
                new_is_member = getattr(event.new_chat_member, 'is_member', False)

                if old_is_member and not new_is_member:
                    is_leave = True
                elif not old_is_member and new_is_member:
                    is_join = True

            # Вызов обработчиков
            if is_join:
                #logger.info(f"    ✨ User joined, calling handle_join")
                await handle_join(event)
            elif is_leave:
                #logger.info(f"    👋 User left, calling handle_leave")
                await handle_leave(event)
            else:
                logger.info(f"ℹ️ Error: статус юзера в чате не определён.")

        except Exception as e:
            logger.error(f"❌ Error in chat member status processing: {e}", exc_info=True)

    async def _process_regular_event(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any],
            user_id: int, name: str, username: str, chat: Any, chat_id: int
    ) -> Any:
        """Обработка регулярных событий (сообщения, колбэки)"""

        # Проверяем игнор
        is_ignored = await is_user_ignored_cached(user_id)

        if is_ignored:
            #logger.debug(f"  User {user_id} is ignored, skipping")
            # Для игнорируемых пользователей
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(cache_time=3600)
                except:
                    pass
            return None

        asyncio.create_task(update_user_activity(user_id))

        # Получаем данные чата перед передачей
        chat_title = None
        chat_username = None
        if chat:
            if hasattr(chat, 'title'):
                chat_title = chat.title
            if hasattr(chat, 'username'):
                chat_username = chat.username

        # Обновляем информацию о пользователе в фоне - используем await для асинхронной функции
        #logger.info(f"📝 Enqueuing update for user {user_id} ({name})")
        await enqueue_user_update({
            "user_id": user_id,
            "name": name,
            "username": username,
            "chat_id": chat_id,
            "chat_title": chat_title,
            "chat_username": chat_username,
            "is_chat_member_update": False,
        }, bot_id=self.bot_id)

        # Пропускаем дальше к хендлерам
        try:
            result = await handler(event, data)
            return result
        except Exception as e:
            logger.error(f"Handler error for user {user_id}: {e}", exc_info=True)
            return None

    async def _update_additional_stats(self, user_id: int, chat: Any):
        """Обновление дополнительной статистики в фоне"""
        try:
            # Обновляем статистику сообщений
            await increment_message(chat.id, user_id)
            # Проверяем и обновляем ранг пользователя
            #await check_and_add_user_rang(user_id, chat.id)
        except Exception as e:
            logger.error(f"Error updating additional stats for user {user_id}: {e}")

    async def on_startup(self):
        """Вызывается при старте бота"""
        logger.info(f"🚀 UpdateChatUserMiddleware starting up for bot {self.bot_id}...")
        self.processed_events.clear()

    async def on_shutdown(self):
        """Вызывается при остановке бота"""
        logger.info(f"🛑 UpdateChatUserMiddleware shutting down for bot {self.bot_id}...")
        from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import timer_manager
        await timer_manager.cleanup()
        self.processed_events.clear()