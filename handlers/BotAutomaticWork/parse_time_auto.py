import re
from datetime import timedelta, datetime
from typing import Optional

import pytz

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Константы ограничений
MAX_YEARS = 100
MAX_DAYS = MAX_YEARS * 365  # ~36500 дней

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


def format_duration(delta: timedelta) -> str:
    """Форматирует timedelta в красивый текст с правильным склонением (макс. 2 единицы)."""
    if not isinstance(delta, timedelta) or delta.total_seconds() < 0:
        return "меньше минуты"

    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "меньше минуты"

    # ПОСЛЕДОВАТЕЛЬНОЕ вычисление остатков — исправление бага
    remaining = total_seconds
    years = remaining // (365 * 24 * 3600)
    remaining %= (365 * 24 * 3600)
    months = remaining // (30 * 24 * 3600)
    remaining %= (30 * 24 * 3600)
    weeks = remaining // (7 * 24 * 3600)
    remaining %= (7 * 24 * 3600)
    days = remaining // (24 * 3600)
    remaining %= (24 * 3600)
    hours = remaining // 3600
    minutes = remaining // 60

    # Формируем части для вывода
    parts = []
    if years > 0:
        parts.append((years, get_plural_form(years, 'год', 'года', 'лет')))
    if months > 0:
        parts.append((months, get_plural_form(months, 'месяц', 'месяца', 'месяцев')))
    if weeks > 0:
        parts.append((weeks, get_plural_form(weeks, 'неделю', 'недели', 'недель')))
    if days > 0:
        parts.append((days, get_plural_form(days, 'день', 'дня', 'дней')))
    if hours > 0:
        parts.append((hours, get_plural_form(hours, 'час', 'часа', 'часов')))
    if minutes > 0:
        parts.append((minutes, get_plural_form(minutes, 'минуту', 'минуты', 'минут')))

    # Выбираем не более двух старших единиц
    result_parts = []
    if len(parts) >= 1:
        result_parts.append(f"{parts[0][0]} {parts[0][1]}")
    if len(parts) >= 2:
        result_parts.append(f"{parts[1][0]} {parts[1][1]}")

    return " ".join(result_parts) if result_parts else "меньше минуты"


def parse_time_string(time_str: str) -> Optional[timedelta]:
    """Парсит строку времени и возвращает timedelta. Совместима со старым кодом."""
    if not time_str or not isinstance(time_str, str):
        return timedelta(days=1)

    time_str = time_str.lower().strip()

    # Поддержка одиночных слов без числа (например: "день", "час", "мин")
    single_word_forms = {
        'минута', 'минуту', 'час', 'день', 'неделя', 'месяц', 'год', 'век',
        'мин', 'ч', 'д', 'н', 'м', 'г', 'в'
    }
    if time_str in single_word_forms:
        time_str = f"1 {time_str}"

    # Извлекаем все (число, единица)
    pattern = r'(\d+)\s*([а-яёa-z]+)'
    matches = re.findall(pattern, time_str)

    if not matches:
        return None

    total_delta = timedelta()
    # Сортируем ключи по длине по убыванию — чтобы длинные формы имели приоритет
    sorted_keys = sorted(time_units.keys(), key=len, reverse=True)

    for value_str, unit_part in matches:
        try:
            value = int(value_str)
        except ValueError:
            continue
        if value <= 0:
            continue

        matched_key = None
        for key in sorted_keys:
            if key.startswith(unit_part):
                matched_key = key
                break

        if matched_key is None:
            return None

        time_type = time_units[matched_key]

        if time_type == 'minutes':
            total_delta += timedelta(minutes=value)
        elif time_type == 'hours':
            total_delta += timedelta(hours=value)
        elif time_type == 'days':
            total_delta += timedelta(days=value)
        elif time_type == 'weeks':
            total_delta += timedelta(weeks=value)
        elif time_type == 'months':
            total_delta += timedelta(days=value * 30)
        elif time_type == 'years':
            total_delta += timedelta(days=min(value, MAX_YEARS) * 365)
        elif time_type == 'centuries':
            total_delta += timedelta(days=min(value, MAX_YEARS // 100) * 36500)

    # Ограничение максимального значения
    if total_delta.days > MAX_DAYS:
        total_delta = timedelta(days=MAX_DAYS)

    return total_delta


def format_time_ago(first_seen: datetime) -> str:
    """Форматирует время в формате 'X месяцев Y дней назад'."""
    if not isinstance(first_seen, datetime):
        return "недавно"

    now = datetime.now(MOSCOW_TZ)
    if first_seen.tzinfo is None:
        first_seen = MOSCOW_TZ.localize(first_seen)
    else:
        first_seen = first_seen.astimezone(MOSCOW_TZ)

    delta = now - first_seen
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "только что"
    if total_seconds < 0:
        return "в будущем"

    years = total_seconds // (365 * 24 * 3600)
    months = (total_seconds % (365 * 24 * 3600)) // (30 * 24 * 3600)
    days = (total_seconds % (30 * 24 * 3600)) // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if years > 0:
        parts.append(f"{years} {get_plural_form(years, 'год', 'года', 'лет')}")
        if months > 0 and len(parts) < 2:
            parts.append(f"{months} {get_plural_form(months, 'месяц', 'месяца', 'месяцев')}")
    elif months > 0:
        parts.append(f"{months} {get_plural_form(months, 'месяц', 'месяца', 'месяцев')}")
        if days > 0 and len(parts) < 2:
            parts.append(f"{days} {get_plural_form(days, 'день', 'дня', 'дней')}")
    elif days > 0:
        parts.append(f"{days} {get_plural_form(days, 'день', 'дня', 'дней')}")
        if hours > 0 and len(parts) < 2:
            parts.append(f"{hours} {get_plural_form(hours, 'час', 'часа', 'часов')}")
    elif hours > 0:
        parts.append(f"{hours} {get_plural_form(hours, 'час', 'часа', 'часов')}")
        if minutes > 0 and len(parts) < 2:
            parts.append(f"{minutes} {get_plural_form(minutes, 'минуту', 'минуты', 'минут')}")
    elif minutes > 0:
        parts.append(f"{minutes} {get_plural_form(minutes, 'минуту', 'минуты', 'минут')}")

    return " ".join(parts) + " назад" if parts else "только что"