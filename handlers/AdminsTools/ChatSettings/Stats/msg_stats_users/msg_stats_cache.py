import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
import asyncio



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler('sapphire.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Кеш: { (chat_id, user_id): { 'total': int, 'daily': int, 'weekly': int, ... } }
MESSAGE_CACHE: Dict[Tuple[int, int], Dict[str, int]] = defaultdict(lambda: defaultdict(int))

# Время последнего сброса кеша
last_flush = datetime.now()

# Интервал сброса кеша в БД (15 минут)
FLUSH_INTERVAL = 900  # сек

async def increment_message(chat_id: int, user_id: int):
    start = datetime.now()
    """Увеличить счётчик сообщений в кеше."""
    key = (chat_id, user_id)
    now = datetime.utcnow()
    MESSAGE_CACHE[key]['total'] += 1
    MESSAGE_CACHE[key]['daily'] += 1
    MESSAGE_CACHE[key]['weekly'] += 1
    MESSAGE_CACHE[key]['monthly'] += 1
    MESSAGE_CACHE[key]['yearly'] += 1

    end = datetime.now()
    ping_ms = (end - start).microseconds // 1000
    print(ping_ms)

    # Запускаем фоновый сброс кеша, если прошло достаточно времени
    try:
        global last_flush
        if (datetime.now() - last_flush).total_seconds() > FLUSH_INTERVAL:
            asyncio.create_task(flush_cache_to_db())

    except Exception as e:
        logger.error(e, exc_info=True)

async def flush_cache_to_db():
    """Сбросить кеш в БД."""
    global last_flush
    from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsDB import save_message_batch

    if not MESSAGE_CACHE:
        return

    batch = []
    for (chat_id, user_id), counts in MESSAGE_CACHE.items():
        batch.append((chat_id, user_id, counts['total'], counts['daily'],
                      counts['weekly'], counts['monthly'], counts['yearly']))

    try:
        await save_message_batch(batch)
        MESSAGE_CACHE.clear()
        last_flush = datetime.now()

        return 'ok'
    except Exception as e:
        logger.error(e, exc_info=True)
        return 'error'