from typing import Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import cache_lock, memory_cache
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
import logging

from handlers.BotAutomaticWork.Gonfig.config import boss_agent

logger = logging.getLogger(__name__)

async def check_command_chat_rang(CommandId: int, ChatId: int) -> Optional[int]:
    """Получает уровень доступа к команде в конкретном чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT AccessLevel FROM commands_chats WHERE CommandId = $1 AND ChatId = $2',
                CommandId, ChatId
            )
            return row['accesslevel'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_command_rang(CommandId: int) -> Optional[int]:
    """Получает глобальный уровень доступа к команде."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT AccessLevel FROM commands WHERE CommandId = $1',
                CommandId
            )
            return row['accesslevel'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None




async def get_user_rank(user_id: int) -> int | None:
    """Возвращает ранг пользователя: 5 для боссов, иначе agent_status из БД или None."""
    if user_id in boss_agent:
        return 5

    cache_key = f"acting_agents_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            return memory_cache[cache_key].get('agent_status')  # предполагаем, что это ранг

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT agent_status FROM acting_agents WHERE acting_agent_id = $1',
                user_id
            )
            rank = row['agent_status'] if row else None

            async with cache_lock:
                memory_cache[cache_key] = {
                    'acting_agent_id': user_id if row else None,
                    'agent_status': rank
                }

            return rank
    except Exception as e:
        logger.error(e, exc_info=True)
        return None