import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def edit_antispam_status(chat_id: int, antispam: str) -> None:
    """
    Обновляет статус уведомлений (push_status) для чата.

    push_status: 'on' или 'off'
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET antispam = $1 WHERE chat_id = $2',
                antispam, chat_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_antispam_status(chat_id: int) -> str | None:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT antispam FROM chats WHERE chat_id = $1',
                chat_id
            )
            return row['antispam'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None