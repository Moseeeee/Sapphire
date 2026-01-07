
import logging
from typing import Optional, List, Tuple

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def get_captcha_settings(chat_id: int) -> Tuple[str, str, int, bool]:
    """Получить настройки капчи для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT time_limit, difficulty, attempts_limit, enabled 
                FROM captcha_settings 
                WHERE chat_id = $1
                ''',
                chat_id
            )
            if row:
                return (row['time_limit'], row['difficulty'], row['attempts_limit'], row['enabled'])
    except Exception as e:
        logger.error(e, exc_info=True)

    return '5 минут', 'средняя', 3, False


async def update_captcha_settings(
    chat_id: int,
    time_limit: Optional[str] = None,
    difficulty: Optional[str] = None,
    attempts_limit: Optional[int] = None,
    enabled: Optional[bool] = None
) -> None:
    """Обновить настройки капчи (UPSERT)."""
    try:
        # Получаем текущие настройки
        current_time, current_difficulty, current_attempts, current_enabled = await get_captcha_settings(chat_id)

        new_time = time_limit if time_limit is not None else current_time
        new_difficulty = difficulty if difficulty is not None else current_difficulty
        new_attempts = attempts_limit if attempts_limit is not None else current_attempts
        new_enabled = enabled if enabled is not None else current_enabled

        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO captcha_settings (chat_id, time_limit, difficulty, attempts_limit, enabled)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (chat_id) DO UPDATE SET
                    time_limit = EXCLUDED.time_limit,
                    difficulty = EXCLUDED.difficulty,
                    attempts_limit = EXCLUDED.attempts_limit,
                    enabled = EXCLUDED.enabled
                ''',
                chat_id, new_time, new_difficulty, new_attempts, new_enabled
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def enable_captcha(chat_id: int, difficulty: str = 'средняя') -> None:
    """Включить капчу в чате."""
    await update_captcha_settings(chat_id, difficulty=difficulty, enabled=True)


async def disable_captcha(chat_id: int) -> None:
    """Выключить капчу в чате."""
    await update_captcha_settings(chat_id, enabled=False)


async def is_captcha_enabled(chat_id: int) -> bool:
    """Проверить, включена ли капча в чате."""
    _, _, _, enabled = await get_captcha_settings(chat_id)
    return enabled


async def add_captcha_history(
    chat_id: int,
    user_id: int,
    captcha_type: str,
    difficulty: str,
    success: bool,
    time_taken: int
) -> None:
    """Добавить запись в историю капчи."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO captcha_history (chat_id, user_id, captcha_type, difficulty, success, time_taken)
                VALUES ($1, $2, $3, $4, $5, $6)
                ''',
                chat_id, user_id, captcha_type, difficulty, success, time_taken
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_user_captcha_history(
    chat_id: int,
    user_id: int,
    limit: int = 10,
    offset: int = 0
) -> List[Tuple]:
    """Получить историю капчи пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT captcha_type, difficulty, success, time_taken, timestamp 
                FROM captcha_history 
                WHERE chat_id = $1 AND user_id = $2
                ORDER BY timestamp DESC
                LIMIT $3 OFFSET $4
                ''',
                chat_id, user_id, limit, offset
            )
            return [(row['captcha_type'], row['difficulty'], row['success'], row['time_taken'], row['timestamp']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_user_captcha_stats(chat_id: int, user_id: int) -> Tuple[int, int, float]:
    """Получить статистику пользователя по капче."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count
                FROM captcha_history 
                WHERE chat_id = $1 AND user_id = $2
                ''',
                chat_id, user_id
            )
            if row and row['total'] > 0:
                total = row['total']
                success_count = row['success_count'] or 0
                success_rate = (success_count / total) * 100
                return total, success_count, success_rate
            return 0, 0, 0.0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0, 0, 0.0


async def get_all_captcha_users(chat_id: int, limit: int = 10, offset: int = 0) -> List[Tuple]:
    """Получить всех пользователей, проходивших капчу в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT DISTINCT user_id 
                FROM captcha_history 
                WHERE chat_id = $1
                ORDER BY (SELECT MAX(timestamp) FROM captcha_history ch2 WHERE ch2.user_id = captcha_history.user_id AND ch2.chat_id = $1) DESC
                LIMIT $2 OFFSET $3
                ''',
                chat_id, limit, offset
            )
            return [(row['user_id'],) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_total_captcha_users_count(chat_id: int) -> int:
    """Получить общее количество пользователей, проходивших капчу."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                'SELECT COUNT(DISTINCT user_id) FROM captcha_history WHERE chat_id = $1',
                chat_id
            )
            return count or 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_user_recent_captcha(chat_id: int, user_id: int) -> Optional[Tuple]:
    """Получить последнюю капчу пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT difficulty, time_taken, timestamp, success
                FROM captcha_history 
                WHERE chat_id = $1 AND user_id = $2 
                ORDER BY timestamp DESC 
                LIMIT 1
                ''',
                chat_id, user_id
            )
            if row:
                return (row['difficulty'], row['time_taken'], row['timestamp'], row['success'])
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_user_last_successful_captcha(chat_id: int, user_id: int) -> Optional[Tuple]:
    """Получить последнюю УСПЕШНУЮ капчу пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT difficulty, time_taken, timestamp
                FROM captcha_history 
                WHERE chat_id = $1 AND user_id = $2 AND success = true
                ORDER BY timestamp DESC 
                LIMIT 1
                ''',
                chat_id, user_id
            )
            if row:
                return (row['difficulty'], row['time_taken'], row['timestamp'])
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None