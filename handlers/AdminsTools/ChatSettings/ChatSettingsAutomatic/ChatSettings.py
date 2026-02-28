import logging
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Tuple, Optional, Dict, List, Union
from collections import defaultdict
import asyncio

import pytz
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, PhotoSize
from aiogram.filters import Command
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_agent_access, \
    auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettingsDB import (
    add_scheduled_change, get_all_active_changes, get_combined_changes_by_date,
    get_change_by_id, delete_change, get_changes_by_type, create_scheduled_changes_table,
    get_statistics, delete_all_changes, MOSCOW_TZ
)
from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.chat_settings_service import (
    get_auto_chat_service, init_auto_chat_service, shutdown_auto_chat_service,
    test_service_status, force_check_now
)

logger = logging.getLogger(__name__)
auto_chat_router = Router()

# Маппинг типов повторения с поддержкой русского и английского
REPEAT_TYPE_MAPPING = {
    # Русские варианты
    'одноразово': 'once',
    'разово': 'once',
    'раз': 'once',
    'однократно': 'once',
    'ежедневно': 'daily',
    'каждый день': 'daily',
    'день': 'daily',
    'дневной': 'daily',
    'еженедельно': 'weekly',
    'каждую неделю': 'weekly',
    'неделя': 'weekly',
    'неделю': 'weekly',
    'недельный': 'weekly',
    'ежемесячно': 'monthly',
    'каждый месяц': 'monthly',
    'месяц': 'monthly',
    'месячный': 'monthly',
    'ежегодно': 'yearly',
    'каждый год': 'yearly',
    'год': 'yearly',
    'годовой': 'yearly',
    # Английские варианты
    'once': 'once',
    'daily': 'daily',
    'weekly': 'weekly',
    'monthly': 'monthly',
    'yearly': 'yearly'
}

# Обратный маппинг для отображения
REPEAT_TYPE_DISPLAY = {
    'once': 'одноразово',
    'daily': 'ежедневно',
    'weekly': 'еженедельно',
    'monthly': 'ежемесячно',
    'yearly': 'ежегодно'
}

# Относительные даты на русском
RELATIVE_DATE_MAPPING = {
    'сегодня': 0,
    'завтра': 1,
    'послезавтра': 2,
    'через день': 2,
    'через 2 дня': 2,
    'через 3 дня': 3,
    'через неделю': 7,
    'через месяц': 30,
    'через год': 365,
    'на следующей неделе': 7,
    'в следующем месяце': 30,
    'в следующем году': 365,
    'today': 0,
    'tomorrow': 1,
    'next week': 7,
    'next month': 30,
    'next year': 365
}

# Кэш для отслеживания последних изменений аватарок
_last_avatar_change: Dict[int, datetime] = {}
# Блокировка для защиты от конкурентного доступа
_avatar_lock: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def parse_repeat_type(user_input: str) -> str:
    """Парсит тип повторения с поддержкой русского и английского."""
    user_input = user_input.strip().lower()
    return REPEAT_TYPE_MAPPING.get(user_input, 'once')


def validate_repeat_type(repeat_type: str) -> tuple[bool, Union[str, None]]:
    """Проверяет и нормализует тип повторения."""
    normalized = parse_repeat_type(repeat_type)
    valid_types = ['once', 'daily', 'weekly', 'monthly', 'yearly']
    if normalized not in valid_types:
        russian_types = ['одноразово', 'ежедневно', 'еженедельно', 'ежемесячно', 'ежегодно']
        return False, f"❌ Неверный тип повторения.\n📝 Доступные: {', '.join(russian_types)}"
    return True, normalized


def validate_text_length(text: str, max_length: int, field_name: str) -> tuple[bool, str]:
    """Валидирует длину текста."""
    if len(text) > max_length:
        return False, f"❌ {field_name} не может превышать {max_length} символов (сейчас: {len(text)})"
    return True, ""


async def check_avatar_rate_limit(chat_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, не превышен ли лимит на изменение аватарки (минимум 5 минут).
    Возвращает (можно_менять, сообщение_об_ошибке)
    """
    lock = _avatar_lock.get(chat_id)
    if not lock:
        lock = asyncio.Lock()
        _avatar_lock[chat_id] = lock

    async with lock:
        now = datetime.now(MOSCOW_TZ)
        last_change = _last_avatar_change.get(chat_id)

        if last_change:
            time_diff = (now - last_change).total_seconds() / 60  # разница в минутах
            if time_diff < 5:
                next_allowed = last_change + timedelta(minutes=5)
                minutes_left = int(5 - time_diff)
                seconds_left = int((5 - time_diff) * 60) % 60
                return False, (f"❌ Слишком часто! Аватарку можно менять не чаще раза в 5 минут.\n"
                               f"⏳ Следующее изменение доступно через {minutes_left} мин {seconds_left} сек")

        return True, None


async def update_avatar_change_time(chat_id: int):
    """Обновляет время последнего изменения аватарки."""
    lock = _avatar_lock.get(chat_id)
    if not lock:
        lock = asyncio.Lock()
        _avatar_lock[chat_id] = lock

    async with lock:
        _last_avatar_change[chat_id] = datetime.now(MOSCOW_TZ)


class DateTimeParser:
    """Универсальный парсер даты и времени."""

    def __init__(self):
        self.now = datetime.now(MOSCOW_TZ)

    def parse_relative_date(self, text: str) -> Optional[int]:
        """Парсит относительную дату (завтра, через месяц и т.д.)."""
        text = text.lower().strip()

        # Прямое сопоставление
        if text in RELATIVE_DATE_MAPPING:
            return RELATIVE_DATE_MAPPING[text]

        # Парсинг "через X дней/недель/месяцев/лет"
        pattern = r'через\s+(\d+)\s*(день|дня|дней|недел[юьи]|месяц[а]?|год[а]?|лет)'
        match = re.search(pattern, text)

        if match:
            number = int(match.group(1))
            unit = match.group(2)

            if 'день' in unit or 'дня' in unit or 'дней' in unit:
                return number
            elif 'недел' in unit:
                return number * 7
            elif 'месяц' in unit:
                return number * 30
            elif 'год' in unit or 'лет' in unit:
                return number * 365

        return None

    def parse_date_part(self, date_str: str) -> Tuple[Optional[datetime], Optional[str]]:
        """Парсит часть с датой, поддерживая различные форматы."""
        date_str = date_str.strip().lower()

        # Проверяем на относительную дату
        days_offset = self.parse_relative_date(date_str)
        if days_offset is not None:
            target_date = self.now + timedelta(days=days_offset)
            # Возвращаем дату БЕЗ timezone, только дата
            return target_date.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None), None

        # Формат: ДД.ММ.ГГГГ
        pattern_full = r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$'
        match = re.match(pattern_full, date_str)
        if match:
            day, month, year = map(int, match.groups())
            try:
                # Возвращаем naive datetime (без timezone)
                return datetime(year, month, day), None
            except ValueError:
                return None, f"❌ Неверная дата: {date_str}"

        # Формат: ДД.ММ
        pattern_short = r'^(\d{1,2})\.(\d{1,2})$'
        match = re.match(pattern_short, date_str)
        if match:
            day, month = map(int, match.groups())
            year = self.now.year
            try:
                target_date = datetime(year, month, day)

                # Если дата уже прошла в этом году, берем следующий год
                if target_date < self.now.replace(hour=0, minute=0, second=0, microsecond=0):
                    target_date = datetime(year + 1, month, day)

                return target_date, None
            except ValueError:
                return None, f"❌ Неверная дата: {date_str}"

        # Формат: ДД (только число)
        if date_str.isdigit() and 1 <= int(date_str) <= 31:
            day = int(date_str)
            month = self.now.month
            year = self.now.year

            try:
                target_date = datetime(year, month, day)

                # Если число уже прошло в этом месяце, берем следующий месяц
                if target_date < self.now.replace(hour=0, minute=0, second=0, microsecond=0):
                    if month == 12:
                        target_date = datetime(year + 1, 1, day)
                    else:
                        target_date = datetime(year, month + 1, day)

                return target_date, None
            except ValueError:
                # Если день не подходит для текущего месяца, пробуем следующий
                if month == 12:
                    try:
                        return datetime(year + 1, 1, day), None
                    except ValueError:
                        return None, f"❌ Неверный день: {day}"
                else:
                    try:
                        return datetime(year, month + 1, day), None
                    except ValueError:
                        return None, f"❌ Неверный день: {day}"

        return None, f"❌ Неверный формат даты: {date_str}"

    def parse_time_part(self, time_str: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """Парсит часть со временем."""
        time_str = time_str.strip()

        # Формат: ЧЧ:ММ
        pattern = r'^(\d{1,2}):(\d{1,2})$'
        match = re.match(pattern, time_str)
        if match:
            hour, minute = map(int, match.groups())
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, None
            else:
                return None, None, f"❌ Неверное время: {time_str} (часы 0-23, минуты 0-59)"

        return None, None, f"❌ Неверный формат времени: {time_str}. Используйте ЧЧ:ММ"

    def parse_datetime(self, date_str: str, time_str: Optional[str] = None) -> Tuple[Optional[datetime], Optional[str]]:
        """
        Основной метод парсинга даты и времени.
        Поддерживает:
        - Относительные даты (завтра, через месяц)
        - Форматы: ДД, ДД.ММ, ДД.ММ.ГГГГ
        - Время опционально, если не указано - 00:00
        """
        # Парсим дату (получаем naive datetime)
        target_date, error = self.parse_date_part(date_str)
        if error:
            return None, error

        # Если время не указано, устанавливаем 00:00
        if not time_str:
            hour, minute = 0, 0
        else:
            hour, minute, error = self.parse_time_part(time_str)
            if error:
                return None, error

        # Устанавливаем время (target_date уже naive)
        target_datetime = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Проверяем, что время в будущем (сравниваем naive datetime с self.now без timezone)
        now_naive = self.now.replace(tzinfo=None)
        if target_datetime <= now_naive:
            # Если время сегодня и указано, но уже прошло - переносим на завтра
            if target_datetime.date() == now_naive.date() and time_str:
                target_datetime += timedelta(days=1)
            else:
                return None, "❌ Время должно быть в будущем!"

        # Локализуем в московское время только в конце
        return MOSCOW_TZ.localize(target_datetime), None

    def extract_datetime_from_parts(self, parts: list) -> Tuple[Optional[datetime], int, Optional[str]]:
        """
        Извлекает дату и время из списка частей команды.
        Возвращает: (datetime, индекс после разобранных частей, ошибка)
        """
        if not parts:
            return None, 0, "❌ Не указана дата"

        # Пробуем разные комбинации
        # Сначала ищем время (формат ЧЧ:ММ)
        time_index = -1
        time_str = None

        for i, part in enumerate(parts):
            if re.match(r'^\d{1,2}:\d{1,2}$', part):
                time_index = i
                time_str = part
                break

        # Если нашли время, дата должна быть перед ним
        if time_index > 0:
            # Пробуем объединить предыдущие части как дату
            date_str = ' '.join(parts[:time_index])
            dt, error = self.parse_datetime(date_str, time_str)
            if not error:
                return dt, time_index + 1, None

        # Если время не нашли или не удалось распарсить с ним,
        # пробуем все части как дату
        date_str = ' '.join(parts)
        dt, error = self.parse_datetime(date_str, None)

        if not error:
            return dt, len(parts), None

        # Если не получилось, пробуем первую часть как дату, остальное как время?
        if len(parts) >= 2:
            dt, error = self.parse_datetime(parts[0], parts[1])
            if not error:
                return dt, 2, None

        return None, 0, f"❌ Не удалось распознать дату/время: {' '.join(parts)}"


# Создаем экземпляр парсера
dt_parser = DateTimeParser()


def parse_description_command(text: str) -> tuple[bool, str, str, str, str]:
    """
    Парсит команду для описания с поддержкой многострочного текста.
    Формат: +описание [дата/время] [тип]
    [многострочный текст]
    """
    try:
        lines = text.split('\n', 1)
        if len(lines) < 2:
            return False, "❌ Описание должно быть на новой строке", "", "", ""

        command_line = lines[0].strip()
        description_text = lines[1].strip()

        if not description_text:
            return False, "❌ Описание не может быть пустым", "", "", ""

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 2:
            return False, "❌ Неверный формат команды.\n✅ Используйте: +описание [дата/время] [тип]\n[текст описания]", "", "", ""

        # Проверяем префикс
        if not parts[0].startswith(('+', '!', '/', '.')):
            return False, "❌ Неверный префикс команды", "", "", ""

        # Удаляем префикс команды
        command_parts = parts[1:] if parts[0].lstrip('+!/.').lower() == 'описание' else parts

        if not command_parts:
            return False, "❌ Укажите дату и тип повторения", "", "", ""

        # Извлекаем дату/время и тип
        dt, used_parts, error = dt_parser.extract_datetime_from_parts(command_parts)
        if error:
            return False, error, "", "", ""

        # Оставшиеся части - это тип повторения
        remaining_parts = command_parts[used_parts:]
        repeat_type_input = ' '.join(remaining_parts) if remaining_parts else 'once'

        date_str = dt.strftime("%d.%m.%Y")
        time_str = dt.strftime("%H:%M")

        return True, description_text, date_str, time_str, repeat_type_input

    except Exception as e:
        logger.error(f"Ошибка парсинга команды описания: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", "", ""


def parse_title_command(text: str) -> tuple[bool, str, str, str, str]:
    """
    Парсит команду для названия.
    Формат: +менять название [дата/время] [тип]
    [текст названия]
    """
    try:
        lines = text.split('\n', 1)
        if len(lines) < 2:
            return False, "❌ Название должно быть на новой строке", "", "", ""

        command_line = lines[0].strip()
        title_text = lines[1].strip()

        if not title_text:
            return False, "❌ Название не может быть пустым", "", "", ""

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 3:
            return False, "❌ Неверный формат команды.\n✅ Используйте: +менять название [дата/время] [тип]\n[текст названия]", "", "", ""

        # Проверяем префикс и ключевые слова
        if not parts[0].startswith(('+', '!', '/', '.')):
            return False, "❌ Неверный префикс команды", "", "", ""

        # Проверяем что это команда "менять название"
        cmd = parts[0].lstrip('+!/.').lower()
        if len(parts) < 2 or cmd != 'менять' or parts[1].lower() != 'название':
            return False, "❌ Неверная команда. Используйте: +менять название", "", "", ""

        # Удаляем 'менять' и 'название'
        command_parts = parts[2:]

        if not command_parts:
            return False, "❌ Укажите дату и тип повторения", "", "", ""

        # Извлекаем дату/время и тип
        dt, used_parts, error = dt_parser.extract_datetime_from_parts(command_parts)
        if error:
            return False, error, "", "", ""

        # Оставшиеся части - это тип повторения
        remaining_parts = command_parts[used_parts:]
        repeat_type_input = ' '.join(remaining_parts) if remaining_parts else 'once'

        date_str = dt.strftime("%d.%m.%Y")
        time_str = dt.strftime("%H:%M")

        return True, title_text, date_str, time_str, repeat_type_input

    except Exception as e:
        logger.error(f"Ошибка парсинга команды названия: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", "", ""


def parse_avatar_command(text: str, has_photo: bool = False, has_reply: bool = False) -> tuple[
    bool, str, str, str, str]:
    """
    Парсит команду для аватарки.
    Варианты:
    1. С фото в сообщении: +аватарка [дата/время] [тип] [описание?]
    2. С reply на фото: +аватарка [дата/время] [тип] [описание?]
    """
    try:
        # Проверяем наличие фото
        if not has_photo and not has_reply:
            return False, "❌ Для аватарки необходимо прикрепить фото к сообщению или ответить на фото", "", "", ""

        # Удаляем префикс команды
        text = text.strip()
        prefixes = ['+аватарка', '!аватарка', '/аватарка', '.аватарка']
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            return False, "❌ Укажите дату и тип повторения", "", "", ""

        # Разбиваем на части
        parts = text.split()

        # Извлекаем дату/время и тип
        dt, used_parts, error = dt_parser.extract_datetime_from_parts(parts)
        if error:
            return False, error, "", "", ""

        # Оставшиеся части - это тип повторения и описание
        remaining_parts = parts[used_parts:]

        # Первое из оставшихся - тип повторения, остальное - описание
        repeat_type_input = 'once'
        description = ''

        if remaining_parts:
            repeat_type_input = remaining_parts[0]
            if len(remaining_parts) > 1:
                description = ' '.join(remaining_parts[1:])

        date_str = dt.strftime("%d.%m.%Y")
        time_str = dt.strftime("%H:%M")

        return True, description, date_str, time_str, repeat_type_input

    except Exception as e:
        logger.error(f"Ошибка парсинга команды аватарки: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", "", ""


def parse_quick_avatar_command(text: str, day: str) -> tuple[bool, str, str, str]:
    """Парсит быструю команду аватарки (сегодня/завтра)."""
    try:
        # Удаляем префикс команды
        prefixes = [f'+{day} аватарка', f'!{day} аватарка', f'/{day} аватарка', f'.{day} аватарка']
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            return False, "❌ Укажите время и тип повторения", "", ""

        parts = text.split()

        # Ищем время
        time_str = None
        time_index = -1
        for i, part in enumerate(parts):
            if re.match(r'^\d{1,2}:\d{1,2}$', part):
                time_str = part
                time_index = i
                break

        if not time_str:
            return False, "❌ Укажите время в формате ЧЧ:ММ", "", ""

        # Тип повторения - следующий после времени
        if len(parts) > time_index + 1:
            repeat_type_input = parts[time_index + 1]
            # Описание - все остальное
            description = ' '.join(parts[time_index + 2:]) if len(parts) > time_index + 2 else ""
        else:
            return False, "❌ Укажите тип повторения", "", ""

        return True, time_str, repeat_type_input, description

    except Exception as e:
        logger.error(f"Ошибка парсинга быстрой команды аватарки: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", ""


# Исправленная функция проверки прав для callback
async def _check_chat_admin_callback(callback: CallbackQuery) -> bool:
    """Проверяет права для callback-запросов."""
    try:
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id

        agent_rang = await check_agent_access(user_id)
        if agent_rang >= 3:
            return True

        chat_member = await callback.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав в callback: {e}", exc_info=True)
        return False


def _get_repeat_text(repeat_type: str) -> str:
    """Возвращает читабельный текст типа повторения."""
    return REPEAT_TYPE_DISPLAY.get(repeat_type, 'Неизвестно')


@auto_chat_router.message(F.text.regexp(r'^[+!/.].*менять название'))
async def schedule_title_change(msg: Message):
    """Добавляет запланированное изменение названия чата."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        success, title_text, date_str, time_str, repeat_type_input = parse_title_command(msg.text)
        if not success:
            await msg.reply(title_text)
            return

        # Проверяем длину названия
        is_valid, error_msg = validate_text_length(title_text, 255, "Название")
        if not is_valid:
            await msg.reply(error_msg)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Парсим дату и время
        try:
            scheduled_time_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            scheduled_time = MOSCOW_TZ.localize(scheduled_time_naive)
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.")
            return

        now_moscow = datetime.now(MOSCOW_TZ)
        if scheduled_time <= now_moscow:
            await msg.reply("❌ Время должно быть в будущем!")
            return

        # Сохраняем в БД
        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='title',
            new_value=title_text,
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id
        )

        if success:
            repeat_text = _get_repeat_text(repeat_type)
            display_title = title_text if len(title_text) <= 100 else title_text[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение названия:\n"
                f"📝 Название: {display_title}\n"
                f"⏰ Когда: {date_str} {time_str}\n"
                f"🔄 Повторение: {repeat_text}\n"
                f"🆔 Используйте !удалить название [ID] для отмены"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение. Возможно, такое уже существует.")

    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_title_change: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[+!/.].*описание'))
async def schedule_description_change(msg: Message):
    """Добавляет запланированное изменение описания."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        success, description_text, date_str, time_str, repeat_type_input = parse_description_command(msg.text)
        if not success:
            await msg.reply(description_text)
            return

        # Проверяем длину описания
        is_valid, error_msg = validate_text_length(description_text, 255, "Описание")
        if not is_valid:
            await msg.reply(error_msg)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Парсим дату и время
        try:
            scheduled_time_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            scheduled_time = MOSCOW_TZ.localize(scheduled_time_naive)
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.")
            return

        now_moscow = datetime.now(MOSCOW_TZ)
        if scheduled_time <= now_moscow:
            await msg.reply("❌ Время должно быть в будущем!")
            return

        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='description',
            new_value=description_text,
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id
        )

        if success:
            repeat_text = _get_repeat_text(repeat_type)
            display_desc = description_text if len(description_text) <= 100 else description_text[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение описания:\n"
                f"📝 Описание: {display_desc}\n"
                f"⏰ Когда: {date_str} {time_str}\n"
                f"🔄 Повторение: {repeat_text}\n"
                f"🆔 Используйте !удалить описание [ID] для отмены"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")

    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_description_change: {e}", exc_info=True)


@auto_chat_router.message(F.photo)
@auto_chat_router.message(F.reply_to_message & F.reply_to_message.photo)
@auto_chat_router.message(F.text.regexp(r'^[+!/.].*аватарка'))
@auto_chat_router.message(F.caption.regexp(r'^[+!/.].*аватарка'))
async def schedule_avatar_change(msg: Message):
    """Добавляет запланированное изменение аватарки."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Проверяем лимит на частоту изменений аватарки
        can_change, limit_message = await check_avatar_rate_limit(chat_id)
        if not can_change:
            await msg.reply(limit_message)
            return

        # Проверяем, есть ли фото в сообщении
        has_photo = bool(msg.photo)
        has_reply_photo = bool(msg.reply_to_message and msg.reply_to_message.photo)

        if not has_photo and not has_reply_photo:
            await msg.reply(
                "❌ Для аватарки необходимо:\n"
                "1. Прикрепить фото к сообщению с командой в подписи\n"
                "2. Или ответить на фото командой\n"
                "Пример подписи:\n"
                "+аватарка завтра 14:30 ежедневно\n"
                "или\n"
                "+аватарка 25.12 14:30 ежедневно"
            )
            return

        file_id = None
        file_unique_id = None

        if has_photo:
            photo: PhotoSize = msg.photo[-1]
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id
            command_text = msg.caption or ""
        elif has_reply_photo:
            photo: PhotoSize = msg.reply_to_message.photo[-1]
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id
            command_text = msg.text or ""

        if not command_text or not command_text.strip():
            await msg.reply(
                "❌ Команда не найдена. Убедитесь, что команда указана в подписи к фото или в тексте ответа.")
            return

        # Парсим команду
        success, description, date_str, time_str, repeat_type_input = parse_avatar_command(
            command_text, has_photo=has_photo, has_reply=has_reply_photo
        )

        if not success:
            await msg.reply(description)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Парсим дату и время
        try:
            scheduled_time_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            scheduled_time = MOSCOW_TZ.localize(scheduled_time_naive)
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.")
            return

        now_moscow = datetime.now(MOSCOW_TZ)
        if scheduled_time <= now_moscow:
            await msg.reply("❌ Время должно быть в будущем!")
            return

        # Сохраняем в БД
        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='avatar',
            new_value=description if description else "Аватарка",
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            notes=description if description else None
        )

        if success:
            # Обновляем время последнего изменения (для планируемых изменений тоже учитываем)
            await update_avatar_change_time(chat_id)

            repeat_text = _get_repeat_text(repeat_type)
            response = (
                f"✅ Запланирована смена аватарки:\n"
                f"⏰ Когда: {date_str} {time_str}\n"
                f"🔄 Повторение: {repeat_text}\n"
                f"🆔 Используйте !удалить аватарку [ID] для отмены"
            )

            if description:
                response += f"\n📝 Описание: {description}"

            await msg.reply_photo(file_id, caption=response)
        else:
            await msg.reply("❌ Не удалось запланировать изменение. Возможно, такое уже существует.")

    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_avatar_change: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[+!/.](завтра|сегодня) аватарка'))
async def schedule_avatar_quick(msg: Message):
    """Быстрое планирование аватарки на сегодня/завтра."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Проверяем лимит на частоту изменений аватарки
        can_change, limit_message = await check_avatar_rate_limit(chat_id)
        if not can_change:
            await msg.reply(limit_message)
            return

        # Определяем день
        text = msg.text.strip()
        day = 'сегодня' if 'сегодня' in text.lower() else 'завтра'

        # Проверяем, есть ли фото в сообщении
        has_photo = bool(msg.photo)
        has_reply_photo = bool(msg.reply_to_message and msg.reply_to_message.photo)

        if not has_photo and not has_reply_photo:
            await msg.reply(
                f"❌ Для аватарки необходимо:\n"
                "1. Прикрепить фото к сообщению\n"
                "2. Или ответить на фото\n"
                f"Пример использования:\n"
                f"+{day} аватарка 14:30 ежедневно"
            )
            return

        file_id = None
        file_unique_id = None

        if has_photo:
            photo = msg.photo[-1]
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id
        elif has_reply_photo:
            photo = msg.reply_to_message.photo[-1]
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id

        # Парсим команду
        success, time_str, repeat_type_input, description = parse_quick_avatar_command(text, day)
        if not success:
            await msg.reply(time_str)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Устанавливаем дату
        now_moscow = datetime.now(MOSCOW_TZ)
        if day == 'завтра':
            target_date = now_moscow + timedelta(days=1)
        else:
            target_date = now_moscow

        date_str = target_date.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            scheduled_time = MOSCOW_TZ.localize(scheduled_time_naive)
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Проверяем, что время в будущем (для сегодня)
        if day == 'сегодня' and scheduled_time <= now_moscow:
            await msg.reply("❌ Время должно быть в будущем! Используйте время позже текущего.")
            return

        # Сохраняем в БД
        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='avatar',
            new_value=description if description else f"Аватарка на {day}",
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            notes=description if description else None
        )

        if success:
            # Обновляем время последнего изменения
            await update_avatar_change_time(chat_id)

            repeat_text = _get_repeat_text(repeat_type)
            response = (
                f"✅ Запланирована смена аватарки:\n"
                f"⏰ {day.capitalize()} в {time_str}\n"
                f"🔄 Повторение: {repeat_text}"
            )

            if description:
                response += f"\n📝 Описание: {description}"

            await msg.reply_photo(file_id, caption=response)
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")

    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_avatar_quick: {e}", exc_info=True)


# Функция для проверки лимита при реальном применении изменений
async def check_and_update_avatar_application(chat_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверяет лимит при реальном применении аватарки.
    Вызывается из сервиса перед применением изменения.
    """
    return await check_avatar_rate_limit(chat_id)


# Функция для обновления времени после применения аватарки
async def update_avatar_after_application(chat_id: int):
    """Обновляет время после успешного применения аватарки."""
    await update_avatar_change_time(chat_id)


# Команды для просмотра
@auto_chat_router.message(F.text.regexp(r'^[!/.]названия чата(\s+\d+)?$'))
async def view_titles(msg: Message):
    """Показывает запланированные названия."""
    await _view_changes_by_type(msg, 'title')


@auto_chat_router.message(F.text.regexp(r'^[!/.]аватарки чата(\s+\d+)?$'))
async def view_avatars(msg: Message):
    """Показывает запланированные аватарки."""
    await _view_changes_by_type(msg, 'avatar')


@auto_chat_router.message(F.text.regexp(r'^[!/.]описания чата(\s+\d+)?$'))
async def view_descriptions(msg: Message):
    """Показывает запланированные описания."""
    await _view_changes_by_type(msg, 'description')


@auto_chat_router.message(F.text.regexp(r'^[!/.]изменения чата(\s+\d+)?$'))
async def view_all_changes(msg: Message):
    """Показывает все запланированные изменения."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    page = 1
    parts = msg.text.split()
    if len(parts) > 1 and parts[-1].isdigit():
        page = int(parts[-1])

    changes = await get_all_active_changes(chat_id)
    if not changes:
        await msg.reply("📭 Нет запланированных изменений для этого чата.")
        return

    changes_by_date = {}
    for change in changes:
        date_key = change['scheduled_time'].strftime("%d.%m.%Y")
        if date_key not in changes_by_date:
            changes_by_date[date_key] = []
        changes_by_date[date_key].append(change)

    sorted_dates = sorted(changes_by_date.keys(),
                          key=lambda x: datetime.strptime(x, "%d.%m.%Y"))

    dates_per_page = 3
    total_pages = (len(sorted_dates) + dates_per_page - 1) // dates_per_page
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * dates_per_page
    end_idx = start_idx + dates_per_page
    current_dates = sorted_dates[start_idx:end_idx]

    response = f"📅 Все запланированные изменения (Страница {page}/{total_pages}):\n"

    for date_str in current_dates:
        response += f"📌 <b>{date_str}</b>:\n"
        for change in changes_by_date[date_str]:
            time_str = change['scheduled_time'].strftime("%H:%M")
            type_emoji = {
                'title': '🏷️',
                'avatar': '🖼️',
                'description': '📝'
            }.get(change['change_type'], '📌')
            repeat_text = _get_repeat_text(change['repeat_type'])

            display_value = change['new_value']
            if len(display_value) > 50:
                display_value = display_value[:47] + "..."

            response += (f"  {type_emoji} <b>{change['change_type'].capitalize()}</b>\n"
                         f"  ⏰ {time_str} | {repeat_text}\n"
                         f"  📋 {display_value}\n"
                         f"  🆔 ID: {change['id']}\n")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []

    if page > 1:
        row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"all_changes_{page - 1}"
        ))

    if page < total_pages:
        row.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"all_changes_{page + 1}"
        ))

    if row:
        keyboard.inline_keyboard.append(row)

    types_row = [
        InlineKeyboardButton(text="🏷️ Названия", callback_data="view_titles_1"),
        InlineKeyboardButton(text="🖼️ Аватарки", callback_data="view_avatars_1"),
        InlineKeyboardButton(text="📝 Описания", callback_data="view_descriptions_1")
    ]
    keyboard.inline_keyboard.append(types_row)

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
    ])

    await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)


@auto_chat_router.message(F.text.regexp(r'^[!/.]статистика изменений$'))
async def view_stats(msg: Message):
    """Показывает статистику по изменениям."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    try:
        stats = await get_statistics(chat_id)
        if not stats or not stats.get('type_stats'):
            await msg.reply("📭 Нет активных запланированных изменений.")
            return

        response = "📊 <b>Статистика изменений чата:</b>\n\n"

        response += "📈 <b>По типам:</b>\n"
        type_names = {'title': '🏷️ Названия', 'avatar': '🖼️ Аватарки', 'description': '📝 Описания'}

        for type_stat in stats.get('type_stats', []):
            change_type = type_stat['change_type']
            count = type_stat.get('count', 0)
            response += f"  {type_names.get(change_type, change_type)}: {count}\n"

        response += "\n🔄 <b>По повторению:</b>\n"
        for repeat_stat in stats.get('repeat_stats', []):
            repeat_name = _get_repeat_text(repeat_stat['repeat_type'])
            response += f"  {repeat_name}: {repeat_stat['count']}\n"

        upcoming_count = stats.get('upcoming_count', 0)
        response += f"\n⏰ <b>Ближайшие изменения (24ч):</b> {upcoming_count}\n"

        # Добавляем информацию о лимите аватарок
        last_avatar = _last_avatar_change.get(chat_id)
        if last_avatar:
            now = datetime.now(MOSCOW_TZ)
            time_since = (now - last_avatar).total_seconds() / 60
            if time_since < 5:
                next_allowed = last_avatar + timedelta(minutes=5)
                minutes_left = int(5 - time_since)
                response += f"\n🖼️ <b>Лимит аватарок:</b> ⏳ {minutes_left} мин до следующего изменения\n"
            else:
                response += f"\n🖼️ <b>Лимит аватарок:</b> ✅ Можно менять\n"

        total_active = sum(stat.get('count', 0) for stat in stats.get('type_stats', []))
        response += f"\n📊 <b>Всего активных:</b> {total_active} изменений"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 Все изменения", callback_data="all_changes_1"),
            InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_all_confirm")
        ]])

        await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        await msg.reply("❌ Ошибка при получении статистики.")
        logger.error(f"Ошибка в view_stats: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[!/.]изменения на\s+\d{2}\.\d{2}\.\d{4}$'))
async def view_changes_by_date(msg: Message):
    """Показывает изменения на конкретную дату."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    try:
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', msg.text)
        if not date_match:
            await msg.reply("❌ Неверный формат даты. Используйте: !изменения на ДД.ММ.ГГГГ")
            return

        date_str = date_match.group(1)
        target_date = datetime.strptime(date_str, "%d.%m.%Y")

        changes = await get_combined_changes_by_date(chat_id, target_date)
        if not changes:
            await msg.reply(f"📭 На {date_str} нет запланированных изменений.")
            return

        changes_by_type = {}
        for change in changes:
            if change['change_type'] not in changes_by_type:
                changes_by_type[change['change_type']] = []
            changes_by_type[change['change_type']].append(change)

        response = f"📅 Изменения на {date_str}:\n"

        type_names = {
            'title': '🏷️ Названия',
            'avatar': '🖼️ Аватарки',
            'description': '📝 Описания'
        }

        for change_type, type_changes in changes_by_type.items():
            response += f"<b>{type_names.get(change_type, change_type.capitalize())}:</b>\n"

            for change in type_changes:
                time_str = change['scheduled_time'].strftime("%H:%M")
                repeat_text = _get_repeat_text(change['repeat_type'])

                display_value = change['new_value']
                if len(display_value) > 40:
                    display_value = display_value[:37] + "..."

                response += (f"  ⏰ {time_str} | {repeat_text}\n"
                             f"  📋 {display_value}\n"
                             f"  🆔 ID: {change['id']}\n")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🗑️ Удалить все на эту дату",
                callback_data=f"delete_all_{date_str.replace('.', '_')}"
            )
        ]])

        await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        await msg.reply("❌ Ошибка при получении изменений.")
        logger.error(f"Ошибка в view_changes_by_date: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[!/.]удалить (название|аватарку|описание)\s+\d+$'))
async def delete_scheduled_change_by_type(msg: Message):
    """Удаляет запланированное изменение по типу и ID."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 39):
        return

    try:
        parts = msg.text.split()
        type_russian = parts[1].lower()
        change_id = int(parts[2])

        type_mapping = {
            'название': 'title',
            'аватарку': 'avatar',
            'описание': 'description'
        }

        change_type = type_mapping.get(type_russian)
        if not change_type:
            await msg.reply("❌ Неверный тип изменения. Используйте: название, аватарку или описание")
            return

        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply("❌ Изменение с таким ID не найдено.")
            return

        if change['change_type'] != change_type:
            await msg.reply(f"❌ Изменение с ID {change_id} не является {type_russian}.")
            return



        success = await delete_change(change_id)
        if success:
            type_names = {
                'title': 'название',
                'avatar': 'аватарку',
                'description': 'описание'
            }
            type_name = type_names.get(change_type, 'изменение')
            await msg.reply(f"✅ Запланированная {type_name} (ID: {change_id}) удалена.")
        else:
            await msg.reply("❌ Не удалось удалить изменение.")

    except ValueError:
        await msg.reply("❌ Неверный формат ID. Используйте: !удалить название/аватарку/описание ID")
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при удалении.")
        logger.error(f"Ошибка в delete_scheduled_change_by_type: {e}", exc_info=True)


#@auto_chat_router.message(F.text.regexp(r'^[!/.]статус изменений$'))
async def check_service_status(msg: Message):
    """Проверяет статус сервиса автоматических изменений."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.chat.id, 40):
        return

    try:
        status = await test_service_status(msg.bot)
        if 'error' in status:
            response = f"❌ Сервис не инициализирован: {status['error']}"
        else:
            response = (
                f"📊 <b>Статус сервиса автоматических изменений:</b>\n"
                f"🔄 Статус: {'✅ Запущен' if status.get('is_running', False) else '⛔ Остановлен'}\n"
                f"⏰ Интервал проверки: {status.get('check_interval', 'N/A')} сек\n"
                f"📋 Задача проверки: {'✅ Работает' if status.get('check_task_running', False) else '⛔ Не работает'}\n"
                f"🤖 ID бота: {status.get('bot_id', 'N/A')}\n"
                f"🖼️ Лимит аватарок: 5 минут между изменениями\n"
                f"<i>Для принудительной проверки используйте !проверить изменения</i>"
            )

        await msg.reply(response, parse_mode='HTML')
    except Exception as e:
        await msg.reply(f"❌ Ошибка проверки статуса: {e}")
        logger.error(f"Ошибка в check_service_status: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[!/.]проверить изменения$'))
async def force_check_changes(msg: Message):
    """Принудительно запускает проверку изменений."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.chat.id, 40):
        return

    try:
        result = await force_check_now(msg.bot)
        if 'error' in result:
            response = f"❌ Не удалось запустить проверку: {result['error']}"
        else:
            response = "✅ Проверка изменений запущена принудительно"

        await msg.reply(response)
    except Exception as e:
        await msg.reply(f"❌ Ошибка запуска проверки: {e}")
        logger.error(f"Ошибка в force_check_changes: {e}", exc_info=True)


#@auto_chat_router.message(F.text.regexp(r'^[!/.]тест изменения\s+\d+$'))
async def test_change_application(msg: Message):
    """Тестирует принудительное применение изменения по ID."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.chat.id, 39):
        return

    try:
        change_id = int(msg.text.split()[-1])
        service = get_auto_chat_service(msg.bot)
        if not service:
            await msg.reply("❌ Сервис не инициализирован")
            return

        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply(f"❌ Изменение с ID {change_id} не найдено")
            return

        # Для аватарки проверяем лимит
        if change['change_type'] == 'avatar':
            can_change, limit_message = await check_avatar_rate_limit(msg.chat.id)
            if not can_change:
                await msg.reply(f"⚠️ {limit_message}\nПрименение отложено до истечения лимита.")
                return

        success = await service.apply_change_now(change_id)
        if success:
            # Если успешно применили аватарку, обновляем время
            if change['change_type'] == 'avatar':
                await update_avatar_after_application(msg.chat.id)
            await msg.reply(f"✅ Изменение {change_id} успешно применено")
        else:
            await msg.reply(f"❌ Не удалось применить изменение {change_id}")

    except Exception as e:
        await msg.reply(f"❌ Ошибка тестирования изменения: {e}")
        logger.error(f"Ошибка в test_change_application: {e}", exc_info=True)


# Обработчики callback-запросов
@auto_chat_router.callback_query(
    F.data.startswith(('titles_', 'avatars_', 'descriptions_', 'all_changes_',
                       'delete_all_', 'stats', 'clear_all_',
                       'view_titles_', 'view_avatars_', 'view_descriptions_')))
@rate_limit_with_cleanup(limit=1)
async def handle_pagination_callback(callback: CallbackQuery):
    # Проверяем, что callback от того же пользователя
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    #if not await _check_chat_admin_callback(callback):
     #   await callback.answer("❌ Недостаточно прав для выполнения действия", show_alert=True)
      #  return

    try:
        data = callback.data

        if data.startswith('titles_'):
            page = int(data.split('_')[1])
            await _send_changes_page(callback, 'title', page)
        elif data.startswith('avatars_'):
            page = int(data.split('_')[1])
            await _send_changes_page(callback, 'avatar', page)
        elif data.startswith('descriptions_'):
            page = int(data.split('_')[1])
            await _send_changes_page(callback, 'description', page)
        elif data.startswith('view_titles_'):
            parts = data.split('_')
            page = int(parts[2]) if len(parts) > 2 else 1
            await _send_changes_page(callback, 'title', page)
        elif data.startswith('view_avatars_'):
            parts = data.split('_')
            page = int(parts[2]) if len(parts) > 2 else 1
            await _send_changes_page(callback, 'avatar', page)
        elif data.startswith('view_descriptions_'):
            parts = data.split('_')
            page = int(parts[2]) if len(parts) > 2 else 1
            await _send_changes_page(callback, 'description', page)
        elif data.startswith('all_changes_'):
            parts = data.split('_')
            page = int(parts[2]) if len(parts) > 2 else 1
            await _send_all_changes_page(callback, page)
        elif data.startswith('delete_all_'):
            parts = data.split('_')
            if len(parts) >= 3:
                date_str = parts[2].replace('_', '.')
                await _delete_all_changes_on_date(callback, date_str)
        elif data == 'stats':
            await _show_stats_callback(callback)
        elif data == 'clear_all_confirm':
            await _confirm_clear_all(callback)
        elif data.startswith('clear_all_yes'):
            await _clear_all_changes(callback)

        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка при обработке запроса.")
        logger.error(f"Ошибка в handle_pagination_callback: {e}", exc_info=True)


# Вспомогательные функции для пагинации
async def _view_changes_by_type(msg: Message, change_type: str):
    """Отображает изменения определенного типа."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    page = 1
    parts = msg.text.split()
    if len(parts) > 1 and parts[-1].isdigit():
        page = int(parts[-1])

    await _send_changes_page(msg, change_type, page)


async def _send_changes_page(source: Union[Message, CallbackQuery], change_type: str, page: int = 1):
    """Отправляет страницу с изменениями."""
    if isinstance(source, Message):
        chat_id = source.chat.id
        reply_method = source.reply
    else:
        chat_id = source.message.chat.id
        reply_method = source.message.edit_text

    limit = 5

    changes, total = await get_changes_by_type(chat_id, change_type, page, limit)

    if not changes:
        text = "📭 Нет запланированных изменений этого типа."
        if isinstance(source, CallbackQuery):
            await reply_method(text)
        else:
            await reply_method(text)
        return

    type_names = {
        'title': '🏷️ Названия',
        'avatar': '🖼️ Аватарки',
        'description': '📝 Описания'
    }
    type_name = type_names.get(change_type, change_type.capitalize())

    total_pages = (total + limit - 1) // limit
    response = f"{type_name} (Страница {page}/{total_pages}):\n"

    for i, change in enumerate(changes, start=(page - 1) * limit + 1):
        date_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M")
        repeat_text = _get_repeat_text(change['repeat_type'])

        display_value = change['new_value']
        if len(display_value) > 60:
            display_value = display_value[:57] + "..."

        response += (f"<b>{i}. ID: {change['id']}</b>\n"
                     f"📅 {date_str} | {repeat_text}\n"
                     f"📋 {display_value}\n")

        if change.get('created_by'):
            creator_link = await user_link_global(change['created_by'])
            response += f"👤 Создал: {creator_link}\n"

        response += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []

    if page > 1:
        row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"{change_type}s_{page - 1}"
        ))

    if page < total_pages:
        row.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"{change_type}s_{page + 1}"
        ))

    if row:
        keyboard.inline_keyboard.append(row)

    action_row = [
        InlineKeyboardButton(
            text="🗑️ Удалить по ID",
            callback_data=f"delete_prompt_{change_type}"
        ),
        InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="stats"
        )
    ]
    keyboard.inline_keyboard.append(action_row)

    if isinstance(source, CallbackQuery):
        await reply_method(response, parse_mode='HTML', reply_markup=keyboard)
    else:
        await reply_method(response, parse_mode='HTML', reply_markup=keyboard)


async def _send_all_changes_page(callback: CallbackQuery, page: int):
    """Отправляет страницу со всеми изменениями через callback."""
    chat_id = callback.message.chat.id

    changes = await get_all_active_changes(chat_id)
    if not changes:
        await callback.message.edit_text("📭 Нет запланированных изменений для этого чата.")
        return

    changes_by_date = {}
    for change in changes:
        date_key = change['scheduled_time'].strftime("%d.%m.%Y")
        if date_key not in changes_by_date:
            changes_by_date[date_key] = []
        changes_by_date[date_key].append(change)

    sorted_dates = sorted(changes_by_date.keys(),
                          key=lambda x: datetime.strptime(x, "%d.%m.%Y"))

    dates_per_page = 3
    total_pages = (len(sorted_dates) + dates_per_page - 1) // dates_per_page
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * dates_per_page
    end_idx = start_idx + dates_per_page
    current_dates = sorted_dates[start_idx:end_idx]

    response = f"📅 Все запланированные изменения (Страница {page}/{total_pages}):\n"

    for date_str in current_dates:
        response += f"📌 <b>{date_str}</b>:\n"

        for change in changes_by_date[date_str]:
            time_str = change['scheduled_time'].strftime("%H:%M")
            type_emoji = {
                'title': '🏷️',
                'avatar': '🖼️',
                'description': '📝'
            }.get(change['change_type'], '📌')
            repeat_text = _get_repeat_text(change['repeat_type'])

            display_value = change['new_value']
            if len(display_value) > 50:
                display_value = display_value[:47] + "..."

            response += (f"  {type_emoji} <b>{change['change_type'].capitalize()}</b>\n"
                         f"  ⏰ {time_str} | {repeat_text}\n"
                         f"  📋 {display_value}\n"
                         f"  🆔 ID: {change['id']}\n")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []

    if page > 1:
        row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"all_changes_{page - 1}"
        ))

    if page < total_pages:
        row.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"all_changes_{page + 1}"
        ))

    if row:
        keyboard.inline_keyboard.append(row)

    types_row = [
        InlineKeyboardButton(text="🏷️ Названия", callback_data="view_titles_1"),
        InlineKeyboardButton(text="🖼️ Аватарки", callback_data="view_avatars_1"),
        InlineKeyboardButton(text="📝 Описания", callback_data="view_descriptions_1")
    ]
    keyboard.inline_keyboard.append(types_row)

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_all_confirm")
    ])

    await callback.message.edit_text(response, parse_mode='HTML', reply_markup=keyboard)


async def _delete_all_changes_on_date(callback: CallbackQuery, date_str: str):
    """Удаляет все изменения на указанную дату."""
    chat_id = callback.message.chat.id

    try:
        target_date = datetime.strptime(date_str, "%d.%m.%Y")
        changes = await get_combined_changes_by_date(chat_id, target_date)

        if not changes:
            await callback.message.edit_text(f"📭 На {date_str} нет изменений для удаления.")
            return

        # Удаляем каждое изменение
        deleted_count = 0
        for change in changes:
            success = await delete_change(change['id'])
            if success:
                deleted_count += 1

        await callback.message.edit_text(
            f"✅ Удалено {deleted_count} изменений на {date_str}."
        )
    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при удалении изменений.")
        logger.error(f"Ошибка в _delete_all_changes_on_date: {e}", exc_info=True)


async def _show_stats_callback(callback: CallbackQuery):
    """Показывает статистику для callback."""
    chat_id = callback.message.chat.id

    try:
        stats = await get_statistics(chat_id)
        if not stats or not stats.get('type_stats'):
            await callback.message.edit_text("📭 Нет активных запланированных изменений.")
            return

        response = "📊 <b>Статистика изменений чата:</b>\n\n"

        response += "📈 <b>По типам:</b>\n"
        type_names = {'title': '🏷️ Названия', 'avatar': '🖼️ Аватарки', 'description': '📝 Описания'}

        for type_stat in stats.get('type_stats', []):
            change_type = type_stat['change_type']
            count = type_stat.get('count', 0)
            response += f"  {type_names.get(change_type, change_type)}: {count}\n"

        response += "\n🔄 <b>По повторению:</b>\n"
        for repeat_stat in stats.get('repeat_stats', []):
            repeat_name = _get_repeat_text(repeat_stat['repeat_type'])
            response += f"  {repeat_name}: {repeat_stat['count']}\n"

        upcoming_count = stats.get('upcoming_count', 0)
        response += f"\n⏰ <b>Ближайшие изменения (24ч):</b> {upcoming_count}\n"

        total_active = sum(stat.get('count', 0) for stat in stats.get('type_stats', []))
        response += f"\n📊 <b>Всего активных:</b> {total_active} изменений"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 Все изменения", callback_data="all_changes_1"),
            InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_all_confirm")
        ]])

        await callback.message.edit_text(response, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при получении статистики.")
        logger.error(f"Ошибка в _show_stats_callback: {e}", exc_info=True)


async def _confirm_clear_all(callback: CallbackQuery):
    """Запрашивает подтверждение удаления всех изменений."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить все", callback_data="clear_all_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="all_changes_1")
        ]
    ])

    await callback.message.edit_text(
        "⚠️ <b>Вы уверены, что хотите удалить ВСЕ запланированные изменения?</b>\n"
        "Это действие нельзя отменить!",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _clear_all_changes(callback: CallbackQuery):
    """Удаляет все изменения в чате."""
    chat_id = callback.message.chat.id

    try:
        deleted_count = await delete_all_changes(chat_id)
        await callback.message.edit_text(
            f"✅ Удалено {deleted_count} изменений."
        )
    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при удалении изменений.")
        logger.error(f"Ошибка в _clear_all_changes: {e}", exc_info=True)


# Помощь по командам
#@auto_chat_router.message(Command("помощь_изменения"))
async def show_help(msg: Message):
    """Показывает справку по командам изменений."""
    help_text = """
🤖 <b>Автоматические изменения чата - Справка</b>

<b>📝 Планирование названия:</b>
• <code>+менять название [дата/время] [тип]</code>
  [текст названия на новой строке]

<b>📝 Планирование описания:</b>
• <code>+описание [дата/время] [тип]</code>
  [текст описания на новой строке]

<b>🖼️ Планирование аватарки:</b>
• <code>+аватарка [дата/время] [тип] [описание?]</code> + прикрепить фото
• <code>+сегодня аватарка ЧЧ:ММ [тип] [описание?]</code> + фото
• <code>+завтра аватарка ЧЧ:ММ [тип] [описание?]</code> + фото

<b>📊 Форматы даты/времени:</b>
• <b>Число:</b> 25
• <b>Число.месяц:</b> 25.12
• <b>Полная дата:</b> 25.12.2024
• <b>С временем:</b> 25.12 14:30 или 25.12.2024 14:30
• <b>Относительные:</b> сегодня, завтра, через неделю, через месяц

<b>🔄 Типы повторения:</b>
• <b>Русские:</b> одноразово, ежедневно, еженедельно, ежемесячно, ежегодно
• <b>English:</b> once, daily, weekly, monthly, yearly

<b>⚙️ Управление:</b>
• <code>!названия чата</code> - список названий
• <code>!аватарки чата</code> - список аватарок
• <code>!описания чата</code> - список описаний
• <code>!изменения чата</code> - все изменения
• <code>!статистика изменений</code> - статистика
• <code>!удалить название [ID]</code> - удалить название
• <code>!удалить аватарку [ID]</code> - удалить аватарку
• <code>!удалить описание [ID]</code> - удалить описание

⚠️ <b>Важно:</b> Аватарку можно менять не чаще 1 раза в 5 минут!
"""

    await msg.reply(help_text, parse_mode='HTML')


# Инициализация при старте
@auto_chat_router.startup()
async def on_startup():
    """Создает таблицу при старте бота."""
    await create_scheduled_changes_table()
    logger.info("Модуль автоматических изменений чата инициализирован")

    for cfg in MultiBotConfig.BOTS:
        bot = get_bot_by_token(cfg["TOKEN"])
        if bot:
            await init_auto_chat_service(bot)
            logger.info("Сервис автоматических изменений запущен для бота")


@auto_chat_router.shutdown()
async def on_shutdown():
    """Очищает кэш и останавливает сервис при выключении."""
    _last_avatar_change.clear()
    _avatar_lock.clear()
    await shutdown_auto_chat_service()
    logger.info("Сервис автоматических изменений остановлен")