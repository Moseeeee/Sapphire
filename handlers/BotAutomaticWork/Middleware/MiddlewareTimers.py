import asyncio
import logging
from datetime import datetime
import pytz
from collections import OrderedDict
import time
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


class TimerManager:
    def __init__(self, max_timers: int = 10000):
        self.timers = OrderedDict()
        self.max_timers = max_timers
        self._lock = asyncio.Lock()
        self.last_update_cache = {}  # Кэш последнего обновления статуса
        self.STATUS_OFFLINE_DELAY = 900.0

    async def update_user_activity(self, user_id: int) -> bool:
        """Сразу обновить активность пользователя и сбросить таймер"""
        async with self._lock:
            # Сразу обновляем в БД
            await self._update_activity_in_db(user_id)

            # Отменяем старый таймер если есть
            if user_id in self.timers:
                old_task = self.timers[user_id]
                old_task.cancel()
                del self.timers[user_id]


            await self._set_offline_timer(user_id, self.STATUS_OFFLINE_DELAY)

            # Кэшируем время обновления
            self.last_update_cache[user_id] = time.time()

            logger.debug(f"✅ Updated activity for user {user_id}")
            return True

    async def _update_activity_in_db(self, user_id: int):
        """Немедленно обновить активность в БД"""
        try:
            pool = get_db_pool()
            async with pool.acquire() as conn:
                now = datetime.now(MOSCOW_TZ).isoformat()
                await conn.execute(
                    "UPDATE users SET last_activity = $1 WHERE user_id = $2",
                    now,
                    user_id
                )
        except Exception as e:
            logger.error(f"❌ Error updating activity for {user_id}: {e}")

    async def _set_offline_timer(self, user_id: int, delay: float):
        """Установить таймер оффлайн"""

        async def timer_task():
            try:
                await asyncio.sleep(delay)
                await self._mark_user_offline(user_id)
            except asyncio.CancelledError:
                logger.debug(f"Timer cancelled for user {user_id}")
            finally:
                async with self._lock:
                    if user_id in self.timers:
                        del self.timers[user_id]
                    self.last_update_cache.pop(user_id, None)

        task = asyncio.create_task(timer_task())
        self.timers[user_id] = task
        self.timers.move_to_end(user_id, last=True)  # Перемещаем в конец как самый свежий

    async def _mark_user_offline(self, user_id: int):
        """Пометить пользователя как оффлайн"""
        try:
            # Здесь можно логировать изменение статуса если нужно
            logger.debug(f"⏱️ User {user_id} marked as offline")
            # Не обновляем БД повторно - активность уже обновлена
        except Exception as e:
            logger.error(f"❌ Error marking user offline {user_id}: {e}")

    async def cancel_timer(self, user_id: int):
        """Отменить таймер"""
        async with self._lock:
            if user_id in self.timers:
                task = self.timers[user_id]
                task.cancel()
                del self.timers[user_id]
                self.last_update_cache.pop(user_id, None)
                logger.debug(f"⏱️ Timer cancelled for user {user_id}")

    async def _cleanup_old_timers(self):
        """Очистить 10% самых старых таймеров"""
        if len(self.timers) < self.max_timers:
            return

        cleanup_count = max(1, len(self.timers) // 10)
        logger.warning(f"⏱️ Cleaning up {cleanup_count} old timers")

        for _ in range(cleanup_count):
            if self.timers:
                user_id, task = next(iter(self.timers.items()))
                task.cancel()
                del self.timers[user_id]
                self.last_update_cache.pop(user_id, None)

    async def get_active_timers_count(self):
        """Получить количество активных таймеров"""
        async with self._lock:
            return len(self.timers)

    async def cleanup(self):
        """Полная очистка всех таймеров"""
        async with self._lock:
            logger.info(f"⏱️ Cleaning up {len(self.timers)} timers")
            for user_id, task in self.timers.items():
                task.cancel()
            self.timers.clear()
            self.last_update_cache.clear()


timer_manager = TimerManager()


async def update_user_activity(user_id: int):
    """Немедленно обновить активность пользователя"""
    return await timer_manager.update_user_activity(user_id)