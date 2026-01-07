import logging
from typing import List, Tuple, Dict, Any
import pytz
from datetime import datetime

# Кэш импортируем как есть (убедись, что путь корректен)
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import MESSAGE_CACHE
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


async def save_message_batch(batch: List[Tuple[int, int, int, int, int, int, int]]):
    """Сохранить или обновить статистику из кеша."""
    if not batch:
        return

    pool = get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.executemany("""
            INSERT INTO message_stats (
                chat_id, user_id, total, daily, weekly, monthly, yearly
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                total = message_stats.total + EXCLUDED.total,
                daily = message_stats.daily + EXCLUDED.daily,
                weekly = message_stats.weekly + EXCLUDED.weekly,
                monthly = message_stats.monthly + EXCLUDED.monthly,
                yearly = message_stats.yearly + EXCLUDED.yearly
            """, batch)
            logger.info(f"Успешно сохранена пачка из {len(batch)} записей")
        except Exception as e:
            logger.error(e, exc_info=True)


async def get_stats(chat_id: int, period: str) -> List[Tuple[int, str, int]]:
    """Получить топ пользователей за период."""
    await clean_old_stats(chat_id, period)

    period_to_field = {
        'всего': 'total',
        'день': 'daily',
        'неделя': 'weekly',
        'месяц': 'monthly',
        'год': 'yearly',
        'вся': 'total'
    }

    field = period_to_field.get(period)
    if not field:
        logger.error(f"Неизвестный период: {period}")
        return []

    pool = get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(f"""
            SELECT user_id, daily, weekly, monthly, yearly, total
            FROM message_stats 
            WHERE chat_id = $1 AND {field} > 0
            ORDER BY {field} DESC
            LIMIT 1000
            """, chat_id)

            merged: Dict[int, List[int]] = {}

            for row in rows:
                uid = row['user_id']
                merged[uid] = [
                    row['daily'],
                    row['weekly'],
                    row['monthly'],
                    row['yearly'],
                    row['total']
                ]

            for (cid, uid), counts in MESSAGE_CACHE.items():
                if cid == chat_id:
                    if uid not in merged:
                        merged[uid] = [0, 0, 0, 0, 0]
                    merged[uid][0] += counts.get('daily', 0)
                    merged[uid][1] += counts.get('weekly', 0)
                    merged[uid][2] += counts.get('monthly', 0)
                    merged[uid][3] += counts.get('yearly', 0)
                    merged[uid][4] += counts.get('total', 0)

            field_index = {'daily': 0, 'weekly': 1, 'monthly': 2, 'yearly': 3, 'total': 4}[field]
            result = [
                (uid, '', values[field_index])
                for uid, values in merged.items()
                if values[field_index] > 0
            ]
            result.sort(key=lambda x: x[2], reverse=True)
            return result

        except Exception as e:
            logger.error(e, exc_info=True)
            return []


async def get_total_messages(chat_id: int) -> int:
    """Получить общее число сообщений в чате."""
    total = 0

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT SUM(total) FROM message_stats WHERE chat_id = $1
            """, chat_id)
            total += (row[0] or 0) if row else 0

        for (cid, _), counts in MESSAGE_CACHE.items():
            if cid == chat_id:
                total += counts.get('total', 0)

        return total

    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_user_stats(chat_id: int, user_id: int) -> Dict[str, int]:
    """Получить статистику конкретного пользователя."""
    stats = {'daily': 0, 'weekly': 0, 'monthly': 0, 'yearly': 0, 'total': 0}

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT daily, weekly, monthly, yearly, total 
            FROM message_stats 
            WHERE chat_id = $1 AND user_id = $2
            """, chat_id, user_id)

            if row:
                stats.update({
                    'daily': row['daily'],
                    'weekly': row['weekly'],
                    'monthly': row['monthly'],
                    'yearly': row['yearly'],
                    'total': row['total']
                })

        cache_key = (chat_id, user_id)
        if cache_key in MESSAGE_CACHE:
            cache_data = MESSAGE_CACHE[cache_key]
            for key in stats:
                stats[key] += cache_data.get(key, 0)

        return stats

    except Exception as e:
        logger.error(e, exc_info=True)
        return stats


async def clean_old_stats(chat_id: int, period: str):
    """Очистить устаревшие данные для указанного периода."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if period == 'daily':
                await conn.execute("""
                UPDATE message_stats 
                SET daily = 0, last_daily_reset = NOW()
                WHERE chat_id = $1 AND (
                    last_daily_reset IS NULL OR 
                    EXTRACT(EPOCH FROM (NOW() - last_daily_reset)) >= 86400
                )
                """, chat_id)
            elif period == 'weekly':
                await conn.execute("""
                UPDATE message_stats 
                SET weekly = 0, last_weekly_reset = NOW()
                WHERE chat_id = $1 AND (
                    last_weekly_reset IS NULL OR 
                    EXTRACT(EPOCH FROM (NOW() - last_weekly_reset)) >= 604800
                )
                """, chat_id)
            elif period == 'monthly':
                await conn.execute("""
                UPDATE message_stats 
                SET monthly = 0, last_monthly_reset = NOW()
                WHERE chat_id = $1 AND (
                    last_monthly_reset IS NULL OR 
                    EXTRACT(EPOCH FROM (NOW() - last_monthly_reset)) >= 2592000
                )
                """, chat_id)
            elif period == 'yearly':
                await conn.execute("""
                UPDATE message_stats 
                SET yearly = 0, last_yearly_reset = NOW()
                WHERE chat_id = $1 AND (
                    last_yearly_reset IS NULL OR 
                    EXTRACT(EPOCH FROM (NOW() - last_yearly_reset)) >= 31536000
                )
                """, chat_id)

    except Exception as e:
        logger.error(e, exc_info=True)


async def reset_all_stats(chat_id: int):
    """Сбросить всю статистику для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM message_stats WHERE chat_id = $1", chat_id)
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_chat_stats_summary(chat_id: int) -> Dict[str, Any]:
    """Получить сводную статистику по чату."""
    summary = {
        'total_users': 0,
        'total_messages': 0,
        'daily_messages': 0,
        'weekly_messages': 0,
        'monthly_messages': 0,
        'yearly_messages': 0
    }

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_users,
                COALESCE(SUM(total), 0) as total_messages,
                COALESCE(SUM(daily), 0) as daily_messages,
                COALESCE(SUM(weekly), 0) as weekly_messages,
                COALESCE(SUM(monthly), 0) as monthly_messages,
                COALESCE(SUM(yearly), 0) as yearly_messages
            FROM message_stats 
            WHERE chat_id = $1
            """, chat_id)

            if row:
                summary.update({
                    'total_users': row['total_users'],
                    'total_messages': row['total_messages'],
                    'daily_messages': row['daily_messages'],
                    'weekly_messages': row['weekly_messages'],
                    'monthly_messages': row['monthly_messages'],
                    'yearly_messages': row['yearly_messages']
                })

        # Добавляем кеш
        unique_users = set()
        for (cid, uid), counts in MESSAGE_CACHE.items():
            if cid == chat_id:
                summary['total_messages'] += counts.get('total', 0)
                summary['daily_messages'] += counts.get('daily', 0)
                summary['weekly_messages'] += counts.get('weekly', 0)
                summary['monthly_messages'] += counts.get('monthly', 0)
                summary['yearly_messages'] += counts.get('yearly', 0)
                unique_users.add(uid)

        if unique_users:
            summary['total_users'] = max(summary['total_users'], len(unique_users))

        return summary

    except Exception as e:
        logger.error(e, exc_info=True)
        return summary