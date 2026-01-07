import asyncpg
import logging

from handlers.BotAutomaticWork.Gonfig.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Глобальный пул
db_pool: asyncpg.Pool | None = None



async def init_db_pool():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("✅ Пул подключений к PostgreSQL инициализирован")
        return 'ok'
    except Exception as e:
        logger.critical(f"❌ Не удалось создать пул подключений: {e}")
        return 'error'


async def close_db_pool():
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("🔌 Пул подключений к PostgreSQL закрыт")


def get_db_pool() -> asyncpg.Pool:
    if db_pool is None:
        raise RuntimeError("База данных не инициализирована! Вызовите init_db_pool() сначала.")
    return db_pool