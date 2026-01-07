import logging
from datetime import datetime
from typing import List, Tuple

import pytz

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
logger = logging.getLogger(__name__)


async def add_pinned_message(chat_id: int, message_id: int, unpin_time: datetime):
    """Добавляет информацию о закрепленном сообщении в БД"""
    try:
        # Убедимся, что время в московском часовом поясе
        if unpin_time.tzinfo is None:
            unpin_time = MOSCOW_TZ.localize(unpin_time)
        else:
            unpin_time = unpin_time.astimezone(MOSCOW_TZ)

        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO pinned_messages (chat_id, message_id, unpin_time)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, message_id) 
                DO UPDATE SET unpin_time = $3
            ''', chat_id, message_id, unpin_time)

    except Exception as e:
        logger.error(e, exc_info=True)

async def remove_pinned_message(chat_id: int, message_id: int):
    """Удаляет информацию о закрепленном сообщении из БД"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                DELETE FROM pinned_messages 
                WHERE chat_id = $1 AND message_id = $2
            ''', chat_id, message_id)
    except Exception as e:
        logger.error(e, exc_info=True)

async def clear_chat_pins(chat_id: int):
    """Очищает все закрепления для чата из БД"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                DELETE FROM pinned_messages 
                WHERE chat_id = $1
            ''', chat_id)
    except Exception as e:
        logger.error(e, exc_info=True)

async def is_message_pinned(chat_id: int, message_id: int) -> bool:
    """Проверяет, закреплено ли сообщение через бота"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval('''
                SELECT 1 FROM pinned_messages 
                WHERE chat_id = $1 AND message_id = $2
            ''', chat_id, message_id)
            return result is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False

async def get_chat_pinned_messages(chat_id: int) -> List[Tuple[int, datetime]]:
    """Получает все закрепленные сообщения чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT message_id, unpin_time 
                FROM pinned_messages 
                WHERE chat_id = $1
            ''', chat_id)
            return [(row['message_id'], row['unpin_time']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []

async def get_expired_pinned_messages() -> List[Tuple[int, int]]:
    """Получает список сообщений, которые нужно открепить"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = datetime.now(MOSCOW_TZ)
            rows = await conn.fetch('''
                SELECT chat_id, message_id 
                FROM pinned_messages 
                WHERE unpin_time <= $1
            ''', current_time)
            return [(row['chat_id'], row['message_id']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []