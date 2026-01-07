# handlers/AgentsFeatures/ChatSettings/parse_chat_date.py
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dateutil import parser
from pytz import timezone

MOSCOW_TZ = timezone('Europe/Moscow')

# Маппинг русских названий дней и месяцев
RUSSIAN_MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
    'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
    'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12
}

RUSSIAN_DAYS = {
    'понедельник': 0, 'вторник': 1, 'среду': 2, 'четверг': 3, 'пятницу': 4, 'субботу': 5, 'воскресенье': 6,
    'пн': 0, 'вт': 1, 'ср': 2, 'чт': 3, 'пт': 4, 'сб': 5, 'вс': 6
}

REPEAT_TYPES = {
    'одноразово': 'once',
    'однажды': 'once',
    'разово': 'once',
    'ежедневно': 'daily',
    'каждый день': 'daily',
    'день': 'daily',
    'еженедельно': 'weekly',
    'каждую неделю': 'weekly',
    'неделя': 'weekly',
    'ежемесячно': 'monthly',
    'каждый месяц': 'monthly',
    'месяц': 'monthly',
    'ежегодно': 'yearly',
    'каждый год': 'yearly',
    'год': 'yearly',
    'праздник': 'holiday',
    'празднично': 'holiday'
}


def parse_datetime_string(date_str: str, time_str: str = None) -> Optional[datetime]:
    """Парсит строку с датой и временем"""
    try:
        # Убираем лишние пробелы
        date_str = date_str.strip().lower()

        # Пытаемся распарсить с помощью dateutil (умеет много форматов)
        if time_str:
            full_str = f"{date_str} {time_str}"
        else:
            full_str = date_str

        # Заменяем русские названия месяцев
        for rus_month, num in RUSSIAN_MONTHS.items():
            if rus_month in full_str:
                full_str = full_str.replace(rus_month, str(num))

        try:
            dt = parser.parse(full_str, dayfirst=True)
            # Приводим к московскому времени
            dt = MOSCOW_TZ.localize(dt.replace(tzinfo=None))
            return dt
        except:
            pass

        # Пытаемся распарсить вручную
        patterns = [
            # DD.MM.YYYY HH:MM
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{1,2})',
            # DD.MM HH:MM (предполагаем текущий год)
            r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})',
            # DD.MM.YYYY
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
            # DD.MM
            r'(\d{1,2})\.(\d{1,2})',
            # Сегодня/завтра/послезавтра
        ]

        now = datetime.now(MOSCOW_TZ)

        # Специальные случаи
        if 'сегодня' in full_str:
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Пытаемся извлечь время
            time_match = re.search(r'(\d{1,2}):(\d{1,2})', full_str)
            if time_match:
                dt = dt.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
            return dt

        elif 'завтра' in full_str:
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            time_match = re.search(r'(\d{1,2}):(\d{1,2})', full_str)
            if time_match:
                dt = dt.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
            return dt

        elif 'послезавтра' in full_str:
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)
            time_match = re.search(r'(\d{1,2}):(\d{1,2})', full_str)
            if time_match:
                dt = dt.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
            return dt

        # Дни недели
        for day_name, day_num in RUSSIAN_DAYS.items():
            if day_name in full_str:
                current_weekday = now.weekday()
                days_ahead = (day_num - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7  # На следующей неделе
                dt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
                time_match = re.search(r'(\d{1,2}):(\d{1,2})', full_str)
                if time_match:
                    dt = dt.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
                return dt

        return None

    except Exception as e:
        print(f"Error parsing datetime: {e}")
        return None


def parse_repeat_type(repeat_str: str) -> str:
    """Парсит тип повторения"""
    repeat_str = repeat_str.strip().lower()

    # Пытаемся найти в словаре
    for key, value in REPEAT_TYPES.items():
        if key in repeat_str:
            return value

    # По умолчанию - одноразово
    return 'once'


def parse_chat_command(text: str) -> Tuple[Optional[datetime], str, Optional[str]]:
    """
    Парсит команду для настроек чата
    Возвращает: (дата, тип_повторения, оставшийся_текст)
    """
    text_lower = text.lower()

    # Сначала ищем дату
    date_patterns = [
        # Дата и время
        r'(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{1,2})',
        r'(\d{1,2}\.\d{1,2}\s+\d{1,2}:\d{1,2})',
        # Просто дата
        r'(\d{1,2}\.\d{1,2}\.\d{4})',
        r'(\d{1,2}\.\d{1,2})',
        # Сегодня/завтра
        r'(сегодня(?:\s+\d{1,2}:\d{1,2})?)',
        r'(завтра(?:\s+\d{1,2}:\d{1,2})?)',
        r'(послезавтра(?:\s+\d{1,2}:\d{1,2})?)',
        # Дни недели
        r'((?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье|пн|вт|ср|чт|пт|сб|вс)(?:\s+\d{1,2}:\d{1,2})?)'
    ]

    found_date = None
    date_str = None

    for pattern in date_patterns:
        match = re.search(pattern, text_lower)
        if match:
            date_str = match.group(1)
            found_date = parse_datetime_string(date_str)
            if found_date:
                break

    # Ищем тип повторения
    repeat_type = 'once'
    for key, value in REPEAT_TYPES.items():
        if key in text_lower:
            repeat_type = value
            break

    # Удаляем дату и тип повторения из текста
    remaining_text = text
    if date_str:
        remaining_text = remaining_text.replace(date_str, '')

    for key in REPEAT_TYPES:
        if key in text_lower:
            remaining_text = remaining_text.replace(key, '')

    # Очищаем текст
    remaining_text = re.sub(r'\s+', ' ', remaining_text).strip()

    return found_date, repeat_type, remaining_text


def format_schedule_date(dt: datetime) -> str:
    """Форматирует дату для красивого отображения"""
    if not dt:
        return "Не указано"

    now = datetime.now(MOSCOW_TZ)

    # Если сегодня
    if dt.date() == now.date():
        return f"Сегодня в {dt.strftime('%H:%M')}"

    # Если завтра
    if dt.date() == (now + timedelta(days=1)).date():
        return f"Завтра в {dt.strftime('%H:%M')}"

    # Если послезавтра
    if dt.date() == (now + timedelta(days=2)).date():
        return f"Послезавтра в {dt.strftime('%H:%M')}"

    # Обычная дата
    return dt.strftime('%d.%m.%Y в %H:%M')


def format_repeat_type(repeat_type: str) -> str:
    """Форматирует тип повторения"""
    mapping = {
        'once': 'Одноразово',
        'daily': 'Ежедневно',
        'weekly': 'Еженедельно',
        'monthly': 'Ежемесячно',
        'yearly': 'Ежегодно',
        'holiday': 'Празднично'
    }
    return mapping.get(repeat_type, 'Одноразово')