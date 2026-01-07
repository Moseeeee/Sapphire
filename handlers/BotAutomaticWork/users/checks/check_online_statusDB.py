import logging
from datetime import datetime
from typing import Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import cache_lock, memory_cache
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool


logger = logging.getLogger(__name__)



async def get_user_activity(user_id: int) -> Optional[str]:
    """Получает время последней активности пользователя."""
    try:
        # Сначала проверяем кэш
        cache_key = f"users_{user_id}"
        async with cache_lock:
            if cache_key in memory_cache:
                return memory_cache[cache_key].get('last_activity')

        # Если нет в кэше, запрашиваем из БД
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT last_activity FROM users WHERE user_id = $1',
                user_id
            )
            return row['last_activity'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None