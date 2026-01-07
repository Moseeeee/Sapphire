from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, multi_cache_update
import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


@auto_cache_update("users_rangs", key_columns=["UserId", "ChatId"])
async def add_admin_for_rang(
    UserId: int,
    ChatId: int,
    rang: int,
    ManagementAdminId: int,
    ManagementRang: int,
    time: str
) -> None:
    """Добавляет или обновляет администратора и его ранг."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Вставляем/обновляем ранг
            await conn.execute('''
                INSERT INTO users_rangs (UserId, ChatId, rang)
                VALUES ($1, $2, $3)
                ON CONFLICT (UserId, ChatId) DO UPDATE SET rang = EXCLUDED.rang
            ''', UserId, ChatId, rang)

            # Вставляем/обновляем данные в chat_admins
            await conn.execute('''
                INSERT INTO chat_admins (UserId, ChatId, ManagementAdminId, ManagementRang, time)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (UserId, ChatId) DO UPDATE SET
                    ManagementAdminId = EXCLUDED.ManagementAdminId,
                    ManagementRang = EXCLUDED.ManagementRang,
                    time = EXCLUDED.time
            ''', UserId, ChatId, ManagementAdminId, ManagementRang, time)


    except Exception as e:
        logger.error(e, exc_info=True)
        raise


@multi_cache_update(
    ("chat_admins", None, ["UserId", "ChatId"]),
    ("users_rangs", None, ["UserId", "ChatId"])
)
async def update_admin_for_rang(
    rang: int,
    ManagementAdminId: int,
    ManagementRang: int,
    time: str,
    UserId: int,
    ChatId: int
) -> None:
    """Обновляет данные администратора."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE users_rangs 
                SET rang = $1 
                WHERE UserId = $2 AND ChatId = $3
            ''', rang, UserId, ChatId)

            await conn.execute('''
                UPDATE chat_admins 
                SET ManagementAdminId = $1, ManagementRang = $2, time = $3
                WHERE UserId = $4 AND ChatId = $5
            ''', ManagementAdminId, ManagementRang, time, UserId, ChatId)


    except Exception as e:
        logger.error(e, exc_info=True)


async def check_admin_for_rang(UserId: int, ChatId: int) -> int:
    """Получает текущий ранг пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT rang FROM users_rangs WHERE UserId = $1 AND ChatId = $2',
                UserId, ChatId
            )
            return row['rang'] if row else 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def add_history_admin_for_rang(
    UserId: int,
    ChatId: int,
    rang: int,
    OldRang: int,
    ManagementAdminId: int,
    ManagementRang: int,
    time: str
) -> None:
    """Добавляет запись в историю изменений рангов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO history_chat_admins (UserId, ChatId, rang, OldRang, ManagementAdminId, ManagementRang, time) 
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', UserId, ChatId, rang, OldRang, ManagementAdminId, ManagementRang, time)
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_history_admin_for_rang(UserId: int, ChatId: int) -> list:
    """Получает историю изменений рангов для пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT rang, OldRang, ManagementAdminId, time 
                FROM history_chat_admins 
                WHERE UserId = $1 AND ChatId = $2
                ''',
                UserId, ChatId
            )
            return [(row['rang'], row['oldrang'], row['managementadminid'], row['time']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def del_admin_for_rang(UserId: int, ChatId: int) -> None:
    """Удаляет администратора (сбрасывает ранг до 0)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM chat_admins WHERE UserId = $1 AND ChatId = $2',
                UserId, ChatId
            )
            await conn.execute(
                'UPDATE users_rangs SET rang = 0 WHERE UserId = $1 AND ChatId = $2',
                UserId, ChatId
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_all_chat_admins(chat_id: int) -> list:
    """Получает всех администраторов чата с рангом > 0."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT UserId, rang 
                FROM users_rangs 
                WHERE ChatId = $1 AND rang > 0 
                ORDER BY rang DESC, UserId
                ''',
                chat_id
            )
            return [{'UserId': row['userid'], 'rang': row['rang']} for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def check_and_add_user_rang(UserId: int, ChatId: int) -> int:
    """Проверяет и добавляет пользователя с рангом 0, если его нет."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Пытаемся вставить с рангом 0, если не существует
            await conn.execute('''
                INSERT INTO users_rangs (UserId, ChatId, rang)
                VALUES ($1, $2, 0)
                ON CONFLICT (UserId, ChatId) DO NOTHING
            ''', UserId, ChatId)

            # Получаем текущий ранг
            row = await conn.fetchrow(
                'SELECT rang FROM users_rangs WHERE UserId = $1 AND ChatId = $2',
                UserId, ChatId
            )
            return row['rang'] if row else 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0