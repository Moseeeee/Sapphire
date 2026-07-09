from aiogram import BaseMiddleware
from aiogram.enums import ChatMemberStatus
from aiogram.types import Update, Message, CallbackQuery, InlineQuery, ChatMemberUpdated
import time
import logging
import hashlib
from typing import Callable, Awaitable, Dict, Any, Optional
from datetime import datetime
import pytz
import asyncio

from handlers.AdminsTools.ChatSettings.welcome.check_join_left import handle_join, handle_leave
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import increment_message
from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_and_add_user_rang

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

class TimerManager:
    """Асинхронный менеджер таймеров"""
    def __init__(self, max_timers: int = 10000):
        self.timers = {}
        self.max_timers = max_timers
        self._lock = asyncio.Lock()

    async def set_timer(self, user_id: int, callback, delay: float) -> asyncio.Task:
        """Устанавливает или обновляет таймер для пользователя"""
        async with self._lock:
            if user_id in self.timers:
                task = self.timers[user_id]
                task.cancel()
                del self.timers[user_id]

            async def timer_task():
                try:
                    await asyncio.sleep(delay)
                    await callback(user_id)
                except asyncio.CancelledError:
                    pass
                finally:
                    async with self._lock:
                        if user_id in self.timers:
                            del self.timers[user_id]

            task = asyncio.create_task(timer_task())
            self.timers[user_id] = task
            if len(self.timers) > self.max_timers:
                await self._cleanup_old_timers()
            return task

    async def cancel_timer(self, user_id: int):
        """Отменяет таймер для пользователя"""
        async with self._lock:
            if user_id in self.timers:
                task = self.timers[user_id]
                task.cancel()
                del self.timers[user_id]

    async def _cleanup_old_timers(self):
        """Очищает 10% самых старых таймеров"""
        remove_count = max(1, len(self.timers) // 10)
        for _ in range(remove_count):
            if self.timers:
                user_id, task = self.timers.popitem()
                task.cancel()

    async def cleanup(self):
        """Полная очистка всех таймеров"""
        async with self._lock:
            for task in self.timers.values():
                task.cancel()
            self.timers.clear()

class UserRPSCounter:
    """Асинхронный счетчик RPS"""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cleanup_task = None
        self.start_time = time.time()
        self.users_per_second = {}
        self.all_unique_users = set()
        self.current_second_users = set()
        self.current_second_key = int(self.start_time)

    async def start(self):
        """Запускает фоновую задачу для очистки"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def add_user(self, user_id: int) -> None:
        """Добавляет пользователя в статистику"""
        async with self._lock:
            current_time = time.time()
            current_second = int(current_time)
            if current_second != self.current_second_key:
                if self.current_second_users:
                    self.users_per_second[self.current_second_key] = self.current_second_users.copy()
                self.current_second_key = current_second
                self.current_second_users = set()
            self.current_second_users.add(user_id)
            self.all_unique_users.add(user_id)

    async def _periodic_cleanup(self) -> None:
        """Фоновая задача для очистки старых данных"""
        try:
            while True:
                await asyncio.sleep(60)
                await self._cleanup_old_data()
        except asyncio.CancelledError:
            pass

    async def _cleanup_old_data(self) -> None:
        """Очистка данных старше 1 часа"""
        async with self._lock:
            current_second = int(time.time())
            one_hour_ago = current_second - 3600
            keys_to_delete = [
                timestamp for timestamp in self.users_per_second.keys()
                if timestamp < one_hour_ago
            ]
            for key in keys_to_delete:
                del self.users_per_second[key]

    async def shutdown(self):
        """Завершение работы"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

# Глобальные экземпляры
user_rps_counter = UserRPSCounter()
timer_manager = TimerManager()

async def set_user_offline_timer(user_id: int) -> None:
    """Устанавливает таймер на 15 минут для перевода пользователя в оффлайн"""
    async def offline_callback(uid: int):
        try:
            pool = get_db_pool()  # ← ИСПРАВЛЕНО: БЕЗ await!
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET last_activity = $1 WHERE user_id = $2",
                    datetime.now(MOSCOW_TZ).isoformat(),
                    uid
                )
        except Exception as e:
            logger.error(f"Ошибка в колбэке оффлайн таймера для {uid}: {e}")
    await timer_manager.set_timer(user_id, offline_callback, 900)

class UpdateChatUserMiddleware(BaseMiddleware):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_startup(self):
        """Метод для запуска при старте бота"""
        await user_rps_counter.start()

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        try:
            if isinstance(event, ChatMemberUpdated):
                return await self.handle_chat_member_updated(event)
            return await self.handle_regular_event(handler, event, data)
        except Exception as e:
            logger.error(f"Критическая ошибка в UpdateChatUserMiddleware: {e}", exc_info=True)
            return "error"

    async def handle_chat_member_updated(self, event: ChatMemberUpdated) -> str:
        """Обработка событий обновления участника чата"""
        try:
            if event.new_chat_member.user.is_bot:
                return "ok"
            user = event.new_chat_member.user
            user_id = user.id
            asyncio.create_task(user_rps_counter.add_user(user_id))
            name = clean_name(user.first_name) if user.first_name else "Без имени"
            username = user.username if user.username else None
            await self.update_basic_user_data(
                user_id=user_id,
                name=name,
                username=username,
                chat=event.chat
            )
            await self.process_chat_member_update(event)
            return "ok"
        except Exception as e:
            logger.error(f"Ошибка при обработке ChatMemberUpdated: {e}", exc_info=True)
            return "error"

    async def handle_regular_event(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        """Обработка обычных событий"""
        user_info = await self.extract_user_info(event)
        if not user_info:
            return await handler(event, data)
        user_id, name, username, chat, chat_id = user_info
        asyncio.create_task(user_rps_counter.add_user(user_id))
        is_ignored = await self.is_user_ignored(user_id)
        await self.update_basic_user_data(user_id, name, username, chat, is_ignored)
        if is_ignored:
            return await self.handle_ignored_user(event, user_id)
        await self.update_additional_stats(user_id, chat)
        result = await handler(event, data)
        return "ok"

    async def update_basic_user_data(self, user_id: int, name: str, username: str, chat: Any):
        """Обновляет данные пользователя — максимально быстро и без лишних запросов."""
        try:
            pool = get_db_pool()
            async with pool.acquire() as conn:
                now = datetime.now(MOSCOW_TZ).isoformat()

                # 1. Одно атомарное обновление данных (name, username + last_activity)
                # ON CONFLICT делает всё за 1 запрос вместо SELECT+UPDATE/INSERT
                await conn.execute('''
                    INSERT INTO users (user_id, name, username, first_seen, last_activity)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    username = EXCLUDED.username,
                    last_activity = EXCLUDED.last_activity
                ''', user_id, name, username, now, now)

                # 2. Привязка к чату (только если это группа)
                if chat and hasattr(chat, 'type') and chat.type != 'private':
                    await conn.execute('''
                        INSERT INTO users_chats (chat_id, user_id)
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id, user_id) DO NOTHING
                    ''', chat.id, user_id)

                    # 3. Умное обновление инфо о чате (оставляем, как было, оно полезно)
                    await self.update_chat_info_smart(conn, chat)

        except Exception as e:
            logger.error(f"Ошибка при обновлении данных пользователя {user_id}: {e}", exc_info=True)

    async def update_chat_info_smart(self, conn, chat) -> bool:
        """
        Умное обновление информации о чате.
        Обновляет данные только раз в день для каждого чата.
        """
        try:
            chat_id = chat.id
            current_time = datetime.now(MOSCOW_TZ)  # ← ИСПРАВЛЕНО: не utcnow!

            chat_record = await conn.fetchrow(
                '''SELECT chat_title, chat_username, invite_link, 
                          invite_link_updated_at, owner_id 
                   FROM chats WHERE chat_id = $1''',
                chat_id
            )

            needs_update = False
            if not chat_record:
                needs_update = True
            else:
                if chat_record['chat_title'] != chat.title or chat_record['chat_username'] != chat.username:
                    needs_update = True
                else:
                    last_update = chat_record['invite_link_updated_at']
                    if last_update:
                        last_update_dt = datetime.fromisoformat(last_update)
                        if last_update_dt.tzinfo is None:
                            last_update_dt = last_update_dt.replace(tzinfo=pytz.UTC)
                        last_update_dt = last_update_dt.astimezone(MOSCOW_TZ)
                        hours_since_update = (current_time - last_update_dt).total_seconds() / 3600
                        if hours_since_update >= 24:
                            should_update_now = self._should_update_now(chat_id, current_time)
                            if should_update_now:
                                needs_update = True
                    else:
                        should_update_now = self._should_update_now(chat_id, current_time)
                        if should_update_now:
                            needs_update = True

            if not needs_update:
                return False

            owner_id = None
            try:
                admins = await self.bot.get_chat_administrators(chat_id)
                chat_owner = next((admin for admin in admins if admin.status == 'creator'), None)
                if chat_owner:
                    owner_id = chat_owner.user.id
            except Exception as e:
                logger.error(f"Не удалось получить владельца чата {chat_id}: {e}")

            invite_link = None
            try:
                invite_link = await self.bot.export_chat_invite_link(chat_id)
            except Exception as e:
                logger.error(f"Не удалось получить инвайт-ссылку для чата {chat_id}: {e}")

            if chat_record:
                await conn.execute('''
                    UPDATE chats SET
                        chat_title = $1,
                        chat_username = $2,
                        invite_link = COALESCE($3, invite_link),
                        invite_link_updated_at = $4,
                        owner_id = COALESCE($5, owner_id)
                    WHERE chat_id = $6
                ''', chat.title, chat.username, invite_link,
                                   current_time.isoformat(), owner_id, chat_id)
            else:
                await conn.execute('''
                    INSERT INTO chats (
                        chat_id, chat_title, chat_username, invite_link, 
                        invite_link_updated_at, owner_id, bot_chat_status, number_for_inputs
                    ) VALUES ($1, $2, $3, $4, $5, $6, 'unknown', 1)
                ''', chat_id, chat.title, chat.username, invite_link,
                                   current_time.isoformat(), owner_id)
            return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении информации о чате {chat.id}: {e}", exc_info=True)
            return False

    def _should_update_now(self, chat_id: int, current_time: datetime) -> bool:
        """
        Определяет, нужно ли обновлять чат СЕЙЧАС на основе детерминированного хеша.
        Гарантирует равномерное распределение обновлений в течение дня.
        """
        date_str = current_time.strftime("%Y-%m-%d")
        hash_input = f"{chat_id}_{date_str}"
        hash_obj = hashlib.md5(hash_input.encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        hour_to_update = hash_int % 24
        return current_time.hour == hour_to_update

    async def process_chat_member_update(self, event: ChatMemberUpdated):
        """Обработка обновления статуса участника чата"""
        try:
            old_status = event.old_chat_member.status
            new_status = event.new_chat_member.status
            user = event.new_chat_member.user
            is_join = False
            is_leave = False
            if (user in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and
                    new_status == ChatMemberStatus.MEMBER):
                is_join = True
            elif (user == ChatMemberStatus.MEMBER and
                  new_status == ChatMemberStatus.LEFT):
                is_leave = True
            elif (user in [ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED,
                                 ChatMemberStatus.ADMINISTRATOR] and
                  new_status == ChatMemberStatus.KICKED):
                is_leave = True
            elif user == ChatMemberStatus.RESTRICTED and new_status == ChatMemberStatus.RESTRICTED:
                old_is_member = getattr(event.old_chat_member, 'is_member', False)
                new_is_member = getattr(event.new_chat_member, 'is_member', False)
                if old_is_member and not new_is_member:
                    is_leave = True
                elif not old_is_member and new_is_member:
                    is_join = True
            if is_join:
                await handle_join(event)
            elif is_leave:
                await handle_leave(event)
        except Exception as e:
            logger.error(f"Ошибка при обработке обновления статуса участника: {e}", exc_info=True)

    async def handle_ignored_user(self, event: Update, user_id: int) -> Any:
        """Обрабатывает игнорируемого пользователя"""
        try:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(cache_time=3600)
                except Exception:
                    pass
            return "ok"
        except Exception as e:
            logger.error(f"Ошибка при обработке игнорируемого пользователя {user_id}: {e}")
            return "error"

    async def extract_user_info(self, event: Update) -> Optional[tuple]:
        """Извлекает информацию о пользователе"""
        try:
            user = None
            chat = None
            if isinstance(event, Message):
                user = event.from_user
                chat = event.chat
            elif isinstance(event, CallbackQuery):
                user = event.from_user
                if event.message:
                    chat = event.message.chat
            elif isinstance(event, InlineQuery):
                user = event.from_user
            else:
                if event.message:
                    user = event.message.from_user
                    chat = event.message.chat
                elif event.callback_query:
                    user = event.callback_query.from_user
                    if event.callback_query.message:
                        chat = event.callback_query.message.chat
                elif event.my_chat_member:
                    user = event.my_chat_member.from_user
                    chat = event.my_chat_member.chat
                elif event.chat_member:
                    user = event.chat_member.from_user
                    chat = event.chat_member.chat
                elif event.chat_join_request:
                    user = event.chat_join_request.from_user
                    chat = event.chat_join_request.chat
            if not user or not hasattr(user, 'id'):
                return None
            name = clean_name(user.first_name) if user.first_name else "Без имени"
            username = user.username if user.username else None
            chat_id = chat.id if chat else None
            return (user.id, name, username, chat, chat_id)
        except Exception as e:
            event_type = type(event).__name__
            logger.error(f"Ошибка при извлечении информации о пользователе из {event_type}: {e}")
            return None

    async def is_user_ignored(self, user_id: int) -> bool:
        """Проверяет, находится ли пользователь в списке игнора"""
        try:
            pool = get_db_pool()  # ← ИСПРАВЛЕНО: БЕЗ await!
            async with pool.acquire() as conn:
                result = await conn.fetchval(
                    'SELECT 1 FROM ignore_users WHERE user_id = $1',
                    user_id
                )
                return result is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке игнора пользователя {user_id}: {e}")
            return False

    async def update_additional_stats(self, user_id: int, chat: Any):
        """Обновляет дополнительную статистику"""
        try:
            if chat and hasattr(chat, 'type') and chat.type != 'private':
                await increment_message(chat.id, user_id)
                await check_and_add_user_rang(user_id, chat.id)
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики для пользователя {user_id}: {e}")

    async def shutdown(self):
        """Завершение работы"""
        await timer_manager.cleanup()
        await user_rps_counter.shutdown()

class PerformanceMonitoringMiddleware(BaseMiddleware):
    """Middleware для мониторинга производительности"""
    def __init__(self, alert_threshold: float = 1.0):
        super().__init__()
        self.alert_threshold = alert_threshold
        self.slow_handlers = {}

    async def __call__(self, handler, event: Update, data: dict):
        start_time = time.time()
        try:
            result = await handler(event, data)
            return result
        finally:
            processing_time = time.time() - start_time
            if processing_time > self.alert_threshold:
                event_type = type(event).__name__
                handler_name = handler.__name__ if hasattr(handler, '__name__') else 'unknown'
                logger.warning(
                    f"⏱️ SLOW PROCESSING: {processing_time:.3f}s "
                    f"for {event_type} (handler: {handler_name}, update_id: {event.update_id})"
                )
                key = f"{event_type}_{handler_name}"
                if key not in self.slow_handlers:
                    self.slow_handlers[key] = {
                        'count': 0,
                        'total_time': 0,
                        'max_time': 0
                    }
                stats = self.slow_handlers[key]
                stats['count'] += 1
                stats['total_time'] += processing_time
                stats['max_time'] = max(stats['max_time'], processing_time)
                if stats['count'] % 10 == 0:
                    avg_time = stats['total_time'] / stats['count']
                    logger.warning(
                        f"📊 SLOW STATS for {key}: "
                        f"count={stats['count']}, avg={avg_time:.3f}s, max={stats['max_time']:.3f}s"
                    )
            elif logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Update {event.update_id} processed in {processing_time:.3f}s")