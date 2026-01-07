import logging
import re
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from pytz import timezone as pytz_timezone

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

WARNS_PER_PAGE = 10
MOSCOW_TZ = pytz_timezone('Europe/Moscow')

time_units = {
    'минуту': 'minutes', 'минуты': 'minutes', 'минут': 'minutes',
    'час': 'hours', 'часа': 'hours', 'часов': 'hours',
    'день': 'days', 'дня': 'days', 'дней': 'days',
    'неделю': 'weeks', 'недели': 'weeks', 'недель': 'weeks',
    'месяц': 'months', 'месяца': 'months', 'месяцев': 'months',
    'год': 'years', 'года': 'years', 'лет': 'years',
    'век': 'centuries', 'века': 'centuries', 'веков': 'centuries',
    # Сокращения
    'мин': 'minutes',
    'ч': 'hours',
    'д': 'days',
    'н': 'weeks',
    'м': 'months',
    'г': 'years',
    'в': 'centuries'
}


def format_duration(delta: timedelta) -> str:
    """Форматирует timedelta в красивый текст на русском."""
    total_seconds = int(delta.total_seconds())
    years = total_seconds // (365 * 24 * 3600)
    months = (total_seconds % (365 * 24 * 3600)) // (30 * 24 * 3600)
    weeks = (total_seconds % (30 * 24 * 3600)) // (7 * 24 * 3600)
    days = (total_seconds % (7 * 24 * 3600)) // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []

    def append_part(value, forms):
        if value:
            if value % 10 == 1 and value % 100 != 11:
                parts.append(f"{value} {forms[0]}")
            elif 2 <= value % 10 <= 4 and not (10 <= value % 100 <= 20):
                parts.append(f"{value} {forms[1]}")
            else:
                parts.append(f"{value} {forms[2]}")

    append_part(years, ["год", "года", "лет"])
    append_part(months, ["месяц", "месяца", "месяцев"])
    append_part(weeks, ["неделю", "недели", "недель"])
    append_part(days, ["день", "дня", "дней"])
    append_part(hours, ["час", "часа", "часов"])
    append_part(minutes, ["минуту", "минуты", "минут"])

    return " ".join(parts) if parts else "меньше минуты"


def parse_time_string(time_str: str) -> Optional[timedelta]:
    """Парсит строку времени и возвращает timedelta."""
    if not time_str:
        return timedelta(days=1)

    time_str = time_str.lower().strip()

    # Обработка простых форм
    simple_units = {
        'минута': '1 мин', 'час': '1 ч', 'день': '1 д',
        'неделя': '1 н', 'месяц': '1 м', 'год': '1 г'
    }
    if time_str in simple_units:
        time_str = simple_units[time_str]

    pattern = r'(\d+)\s*([а-яa-z]+)'
    matches = re.findall(pattern, time_str)

    if not matches:
        return None

    total_delta = timedelta()
    for value, unit in matches:
        value = int(value)
        unit_key = None
        for key in sorted(time_units.keys(), key=len, reverse=True):
            if unit.startswith(key):
                unit_key = key
                break
        if not unit_key:
            return None

        time_type = time_units[unit_key]
        if time_type == 'minutes':
            total_delta += timedelta(minutes=value)
        elif time_type == 'hours':
            total_delta += timedelta(hours=value)
        elif time_type == 'days':
            total_delta += timedelta(days=value)
        elif time_type == 'weeks':
            total_delta += timedelta(weeks=value)
        elif time_type == 'months':
            total_delta += timedelta(days=value * 30)  # Ограничим 30 днями на месяц
        elif time_type == 'years':
            # Ограничим 50 годами для предотвращения переполнения
            if value > 50:
                value = 50
            total_delta += timedelta(days=value * 365)
        # Убираем обработку веков, она вызывает переполнение

    # Дополнительная проверка на максимальное значение
    # Максимальное значение timedelta в Python примерно 999999999 дней
    # Ограничим 36500 дней (100 лет)
    MAX_DAYS = 36500
    if total_delta.days > MAX_DAYS:
        total_delta = timedelta(days=MAX_DAYS)

    return total_delta

# Специальные ключевые слова для времени
SPECIAL_DURATIONS = {
    'навсегда': 'forever',
    'перманентно': 'forever',
    'навечно': 'forever',
    'вечно': 'forever',
    'permanent': 'forever',
    'forever': 'forever',
    'бессрочно': 'forever',
    'доотзыва': 'forever',
    'снятия': 'forever'
}


def parse_warn_duration(time_str: str) -> Optional[timedelta]:
    """Парсит строку времени для варна, возвращает None для навсегда."""
    if not time_str:
        return None  # Используем по умолчанию

    time_str = time_str.lower().strip()

    # Проверяем специальные ключевые слова
    for keyword in SPECIAL_DURATIONS:
        if keyword in time_str:
            return None  # None означает "навсегда"

    # Используем существующую функцию парсинга
    return parse_time_string(time_str)


def get_moscow_datetime() -> datetime:
    """Возвращает текущее время в московской таймзоне."""
    return datetime.now(MOSCOW_TZ)


def ensure_moscow_time(dt: datetime) -> datetime:
    """Обеспечивает, что datetime имеет московскую таймзону."""
    if dt.tzinfo is None:
        return MOSCOW_TZ.localize(dt)
    return dt.astimezone(MOSCOW_TZ)


async def get_column_types() -> dict:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetch('''
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'warns' 
                AND column_name IN ('created_at', 'expires_at')
                ORDER BY column_name;
            ''')
            # Возвращаем словарь с результатами
            return {row['column_name']: row['data_type'] for row in result} if result else {}
    except Exception as e:
        logger.error(f"Error checking column types: {e}")
        # Возвращаем пустой словарь вместо None
        return {}


def prepare_datetime_for_db(dt: datetime, column_type: str) -> object:
    """Подготавливает datetime для вставки в БД в зависимости от типа колонки."""
    if not column_type:
        # Если тип колонки не определен, используем timestamp
        return dt

    if column_type in ['timestamp with time zone', 'timestamp without time zone', 'timestamp']:
        return dt
    else:
        # Для TEXT и других типов преобразуем в строку
        return dt.isoformat()


# -------------------------
# НАСТРОЙКИ ВАРНОВ
# -------------------------

async def get_default_warn_duration(chat_id: int) -> timedelta:
    """Возвращает время действия варна (по умолчанию — неделя)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT time FROM default_time WHERE chat_id = $1 AND type = $2',
                chat_id, 'warn'
            )
            if row and row['time']:
                parsed = parse_time_string(row['time'])
                return parsed if parsed else timedelta(weeks=1)
    except Exception as e:
        logger.error(e, exc_info=True)
    return timedelta(weeks=1)


async def set_default_warn_duration(chat_id: int, duration_str: str) -> None:
    """Устанавливает длительность варна по умолчанию."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO default_time (chat_id, type, time)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, type) DO UPDATE SET time = EXCLUDED.time
            ''', chat_id, 'warn', duration_str)
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_warn_action(chat_id: int) -> str:
    """Возвращает действие при превышении лимита (ban/mute/kick)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT action FROM warn_settings WHERE chat_id = $1',
                chat_id
            )
            return row['action'] if row else 'ban'
    except Exception as e:
        logger.error(e, exc_info=True)
        return 'ban'


async def set_warn_action(chat_id: int, action: str) -> None:
    """Устанавливает действие при превышении лимита."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO warn_settings (chat_id, action)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE SET action = EXCLUDED.action
            ''', chat_id, action)
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_warn_limit(chat_id: int) -> int:
    """Возвращает лимит варнов (по умолчанию — 3)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT warn_limit FROM warn_settings WHERE chat_id = $1',
                chat_id
            )
            return row['warn_limit'] if row else 3
    except Exception as e:
        logger.error(e, exc_info=True)
        return 3


async def set_warn_limit(chat_id: int, limit: int) -> None:
    """Устанавливает лимит варнов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO warn_settings (chat_id, warn_limit)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE SET warn_limit = EXCLUDED.warn_limit
            ''', chat_id, limit)
    except Exception as e:
        logger.error(e, exc_info=True)


# -------------------------
# РАБОТА С ВАРНАМИ (универсальная версия)
# -------------------------

async def add_warn(chat_id: int, user_id: int, admin_id: int, reason: str = "Не указана",
                   duration: Optional[timedelta] = None) -> int:
    """Добавляет варн и возвращает новое количество активных варнов."""
    try:
        now = get_moscow_datetime()

        # Определяем длительность варна
        if duration is None:
            duration = await get_default_warn_duration(chat_id)

        # Если duration = None (навсегда), устанавливаем дату истечения очень далеко в будущем
        if duration is None:
            # Устанавливаем дату истечения через 100 лет (по сути "навсегда")
            expires_at = now + timedelta(days=36525)  # 100 лет
        else:
            expires_at = now + duration

        # Получаем типы колонок
        column_types = await get_column_types()
        created_type = column_types.get('created_at', 'text')
        expires_type = column_types.get('expires_at', 'text')

        # Подготавливаем значения для БД
        created_value = prepare_datetime_for_db(now, created_type)
        expires_value = prepare_datetime_for_db(expires_at, expires_type)

        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', chat_id, user_id, admin_id, reason, created_value, expires_value)

        return await get_user_warns_count(chat_id, user_id)
    except Exception as e:
        logger.error(f"Error in add_warn: {e}", exc_info=True)
        return await get_user_warns_count(chat_id, user_id)


async def remove_warn(chat_id: int, user_id: int, warn_id: Optional[int] = None) -> int:
    """Удаляет варн: по номеру (1,2,3...) или последний."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            if warn_id:
                # Получаем активные варны в порядке старшинства
                rows = await conn.fetch('''
                    SELECT id FROM warns 
                    WHERE chat_id = $1 AND user_id = $2 AND expires_at > $3
                    ORDER BY created_at ASC
                ''', chat_id, user_id, now_value)

                if 1 <= warn_id <= len(rows):
                    real_id = rows[warn_id - 1]['id']
                    await conn.execute('DELETE FROM warns WHERE id = $1', real_id)
            else:
                # Удаляем самый свежий варн
                await conn.execute('''
                    DELETE FROM warns WHERE id = (
                        SELECT id FROM warns 
                        WHERE chat_id = $1 AND user_id = $2 AND expires_at > $3
                        ORDER BY created_at DESC LIMIT 1
                    )
                ''', chat_id, user_id, now_value)

        return await get_user_warns_count(chat_id, user_id)
    except Exception as e:
        logger.error(e, exc_info=True)
        return await get_user_warns_count(chat_id, user_id)


async def get_user_warns_count(chat_id: int, user_id: int) -> int:
    """Возвращает количество активных варнов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            count = await conn.fetchval('''
                SELECT COUNT(*) FROM warns 
                WHERE chat_id = $1 AND user_id = $2 AND expires_at > $3
            ''', chat_id, user_id, now_value)
            return count or 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_user_warns(chat_id: int, user_id: int) -> List[Tuple]:
    """Возвращает список варнов с относительными ID."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            rows = await conn.fetch('''
                SELECT id, admin_id, reason, created_at, expires_at 
                FROM warns 
                WHERE chat_id = $1 AND user_id = $2 AND expires_at > $3
                ORDER BY created_at ASC
            ''', chat_id, user_id, now_value)

            result = []
            for i, row in enumerate(rows, 1):
                # Преобразуем значения в datetime если нужно
                created_at = row['created_at']
                expires_at = row['expires_at']

                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except (ValueError, TypeError):
                        created_at = get_moscow_datetime()

                if isinstance(expires_at, str):
                    try:
                        expires_at = datetime.fromisoformat(expires_at)
                    except (ValueError, TypeError):
                        expires_at = get_moscow_datetime()

                # Приводим к московскому времени
                created_at = ensure_moscow_time(created_at)
                expires_at = ensure_moscow_time(expires_at)

                result.append((i, row['admin_id'], row['reason'],
                               created_at, expires_at, row['id']))
            return result
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_all_warns(chat_id: int, offset: int = 0, limit: int = WARNS_PER_PAGE) -> List[Tuple]:
    """Возвращает статистику по варнам (пользователи с количеством)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            rows = await conn.fetch('''
                SELECT user_id, COUNT(*) as warn_count 
                FROM warns 
                WHERE chat_id = $1 AND expires_at > $2
                GROUP BY user_id 
                ORDER BY warn_count DESC
                LIMIT $3 OFFSET $4
            ''', chat_id, now_value, limit, offset)
            return [(row['user_id'], row['warn_count']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_total_warns_count(chat_id: int) -> int:
    """Возвращает количество пользователей с активными варнами."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            count = await conn.fetchval('''
                SELECT COUNT(DISTINCT user_id) FROM warns 
                WHERE chat_id = $1 AND expires_at > $2
            ''', chat_id, now_value)
            return count or 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0


async def get_warn_details(warn_id: int) -> Optional[Tuple]:
    """Возвращает детали варна по ID."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT chat_id, user_id, admin_id, reason, created_at, expires_at 
                FROM warns 
                WHERE id = $1
            ''', warn_id)
            if row:
                # Обрабатываем даты
                created_at = row['created_at']
                expires_at = row['expires_at']

                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except (ValueError, TypeError):
                        created_at = get_moscow_datetime()

                if isinstance(expires_at, str):
                    try:
                        expires_at = datetime.fromisoformat(expires_at)
                    except (ValueError, TypeError):
                        expires_at = get_moscow_datetime()

                created_at = ensure_moscow_time(created_at)
                expires_at = ensure_moscow_time(expires_at)

                return (row['chat_id'], row['user_id'], row['admin_id'],
                        row['reason'], created_at, expires_at)
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def clear_user_warns(chat_id: int, user_id: int) -> None:
    """Очищает все варны пользователя."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM warns WHERE chat_id = $1 AND user_id = $2', chat_id, user_id)
    except Exception as e:
        logger.error(e, exc_info=True)


async def clear_expired_warns() -> None:
    """Очищает истёкшие варны."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))
            await conn.execute('DELETE FROM warns WHERE expires_at <= $1', now_value)
    except Exception as e:
        logger.error(e, exc_info=True)


async def get_warn_relative_id(chat_id: int, user_id: int, real_warn_id: int) -> int:
    """Возвращает относительный номер варна (1, 2, 3...)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now = get_moscow_datetime()
            column_types = await get_column_types()
            now_value = prepare_datetime_for_db(now, column_types.get('expires_at', 'text'))

            rows = await conn.fetch('''
                SELECT id FROM warns 
                WHERE chat_id = $1 AND user_id = $2 AND expires_at > $3
                ORDER BY created_at ASC
            ''', chat_id, user_id, now_value)
            for i, row in enumerate(rows, 1):
                if row['id'] == real_warn_id:
                    return i
            return 0
    except Exception as e:
        logger.error(e, exc_info=True)
        return 0