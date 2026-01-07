from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, \
    memory_cache
import logging
from datetime import datetime

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


@auto_cache_update('users', 'user_id')
async def add_user(user_id: int, name: str, username: str | None) -> None:
    """Добавляет пользователя с временем первой и последней активности."""
    try:
        current_time = datetime.now().isoformat()
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO users (user_id, name, username, first_seen, last_activity)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    username = EXCLUDED.username,
                    last_activity = EXCLUDED.last_activity
                ''',
                user_id, name, username, current_time, current_time
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_user(user_id: int) -> bool:
    """Проверяет наличие пользователя в кэше."""
    cache_key = f"users_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            return True

    # Если нет в кэше, проверяем в БД
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                'SELECT 1 FROM users WHERE user_id = $1',
                user_id
            )
            return exists is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def check_user_full(user_id: int) -> int | None:
    """Получает полную информацию о пользователе (с кэшированием)."""
    cache_key = f"users_{user_id}"

    # Проверка кэша
    async with cache_lock:
        if cache_key in memory_cache:
            return memory_cache[cache_key].get('user_id')

    # Запрос к БД
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id, name, username, first_seen FROM users WHERE user_id = $1',
                user_id
            )
            if row:
                user_data = {
                    'user_id': row['user_id'],
                    'name': row['name'],
                    'username': row['username'],
                    'first_seen': row['first_seen']
                }
                async with cache_lock:
                    memory_cache[cache_key] = user_data
                return row['user_id']
    except Exception as e:
        logger.error(e, exc_info=True)

    return None


@auto_cache_update('users', 'user_id')
async def update_user(user_id: int, name: str, username: str | None) -> None:
    """Обновляет данные пользователя и время последней активности."""
    try:
        current_time = datetime.now().isoformat()
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                UPDATE users 
                SET name = $1, username = $2, last_activity = $3 
                WHERE user_id = $4
                ''',
                name, username, current_time, user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


@auto_cache_update('users', 'user_id')
async def update_user_activity(user_id: int) -> None:
    """Обновляет время последней активности пользователя."""
    try:
        current_time = datetime.now().isoformat()
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET last_activity = $1 WHERE user_id = $2',
                current_time, user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_user_full_data(user_id: int) -> dict | None:
    """Получает полную информацию о пользователе из кэша или БД."""
    cache_key = f"users_{user_id}"

    # Проверка кэша
    #async with cache_lock:
    #   if cache_key in memory_cache:
    #       return memory_cache[cache_key]

    # Запрос к БД
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id, name, username, first_seen, gender FROM users WHERE user_id = $1',
                user_id
            )
            if row:
                user_data = {
                    'user_id': row['user_id'],
                    'name': row['name'],
                    'username': row['username'],
                    'first_seen': row['first_seen'],
                    'gender': row['gender'] if row['gender'] else 'оно'
                }
                #async with cache_lock:
                 #   memory_cache[cache_key] = user_data

                return user_data
    except Exception as e:
        logger.error(e, exc_info=True)

    return None


async def get_user_first_seen(user_id: int) -> datetime | None:
    """Получает время первого появления пользователя."""
    try:
        user_data = await get_user_full_data(user_id)
        if user_data and user_data.get('first_seen'):
            first_seen = user_data['first_seen']
            # Если это строка, преобразуем в datetime
            if isinstance(first_seen, str):
                return datetime.fromisoformat(first_seen)
            return first_seen
    except Exception as e:
        logger.error(e, exc_info=True)
    return None