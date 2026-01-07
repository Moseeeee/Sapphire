from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, \
    memory_cache
import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


@auto_cache_update('chats', 'chat_id')
async def edit_status_v(chat_id: int, status_v: str) -> None:
    """Обновляет статус 'v' (верификации) для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET status_v = $1 WHERE chat_id = $2',
                status_v, chat_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


@auto_cache_update('chats', 'chat_id')
async def edit_status_e(chat_id: int, status_e: str) -> None:
    """Обновляет статус 'e' (репортов) для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE chats SET status_e = $1 WHERE chat_id = $2',
                status_e, chat_id
            )

    except Exception as e:
        logger.error(e, exc_info=True)


async def check_status_v(chat_id: int) -> str | None:
    """Получает статус 'v' для чата (с кэшированием)."""
    #cache_key = f"chats_{chat_id}"

    # Проверка кэша
    #async with cache_lock:
     #   if cache_key in memory_cache:
      #      status_v = memory_cache[cache_key].get('status_v')
       #     if status_v is not None:
        #        return status_v

    # Запрос к БД
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT status_v FROM chats WHERE chat_id = $1',
                chat_id
            )
            status_v = row['status_v'] if row else None

        # Обновление кэша
        #async with cache_lock:
            #memory_cache.setdefault(cache_key, {})['status_v'] = status_v

        return status_v

    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_status_e(chat_id: int) -> str | None:
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
                'SELECT status_e FROM chats WHERE chat_id = $1',
                chat_id
            )
            status_e = row['status_e'] if row else None

        # Обновление кэша
        #async with cache_lock:
         #   memory_cache.setdefault(cache_key, {})['status_e'] = status_e

        return status_e

    except Exception as e:
        logger.error(e, exc_info=True)
        return None