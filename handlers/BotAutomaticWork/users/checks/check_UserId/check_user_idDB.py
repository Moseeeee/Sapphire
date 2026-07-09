from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import cache_lock, memory_cache
import logging

from typing import Optional
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def check_username(username: str) -> Optional[int]:
    """Получает user_id по username (с кэшированием)."""
    if not username:
        return None

    cache_key = f"username_{username}"
    async with cache_lock:
        if cache_key in memory_cache:
            user_id = memory_cache[cache_key].get('user_id')
            if user_id is not None:
                logger.debug("✅ Кэш: username -> user_id")
                return user_id

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id FROM users WHERE username = $1',
                username
            )
            user_id = row['user_id'] if row else None

        async with cache_lock:
            memory_cache[cache_key] = {'user_id': user_id}

        logger.debug("✅ БД: username -> user_id")
        return user_id

    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def user_name(user_id: int) -> Optional[str]:
    """Получает имя пользователя по ID (с кэшированием)."""
    cache_key = f"users_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            name = memory_cache[cache_key].get('name')
            if name is not None:
                return name

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT name FROM users WHERE user_id = $1',
                user_id
            )
            name = row['name'] if row else None

        async with cache_lock:
            memory_cache.setdefault(cache_key, {})['name'] = name

        return name

    except Exception as e:
        logger.error(e, exc_info=True)
        return None