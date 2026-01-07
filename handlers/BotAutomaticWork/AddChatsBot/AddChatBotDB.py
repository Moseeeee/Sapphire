from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update

import logging
from typing import Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


@auto_cache_update('chats', 'chat_id')
async def add_chat_info(
    chat_id: int,
    chat_title: str,
    chat_username: Optional[str],
    bot_chat_status: str,
    owner_id: Optional[int]
) -> None:
    """Добавляет или обновляет информацию о чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO chats (
                    chat_id, chat_title, chat_username, bot_chat_status, owner_id
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (chat_id) DO UPDATE SET
                    chat_title = EXCLUDED.chat_title,
                    chat_username = EXCLUDED.chat_username,
                    bot_chat_status = EXCLUDED.bot_chat_status,
                    owner_id = EXCLUDED.owner_id
            ''', chat_id, chat_title, chat_username, bot_chat_status, owner_id)
    except Exception as e:
        logger.error(e, exc_info=True)


@auto_cache_update('chats', 'chat_id')
async def update_chat_leave_time(chat_id: int) -> None:
    """Помечает чат как покинутый ботом."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET bot_chat_status = $1 WHERE chat_id = $2',
                'left', chat_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def update_owner_rang(user_id: int, chat_id: int, rang: int, update_time: str) -> None:
    """Обновляет ранг пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users_rangs SET rang = $1, update_time = $2 WHERE UserId = $3 AND ChatId = $4",
                rang, update_time, user_id, chat_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def upsert_owner_rang(user_id: int, chat_id: int, rang: int, update_time: str) -> None:
    """Добавляет или обновляет ранг владельца (UPSERT)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users_rangs (UserId, ChatId, rang, update_time)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (UserId, ChatId) DO UPDATE SET
                    rang = EXCLUDED.rang,
                    update_time = EXCLUDED.update_time
            ''', user_id, chat_id, rang, update_time)
    except Exception as e:
        logger.error(e, exc_info=True)