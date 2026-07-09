import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import pytz
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# Константы часовых поясов
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Константа для количества неудачных попыток
MAX_FAILED_ATTEMPTS = 3


async def create_scheduled_changes_table():
    """Создает таблицу для запланированных изменений чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Основная таблица
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_chat_changes (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    change_type VARCHAR(20) NOT NULL CHECK (change_type IN ('title', 'avatar', 'description')),
                    new_value TEXT NOT NULL,
                    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    repeat_type VARCHAR(20) NOT NULL DEFAULT 'once'
                        CHECK (repeat_type IN ('once', 'daily', 'weekly', 'monthly', 'yearly')),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by BIGINT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_applied TIMESTAMP WITH TIME ZONE,
                    file_id TEXT,
                    file_unique_id TEXT,
                    notes TEXT,
                    timezone VARCHAR(50) DEFAULT 'Europe/Moscow'
                )
            ''')

            # Индексы
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_chat_active
                ON scheduled_chat_changes(chat_id, is_active)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_scheduled_time_active
                ON scheduled_chat_changes(scheduled_time)
                WHERE is_active = TRUE
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_chat_created_by
                ON scheduled_chat_changes(chat_id, created_by)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_change_type
                ON scheduled_chat_changes(change_type)
            ''')
            logger.info("Таблица для запланированных изменений создана/проверена")
    except Exception as e:
        logger.error(f"Ошибка создания таблиц: {e}", exc_info=True)


def localize_to_moscow(dt: datetime) -> datetime:
    """Локализует время в московский часовой пояс."""
    if dt.tzinfo is None:
        return MOSCOW_TZ.localize(dt)
    return dt.astimezone(MOSCOW_TZ)


def convert_to_utc(dt: datetime) -> datetime:
    """Конвертирует время в UTC."""
    moscow_time = localize_to_moscow(dt)
    return moscow_time.astimezone(pytz.UTC)


async def add_scheduled_change(
        chat_id: int,
        change_type: str,
        new_value: str,
        scheduled_time: datetime,
        repeat_type: str,
        created_by: int,
        file_id: Optional[str] = None,
        file_unique_id: Optional[str] = None,
        notes: Optional[str] = None
) -> bool:
    """Добавляет запланированное изменение."""
    try:
        scheduled_time_utc = convert_to_utc(scheduled_time)
        pool = get_db_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow('''
                SELECT id FROM scheduled_chat_changes
                WHERE chat_id = $1 AND change_type = $2 AND scheduled_time = $3
                AND repeat_type = $4 AND is_active = TRUE
            ''', chat_id, change_type, scheduled_time_utc, repeat_type)
            if existing:
                return False

            await conn.execute('''
                INSERT INTO scheduled_chat_changes
                (chat_id, change_type, new_value, scheduled_time, repeat_type,
                 created_by, file_id, file_unique_id, notes, timezone)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'Europe/Moscow')
            ''', chat_id, change_type, new_value, scheduled_time_utc,
                               repeat_type, created_by, file_id, file_unique_id, notes)
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления запланированного изменения: {e}", exc_info=True)
        return False


async def record_failed_attempt(change_id: int, error_message: str) -> bool:
    """
    Отмечает неудачную попытку и удаляет изменение после 3 неудач.
    Использует существующие колонки.
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем информацию об изменении
            row = await conn.fetchrow(
                'SELECT repeat_type, notes FROM scheduled_chat_changes WHERE id = $1 AND is_active = TRUE',
                change_id
            )
            if not row:
                return False

            # Используем notes для хранения количества попыток
            # Формат: "failed:2|ошибка"
            notes = row['notes'] or ''
            failed_count = 0

            if notes.startswith('failed:'):
                try:
                    parts = notes.split('|', 1)
                    failed_count = int(parts[0].replace('failed:', ''))
                except:
                    failed_count = 0

            failed_count += 1
            new_notes = f"failed:{failed_count}|{error_message[:200]}"

            # Обновляем notes
            await conn.execute('''
                UPDATE scheduled_chat_changes
                SET notes = $1
                WHERE id = $2
            ''', new_notes, change_id)

            # Если 3 неудачные попытки - удаляем
            if failed_count >= 3:
                logger.warning(f"Изменение {change_id} удалено после {failed_count} неудачных попыток")
                await conn.execute('DELETE FROM scheduled_chat_changes WHERE id = $1', change_id)
                return True

            return False
    except Exception as e:
        logger.error(f"Ошибка записи неудачной попытки: {e}", exc_info=True)
        return False


async def reset_failed_attempts(change_id: int) -> bool:
    """Сбрасывает счетчик неудачных попыток."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем текущие notes
            row = await conn.fetchrow(
                'SELECT notes FROM scheduled_chat_changes WHERE id = $1',
                change_id
            )
            if not row:
                return False

            notes = row['notes'] or ''

            # Если есть запись о неудачах, убираем её
            if notes.startswith('failed:'):
                # Оставляем только описание если оно было
                parts = notes.split('|', 1)
                if len(parts) > 1 and parts[1]:
                    new_notes = parts[1]
                else:
                    new_notes = ''
            else:
                new_notes = notes

            await conn.execute('''
                UPDATE scheduled_chat_changes
                SET notes = $1
                WHERE id = $2
            ''', new_notes, change_id)
            return True
    except Exception as e:
        logger.error(f"Ошибка сброса счетчика попыток: {e}", exc_info=True)
        return False


async def get_failed_attempts(change_id: int) -> int:
    """Возвращает количество неудачных попыток."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT notes FROM scheduled_chat_changes WHERE id = $1',
                change_id
            )
            if not row or not row['notes']:
                return 0

            notes = row['notes']
            if notes.startswith('failed:'):
                try:
                    parts = notes.split('|', 1)
                    return int(parts[0].replace('failed:', ''))
                except:
                    return 0
            return 0
    except Exception as e:
        logger.error(f"Ошибка получения количества попыток: {e}", exc_info=True)
        return 0


async def get_changes_by_type(chat_id: int, change_type: str, page: int = 1, limit: int = 10) -> Tuple[List[Dict], int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                'SELECT COUNT(*) as total FROM scheduled_chat_changes WHERE chat_id = $1 AND change_type = $2 AND is_active = TRUE',
                chat_id, change_type
            )
            total = count_row['total'] if count_row else 0

            offset = (page - 1) * limit
            rows = await conn.fetch('''
                SELECT id, chat_id, change_type, new_value,
                       scheduled_time, repeat_type, created_by, created_at,
                       last_applied, file_id, file_unique_id, notes
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND change_type = $2 AND is_active = TRUE
                ORDER BY scheduled_time ASC
                LIMIT $3 OFFSET $4
            ''', chat_id, change_type, limit, offset)

            changes = []
            for row in rows:
                change_dict = dict(row)
                if change_dict['scheduled_time']:
                    utc_time = change_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                    change_dict['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                for field in ['created_at', 'last_applied']:
                    if change_dict.get(field):
                        utc_time = change_dict[field].replace(tzinfo=pytz.UTC)
                        change_dict[field] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                changes.append(change_dict)
            return changes, total
    except Exception as e:
        logger.error(f"Ошибка получения изменений по типу: {e}", exc_info=True)
        return [], 0


async def get_all_active_changes(chat_id: int) -> List[Dict]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, change_type, new_value, scheduled_time,
                       repeat_type, file_id, file_unique_id, notes
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND is_active = TRUE
                ORDER BY scheduled_time ASC
            ''', chat_id)

            changes = []
            for row in rows:
                change_dict = dict(row)
                if change_dict['scheduled_time']:
                    utc_time = change_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                    change_dict['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                changes.append(change_dict)
            return changes
    except Exception as e:
        logger.error(f"Ошибка получения активных изменений: {e}", exc_info=True)
        return []


async def get_changes_due_now() -> List[Dict]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            now_utc = datetime.now(pytz.UTC)
            rows = await conn.fetch('''
                SELECT id, chat_id, change_type, new_value,
                       scheduled_time, repeat_type, file_id, file_unique_id, notes
                FROM scheduled_chat_changes
                WHERE scheduled_time <= $1 AND is_active = TRUE
                ORDER BY scheduled_time ASC
                LIMIT 50
            ''', now_utc)

            changes = []
            for row in rows:
                change_dict = dict(row)
                if change_dict['scheduled_time']:
                    change_dict['scheduled_time'] = change_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                changes.append(change_dict)
            return changes
    except Exception as e:
        logger.error(f"Ошибка получения изменений для применения: {e}", exc_info=True)
        return []


async def _calculate_next_time(scheduled_time: datetime, repeat_type: str) -> datetime:
    """Вычисляет следующее время для повторяющихся изменений."""
    if scheduled_time.tzinfo is None:
        scheduled_time_utc = scheduled_time.replace(tzinfo=pytz.UTC)
    else:
        scheduled_time_utc = scheduled_time.astimezone(pytz.UTC)

    scheduled_time_moscow = scheduled_time_utc.astimezone(MOSCOW_TZ)

    if repeat_type == 'daily':
        next_time_moscow = scheduled_time_moscow + timedelta(days=1)
    elif repeat_type == 'weekly':
        next_time_moscow = scheduled_time_moscow + timedelta(weeks=1)
    elif repeat_type == 'monthly':
        # Используем 30 дней как приближение месяца
        next_time_moscow = scheduled_time_moscow + timedelta(days=30)
    elif repeat_type == 'yearly':
        # Используем 365 дней как приближение года
        next_time_moscow = scheduled_time_moscow + timedelta(days=365)
    else:
        # По умолчанию - через день
        next_time_moscow = scheduled_time_moscow + timedelta(days=1)

    return next_time_moscow.astimezone(pytz.UTC)


async def update_change_after_application(change_id: int):
    """Обновляет запись после применения изменения."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT repeat_type, scheduled_time FROM scheduled_chat_changes WHERE id = $1',
                change_id
            )
            if not row:
                return

            repeat_type = row['repeat_type']
            if repeat_type == 'once':
                # Полное удаление без архивации
                await conn.execute('DELETE FROM scheduled_chat_changes WHERE id = $1', change_id)
            else:
                current_time = row['scheduled_time']
                next_time = await _calculate_next_time(current_time, repeat_type)
                await conn.execute('''
                    UPDATE scheduled_chat_changes
                    SET scheduled_time = $1, last_applied = CURRENT_TIMESTAMP
                    WHERE id = $2
                ''', next_time, change_id)
    except Exception as e:
        logger.error(f"Ошибка обновления после применения: {e}", exc_info=True)


async def delete_change(change_id: int) -> bool:
    """Полностью удаляет изменение без архивации."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM scheduled_chat_changes WHERE id = $1', change_id)
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления изменения: {e}", exc_info=True)
        return False


async def delete_all_changes(chat_id: int) -> int:
    """Удаляет все изменения в чате без архивации."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM scheduled_chat_changes WHERE chat_id = $1',
                chat_id
            )
            # `execute` возвращает строку вида "DELETE N"
            deleted_count = int(result.split()[1]) if result else 0
            return deleted_count
    except Exception as e:
        logger.error(f"Ошибка удаления всех изменений: {e}", exc_info=True)
        return 0


async def deactivate_change(change_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE scheduled_chat_changes SET is_active = FALSE WHERE id = $1',
                change_id
            )
        return True
    except Exception as e:
        logger.error(f"Ошибка деактивации изменения: {e}", exc_info=True)
        return False


async def activate_change(change_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE scheduled_chat_changes SET is_active = TRUE WHERE id = $1',
                change_id
            )
        return True
    except Exception as e:
        logger.error(f"Ошибка активации изменения: {e}", exc_info=True)
        return False


async def get_change_by_id(change_id: int) -> Optional[Dict]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM scheduled_chat_changes WHERE id = $1', change_id)
            if row:
                change_dict = dict(row)
                for field in ['scheduled_time', 'created_at', 'last_applied']:
                    if change_dict.get(field):
                        utc_time = change_dict[field].replace(tzinfo=pytz.UTC)
                        change_dict[field] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                return change_dict
            return None
    except Exception as e:
        logger.error(f"Ошибка получения изменения: {e}", exc_info=True)
        return None


async def get_combined_changes_by_date(chat_id: int, date: datetime) -> List[Dict]:
    try:
        date_moscow = localize_to_moscow(date)
        start_date_moscow = date_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_moscow = start_date_moscow + timedelta(days=1)

        start_date_utc = convert_to_utc(start_date_moscow)
        end_date_utc = convert_to_utc(end_date_moscow)

        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, change_type, new_value, scheduled_time,
                       repeat_type, file_id, file_unique_id
                FROM scheduled_chat_changes
                WHERE chat_id = $1
                  AND scheduled_time >= $2
                  AND scheduled_time < $3
                  AND is_active = TRUE
                ORDER BY scheduled_time ASC
            ''', chat_id, start_date_utc, end_date_utc)

            changes = []
            for row in rows:
                change_dict = dict(row)
                if change_dict['scheduled_time']:
                    utc_time = change_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                    change_dict['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                changes.append(change_dict)
            return changes
    except Exception as e:
        logger.error(f"Ошибка получения изменений по дате: {e}", exc_info=True)
        return []


async def get_changes_by_status(chat_id: int, is_active: bool = True, page: int = 1, limit: int = 10) -> Tuple[
    List[Dict], int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                'SELECT COUNT(*) as total FROM scheduled_chat_changes WHERE chat_id = $1 AND is_active = $2',
                chat_id, is_active
            )
            total = count_row['total'] if count_row else 0

            offset = (page - 1) * limit
            rows = await conn.fetch('''
                SELECT id, change_type, new_value, scheduled_time,
                       repeat_type, created_by, created_at, last_applied,
                       file_id, notes
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND is_active = $2
                ORDER BY scheduled_time DESC
                LIMIT $3 OFFSET $4
            ''', chat_id, is_active, limit, offset)

            changes = []
            for row in rows:
                change_dict = dict(row)
                if change_dict['scheduled_time']:
                    utc_time = change_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                    change_dict['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                for field in ['created_at', 'last_applied']:
                    if change_dict.get(field):
                        utc_time = change_dict[field].replace(tzinfo=pytz.UTC)
                        change_dict[field] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                changes.append(change_dict)
            return changes, total
    except Exception as e:
        logger.error(f"Ошибка получения изменений по статусу: {e}", exc_info=True)
        return [], 0


async def get_statistics(chat_id: int) -> Dict:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            type_stats = await conn.fetch('''
                SELECT change_type, COUNT(*) as count,
                       SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN NOT is_active THEN 1 ELSE 0 END) as inactive
                FROM scheduled_chat_changes
                WHERE chat_id = $1
                GROUP BY change_type
            ''', chat_id)

            repeat_stats = await conn.fetch('''
                SELECT repeat_type, COUNT(*) as count
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND is_active = TRUE
                GROUP BY repeat_type
            ''', chat_id)

            now_moscow = datetime.now(MOSCOW_TZ)
            now_utc = convert_to_utc(now_moscow)
            tomorrow_utc = convert_to_utc(now_moscow + timedelta(hours=24))

            upcoming = await conn.fetchrow('''
                SELECT COUNT(*) as count
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND is_active = TRUE
                  AND scheduled_time > $2 AND scheduled_time <= $3
            ''', chat_id, now_utc, tomorrow_utc)

            recent = await conn.fetch('''
                SELECT id, change_type, scheduled_time, new_value
                FROM scheduled_chat_changes
                WHERE chat_id = $1 AND is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 5
            ''', chat_id)

            recent_changes = []
            for row in recent:
                row_dict = dict(row)
                if row_dict.get('scheduled_time'):
                    utc_time = row_dict['scheduled_time'].replace(tzinfo=pytz.UTC)
                    row_dict['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                if len(row_dict.get('new_value', '')) > 30:
                    row_dict['new_value'] = row_dict['new_value'][:27] + "..."
                recent_changes.append(row_dict)

            return {
                'type_stats': [dict(row) for row in type_stats],
                'repeat_stats': [dict(row) for row in repeat_stats],
                'upcoming_count': upcoming['count'] if upcoming else 0,
                'recent_changes': recent_changes
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}", exc_info=True)
        return {}


async def get_avatar_changes_with_files(chat_id: int, page: int = 1, limit: int = 10) -> Tuple[List[Dict], int]:
    """
    Получает изменения аватарок с информацией о файлах

    Args:
        chat_id: ID чата
        page: Номер страницы
        limit: Количество записей на странице

    Returns:
        Tuple[List[Dict], int]: (список изменений, общее количество)
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            offset = (page - 1) * limit

            # Получаем общее количество
            count_row = await conn.fetchrow("""
                SELECT COUNT(*) as total
                FROM scheduled_chat_changes
                WHERE chat_id = $1 
                AND change_type = 'avatar' 
                AND is_active = TRUE
            """, chat_id)

            total = count_row['total'] if count_row else 0

            # Получаем изменения с файлами
            rows = await conn.fetch("""
                SELECT id, chat_id, change_type, new_value, scheduled_time, 
                       repeat_type, created_by, created_at, last_applied, 
                       file_id, file_unique_id, notes
                FROM scheduled_chat_changes
                WHERE chat_id = $1 
                AND change_type = 'avatar' 
                AND is_active = TRUE
                ORDER BY scheduled_time ASC
                LIMIT $2 OFFSET $3
            """, chat_id, limit, offset)

            changes = []
            for row in rows:
                change = {
                    'id': row['id'],
                    'chat_id': row['chat_id'],
                    'change_type': row['change_type'],
                    'new_value': row['new_value'],
                    'scheduled_time': row['scheduled_time'],
                    'repeat_type': row['repeat_type'],
                    'created_by': row['created_by'],
                    'created_at': row['created_at'],
                    'last_applied': row['last_applied'],
                    'file_id': row['file_id'],
                    'file_unique_id': row['file_unique_id'],
                    'notes': row['notes']
                }

                # Конвертируем время в московское
                if change['scheduled_time']:
                    utc_time = change['scheduled_time'].replace(tzinfo=pytz.UTC)
                    change['scheduled_time'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                if change['created_at']:
                    utc_time = change['created_at'].replace(tzinfo=pytz.UTC)
                    change['created_at'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
                if change['last_applied']:
                    utc_time = change['last_applied'].replace(tzinfo=pytz.UTC)
                    change['last_applied'] = utc_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)

                changes.append(change)

            return changes, total

    except Exception as e:
        logger.error(f"Ошибка получения аватарок с файлами: {e}", exc_info=True)
        return [], 0