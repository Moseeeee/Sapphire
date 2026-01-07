
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, memory_cache
import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


# -------------------------
# УПРАВЛЕНИЕ АГЕНТАМИ
# -------------------------

@auto_cache_update('agents', 'agent_id')
async def add_agents(agent_id: int, agent_appointed_id: int, date_appointed: str) -> None:
    """Добавляет агента поддержки."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO agents (agent_id, agent_appointed_id, date_appointed) VALUES ($1, $2, $3)',
                agent_id, agent_appointed_id, date_appointed
            )
    except Exception as e:
        logger.error(e, exc_info=True)


@auto_cache_update('acting_agents', 'acting_agent_id')
async def edit_status(user_id: int, status: int) -> None:
    """Обновляет статус действующего агента."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE acting_agents SET agent_status = $1 WHERE acting_agent_id = $2',
                status, user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_agents(user_id: int) -> int | None:
    """Проверяет, является ли пользователь агентом (по agent_id)."""
    #cache_key = f"agents_{user_id}"
    #async with cache_lock:
        #if cache_key in memory_cache:
         #   return memory_cache[cache_key].get('agent_id')

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT agent_id FROM agents WHERE agent_id = $1',
                user_id
            )
            agent_id = row['agent_id'] if row else None

            #async with cache_lock:
              #  memory_cache[cache_key] = {'agent_id': agent_id}

            return agent_id
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def user_for_status(user_id: int) -> int:
    """Возвращает статус действующего агента (0 — не агент)."""
    #cache_key = f"acting_agents_{user_id}"
    #async with cache_lock:
     #   if cache_key in memory_cache:
       #     status = memory_cache[cache_key].get('agent_status')
       #     if status is not None:
       #         return status

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT agent_status FROM acting_agents WHERE acting_agent_id = $1',
                user_id
            )
            status = row['agent_status'] if row else 0

            #async with cache_lock:
            #    memory_cache[cache_key] = {'acting_agent_id': user_id, 'agent_status': status}

            return status
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def agent_history_db(
    remove_agent_id: int,
    agent_appointed_id: int,
    date_appointed: str,
    old_status: int,
    new_status: int
) -> None:
    """Добавляет запись в историю изменений агентов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO agents_history (remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status)
                VALUES ($1, $2, $3, $4, $5)
                ''',
                remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_agent_history_db(remove_agent_id: int) -> list | None:
    """Возвращает всю историю по уволенному агенту."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status
                FROM agents_history
                WHERE remove_agent_id = $1
                ''',
                remove_agent_id
            )
            return [tuple(row.values()) for row in rows] if rows else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_agent_appointed(agent_id: int) -> list | None:
    """Возвращает информацию о назначении агента."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT agent_id, agent_appointed_id, date_appointed FROM agents WHERE agent_id = $1',
                agent_id
            )
            return [tuple(row.values()) for row in rows] if rows else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


# -------------------------
# УПРАВЛЕНИЕ ДЕЙСТВУЮЩИМИ АГЕНТАМИ
# -------------------------

async def add_acting_agent(user_id: int, agent_status: int) -> None:
    """Добавляет пользователя как действующего агента."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO acting_agents (acting_agent_id, agent_status) VALUES ($1, $2)',
                user_id, agent_status
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def delete_acting_agent(user_id: int) -> None:
    """Удаляет пользователя из действующих агентов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM acting_agents WHERE acting_agent_id = $1',
                user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def search_acting_agents(user_id: int) -> int | None:
    """Проверяет, является ли пользователь действующим агентом."""
    cache_key = f"acting_agents_{user_id}"
    async with cache_lock:
       if cache_key in memory_cache:
           return memory_cache[cache_key].get('acting_agent_id')

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT acting_agent_id FROM acting_agents WHERE acting_agent_id = $1',
                user_id
            )
            agent_id = row['acting_agent_id'] if row else None

            async with cache_lock:
                memory_cache[cache_key] = {'acting_agent_id': agent_id}

            return agent_id
    except Exception as e:
        logger.error(e, exc_info=True)
        return None
