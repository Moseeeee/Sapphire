from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
import logging
import pytz

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# Московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


async def check_db_time_format(chat_id: int) -> str:
    """
    Проверяет, в каком формате хранится время в БД.
    Возвращает 'UTC', 'LOCAL' или 'UNKNOWN'
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Берем последнюю запись для проверки
            query = '''
                SELECT created_at 
                FROM full_users_chats 
                WHERE chat_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            '''
            row = await conn.fetchrow(query, chat_id)

            if not row:
                return "NO_DATA"

            created_at = row['created_at']

            # Проверяем, есть ли у времени информация о часовом поясе
            if created_at.tzinfo is not None:
                # Если есть часовой пояс, проверяем какой
                if created_at.tzinfo == timezone.utc:
                    return "UTC"
                else:
                    return f"TZ_{created_at.tzinfo}"
            else:
                return "LOCAL_NO_TZ"

    except Exception as e:
        logger.error(f"Ошибка при проверке формата времени: {e}", exc_info=True)
        return "ERROR"


async def get_period_stats_data(chat_id: int, period: str) -> Tuple[int, int, int]:
    """
    Возвращает сырые данные статистики за период: (вступивших, вышедших, забаненных).

    Поддерживаемые периоды: 'день', 'неделя', 'месяц', 'год', 'всего'
    """
    if period not in {'день', 'неделя', 'месяц', 'год', 'всего'}:
        return 0, 0, 0

    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Сначала проверим формат времени в БД
            time_format = await check_db_time_format(chat_id)
            logger.info(f"Формат времени в БД для чата {chat_id}: {time_format}")

            # Определяем временную границу
            if period == 'день':
                start_time = datetime.now(timezone.utc) - timedelta(days=1)
            elif period == 'неделя':
                start_time = datetime.now(timezone.utc) - timedelta(weeks=1)
            elif period == 'месяц':
                start_time = datetime.now(timezone.utc) - timedelta(days=30)
            elif period == 'год':
                start_time = datetime.now(timezone.utc) - timedelta(days=365)
            else:  # 'всего'
                start_time = None

            # Если время в БД без часового пояса, нам нужно тоже использовать локальное время
            if time_format == "LOCAL_NO_TZ":
                # Конвертируем UTC время в локальное (без часового пояса)
                if start_time:
                    start_time = start_time.replace(tzinfo=None)

            # Единый агрегирующий запрос
            if start_time is None:
                query = '''
                    SELECT 
                        COUNT(*) FILTER (WHERE member_status = 'JOIN') AS joined,
                        COUNT(*) FILTER (WHERE member_status = 'LEAVE') AS left,
                        COUNT(*) FILTER (WHERE member_status = 'KICKED') AS kicked
                    FROM full_users_chats 
                    WHERE chat_id = $1
                '''
                params = (chat_id,)
            else:
                query = '''
                    SELECT 
                        COUNT(*) FILTER (WHERE member_status = 'JOIN') AS joined,
                        COUNT(*) FILTER (WHERE member_status = 'LEAVE') AS left,
                        COUNT(*) FILTER (WHERE member_status = 'KICKED') AS kicked
                    FROM full_users_chats 
                    WHERE chat_id = $1 AND created_at >= $2
                '''
                params = (chat_id, start_time)

            row = await conn.fetchrow(query, *params)

            joined = row['joined'] or 0 if row else 0
            left = row['left'] or 0 if row else 0
            kicked = row['kicked'] or 0 if row else 0

            return joined, left, kicked

    except Exception as e:
        logger.error(e, exc_info=True)
        return 0, 0, 0


async def get_period_stats_with_timezone(chat_id: int, period: str, use_moscow_time: bool = True) -> str:
    """
    Возвращает статистику с учетом часового пояса.
    Если use_moscow_time=True, считаем что пользователь хочет видеть статистику по московскому времени.
    """
    if period not in {'день', 'неделя', 'месяц', 'год', 'всего'}:
        return "❌ Неверный период. Используйте: день, неделя, месяц, год, всего"

    try:
        # Сначала узнаем формат времени в БД
        time_format = await check_db_time_format(chat_id)

        if use_moscow_time and time_format == "UTC":
            # Нужно адаптировать запрос под московское время
            return await _get_period_stats_moscow_time(chat_id, period, time_format)
        else:
            # Используем оригинальную логику
            joined, left, kicked = await get_period_stats_data(chat_id, period)
            return _format_stats_message(period, joined, left, kicked, time_format, use_moscow_time)

    except Exception as e:
        logger.error(e, exc_info=True)
        return "❌ Произошла ошибка при получении статистики. Попробуйте позже."


async def _get_period_stats_moscow_time(chat_id: int, period: str, db_time_format: str) -> str:
    """
    Специальная функция для получения статистики по московскому времени,
    когда данные в БД хранятся в UTC.
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем текущее время в UTC и московское время
            now_utc = datetime.now(timezone.utc)
            now_moscow = now_utc.astimezone(MOSCOW_TZ)

            # Рассчитываем начало периода в московском времени
            if period == 'день':
                # Начало текущего дня по Москве (00:00)
                start_of_day_moscow = now_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
                start_time_utc = start_of_day_moscow.astimezone(timezone.utc)
            elif period == 'неделя':
                # 7 дней назад от текущего момента
                start_time_moscow = now_moscow - timedelta(days=7)
                start_time_utc = start_time_moscow.astimezone(timezone.utc)
            elif period == 'месяц':
                # 30 дней назад от текущего момента
                start_time_moscow = now_moscow - timedelta(days=30)
                start_time_utc = start_time_moscow.astimezone(timezone.utc)
            elif period == 'год':
                # 365 дней назад от текущего момента
                start_time_moscow = now_moscow - timedelta(days=365)
                start_time_utc = start_time_moscow.astimezone(timezone.utc)
            else:  # 'всего'
                start_time_utc = None

            if start_time_utc is None:
                query = '''
                    SELECT 
                        COUNT(*) FILTER (WHERE member_status = 'JOIN') AS joined,
                        COUNT(*) FILTER (WHERE member_status = 'LEAVE') AS left,
                        COUNT(*) FILTER (WHERE member_status = 'KICKED') AS kicked
                    FROM full_users_chats 
                    WHERE chat_id = $1
                '''
                params = (chat_id,)
            else:
                query = '''
                    SELECT 
                        COUNT(*) FILTER (WHERE member_status = 'JOIN') AS joined,
                        COUNT(*) FILTER (WHERE member_status = 'LEAVE') AS left,
                        COUNT(*) FILTER (WHERE member_status = 'KICKED') AS kicked
                    FROM full_users_chats 
                    WHERE chat_id = $1 AND created_at >= $2
                '''
                params = (chat_id, start_time_utc)

            row = await conn.fetchrow(query, *params)

            joined = row['joined'] or 0 if row else 0
            left = row['left'] or 0 if row else 0
            kicked = row['kicked'] or 0 if row else 0

            return _format_stats_message(period, joined, left, kicked, db_time_format, True)

    except Exception as e:
        logger.error(e, exc_info=True)
        return 0, 0, 0


def _format_stats_message(period: str, joined: int, left: int, kicked: int,
                          db_time_format: str, use_moscow_time: bool) -> str:
    """Форматирует сообщение со статистикой."""
    period_names = {
        'день': 'за день',
        'неделя': 'за неделю',
        'месяц': 'за месяц',
        'год': 'за год',
        'всего': 'за всё время'
    }

    period_text = period_names[period]
    net_change = joined - (left + kicked)

    result_message = (
        f"👥 <b>Информация о пользователях {period_text}:</b>\n"
        f"<blockquote>Вступивших: {joined}\n"
        f"Вышедших: {left}\n"
        f"Забаненных: {kicked}</blockquote>\n\n"
    )

    if net_change > 0:
        result_message += f"📈 Чат вырос на {abs(net_change)} участников"
    elif net_change < 0:
        result_message += f"📉 Чат сократился на {abs(net_change)} участников"
    else:
        result_message += "🔁 Количество участников не изменилось"

    return result_message


async def get_period_stats(chat_id: int, period: str) -> str:
    """
    Основная функция для получения статистики.
    По умолчанию использует московское время если данные в UTC.
    """
    return await get_period_stats_with_timezone(chat_id, period, use_moscow_time=True)