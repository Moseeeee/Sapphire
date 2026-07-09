import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Awaitable, Dict, Any
import pytz
from aiogram import BaseMiddleware
from aiogram.enums import ChatMemberStatus
from aiogram.types import Update, CallbackQuery, ChatMemberUpdated, Message
from handlers.BotAutomaticWork.Middleware.MiddlewareCache import is_user_ignored_cached
from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import enqueue_user_update
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager
from handlers.BotAutomaticWork.Middleware.MiddlewareUtils import extract_user_info
from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import update_user_activity
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import increment_message
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

# Безопасный импорт хука мгновенного онлайна под любую конфигурацию PYTHONPATH
from handlers.BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import track_user_online_instant

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
        # === КЭШ ДАННЫХ ЧАТА ===
        self._chat_cache = {}
        # ======================

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

                # === Мгновенный In-Memory трекинг онлайна (O(1)) ===
                asyncio.create_task(track_user_online_instant(user_id))
                # ==========================================================

                # Проверяем наличие текста для фильтрации ссылок
                if event.message and (event.message.text or event.message.caption):
                    from handlers.AdminsTools.ChatSettings.settings_link_filter.links_filter import \
                        check_links_in_message
                    was_blocked = await check_links_in_message(event.message)

                    if was_blocked:
                        bot_rps_manager.record_handled(self.bot_id)
                        return None

                # === Обрабатываем ChatMemberUpdated и СРАЗУ выходим ===
                if event.chat_member:
                    result = await self._process_chat_member_update(event, user_id, name, username, chat, chat_id)
                    bot_rps_manager.record_handled(self.bot_id)
                    return result

                # === Для остальных обычных событий ===
                result = await self._process_regular_event(handler, event, data, user_id, name, username, chat, chat_id)

                # Обновляем статистику сообщений только для обычных сообщений в групповых чатах
                if (event.message and chat and hasattr(chat, 'type') and chat.type != 'private'):
                    asyncio.create_task(self._update_additional_stats(user_id, chat))

                bot_rps_manager.record_handled(self.bot_id)
                return result
            else:
                logger.debug(f"⚠️ Could not extract user info from update {update_id}")
                bot_rps_manager.record_handled(self.bot_id)
                return await handler(event, data)
        except Exception as e:
            logger.error(f"❌ Middleware error processing update {update_id}: {e}", exc_info=True)
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
            return "ok"

        # 1. НЕМЕДЛЕННО обновляем данные пользователя в БД
        await self._update_user_data_immediately(user_id, name, username, chat, chat_id)

        # 2. Обрабатываем вход/выход СРАЗУ
        await self._process_chat_member_status(chat_member_event)

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

                # Привязка к чату (только для групповых чатов)
                if chat_id and chat_id < 0:
                    await conn.execute('''
                    INSERT INTO users_chats (chat_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id, user_id) DO NOTHING
                    ''', chat_id, user_id)

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
            is_join = False
            is_leave = False

            # Присоединение (ИСПРАВЛЕНО: учитываем дефолтные ограничения RESTRICTED при входе)
            if (old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, None] and
                    new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED]):
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

            # Изменение restricted статуса внутри чата
            elif old_status == ChatMemberStatus.RESTRICTED and new_status == ChatMemberStatus.RESTRICTED:
                old_is_member = getattr(event.old_chat_member, 'is_member', False)
                new_is_member = getattr(event.new_chat_member, 'is_member', False)
                if old_is_member and not new_is_member:
                    is_leave = True
                elif not old_is_member and new_is_member:
                    is_join = True

            # Вызов обработчиков
            if is_join:
                from handlers.AdminsTools.ChatSettings.welcome.check_join_left import handle_join
                await handle_join(event)
            elif is_leave:
                from handlers.AdminsTools.ChatSettings.welcome.check_join_left import handle_leave
                await handle_leave(event)
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
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(cache_time=3600)
                except:
                    pass
            return None

        asyncio.create_task(update_user_activity(user_id))

        # Получаем данные чата перед передачей (с кэшированием)
        chat_key = f"{chat_id}_{self.bot_id}"
        if chat_key in self._chat_cache:
            chat_title, chat_username = self._chat_cache[chat_key]
        else:
            chat_title = None
            chat_username = None
            if chat:
                if hasattr(chat, 'title'):
                    chat_title = chat.title
                if hasattr(chat, 'username'):
                    chat_username = chat.username
            self._chat_cache[chat_key] = (chat_title, chat_username)

        # Обновляем информацию о пользователе в фоне
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
            await increment_message(chat.id, user_id)
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