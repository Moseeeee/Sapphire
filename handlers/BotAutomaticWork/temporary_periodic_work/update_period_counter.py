import logging
from datetime import datetime, timedelta

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def reset_periodic_counters() -> str:
    """
    Сбрасывает периодические счётчики статистики модерации:
    - daily: если last_update < сегодня
    - weekly: если last_update < 7 дней назад
    - monthly: если last_update < 30 дней назад
    - yearly: если last_update < 365 дней назад
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)
            year_ago = today - timedelta(days=365)

            # Сброс дневного счётчика
            await conn.execute(
                "UPDATE moderation_stats SET day_count = 0 WHERE last_update < $1",
                today.isoformat()
            )

            # Сброс недельного счётчика
            await conn.execute(
                "UPDATE moderation_stats SET week_count = 0 WHERE last_update < $1",
                week_ago.isoformat()
            )

            # Сброс месячного счётчика
            await conn.execute(
                "UPDATE moderation_stats SET month_count = 0 WHERE last_update < $1",
                month_ago.isoformat()
            )

            # Сброс годового счётчика
            await conn.execute(
                "UPDATE moderation_stats SET year_count = 0 WHERE last_update < $1",
                year_ago.isoformat()
            )

        logger.info("✅ Периодические счётчики модерации сброшены")
        return 'ok'

    except Exception as e:
        logger.error(e, exc_info=True)
        return 'error'