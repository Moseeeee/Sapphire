import logging
from typing import Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import cache_lock, memory_cache
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool


logger = logging.getLogger(__name__)

async def search_username(user_id: int) -> Optional[str]:
    """Получает username по user_id (с кэшированием)."""
    cache_key = f"users_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            username = memory_cache[cache_key].get('username')
            if username is not None:
                return username

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT username FROM users WHERE user_id = $1',
                user_id
            )
            username = row['username'] if row else None

        async with cache_lock:
            memory_cache.setdefault(cache_key, {})['username'] = username

        return username

    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def user_exists_in_db(user_id: int) -> bool:
    """Проверяет, существует ли пользователь в БД."""
    cache_key = f"users_{user_id}"

    async with cache_lock:
        if cache_key in memory_cache:
            return True

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM users WHERE user_id = $1)',
                user_id
            )

        if exists:
            async with cache_lock:
                memory_cache[cache_key] = {'user_id': user_id}

        return exists

    except Exception as e:
        logger.error(e, exc_info=True)
        return False
