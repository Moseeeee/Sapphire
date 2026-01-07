import asyncio
import logging
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsDB import clean_old_stats
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def periodic_cleaner():
    pool = get_db_pool()
    """
    Фоновая задача: каждые 60 минут чистит устаревшую статистику во всех чатах.
    Запускать один раз при старте приложения.
    """
    while True:
        try:
            logger.info("Запуск периодической очистки статистики...")

            # Получаем список всех чатов из PostgreSQL
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT DISTINCT chat_id FROM message_stats")
                chat_ids = [row['chat_id'] for row in rows]



            # Чистим по каждому периоду для каждого чата
            for chat_id in chat_ids:
                for period in ["daily", "weekly", "monthly", "yearly"]:
                    try:
                        await clean_old_stats(chat_id, period)
                    except Exception as e:
                        logger.error(f"Ошибка при очистке {period} для чата {chat_id}: {e}")

            logger.info("Периодическая очистка завершена")
            return 'ok'

        except Exception as e:
            logger.error(e, exc_info=True)


        # Ждём 1 час (3600 секунд)
        await asyncio.sleep(3600)

        return 'error'