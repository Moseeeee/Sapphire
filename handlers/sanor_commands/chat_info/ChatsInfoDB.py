import logging
from typing import Optional, Dict, Any
from datetime import datetime

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def get_chat_info(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о чате из таблицы chats
    """
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT 
                    chat_id, chat_title, chat_username,
                    status_v, status_e, push_status,
                    antispam, bot_chat_status, chat_ignore_status,
                    number_for_inputs, owner_id, invite_link,
                    invite_link_updated_at, first_seen, last_update
                FROM chats 
                WHERE chat_id = $1;
                ''',
                chat_id
            )

            if row:
                return dict(row)
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении информации о чате {chat_id}: {e}", exc_info=True)
        return None


async def get_chat_stats(chat_id: int) -> Dict[str, Any]:
    """
    Получает статистику сообщений для чата
    """
    pool = await get_db_pool()
    stats = {
        'total': 0,
        'daily': 0,
        'weekly': 0,
        'monthly': 0,
        'yearly': 0,
        'users_count': 0,
        'avg_per_user': 0
    }

    try:
        async with pool.acquire() as conn:
            # Получаем агрегированную статистику по всем пользователям в чате
            row = await conn.fetchrow(
                '''
                SELECT 
                    SUM(total) as total_sum,
                    SUM(daily) as daily_sum,
                    SUM(weekly) as weekly_sum,
                    SUM(monthly) as monthly_sum,
                    SUM(yearly) as yearly_sum,
                    COUNT(DISTINCT user_id) as users_count
                FROM message_stats 
                WHERE chat_id = $1;
                ''',
                chat_id
            )

            if row and row['total_sum']:
                stats['total'] = row['total_sum'] or 0
                stats['daily'] = row['daily_sum'] or 0
                stats['weekly'] = row['weekly_sum'] or 0
                stats['monthly'] = row['monthly_sum'] or 0
                stats['yearly'] = row['yearly_sum'] or 0
                stats['users_count'] = row['users_count'] or 0

                # Рассчитываем среднее на пользователя
                if stats['users_count'] > 0:
                    stats['avg_per_user'] = round(stats['total'] / stats['users_count'], 1)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики чата {chat_id}: {e}", exc_info=True)

    return stats


def format_number(num: int) -> str:
    """
    Форматирует числа в читаемый вид (1K, 1.5K и т.д.)
    """
    if num >= 1000000:
        return f"{num / 1000000:.1f}M".replace('.0', '')
    elif num >= 1000:
        return f"{num / 1000:.1f}K".replace('.0', '')
    return str(num)