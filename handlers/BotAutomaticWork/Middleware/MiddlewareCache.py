import asyncio
import logging
from typing import Dict, Set, Optional
import time

logger = logging.getLogger(__name__)


class IgnoreCache:
    """Кэш игнорируемых пользователей с TTL и автоматическим обновлением"""

    def __init__(self, max_size: int = 50000, ttl_seconds: int = 3600):
        """
        Args:
            max_size: Максимальный размер кэша
            ttl_seconds: Время жизни записей в секундах
        """
        self.cache: Dict[int, tuple[bool, float]] = {}  # user_id -> (ignored, timestamp)
        self.lock = asyncio.Lock()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats = {
            'hits': 0,
            'misses': 0,
            'updates': 0,
            'cleanups': 0
        }

    async def start(self):
        """Запустить фоновую задачу очистки"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ IgnoreCache background cleanup started")

    async def stop(self):
        """Остановить фоновую задачу"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("🛑 IgnoreCache background cleanup stopped")

    async def is_ignored(self, user_id: int) -> bool:
        """Проверить игнор пользователя (с кэшированием)"""
        async with self.lock:
            if user_id in self.cache:
                ignored, timestamp = self.cache[user_id]
                # Проверяем TTL
                if time.time() - timestamp < self.ttl:
                    self._stats['hits'] += 1
                    return ignored
                else:
                    # Запись устарела, удаляем
                    del self.cache[user_id]

            self._stats['misses'] += 1
            return False

    async def update(self, user_id: int, ignored: bool, from_db: bool = False):
        """Обновить кэш игнора"""
        async with self.lock:
            # Если из БД - всегда обновляем, если из кэша - только если значение изменилось
            if from_db or user_id not in self.cache or self.cache[user_id][0] != ignored:
                self._add_to_cache(user_id, ignored)
                self._stats['updates'] += 1

    def _add_to_cache(self, user_id: int, ignored: bool):
        """Добавить/обновить запись в кэше"""
        # Если достигли лимита, удаляем самые старые записи
        if len(self.cache) >= self.max_size:
            self._remove_oldest(10)  # Удаляем 10% самых старых

        self.cache[user_id] = (ignored, time.time())

    def _remove_oldest(self, percent: int = 10):
        """Удалить старые записи из кэша"""
        if not self.cache:
            return

        # Сортируем по времени
        sorted_items = sorted(self.cache.items(), key=lambda x: x[1][1])
        remove_count = max(1, len(self.cache) * percent // 100)

        for i in range(remove_count):
            if i < len(sorted_items):
                user_id, _ = sorted_items[i]
                del self.cache[user_id]

        self._stats['cleanups'] += 1
        logger.debug(f"🧹 IgnoreCache: removed {remove_count} old entries")

    async def bulk_update(self, ignored_users: Set[int]):
        """Массовое обновление кэша из БД"""
        async with self.lock:
            current_time = time.time()
            updated_count = 0

            # Обновляем или добавляем игнорируемых пользователей
            for user_id in ignored_users:
                if user_id not in self.cache or not self.cache[user_id][0]:
                    self.cache[user_id] = (True, current_time)
                    updated_count += 1

            # Помечаем как неигнорируемых тех, кого нет в новом списке
            users_to_remove = []
            for user_id, (ignored, timestamp) in self.cache.items():
                if ignored and user_id not in ignored_users:
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                del self.cache[user_id]
                updated_count += 1

            if updated_count > 0:
                logger.info(f"🔄 IgnoreCache bulk update: {updated_count} records")

    async def remove(self, user_id: int):
        """Удалить пользователя из кэша"""
        async with self.lock:
            if user_id in self.cache:
                del self.cache[user_id]

    async def clear(self):
        """Полностью очистить кэш"""
        async with self.lock:
            self.cache.clear()
            logger.info("🧹 IgnoreCache cleared")

    async def _cleanup_loop(self):
        """Фоновая задача для очистки устаревших записей"""
        try:
            while True:
                await asyncio.sleep(self.ttl // 2)  # Очищаем каждые пол-TTL
                await self._cleanup_expired()
        except asyncio.CancelledError:
            pass

    async def _cleanup_expired(self):
        """Очистить устаревшие записи"""
        async with self.lock:
            current_time = time.time()
            expired_count = 0

            users_to_remove = []
            for user_id, (ignored, timestamp) in self.cache.items():
                if current_time - timestamp >= self.ttl:
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                del self.cache[user_id]
                expired_count += 1

            if expired_count > 0:
                logger.debug(f"🧹 IgnoreCache: cleaned {expired_count} expired entries")

    async def size(self) -> int:
        """Получить текущий размер кэша"""
        async with self.lock:
            return len(self.cache)

    async def get_stats(self) -> Dict:
        """Получить статистику кэша"""
        async with self.lock:
            hits = self._stats['hits']
            misses = self._stats['misses']
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0

            return {
                'size': len(self.cache),
                'hits': hits,
                'misses': misses,
                'hit_rate': round(hit_rate, 2),
                'updates': self._stats['updates'],
                'cleanups': self._stats['cleanups'],
                'max_size': self.max_size,
                'ttl': self.ttl
            }

    async def refresh_from_db(self):
        """Обновить кэш из базы данных"""
        try:
            from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

            pool = get_db_pool()
            async with pool.acquire() as conn:
                # Получаем всех игнорируемых пользователей
                rows = await conn.fetch("SELECT user_id FROM ignore_users")
                ignored_users = {row['user_id'] for row in rows}

                # Обновляем кэш
                await self.bulk_update(ignored_users)
                logger.info(f"🔄 IgnoreCache refreshed from DB: {len(ignored_users)} users")

        except Exception as e:
            logger.error(f"❌ Error refreshing ignore cache from DB: {e}")


# Глобальный экземпляр кэша
_ignore_cache = IgnoreCache()


# Публичные функции для обратной совместимости
async def is_user_ignored_cached(user_id: int) -> bool:
    return await _ignore_cache.is_ignored(user_id)


async def update_ignore_cache(user_id: int, ignored: bool):
    await _ignore_cache.update(user_id, ignored)


async def clear_ignore_cache():
    await _ignore_cache.clear()


async def get_ignore_cache_size() -> int:
    return await _ignore_cache.size()


async def init_ignore_cache():
    """Инициализировать кэш (вызывать при старте бота)"""
    await _ignore_cache.start()
    await _ignore_cache.refresh_from_db()
    logger.info("✅ IgnoreCache initialized")


async def shutdown_ignore_cache():
    """Остановить кэш (вызывать при остановке бота)"""
    await _ignore_cache.stop()


async def get_ignore_cache_stats():
    """Получить статистику кэша"""
    return await _ignore_cache.get_stats()