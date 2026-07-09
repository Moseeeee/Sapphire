from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, \
    memory_cache
import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)





#@auto_cache_update('chats', 'chat_id')
async def edit_status_voice_settings(chat_id: int, status: str) -> None:
    """Обновляет статус 'e' (репортов) для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET voice_settings = $1 WHERE chat_id = $2',
                status, chat_id
            )

    except Exception as e:
        logger.error(e, exc_info=True)



async def check_status_voice_settings(chat_id: int) -> str | None:
    """Получает статус 'e' для чата (с кэшированием)."""
    #cache_key = f"chats_{chat_id}"

    # Проверка кэша
    #async with cache_lock:
        #if cache_key in memory_cache:
         #   status_e = memory_cache[cache_key].get('status_e')
         #   if status_e is not None:
          #      return status_e

    # Запрос к БД
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT voice_settings FROM chats WHERE chat_id = $1',
                chat_id
            )
            status_e = row['voice_settings'] if row else None

        return status_e

    except Exception as e:
        logger.error(e, exc_info=True)
        return None