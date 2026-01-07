import re
from datetime import timedelta, datetime
from typing import Optional

import pytz

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

time_units = {
    'минуту': 'minutes', 'минуты': 'minutes', 'минут': 'minutes',
    'час': 'hours', 'часа': 'hours', 'часов': 'hours',
    'день': 'days', 'дня': 'days', 'дней': 'days',
    'неделю': 'weeks', 'недели': 'weeks', 'недель': 'weeks',
    'месяц': 'months', 'месяца': 'months', 'месяцев': 'months',
    'год': 'years', 'года': 'years', 'лет': 'years',
    'век': 'centuries', 'века': 'centuries', 'веков': 'centuries',
    # Сокращения (должны идти после полных форм)
    'мин': 'minutes',
    'ч': 'hours',
    'д': 'days',
    'н': 'weeks',
    'м': 'months',
    'г': 'years',
    'в': 'centuries'
}


def format_duration(delta):
    """Форматирует timedelta в красивый текст с правильным склонением"""
    total_seconds = int(delta.total_seconds())

    # Если время меньше минуты
    if total_seconds < 60:
        return "меньше минуты"

    # Вычисляем составляющие времени
    years = total_seconds // (365 * 24 * 3600)
    months = (total_seconds % (365 * 24 * 3600)) // (30 * 24 * 3600)
    weeks = (total_seconds % (30 * 24 * 3600)) // (7 * 24 * 3600)
    days = (total_seconds % (7 * 24 * 3600)) // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60

    # Функция для склонения чисел
    def get_plural(number, form1, form2, form5):
        """Возвращает правильную форму слова для числа"""
        n = abs(number) % 100
        n1 = n % 10
        if 10 < n < 20:
            return form5
        if n1 == 1:
            return form1
        if 1 < n1 < 5:
            return form2
        return form5

    # Формируем все возможные части с правильным склонением
    time_parts = []

    if years > 0:
        time_parts.append((years, get_plural(years, 'год', 'года', 'лет')))

    if months > 0:
        time_parts.append((months, get_plural(months, 'месяц', 'месяца', 'месяцев')))

    if weeks > 0:
        time_parts.append((weeks, get_plural(weeks, 'неделю', 'недели', 'недель')))

    if days > 0:
        time_parts.append((days, get_plural(days, 'день', 'дня', 'дней')))

    if hours > 0:
        time_parts.append((hours, get_plural(hours, 'час', 'часа', 'часов')))

    if minutes > 0:
        time_parts.append((minutes, get_plural(minutes, 'минуту', 'минуты', 'минут')))

    # Выбираем только две наибольшие единицы времени
    result_parts = []

    # Если есть годы
    if years > 0:
        result_parts.append(f"{years} {get_plural(years, 'год', 'года', 'лет')}")
        # Если после годов есть месяцы, добавляем их
        if months > 0:
            result_parts.append(f"{months} {get_plural(months, 'месяц', 'месяца', 'месяцев')}")

    # Если нет лет, но есть месяцы
    elif months > 0:
        result_parts.append(f"{months} {get_plural(months, 'месяц', 'месяца', 'месяцев')}")
        # Если после месяцев есть дни, добавляем их
        if days > 0:
            result_parts.append(f"{days} {get_plural(days, 'день', 'дня', 'дней')}")

    # Если нет лет и месяцев, но есть недели
    elif weeks > 0:
        result_parts.append(f"{weeks} {get_plural(weeks, 'неделю', 'недели', 'недель')}")
        # Если после недель есть дни, добавляем их
        if days > 0:
            result_parts.append(f"{days} {get_plural(days, 'день', 'дня', 'дней')}")

    # Если нет лет, месяцев и недель, но есть дни
    elif days > 0:
        result_parts.append(f"{days} {get_plural(days, 'день', 'дня', 'дней')}")
        # Если после дней есть часы, добавляем их
        if hours > 0:
            result_parts.append(f"{hours} {get_plural(hours, 'час', 'часа', 'часов')}")

    # Если есть только часы и минуты
    elif hours > 0:
        result_parts.append(f"{hours} {get_plural(hours, 'час', 'часа', 'часов')}")
        # Если после часов есть минуты, добавляем их
        if minutes > 0:
            result_parts.append(f"{minutes} {get_plural(minutes, 'минуту', 'минуты', 'минут')}")

    # Если есть только минуты
    elif minutes > 0:
        result_parts.append(f"{minutes} {get_plural(minutes, 'минуту', 'минуты', 'минут')}")

    # Если ничего нет (маловероятно, так как мы уже проверили на "меньше минуты")
    if not result_parts:
        return "меньше минуты"

    return " ".join(result_parts)


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
            if value > 100:
                value = 100
            total_delta += timedelta(days=value * 365)

    # Дополнительная проверка на максимальное значение
    # Максимальное значение timedelta в Python примерно 999999999 дней
    # Ограничим 36500 дней (100 лет)
    MAX_DAYS = 36500
    if total_delta.days > MAX_DAYS:
        total_delta = timedelta(days=MAX_DAYS)

    return total_delta


def format_time_ago(first_seen: datetime) -> str:
    """Форматирует время в формате 'X месяцев Y дней назад'."""
    now = datetime.now(MOSCOW_TZ)
    delta = now - first_seen

    total_seconds = int(delta.total_seconds())

    # Если время меньше минуты
    if total_seconds < 60:
        return "только что"

    # Вычисляем составляющие времени
    years = total_seconds // (365 * 24 * 3600)
    months = (total_seconds % (365 * 24 * 3600)) // (30 * 24 * 3600)
    days = (total_seconds % (30 * 24 * 3600)) // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60

    result_parts = []

    # Если есть годы
    if years > 0:
        result_parts.append(f"{years} {get_plural_form(years, 'год', 'года', 'лет')}")
        # Если после годов есть месяцы, добавляем их
        if months > 0:
            result_parts.append(f"{months} {get_plural_form(months, 'месяц', 'месяца', 'месяцев')}")

    # Если нет лет, но есть месяцы
    elif months > 0:
        result_parts.append(f"{months} {get_plural_form(months, 'месяц', 'месяца', 'месяцев')}")
        # Если после месяцев есть дни, добавляем их
        if days > 0:
            result_parts.append(f"{days} {get_plural_form(days, 'день', 'дня', 'дней')}")

    # Если нет лет и месяцев, но есть дни
    elif days > 0:
        result_parts.append(f"{days} {get_plural_form(days, 'день', 'дня', 'дней')}")
        # Если после дней есть часы, добавляем их
        if hours > 0:
            result_parts.append(f"{hours} {get_plural_form(hours, 'час', 'часа', 'часов')}")

    # Если есть только часы и минуты
    elif hours > 0:
        result_parts.append(f"{hours} {get_plural_form(hours, 'час', 'часа', 'часов')}")
        # Если после часов есть минуты, добавляем их
        if minutes > 0:
            result_parts.append(f"{minutes} {get_plural_form(minutes, 'минуту', 'минуты', 'минут')}")

    # Если есть только минуты
    elif minutes > 0:
        result_parts.append(f"{minutes} {get_plural_form(minutes, 'минуту', 'минуты', 'минут')}")

    return " ".join(result_parts) + " назад"


def get_plural_form(n: int, form1: str, form2: str, form5: str) -> str:
    """Возвращает правильную форму слова для числа."""
    n = abs(n) % 100
    n1 = n % 10
    if 10 < n < 20:
        return form5
    if n1 == 1:
        return form1
    if 1 < n1 < 5:
        return form2
    return form5