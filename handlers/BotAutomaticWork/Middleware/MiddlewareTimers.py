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
        # === ДЛЯ ПАКЕТНОЙ ОБРАБОТКИ КАЖДЫЕ 7 СЕКУНД ===
        self._batch_update_queue = {}  # user_id -> timestamp
        self._last_batch_update = 0
        self._batch_processing_task = None
        self.BATCH_UPDATE_INTERVAL = 7.0  # каждые 7 секунд
        self.BATCH_UPDATE_SIZE = 100
        # ===========================================

    async def start_batch_processing(self):
        """Запустить фоновую задачу пакетной обработки"""
        if self._batch_processing_task is None or self._batch_processing_task.done():
            self._batch_processing_task = asyncio.create_task(self._batch_processing_loop())
            logger.debug("🔄 Запущена фоновая пакетная обработка таймеров каждые 7 секунд")

    async def stop_batch_processing(self):
        """Остановить фоновую задачу пакетной обработки"""
        if self._batch_processing_task and not self._batch_processing_task.done():
            self._batch_processing_task.cancel()
            try:
                await self._batch_processing_task
            except asyncio.CancelledError:
                pass
            self._batch_processing_task = None

        # Обработать оставшиеся данные в очереди
        if self._batch_update_queue:
            await self._process_batch_update()

    async def _batch_processing_loop(self):
        """Цикл для пакетной обработки каждые 7 секунд"""
        try:
            while True:
                await asyncio.sleep(self.BATCH_UPDATE_INTERVAL)
                current_time = time.time()
                await self._process_batch_update()
                self._last_batch_update = current_time
        except asyncio.CancelledError:
            logger.debug("⏹ Цикл пакетной обработки таймеров остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле пакетной обработки: {e}")

    async def _process_batch_update(self):
        """Обработка пакета пользователей каждые 7 секунд"""
        if not self._batch_update_queue:
            return

        logger.debug(f"📦 Пакетное обновление активности для {len(self._batch_update_queue)} пользователей")

        # Создаем копию данных и очищаем очередь
        users_to_update = list(self._batch_update_queue.keys())

        try:
            # Фильтруем только числовые ID пользователей
            numeric_user_ids = [user_id for user_id in users_to_update if isinstance(user_id, int)]
            if not numeric_user_ids:
                logger.warning("⚠️ Нет корректных user_id для пакетного обновления")
                self._batch_update_queue.clear()
                return

            pool = get_db_pool()
            async with pool.acquire() as conn:
                now = datetime.now(MOSCOW_TZ).isoformat()

                # Массовое обновление в одной транзакции
                await conn.execute('''
                UPDATE users
                SET last_activity = $1
                WHERE user_id = ANY($2::bigint[])
                ''', now, numeric_user_ids)

                logger.debug(
                    f"✅ Пакетное обновление активности завершено для {len(numeric_user_ids)}/{len(users_to_update)} пользователей")

        except Exception as e:
            logger.error(f"❌ Ошибка при пакетном обновлении: {e}")
        finally:
            # Очищаем очередь
            self._batch_update_queue.clear()

    async def update_user_activity(self, user_id: int) -> bool:
        """Обновить активность пользователя с использованием пакетной обработки"""
        # Явная проверка на целое число
        if not isinstance(user_id, int):
            logger.debug(f"⚠️ Пропущен нечисловой user_id: {user_id} (тип: {type(user_id).__name__})")
            return False

        async with self._lock:
            # Добавляем пользователя в очередь пакетного обновления
            self._batch_update_queue[user_id] = time.time()

            # Отменяем старый таймер если есть
            if user_id in self.timers:
                old_task = self.timers[user_id]
                old_task.cancel()
                del self.timers[user_id]

            # Запускаем фоновую задачу если еще не запущена
            if self._batch_processing_task is None or self._batch_processing_task.done():
                await self.start_batch_processing()

            # Устанавливаем новый таймер
            await self._set_offline_timer(user_id, self.STATUS_OFFLINE_DELAY)

            # Кэшируем время обновления
            self.last_update_cache[user_id] = time.time()

            # Если очередь большая, обрабатываем досрочно
            if len(self._batch_update_queue) >= self.BATCH_UPDATE_SIZE:
                await self._process_batch_update()
                self._last_batch_update = time.time()

            return True

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
            self._batch_update_queue.clear()


timer_manager = TimerManager()


async def update_user_activity(user_id: int):
    """Немедленно обновить активность пользователя"""
    return await timer_manager.update_user_activity(user_id)