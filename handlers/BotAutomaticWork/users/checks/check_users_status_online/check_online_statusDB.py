import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import OrderedDict
import asyncio
import pytz

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


class BoundedPresenceCache:
    def __init__(self, maxsize: int = 50000, ttl_minutes: int = 15):
        self.cache: OrderedDict[int, datetime] = OrderedDict()
        self.maxsize = maxsize
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = asyncio.Lock()

    async def set(self, user_id: int, dt: datetime):
        """Записать пользователя в горячий кэш (O(1))"""
        async with self.lock:
            if user_id in self.cache:
                self.cache.move_to_end(user_id)
            self.cache[user_id] = dt

            # Жесткий лимит: если кэш раздувается, удаляем самого неактивного
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    async def get(self, user_id: int) -> Optional[datetime]:
        """Получить статус из кэша с проверкой на протухание (O(1))"""
        async with self.lock:
            if user_id not in self.cache:
                return None

            dt = self.cache[user_id]
            # Самоочистка по времени (TTL)
            if datetime.now(MOSCOW_TZ) - dt > self.ttl:
                del self.cache[user_id]
                return None

            # Передвигаем в конец очереди как самого свежего
            self.cache.move_to_end(user_id)
            return dt

    async def force_cleanup(self):
        """Фоновый метод для полной очистки протухших записей"""
        async with self.lock:
            now = datetime.now(MOSCOW_TZ)
            expired_keys = []
            for user_id, dt in self.cache.items():
                if now - dt > self.ttl:
                    expired_keys.append(user_id)
                else:
                    break  # Элементы упорядочены, дальше идут свежие

            for user_id in expired_keys:
                del self.cache[user_id]


# Инициализируем кэш внутри модуля
_presence_cache = BoundedPresenceCache(maxsize=50000, ttl_minutes=15)


async def get_user_activity(user_id: int) -> Optional[datetime]:
    """Получает время последней активности пользователя"""
    try:
        user_id = int(user_id)

        # 1. Проверяем быстрый локальный кэш
        cached_dt = await _presence_cache.get(user_id)
        if cached_dt:
            return cached_dt

        # 2. Холодный контур: если в кэше нет, идем в PostgreSQL
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT last_activity FROM users WHERE user_id = $1',
                user_id
            )
            if row and row['last_activity']:
                dt = row['last_activity']
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt)
                if dt.tzinfo is None:
                    dt = MOSCOW_TZ.localize(dt)

                # Закидываем в кэш, чтобы не дергать базу при следующем рендере
                await _presence_cache.set(user_id, dt)
                return dt
            return None

    except Exception as e:
        logger.error(f"Ошибка в get_user_activity: {e}", exc_info=True)
        return None


async def track_user_online_instant(user_id: int):
    """Метод для мгновенного обновления статуса в памяти (вызывать при входящем сообщении)"""
    try:
        await _presence_cache.set(int(user_id), datetime.now(MOSCOW_TZ))
    except Exception as e:
        logger.error(f"Ошибка в track_user_online_instant: {e}")


async def presence_cleanup_task_loop():
    while True:
        try:
            await asyncio.sleep(60)
            # ИСПРАВЛЕНО: Вызываем асинхронный метод напрямую через await.
            # Память очищается мгновенно, бот не зависнет.
            await _presence_cache.force_cleanup()
        except Exception as e:
            logger.error(f"Ошибка в цикле очистки кэша: {e}")