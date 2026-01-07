
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import cache_lock, memory_cache
import logging
from typing import Optional, List, Tuple
from datetime import date

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


# -------------------------
# УПРАВЛЕНИЕ СВЯЗЯМИ ЧАТОВ
# -------------------------

async def add_chat_reports(report_chat: int, reported_chat: int) -> None:
    """Добавляет связь между чатом-репортом и репортируемым чатом."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO chat_reports (report_chat, reported_chat) VALUES ($1, $2)',
                report_chat, reported_chat
            )
    except Exception as e:
        logger.error(e, exc_info=True)




async def all_del_chat_reports_with_info(report_chat: int) -> Tuple[int, int, List[Tuple[str, str]]]:
    """Удаляет все привязки чата и возвращает информацию о репортируемых чатах."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем все reported_chat
            rows = await conn.fetch(
                'SELECT reported_chat FROM chat_reports WHERE report_chat = $1',
                report_chat
            )
            reported_chats = [row['reported_chat'] for row in rows]
            total = len(reported_chats)

            if not total:
                return 0, 0, []

            # Получаем название и ссылку для каждого чата
            chat_info = []
            for chat_id in reported_chats:
                cache_key = f"chats_{chat_id}"
                chat_title = None
                invite_link = None

                # Проверка кэша
                async with cache_lock:
                    if cache_key in memory_cache:
                        chat_title = memory_cache[cache_key].get('chat_title')
                        invite_link = memory_cache[cache_key].get('invite_link')

                # Запрос в БД, если нет в кэше
                if chat_title is None or invite_link is None:
                    row = await conn.fetchrow(
                        'SELECT chat_title, invite_link FROM chats WHERE chat_id = $1',
                        chat_id
                    )
                    if row:
                        chat_title = row['chat_title'] or f"Чат {chat_id}"
                        invite_link = row['invite_link']
                        async with cache_lock:
                            memory_cache[cache_key] = {
                                'chat_id': chat_id,
                                'chat_title': chat_title,
                                'invite_link': invite_link
                            }
                    else:
                        chat_title = f"Чат {chat_id}"
                        invite_link = None

                # Формирование ссылки, если нет invite_link
                if invite_link is None:
                    clean_id = str(chat_id).replace('-100', '')
                    invite_link = f"https://t.me/c/{clean_id}"

                chat_info.append((chat_title, invite_link))

            # Удаляем все записи
            await conn.execute(
                'DELETE FROM chat_reports WHERE report_chat = $1',
                report_chat
            )
            return total, total, chat_info

    except Exception as e:
        logger.error(e, exc_info=True)
        return 0, 0, []


async def del_chat_report(report_chat: int, reported_chat: int) -> bool:
    """Удаляет конкретную пару чатов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM chat_reports WHERE report_chat = $1 AND reported_chat = $2',
                report_chat, reported_chat
            )
            # В asyncpg execute не возвращает rowcount, но если не упало — OK
            return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


# -------------------------
# РАБОТА С ЖАЛОБАМИ
# -------------------------

async def add_info_for_report(
    report_id: int,
    reported_id: int,
    reply_message_id: int,
    message_id: int,
    reported_chat: int
) -> None:
    """Добавляет запись о жалобе."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO reports (report_id, reported_id, reply_message_id, message_id, reported_chat)
                VALUES ($1, $2, $3, $4, $5)
                ''',
                report_id, reported_id, reply_message_id, message_id, reported_chat
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def del_info_for_report(message_id: int, reported_chat: int) -> None:
    """Удаляет жалобу по message_id и чату."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM reports WHERE message_id = $1 AND reported_chat = $2',
                message_id, reported_chat
            )
    except Exception as e:
        logger.error(e, exc_info=True)


# -------------------------
# ПРОВЕРКИ И ПОИСК
# -------------------------

async def check_report_chat_id(reported_chat: int) -> Optional[int]:
    """Возвращает один чат-репорт для данного чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT report_chat FROM chat_reports WHERE reported_chat = $1 LIMIT 1',
                reported_chat
            )
            return row['report_chat'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_report_chats(reported_chat: int) -> List[int]:
    """Возвращает все чаты-репорты для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT report_chat FROM chat_reports WHERE reported_chat = $1',
                reported_chat
            )
            return [row['report_chat'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def check_reports_chats_db(report_chat: int) -> List[int]:
    """Возвращает все репортируемые чаты для чата-репорта."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT reported_chat FROM chat_reports WHERE report_chat = $1',
                report_chat
            )
            return [row['reported_chat'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def check_existing_pair(report_chat: int, reported_chat: int) -> bool:
    """Проверяет существование пары."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM chat_reports WHERE report_chat = $1 AND reported_chat = $2',
                report_chat, reported_chat
            )
            return row is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def is_report_chat(chat_id: int) -> bool:
    """Является ли чат чатом-репортом."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM chat_reports WHERE report_chat = $1 LIMIT 1',
                chat_id
            )
            return row is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def is_reported_chat(chat_id: int) -> bool:
    """Является ли чат репортируемым."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM chat_reports WHERE reported_chat = $1 LIMIT 1',
                chat_id
            )
            return row is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


# -------------------------
# ПОИСК ИНФОРМАЦИИ (С КЭШЕМ)
# -------------------------

async def search_report_chat_link(reported_chat: int) -> Optional[str]:
    cache_key = f"chats_{reported_chat}"
    async with cache_lock:
        if cache_key in memory_cache:
            link = memory_cache[cache_key].get('invite_link')
            if link is not None:
                return link

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT invite_link FROM chats WHERE chat_id = $1', reported_chat)
            invite_link = row['invite_link'] if row else None
            if invite_link is None:
                clean_id = str(reported_chat).replace('-100', '')
                invite_link = f"https://t.me/c/{clean_id}"
            async with cache_lock:
                memory_cache.setdefault(cache_key, {})['invite_link'] = invite_link
            return invite_link
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def search_report_chat_name(reported_chat: int) -> Optional[str]:
    cache_key = f"chats_{reported_chat}"
    async with cache_lock:
        if cache_key in memory_cache:
            title = memory_cache[cache_key].get('chat_title')
            if title is not None:
                return title

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT chat_title FROM chats WHERE chat_id = $1', reported_chat)
            chat_title = row['chat_title'] if row else f"Чат {reported_chat}"
            async with cache_lock:
                memory_cache.setdefault(cache_key, {})['chat_title'] = chat_title
            return chat_title
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_all_reports_for_user(report_id: int, chat_id: int) -> List[int]:
    """Возвращает все message_id жалоб от пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT message_id FROM reports WHERE report_id = $1 AND reported_chat = $2',
                report_id, chat_id
            )
            return [row['message_id'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_all_reports_for_user_reply(report_id: int, chat_id: int) -> List[int]:
    """Возвращает все reply_message_id жалоб от пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT reply_message_id FROM reports WHERE report_id = $1 AND reported_chat = $2',
                report_id, chat_id
            )
            return [row['reply_message_id'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


# -------------------------
# ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЯХ (можно вынести в user_db.py)
# -------------------------

async def search_user_name(user_id: int) -> Optional[str]:
    cache_key = f"users_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            name = memory_cache[cache_key].get('name')
            if name is not None:
                return name

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT name FROM users WHERE user_id = $1', user_id)
            name = row['name'] if row else None
            async with cache_lock:
                memory_cache.setdefault(cache_key, {})['name'] = name
            return name
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def search_user_username(user_id: int) -> Optional[str]:
    cache_key = f"users_{user_id}"
    async with cache_lock:
        if cache_key in memory_cache:
            username = memory_cache[cache_key].get('username')
            if username is not None:
                return username

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT username FROM users WHERE user_id = $1', user_id)
            username = row['username'] if row else None
            async with cache_lock:
                memory_cache.setdefault(cache_key, {})['username'] = username
            return username
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


# -------------------------
# СТАТИСТИКА МОДЕРАЦИИ
# -------------------------

async def update_moderation_stats(user_id: int, chat_id: int) -> None:
    """Обновляет статистику модерации с учётом периодов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            today = date.today()
            today_str = today.isoformat()

            row = await conn.fetchrow(
                "SELECT day_count, week_count, month_count, year_count, last_update FROM moderation_stats WHERE user_id = $1 AND chat_id = $2",
                user_id, chat_id
            )

            if row:
                last_update = date.fromisoformat(row['last_update'])

                # День
                day_count = 1 if last_update != today else row['day_count'] + 1

                # Неделя (ISO)
                if last_update.isocalendar()[:2] == today.isocalendar()[:2]:
                    week_count = row['week_count'] + 1
                else:
                    week_count = 1

                # Месяц
                if last_update.month == today.month and last_update.year == today.year:
                    month_count = row['month_count'] + 1
                else:
                    month_count = 1

                # Год
                if last_update.year == today.year:
                    year_count = row['year_count'] + 1
                else:
                    year_count = 1

                await conn.execute(
                    """
                    UPDATE moderation_stats 
                    SET day_count = $1, week_count = $2, month_count = $3, year_count = $4,
                        total_count = total_count + 1, last_update = $5
                    WHERE user_id = $6 AND chat_id = $7
                    """,
                    day_count, week_count, month_count, year_count, today_str, user_id, chat_id
                )
            else:
                # Новая запись
                await conn.execute(
                    """
                    INSERT INTO moderation_stats 
                    (user_id, chat_id, day_count, week_count, month_count, year_count, total_count, last_update)
                    VALUES ($1, $2, 1, 1, 1, 1, 1, $3)
                    """,
                    user_id, chat_id, today_str
                )

    except Exception as e:
        logger.error(e, exc_info=True)