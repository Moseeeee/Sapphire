
import logging
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.usersDB import get_user_full_data

logger = logging.getLogger(__name__)

@auto_cache_update('users', 'user_id')
async def update_user_gender(user_id: int, gender: str) -> None:
    """Обновляет пол пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET gender = $1 WHERE user_id = $2',
                gender, user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_user_gender(user_id: int) -> str:
    """Получает пол пользователя."""
    try:
        user_data = await get_user_full_data(user_id)
        if user_data and user_data.get('gender'):
            return user_data['gender']

        # Если нет в кэше, запрашиваем из БД
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT gender FROM users WHERE user_id = $1',
                user_id
            )
            return row['gender'] if row and row['gender'] else 'не указано'
    except Exception as e:
        logger.error(e, exc_info=True)
        return ('не указано')