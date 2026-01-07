import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def get_active_user_ids_in_chat(chat_id: int) -> list[int]:
    """Получает ID всех активных (JOIN) пользователей в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM full_users_chats WHERE chat_id = $1 AND member_status = 'JOIN'",
                chat_id
            )
            return [row['user_id'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_all_user_ids_in_chat(chat_id: int) -> list[int]:
    """Получает ID всех когда-либо участвовавших в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT user_id FROM full_users_chats WHERE chat_id = $1",
                chat_id
            )
            return [row['user_id'] for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_moderation_stats_by_user_ids(chat_id: int, user_ids: list[int]) -> list:
    """
    Получает агрегированную статистику модерации по списку user_id.
    Возвращает список кортежей: (user_id, day, week, month, year, total)
    """
    if not user_ids:
        return []

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT 
                    user_id,
                    SUM(day_count) AS day_total,
                    SUM(week_count) AS week_total,
                    SUM(month_count) AS month_total,
                    SUM(year_count) AS year_total,
                    SUM(total_count) AS total
                FROM moderation_stats 
                WHERE chat_id = $1 AND user_id = ANY($2)
                GROUP BY user_id
                ORDER BY total DESC
            ''', chat_id, user_ids)

            return [
                (
                    row['user_id'],
                    row['day_total'] or 0,
                    row['week_total'] or 0,
                    row['month_total'] or 0,
                    row['year_total'] or 0,
                    row['total'] or 0
                )
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_pending_reports_for_chats(report_chats: list[int]) -> list:
    """
    Получает все непроверенные жалобы из списка чатов.
    Возвращает: [(report_id, reported_id, reply_message_id, message_id, reported_chat), ...]
    """
    if not report_chats:
        return []

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT report_id, reported_id, reply_message_id, message_id, reported_chat
                FROM reports
                WHERE reported_chat = ANY($1)
                ORDER BY report_id
            ''', report_chats)

            return [
                (row['report_id'], row['reported_id'], row['reply_message_id'], row['message_id'], row['reported_chat'])
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []