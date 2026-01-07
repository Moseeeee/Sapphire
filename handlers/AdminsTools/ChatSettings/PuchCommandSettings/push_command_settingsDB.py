import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def edit_push_status(chat_id: int, push_status: str) -> None:
    """
    Обновляет статус уведомлений (push_status) для чата.

    push_status: 'on' или 'off'
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET push_status = $1 WHERE chat_id = $2',
                push_status, chat_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_push_status(chat_id: int) -> str | None:
    """
    Возвращает текущий статус уведомлений для чата.

    Возможные значения: 'on', 'off', None (если чат не найден)
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT push_status FROM chats WHERE chat_id = $1',
                chat_id
            )
            return row['push_status'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None