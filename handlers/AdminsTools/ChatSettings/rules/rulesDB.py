# handlers/BotAutomaticWork/DataBase/rules.py
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, memory_cache

import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


#@auto_cache_update('rules', 'chat_id')
async def set_rules(chat_id: int, rules_text: str) -> None:

    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO rules (chat_id, rules_text)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE
                SET rules_text = EXCLUDED.rules_text;
                ''',
                chat_id, rules_text
            )
    except Exception as e:
        logger.error(e, exc_info=True)
        raise



#@auto_cache_update('rules', 'chat_id')
async def delete_rules_text(chat_id: int) -> None:
    """Удаляет правила чата."""
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM rules WHERE chat_id = $1;', chat_id)
    except Exception as e:
        logger.error(e, exc_info=True)
        raise


async def check_rules_text(chat_id: int) -> str | None:
    pool = await get_db_pool()
    cache_key = f"rules_{chat_id}"

    # 1. Проверка кэша
    #async with cache_lock:
     #   if cache_key in memory_cache:
      #      cached = memory_cache[cache_key]
       #     if cached.get("rules_text") is not None:
        #        return cached["rules_text"]

    # 2. Запрос к БД
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT rules_text FROM rules WHERE chat_id = $1;',
                chat_id
            )
            rules_text = row['rules_text'] if row else None

            # 3. Обновление кэша
            #async with cache_lock:
               # memory_cache[cache_key] = {
                 #   'chat_id': chat_id,
                 #   'rules_text': rules_text
                #}
            return rules_text

    except Exception as e:
        logger.error(e, exc_info=True)
        return None

