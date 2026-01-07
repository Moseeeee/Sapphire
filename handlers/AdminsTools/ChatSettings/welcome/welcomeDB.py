from datetime import datetime
import pytz
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update, cache_lock, memory_cache
import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


def format_time(time: datetime) -> str:
    """Форматирует время в строку: 'дд.мм.гггг в чч:мм'"""
    return time.strftime('%d.%m.%Y в %H:%M')


def get_moscow_time() -> datetime:
    """Возвращает текущее время в московском часовом поясе."""
    moscow = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow)


# -------------------------
# УПРАВЛЕНИЕ ПРИВЕТСТВИЯМИ
# -------------------------

#@auto_cache_update('welcome', 'chat_id')
async def add_welcome_text(chat_id: int, welcome_text: str) -> None:
    """Добавляет или обновляет приветствие для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO welcome (chat_id, welcome_text)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE SET welcome_text = EXCLUDED.welcome_text
            ''', chat_id, welcome_text)
    except Exception as e:
        logger.error(e, exc_info=True)




#@auto_cache_update('welcome', 'chat_id')
async def delete_welcome_text(chat_id: int) -> None:
    """Удаляет приветствие чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM welcome WHERE chat_id = $1', chat_id)
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_welcome_text(chat_id: int) -> str | None:
    """Возвращает текст приветствия (с кэшированием)."""
    #cache_key = f"welcome_{chat_id}"
    #async with cache_lock:
      #  if cache_key in memory_cache:
      #      text = memory_cache[cache_key].get('welcome_text')
        #    if text is not None:
       #         return text

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT welcome_text FROM welcome WHERE chat_id = $1',
                chat_id
            )
            welcome_text = row['welcome_text'] if row else None

           # async with cache_lock:
                #memory_cache[cache_key] = {'chat_id': chat_id, 'welcome_text': welcome_text}

            return welcome_text
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


# -------------------------
# ИСТОРИЯ УЧАСТИЯ В ЧАТЕ (full_users_chats)
# -------------------------

async def check_info_full_users_chats(chat_id: int, user_id: int) -> dict:
    """Проверяет наличие записи и возвращает полную информацию."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT join_time, leave_time, member_status 
                FROM full_users_chats 
                WHERE chat_id = $1 AND user_id = $2
                ''',
                chat_id, user_id
            )
            if row:
                return {
                    'join_time': row['join_time'],
                    'leave_time': row['leave_time'],
                    'member_status': row['member_status'],
                    'exists': True
                }
            return {'exists': False}
    except Exception as e:
        logger.error(e, exc_info=True)
        return {'exists': False}


async def add_full_users_chats(chat_id: int, user_id: int, join_time: str) -> None:
    """Добавляет или обновляет запись о входе пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO full_users_chats (chat_id, user_id, join_time, leave_time, member_status)
                VALUES ($1, $2, $3, NULL, 'JOIN')
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    join_time = EXCLUDED.join_time,
                    leave_time = NULL,
                    member_status = 'JOIN'
            ''', chat_id, user_id, join_time)
    except Exception as e:
        logger.error(e, exc_info=True)


async def add_full_users_chats_leave(chat_id: int, user_id: int, leave_time: str) -> None:
    """Обновляет запись о выходе пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Проверяем существование
            exists = await conn.fetchval(
                'SELECT 1 FROM full_users_chats WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )

            if exists:
                await conn.execute('''
                    UPDATE full_users_chats 
                    SET leave_time = $1, member_status = 'LEAVE' 
                    WHERE chat_id = $2 AND user_id = $3
                ''', leave_time, chat_id, user_id)
            else:
                await conn.execute('''
                    INSERT INTO full_users_chats (chat_id, user_id, join_time, leave_time, member_status)
                    VALUES ($1, $2, $3, $3, 'LEAVE')
                ''', chat_id, user_id, leave_time)

    except Exception as e:
        logger.error(e, exc_info=True)


async def update_full_users_chats_status(chat_id: int, user_id: int, member_status: str) -> None:
    """Обновляет статус участника (JOIN, LEAVE, KICKED, BANNED и т.д.)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                'SELECT 1 FROM full_users_chats WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )

            current_time = format_time(get_moscow_time())

            if exists:
                await conn.execute('''
                    UPDATE full_users_chats 
                    SET member_status = $1 
                    WHERE chat_id = $2 AND user_id = $3
                ''', member_status, chat_id, user_id)
            else:
                await conn.execute('''
                    INSERT INTO full_users_chats (chat_id, user_id, join_time, member_status)
                    VALUES ($1, $2, $3, $4)
                ''', chat_id, user_id, current_time, member_status)

    except Exception as e:
        logger.error(e, exc_info=True)