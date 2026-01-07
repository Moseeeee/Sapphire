from typing import List, Dict, Any

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
import logging

logger = logging.getLogger(__name__)

async def base_chats_info(ChatIds: List[int]) -> Dict[int, Dict[str, Any]]:
    """Получает информацию о нескольких чатах по их ID."""
    if not ChatIds:
        return {}

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Используем ANY для массива — безопасно и эффективно
            rows = await conn.fetch(
                '''
                SELECT chat_id, chat_title, chat_username, invite_link
                FROM chats
                WHERE chat_id = ANY($1)
                ORDER BY chat_id
                ''',
                ChatIds
            )

        return {
            row['chat_id']: {
                'title': row['chat_title'],
                'username': row['chat_username'],
                'invite_link': row['invite_link']
            }
            for row in rows
        }

    except Exception as e:
        logger.error(e, exc_info=True)
        return {}