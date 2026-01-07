import logging
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta, timezone
from pytz import timezone as pytz_timezone

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string

logger = logging.getLogger(__name__)

BANS_PER_PAGE = 10
MOSCOW_TZ = pytz_timezone('Europe/Moscow')


# ======================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ======================

async def get_default_ban_duration(chat_id: int) -> Optional[timedelta]:
    """Возвращает timedelta по умолчанию для бана в чате или None (навсегда)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT time FROM default_time WHERE chat_id = $1 AND type = $2',
                chat_id, 'ban'
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


async def set_default_ban_duration(chat_id: int, duration_str: str) -> None:
    """Сохраняет строку времени как настройку по умолчанию для типа 'ban'."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO default_time (chat_id, type, time)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, type) DO UPDATE SET time = EXCLUDED.time
            ''', chat_id, 'ban', duration_str)
    except Exception as e:
        logger.error(e, exc_info=True)


# ======================
# РАБОТА С БАНАМИ В БД
# ======================

async def update_ban_info(chat_id: int, user_id: int, admin_id: int, reason: str, duration_text: str) -> None:
    """Сохраняет или обновляет информацию о бане."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bans (chat_id, user_id, admin_id, reason, duration)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    admin_id = EXCLUDED.admin_id,
                    reason = EXCLUDED.reason,
                    duration = EXCLUDED.duration
            ''', chat_id, user_id, admin_id, reason, duration_text)
    except Exception as e:
        logger.error(e, exc_info=True)


async def update_ban_info_type(chat_id: int, user_id: int, time_end: str) -> None:
    """Сохраняет или обновляет время окончания бана в punishment_time.
    Для вечных банов (duration == 'навсегда') не вызывается."""
    try:
        # Преобразуем строку в datetime
        try:
            time_end_dt = datetime.fromisoformat(time_end)
        except ValueError:
            logger.error(f"Invalid time_end format: {time_end}, converting to proper format")
            if time_end.isdigit():
                minutes = int(time_end)
                time_end_dt = datetime.now(MOSCOW_TZ) + timedelta(minutes=minutes)
            else:
                time_end_dt = datetime.now(MOSCOW_TZ) + timedelta(hours=1)

        # Приводим к aware datetime с московским поясом
        if time_end_dt.tzinfo is None:
            time_end_dt = MOSCOW_TZ.localize(time_end_dt)

        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Сначала пробуем обновить существующую запись
            result = await conn.execute('''
                UPDATE punishment_time 
                SET time_end = $1 
                WHERE chat_id = $2 AND user_id = $3 AND types = $4
            ''', time_end_dt, chat_id, user_id, 'ban')

            # Если запись не была обновлена (не существует), то вставляем новую
            if result == "UPDATE 0":
                await conn.execute('''
                    INSERT INTO punishment_time (chat_id, user_id, types, time_end)
                    VALUES ($1, $2, $3, $4)
                ''', chat_id, user_id, 'ban', time_end_dt)

    except Exception as e:
        logger.error(e, exc_info=True)

async def remove_ban_info(chat_id: int, user_id: int) -> None:
    """Удаляет всю информацию о бане пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM punishment_time WHERE chat_id = $1 AND user_id = $2 AND types = $3',
                chat_id, user_id, 'ban'
            )
            await conn.execute(
                'DELETE FROM bans WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_ban_info(chat_id: int, user_id: int) -> Optional[str]:
    """Возвращает время окончания бана (time_end)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT time_end FROM punishment_time WHERE chat_id = $1 AND user_id = $2 AND types = $3',
                chat_id, user_id, 'ban'
            )
            if row and row['time_end']:
                # Возвращаем строку в ISO формате
                if isinstance(row['time_end'], datetime):
                    return row['time_end'].isoformat()
                return str(row['time_end'])
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_ban_details(chat_id: int, user_id: int) -> Optional[Tuple[int, str, str]]:
    """Возвращает (admin_id, reason, duration) бана."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT admin_id, reason, duration FROM bans WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )
            if row:
                return (row['admin_id'], row['reason'] or "Не указана", row['duration'] or "Неизвестно")
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_all_bans(chat_id: int, offset: int = 0, limit: int = BANS_PER_PAGE) -> List[Tuple[int, str]]:
    """Возвращает список забаненных (user_id, time_end) с пагинацией."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем временные баны из punishment_time
            temp_bans = await conn.fetch('''
                SELECT user_id, time_end FROM punishment_time 
                WHERE chat_id = $1 AND types = $2 
                ORDER BY time_end DESC
            ''', chat_id, 'ban')

            # Получаем вечные баны из bans (у которых duration = 'навсегда')
            permanent_bans = await conn.fetch('''
                SELECT user_id FROM bans 
                WHERE chat_id = $1 AND duration = $2
                AND user_id NOT IN (
                    SELECT user_id FROM punishment_time 
                    WHERE chat_id = $1 AND types = 'ban'
                )
            ''', chat_id, 'навсегда')

            # Объединяем результаты
            all_bans = []

            # Добавляем временные баны с их time_end
            for row in temp_bans:
                time_end = row['time_end']
                if isinstance(time_end, datetime):
                    time_end_str = time_end.isoformat()
                else:
                    time_end_str = str(time_end) if time_end else ""
                all_bans.append((row['user_id'], time_end_str))

            # Добавляем вечные баны с time_end = None
            for row in permanent_bans:
                all_bans.append((row['user_id'], None))

            # Применяем пагинацию
            start_idx = offset
            end_idx = min(offset + limit, len(all_bans))
            paginated_bans = all_bans[start_idx:end_idx]

            return paginated_bans
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_total_bans_count(chat_id: int) -> int:
    """Возвращает общее количество активных банов в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Считаем временные баны
            temp_count = await conn.fetchval(
                'SELECT COUNT(*) FROM punishment_time WHERE chat_id = $1 AND types = $2',
                chat_id, 'ban'
            ) or 0

            # Считаем вечные баны, которых нет в punishment_time
            permanent_count = await conn.fetchval('''
                SELECT COUNT(*) FROM bans 
                WHERE chat_id = $1 AND duration = $2
                AND user_id NOT IN (
                    SELECT user_id FROM punishment_time 
                    WHERE chat_id = $1 AND types = 'ban'
                )
            ''', chat_id, 'навсегда') or 0

            total = temp_count + permanent_count
            logger.info(
                f"get_total_bans_count: chat_id={chat_id}, временные={temp_count}, вечные={permanent_count}, всего={total}")
            return total
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_expired_bans() -> List[Tuple[int, int]]:
    """Возвращает все истёкшие баны (chat_id, user_id)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = datetime.now(MOSCOW_TZ)
            rows = await conn.fetch('''
                SELECT chat_id, user_id FROM punishment_time 
                WHERE types = $1 AND time_end <= $2
            ''', 'ban', current_time)

            # Удаляем эти баны из таблицы bans
            for row in rows:
                await conn.execute(
                    'DELETE FROM bans WHERE chat_id = $1 AND user_id = $2',
                    row['chat_id'], row['user_id']
                )

            return [(row['chat_id'], row['user_id']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []

# ======================
# НОВЫЕ МЕТОДЫ ДЛЯ БАНОВ ПОЛЬЗОВАТЕЛЯ ВО ВСЕХ ЧАТАХ
# ======================

async def get_user_bans_all_chats(user_id: int, check_membership: bool = True) -> List[Dict[str, Any]]:
    """Возвращает все баны пользователя во всех чатах."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Базовый запрос для временных банов из punishment_time
            temp_bans_query = '''
                SELECT 
                    pt.chat_id,
                    pt.time_end,
                    b.admin_id,
                    b.reason,
                    b.duration
                FROM punishment_time pt
                LEFT JOIN bans b ON pt.chat_id = b.chat_id AND pt.user_id = b.user_id
                WHERE pt.user_id = $1 AND pt.types = 'ban'
            '''

            # Запрос для вечных банов из bans
            permanent_bans_query = '''
                SELECT 
                    b.chat_id,
                    NULL as time_end,
                    b.admin_id,
                    b.reason,
                    b.duration
                FROM bans b
                WHERE b.user_id = $1 AND b.duration = 'навсегда'
                AND NOT EXISTS (
                    SELECT 1 FROM punishment_time pt 
                    WHERE pt.chat_id = b.chat_id AND pt.user_id = b.user_id AND pt.types = 'ban'
                )
            '''

            # Добавляем условие для проверки членства если нужно
            if check_membership:
                temp_bans_query += '''
                    AND EXISTS (
                        SELECT 1 FROM full_users_chats fuc 
                        WHERE fuc.chat_id = pt.chat_id AND fuc.user_id = pt.user_id
                    )
                '''
                permanent_bans_query += '''
                    AND EXISTS (
                        SELECT 1 FROM full_users_chats fuc 
                        WHERE fuc.chat_id = b.chat_id AND fuc.user_id = b.user_id
                    )
                '''

            # Объединяем оба запроса
            query = f'''
                {temp_bans_query}
                UNION ALL
                {permanent_bans_query}
                ORDER BY time_end DESC NULLS LAST
            '''

            rows = await conn.fetch(query, user_id)

            result = []
            for row in rows:
                # Получаем время окончания
                time_end = row['time_end']
                if time_end:
                    if isinstance(time_end, datetime):
                        time_end_dt = time_end
                        time_end_str = time_end.isoformat()
                    else:
                        try:
                            time_end_dt = datetime.fromisoformat(str(time_end))
                            time_end_str = str(time_end)
                        except (ValueError, TypeError):
                            time_end_dt = datetime.now(MOSCOW_TZ)
                            time_end_str = ""
                else:
                    time_end_dt = None
                    time_end_str = None

                # Приводим к московскому часовому поясу если нужно
                if time_end_dt and time_end_dt.tzinfo is None:
                    time_end_dt = MOSCOW_TZ.localize(time_end_dt)

                result.append({
                    'chat_id': row['chat_id'],
                    'time_end': time_end_str,
                    'time_end_dt': time_end_dt,
                    'admin_id': row['admin_id'],
                    'reason': row['reason'] or "Не указана",
                    'duration': row['duration'] or "Неизвестно",
                    'is_permanent': time_end_dt is None
                })
            return result
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_bans_by_user_all_chats(admin_id: int) -> List[Dict[str, Any]]:
    """Возвращает все баны, выданные пользователем во всех чатах."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT 
                    b.chat_id,
                    b.user_id,
                    b.reason,
                    b.duration,
                    pt.time_end
                FROM bans b
                LEFT JOIN punishment_time pt ON b.chat_id = pt.chat_id AND b.user_id = pt.user_id AND pt.types = 'ban'
                WHERE b.admin_id = $1
                ORDER BY pt.time_end DESC
            ''', admin_id)

            result = []
            for row in rows:
                time_end = row['time_end']
                if isinstance(time_end, datetime):
                    time_end_dt = time_end
                    time_end_str = time_end.isoformat()
                elif time_end:
                    try:
                        time_end_dt = datetime.fromisoformat(str(time_end))
                        time_end_str = str(time_end)
                    except (ValueError, TypeError):
                        time_end_dt = datetime.now(MOSCOW_TZ)
                        time_end_str = ""
                else:
                    time_end_dt = datetime.now(MOSCOW_TZ)
                    time_end_str = ""

                # Приводим к московскому часовому поясу если нужно
                if time_end_dt.tzinfo is None:
                    time_end_dt = MOSCOW_TZ.localize(time_end_dt)

                result.append({
                    'chat_id': row['chat_id'],
                    'user_id': row['user_id'],
                    'time_end': time_end_str,
                    'time_end_dt': time_end_dt,
                    'reason': row['reason'] or "Не указана",
                    'duration': row['duration'] or "Неизвестно"
                })
            return result
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_user_active_bans_count(user_id: int, check_membership: bool = True) -> int:
    """Возвращает количество активных банов пользователя во всех чатах."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = datetime.now(MOSCOW_TZ)

            # Считаем временные баны (истекающие в будущем)
            temp_count_query = '''
                SELECT COUNT(*) FROM punishment_time pt
                WHERE pt.user_id = $1 AND pt.types = 'ban' 
                AND pt.time_end > $2
            '''

            # Считаем вечные баны
            permanent_count_query = '''
                SELECT COUNT(*) FROM bans b
                WHERE b.user_id = $1 AND b.duration = 'навсегда'
                AND NOT EXISTS (
                    SELECT 1 FROM punishment_time pt 
                    WHERE pt.chat_id = b.chat_id AND pt.user_id = b.user_id AND pt.types = 'ban'
                )
            '''

            # Добавляем условие проверки членства если нужно
            if check_membership:
                temp_count_query += '''
                    AND EXISTS (
                        SELECT 1 FROM full_users_chats fuc 
                        WHERE fuc.chat_id = pt.chat_id AND fuc.user_id = pt.user_id
                    )
                '''
                permanent_count_query += '''
                    AND EXISTS (
                        SELECT 1 FROM full_users_chats fuc 
                        WHERE fuc.chat_id = b.chat_id AND fuc.user_id = b.user_id
                    )
                '''

            # Выполняем оба запроса
            temp_count = await conn.fetchval(temp_count_query, user_id, current_time) or 0
            permanent_count = await conn.fetchval(permanent_count_query, user_id) or 0

            return temp_count + permanent_count
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_bans_given_by_user_count(admin_id: int) -> int:
    """Возвращает количество банов, выданных пользователем во всех чатах."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM bans WHERE admin_id = $1
            ''', admin_id)
            return count or 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def check_user_was_in_chat(user_id: int, chat_id: int) -> bool:
    """Проверяет, был ли пользователь в чате (по таблице full_users_chats)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT 1 FROM full_users_chats WHERE user_id = $1 AND chat_id = $2',
                user_id, chat_id
            )
            return bool(result)
    except Exception as e:
        logger.error(e, exc_info=True)
        return False