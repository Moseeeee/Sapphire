

import logging
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, \
    memory_cache
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


# -------------------------
# УПРАВЛЕНИЕ АНТИСПАМОМ
# -------------------------


async def add_to_anti_spam(user_id: int, agent_id: int, date_added: str, reason: str) -> None:
    """Добавляет пользователя в АС."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO anti_spam_users (user_id, agent_id, date_added, reason) VALUES ($1, $2, $3, $4)',
                user_id, agent_id, date_added, reason
            )
    except Exception as e:
        logger.error(e, exc_info=True)



async def remove_from_anti_spam(user_id: int, agent_id_removed: int, date_removed: str, reason: str) -> None:
    """Удаляет пользователя из АС и добавляет в историю."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем данные о добавлении
            row = await conn.fetchrow(
                'SELECT agent_id, date_added, reason FROM anti_spam_users WHERE user_id = $1',
                user_id
            )

            if row:
                agent_id_added = row['agent_id']
                date_added = row['date_added']
                add_reason = row['reason']

                # Добавляем в историю
                await conn.execute(
                    '''
                    INSERT INTO anti_spam_history 
                    (user_id, agent_id_added, agent_id_removed, date_added, date_removed, reason) 
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ''',
                    user_id, agent_id_added, agent_id_removed, date_added, date_removed, reason
                )

                # Удаляем из текущих
                await conn.execute(
                    'DELETE FROM anti_spam_users WHERE user_id = $1',
                    user_id
                )

    except Exception as e:
        logger.error(e, exc_info=True)


async def check_anti_spam(user_id: int) -> bool:

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id FROM anti_spam_users WHERE user_id = $1',
                user_id
            )
            is_in_as = row is not None


            return is_in_as
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def get_anti_spam_history(user_id: int, page: int = 1, limit: int = 10) -> tuple:
    """Возвращает историю АС пользователя с пагинацией."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Общее количество записей
            count_row = await conn.fetchrow(
                'SELECT COUNT(*) as total FROM anti_spam_history WHERE user_id = $1',
                user_id
            )
            total = count_row['total'] if count_row else 0

            # Записи для текущей страницы
            offset = (page - 1) * limit
            rows = await conn.fetch(
                '''
                SELECT user_id, agent_id_added, agent_id_removed, date_added, date_removed, reason 
                FROM anti_spam_history 
                WHERE user_id = $1 
                ORDER BY date_added DESC 
                LIMIT $2 OFFSET $3
                ''',
                user_id, limit, offset
            )

            history = [tuple(row.values()) for row in rows] if rows else []
            return history, total

    except Exception as e:
        logger.error(e, exc_info=True)
        return [], 0


async def get_anti_spam_info(user_id: int) -> dict | None:
    """Возвращает текущую информацию о пользователе в АС."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id, agent_id, date_added, reason FROM anti_spam_users WHERE user_id = $1',
                user_id
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_all_anti_spam_users(page: int = 1, limit: int = 10) -> tuple:
    """Возвращает всех пользователей в АС с пагинацией."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Общее количество
            count_row = await conn.fetchrow('SELECT COUNT(*) as total FROM anti_spam_users')
            total = count_row['total'] if count_row else 0

            # Записи для текущей страницы
            offset = (page - 1) * limit
            rows = await conn.fetch(
                'SELECT user_id, agent_id, date_added, reason FROM anti_spam_users ORDER BY date_added DESC LIMIT $1 OFFSET $2',
                limit, offset
            )

            users = [tuple(row.values()) for row in rows] if rows else []
            return users, total

    except Exception as e:
        logger.error(e, exc_info=True)
        return [], 0