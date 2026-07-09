import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string

logger = logging.getLogger(__name__)

MUTES_PER_PAGE = 10


# ======================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ======================

async def get_default_mute_duration(chat_id: int) -> Optional[timedelta]:
    """Возвращает timedelta по умолчанию для мута в чате или None (навсегда)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT time FROM default_time WHERE chat_id = $1 AND type = $2',
                chat_id, 'mute'
            )
            if row and row['time']:
                time_val = row['time']
                if time_val == "permanent":
                    return None  # навсегда
                parsed = parse_time_string(time_val)
                return parsed
    except Exception as e:
        logger.error(e, exc_info=True)
    return None  # По умолчанию — навсегда


async def set_default_mute_duration(chat_id: int, duration_str: str) -> None:
    """Сохраняет строку времени как настройку по умолчанию для типа 'mute'."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO default_time (chat_id, type, time)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, type) DO UPDATE SET time = EXCLUDED.time
            ''', chat_id, 'mute', duration_str)
    except Exception as e:
        logger.error(e, exc_info=True)


# ======================
# РАБОТА С МУТАМИ В БД
# ======================

async def update_mute_info(chat_id: int, user_id: int, admin_id: int, reason: str, duration_text: str) -> None:
    """Сохраняет или обновляет информацию о муте."""
    try:
        logger.info(
            f"update_mute_info: chat_id={chat_id}, user_id={user_id}, admin_id={admin_id}, reason={reason}, duration={duration_text}")
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO mutes (chat_id, user_id, admin_id, reason, duration)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    admin_id = EXCLUDED.admin_id,
                    reason = EXCLUDED.reason,
                    duration = EXCLUDED.duration
            ''', chat_id, user_id, admin_id, reason, duration_text)
    except Exception as e:
        logger.error(f"Ошибка в update_mute_info: {e}", exc_info=True)


async def update_mute_info_type(chat_id: int, user_id: int, time_end: str) -> None:
    """Сохраняет время окончания мута в punishment_time (столбец time_end имеет тип TEXT)."""
    try:
        from pytz import timezone
        MOSCOW_TZ = timezone('Europe/Moscow')

        logger.info(f"update_mute_info_type: chat_id={chat_id}, user_id={user_id}, time_end={time_end}")

        # Преобразуем строку в datetime для проверки и нормализации, но сохраняем как строку
        try:
            time_end_dt = datetime.fromisoformat(time_end)
        except ValueError:
            # Если пришло не в ISO, пробуем интерпретировать как минуты
            if time_end.isdigit():
                minutes = int(time_end)
                time_end_dt = datetime.now(MOSCOW_TZ) + timedelta(minutes=minutes)
            else:
                time_end_dt = datetime.now(MOSCOW_TZ) + timedelta(hours=1)

        # Приводим к московскому времени и переводим обратно в строку ISO
        if time_end_dt.tzinfo is None:
            time_end_dt = MOSCOW_TZ.localize(time_end_dt)
        time_end_str = time_end_dt.isoformat()

        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO punishment_time (chat_id, user_id, types, time_end)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (chat_id, user_id, types) DO UPDATE SET time_end = EXCLUDED.time_end
            ''', chat_id, user_id, 'mute', time_end_str)   # ← строка, а не datetime
            logger.info(f"Мут сохранён: chat {chat_id}, user {user_id}, до {time_end_str}")
    except Exception as e:
        logger.error(f"Ошибка в update_mute_info_type: {e}", exc_info=True)


async def remove_mute_info(chat_id: int, user_id: int) -> None:
    """Удаляет всю информацию о муте пользователя."""
    try:
        logger.info(f"remove_mute_info: chat_id={chat_id}, user_id={user_id}")
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM punishment_time WHERE chat_id = $1 AND user_id = $2 AND types = $3',
                chat_id, user_id, 'mute'
            )
            await conn.execute(
                'DELETE FROM mutes WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )
    except Exception as e:
        logger.error(f"Ошибка в remove_mute_info: {e}", exc_info=True)


async def get_mute_info(chat_id: int, user_id: int) -> Optional[str]:
    """Возвращает время окончания мута (time_end)."""
    try:
        logger.info(f"get_mute_info: chat_id={chat_id}, user_id={user_id}")
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT time_end FROM punishment_time WHERE chat_id = $1 AND user_id = $2 AND types = $3',
                chat_id, user_id, 'mute'
            )
            result = row['time_end'] if row else None
            logger.info(f"get_mute_info result: {result}")
            return result
    except Exception as e:
        logger.error(f"Ошибка в get_mute_info: {e}", exc_info=True)
        return None


async def get_mute_details(chat_id: int, user_id: int) -> Optional[Tuple[int, str, str]]:
    """Возвращает (admin_id, reason, duration) мута."""
    try:
        logger.info(f"get_mute_details: chat_id={chat_id}, user_id={user_id}")
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT admin_id, reason, duration FROM mutes WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )
            if row:
                result = (row['admin_id'], row['reason'], row['duration'])
                logger.info(f"get_mute_details found: admin_id={result[0]}, reason={result[1]}, duration={result[2]}")
                return result
            logger.info(f"get_mute_details: не найдено для user_id={user_id}")
            return None
    except Exception as e:
        logger.error(f"Ошибка в get_mute_details: {e}", exc_info=True)
        return None


async def get_all_mutes(chat_id: int, offset: int = 0, limit: int = MUTES_PER_PAGE) -> List[Tuple[int, str]]:
    """Возвращает список замученных (user_id, time_end) с пагинацией."""
    try:
        logger.info(f"get_all_mutes: chat_id={chat_id}, offset={offset}, limit={limit}")
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем временные муты из punishment_time
            temp_mutes = await conn.fetch('''
                SELECT user_id, time_end FROM punishment_time 
                WHERE chat_id = $1 AND types = $2 
                ORDER BY time_end DESC
            ''', chat_id, 'mute')

            # Получаем вечные муты из mutes (у которых duration = 'навсегда')
            permanent_mutes = await conn.fetch('''
                SELECT user_id FROM mutes 
                WHERE chat_id = $1 AND duration = $2
                AND user_id NOT IN (
                    SELECT user_id FROM punishment_time 
                    WHERE chat_id = $1 AND types = 'mute'
                )
            ''', chat_id, 'навсегда')

            # Объединяем результаты
            all_mutes = []

            # Добавляем временные муты с их time_end
            for row in temp_mutes:
                all_mutes.append((row['user_id'], row['time_end']))

            # Добавляем вечные муты с time_end = None
            for row in permanent_mutes:
                all_mutes.append((row['user_id'], None))

            logger.info(
                f"Всего мутов: временных={len(temp_mutes)}, вечных={len(permanent_mutes)}, всего={len(all_mutes)}")

            # Применяем пагинацию
            start_idx = offset
            end_idx = min(offset + limit, len(all_mutes))
            paginated_mutes = all_mutes[start_idx:end_idx]

            logger.info(f"После пагинации: {len(paginated_mutes)} мутов")

            # Логирование найденных строк
            for i, (user_id, time_end) in enumerate(paginated_mutes):
                logger.info(f"Строка {i}: user_id={user_id}, time_end={time_end}")

            return paginated_mutes
    except Exception as e:
        logger.error(f"Ошибка в get_all_mutes: {e}", exc_info=True)
        return []


async def get_total_mutes_count(chat_id: int) -> int:
    """Возвращает общее количество активных мутов в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Считаем временные муты
            temp_count = await conn.fetchval(
                'SELECT COUNT(*) FROM punishment_time WHERE chat_id = $1 AND types = $2',
                chat_id, 'mute'
            ) or 0

            # Считаем вечные муты, которых нет в punishment_time
            permanent_count = await conn.fetchval('''
                SELECT COUNT(*) FROM mutes 
                WHERE chat_id = $1 AND duration = $2
                AND user_id NOT IN (
                    SELECT user_id FROM punishment_time 
                    WHERE chat_id = $1 AND types = 'mute'
                )
            ''', chat_id, 'навсегда') or 0

            total = temp_count + permanent_count
            logger.info(
                f"get_total_mutes_count: chat_id={chat_id}, временные={temp_count}, вечные={permanent_count}, всего={total}")
            return total
    except Exception as e:
        logger.error(f"Ошибка в get_total_mutes_count: {e}", exc_info=True)
        return 0


async def get_expired_mutes() -> List[Tuple[int, int]]:
    """Возвращает все истёкшие муты (chat_id, user_id)."""
    try:
        from pytz import timezone
        MOSCOW_TZ = timezone('Europe/Moscow')

        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = datetime.now(MOSCOW_TZ)
            rows = await conn.fetch('''
                SELECT chat_id, user_id FROM punishment_time 
                WHERE types = $1 AND time_end <= $2
            ''', 'mute', current_time)

            logger.info(f"get_expired_mutes: найдено {len(rows)} истёкших мутов")

            # Удаляем эти муты из таблицы mutes
            for row in rows:
                await conn.execute(
                    'DELETE FROM mutes WHERE chat_id = $1 AND user_id = $2',
                    row['chat_id'], row['user_id']
                )

            return [(row['chat_id'], row['user_id']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []