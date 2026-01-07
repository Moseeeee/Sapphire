
import logging
import re
from datetime import datetime, timedelta

import pytz
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, PhotoSize
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_agent_access, \
    auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettingsDB import (
    add_scheduled_change, get_all_active_changes, get_combined_changes_by_date,
    get_change_by_id, delete_change, get_changes_by_type, create_scheduled_changes_table,
    deactivate_change, get_changes_by_status, get_statistics, delete_all_changes
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


def parse_repeat_type(user_input: str) -> str:
    """Парсит тип повторения с поддержкой русского и английского."""
    user_input = user_input.strip().lower()
    return REPEAT_TYPE_MAPPING.get(user_input, 'once')


def validate_repeat_type(repeat_type: str) -> tuple[bool, str]:
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


def parse_description_command(text: str) -> tuple[bool, str, str, str, str]:
    """
    Парсит команду для описания с поддержкой многострочного текста.
    Формат: +описание [дата] [время] [тип]
    [многострочный текст]
    """
    try:
        # Разделяем первую строку (команду) и остальной текст
        lines = text.split('\n', 1)
        if len(lines) < 2:
            return False, "❌ Описание должно быть на новой строке", "", "", ""

        command_line = lines[0].strip()
        description_text = lines[1].strip()

        if not description_text:
            return False, "❌ Описание не может быть пустым", "", "", ""

        # Парсим команду: +описание [дата] [время] [тип]
        parts = command_line.split()
        if len(parts) < 4:
            return False, "❌ Неверный формат команды.\n✅ Используйте: +описание ДД.ММ.ГГГГ ЧЧ:ММ тип\n[текст описания на новой строке]", "", "", ""

        # Проверяем префикс команды
        if not parts[0].startswith(('+', '!', '/', '.')):
            return False, "❌ Неверный префикс команды", "", "", ""

        # Извлекаем дату, время и тип
        date_str = parts[1]
        time_str = parts[2]
        repeat_type_input = ' '.join(parts[3:])  # Объединяем оставшиеся части на случай пробелов в типе

        return True, description_text, date_str, time_str, repeat_type_input
    except Exception as e:
        logger.error(f"Ошибка парсинга команды описания: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", "", ""


def parse_title_command(text: str) -> tuple[bool, str, str, str, str]:
    """
    Парсит команду для названия с поддержкой многострочного текста.
    Формат: +менять название [дата] [время] [тип]
    [многострочный текст]
    """
    try:
        # Разделяем первую строку (команду) и остальной текст
        lines = text.split('\n', 1)
        if len(lines) < 2:
            return False, "❌ Название должно быть на новой строке", "", "", ""

        command_line = lines[0].strip()
        title_text = lines[1].strip()

        if not title_text:
            return False, "❌ Название не может быть пустым", "", "", ""

        # Парсим команду: +менять название [дата] [время] [тип]
        parts = command_line.split()
        if len(parts) < 5:
            return False, "❌ Неверный формат команды.\n✅ Используйте: +менять название ДД.ММ.ГГГГ ЧЧ:ММ тип\n[текст названия на новой строке]", "", "", ""

        # Проверяем префикс команды
        if not parts[0].startswith(('+', '!', '/', '.')):
            return False, "❌ Неверный префикс команды", "", "", ""

        # Проверяем что это команда "менять название"
        command_words = [parts[1].lower(), parts[2].lower()]
        if 'менять' not in command_words and 'изменить' not in command_words:
            return False, "❌ Неверная команда. Используйте: +менять название", "", "", ""

        if 'название' not in command_words and 'title' not in command_words and 'имя' not in command_words:
            return False, "❌ Неверная команда. Используйте: +менять название", "", "", ""

        # Извлекаем дату, время и тип
        date_str = parts[3]
        time_str = parts[4]
        repeat_type_input = ' '.join(parts[5:]) if len(parts) > 5 else 'once'

        return True, title_text, date_str, time_str, repeat_type_input
    except Exception as e:
        logger.error(f"Ошибка парсинга команды названия: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", "", ""


def parse_avatar_command(text: str, has_photo: bool = False, has_reply: bool = False) -> tuple[
    bool, str, str, str, str]:
    """
    Парсит команду для аватарки.
    Варианты:
    1. С фото в сообщении: +аватарка [описание?] [дата] [время] [тип]
    2. С reply на фото: +аватарка [описание?] [дата] [время] [тип]
    """
    try:
        # Удаляем префикс команды
        text = text.strip()
        prefixes = ['+аватарка', '!аватарка', '/аватарка', '.аватарка']
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        # Если нет фото в сообщении или в ответе, возвращаем ошибку
        if not has_photo and not has_reply:
            return False, "❌ Для аватарки необходимо прикрепить фото к сообщению или ответить на фото", "", "", ""

        # Формат: [описание?] [дата] [время] [тип]
        parts = text.split()

        # Пытаемся найти дату в формате ДД.ММ.ГГГГ
        date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
        date_index = -1
        for i, part in enumerate(parts):
            if re.match(date_pattern, part):
                date_index = i
                break

        if date_index == -1:
            return False, "❌ Не найдена дата в формате ДД.ММ.ГГГГ", "", "", ""

        # Описание - все до даты
        description = ' '.join(parts[:date_index]) if date_index > 0 else ""

        # Проверяем что после даты есть время и тип
        if len(parts) < date_index + 3:
            return False, "❌ Неверный формат. После даты должно быть время и тип", "", "", ""

        date_str = parts[date_index]
        time_str = parts[date_index + 1]
        repeat_type_input = ' '.join(parts[date_index + 2:])

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

        # Формат: [время] [тип] [описание?]
        parts = text.split()
        if len(parts) < 2:
            return False, "❌ Неверный формат. Используйте: ЧЧ:ММ тип [описание?]", "", ""

        time_str = parts[0]
        repeat_type_input = parts[1]
        description = ' '.join(parts[2:]) if len(parts) > 2 else ""

        return True, time_str, repeat_type_input, description
    except Exception as e:
        logger.error(f"Ошибка парсинга быстрой команды аватарки: {e}", exc_info=True)
        return False, f"❌ Ошибка парсинга команды", "", ""



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


@auto_chat_router.message(F.text.regexp(r'^[+]название чата'))
async def schedule_title_change(msg: Message):
    """Добавляет запланированное изменение названия чата."""

    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # === Парсинг внутри функции (без parse_title_command) ===
        lines = msg.html_text.split("\n", 1)
        if len(lines) < 2:
            await msg.reply("❌ Название должно быть на новой строке")
            return

        command_line = lines[0].strip()
        title_text = lines[1].strip()

        if not title_text:
            await msg.reply("❌ Название не может быть пустым")
            return

        parts = command_line.split()
        if len(parts) < 5:
            await msg.reply(
                "❌ Неверный формат команды.\n"
                "✅ Используйте: +название чата ДД.ММ.ГГГГ ЧЧ:ММ тип\n"
                "[текст названия на новой строке]"
            )
            return

        # Проверка префикса и команды
        if not parts[0].startswith(('+', '!', '/', '.')):
            await msg.reply("❌ Неверный префикс команды")
            return

        # parts[0] = '+название', parts[1] = 'чата'
        base_cmd = parts[0][1:].lower()  # 'название'
        second_word = parts[1].lower()   # 'чата'

        if base_cmd != 'название' or second_word != 'чата':
            await msg.reply("❌ Неверная команда. Используйте: +название чата")
            return

        date_str = parts[2]
        time_str = parts[3]
        repeat_type_input = ' '.join(parts[4:])

        # === Валидация длины ===
        if len(title_text) > 255:
            await msg.reply(f"❌ Название не может превышать 255 символов (сейчас: {len(title_text)})")
            return

        # === Валидация типа повторения ===
        repeat_type = parse_repeat_type(repeat_type_input)
        valid_types = ['once', 'daily', 'weekly', 'monthly', 'yearly']
        if repeat_type not in valid_types:
            russian_types = ['одноразово', 'ежедневно', 'еженедельно', 'ежемесячно', 'ежегодно']
            await msg.reply(f"❌ Неверный тип повторения.\n📝 Доступные: {', '.join(russian_types)}")
            return

        # === Парсинг и валидация времени ===
        try:
            scheduled_time_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.\n📅 Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ")
            return

        moscow_tz = pytz.timezone("Europe/Moscow")
        scheduled_time = moscow_tz.localize(scheduled_time_naive)
        now_moscow = datetime.now(moscow_tz)

        if scheduled_time <= now_moscow:
            await msg.reply("❌ Время должно быть в будущем!")
            return

        # === Сохранение в БД ===
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
            display_title = title_text
            if len(display_title) > 100:
                display_title = display_title[:97] + "..."

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


#@auto_chat_router.message(F.text.regexp(r'^[+!/.]завтра название'))
async def schedule_title_tomorrow(msg: Message):
    """Быстрое планирование изменения названия на завтра."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Формат: +завтра название [время] [тип]\n[название]
        lines = msg.text.split('\n', 1)
        if len(lines) < 2:
            await msg.reply(
                "❌ Формат: +завтра название ЧЧ:ММ тип\n"
                "[название на новой строке]\n"
                "Пример:\n"
                "+завтра название 14:30 ежедневно\n"
                "Новое название чата"
            )
            return

        command_line = lines[0].strip()
        title_text = lines[1].strip()

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 4:
            await msg.reply("❌ Неверный формат. Используйте: +завтра название ЧЧ:ММ тип")
            return

        time_str = parts[2]
        repeat_type_input = parts[3]

        # Проверяем длину названия
        is_valid_length, length_error = validate_text_length(title_text, 255, "Название")
        if not is_valid_length:
            await msg.reply(length_error)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Завтрашняя дата
        tomorrow = datetime.now() + timedelta(days=1)
        date_str = tomorrow.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Добавляем в базу
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
            # Обрезаем длинное название для отображения
            display_title = title_text
            if len(display_title) > 100:
                display_title = display_title[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение названия:\n"
                f"📝 Название: {display_title}\n"
                f"⏰ Завтра в {time_str}\n"
                f"🔄 Повторение: {repeat_text}"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_title_tomorrow: {e}", exc_info=True)


#@auto_chat_router.message(F.text.regexp(r'^[+!/.]сегодня название'))
async def schedule_title_today(msg: Message):
    """Быстрое планирование изменения названия на сегодня."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Формат: +сегодня название [время] [тип]\n[название]
        lines = msg.text.split('\n', 1)
        if len(lines) < 2:
            await msg.reply(
                "❌ Формат: +сегодня название ЧЧ:ММ тип\n"
                "[название на новой строке]\n"
                "Пример:\n"
                "+сегодня название 14:30 ежедневно\n"
                "Новое название чата"
            )
            return

        command_line = lines[0].strip()
        title_text = lines[1].strip()

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 4:
            await msg.reply("❌ Неверный формат. Используйте: +сегодня название ЧЧ:ММ тип")
            return

        time_str = parts[2]
        repeat_type_input = parts[3]

        # Проверяем длину названия
        is_valid_length, length_error = validate_text_length(title_text, 255, "Название")
        if not is_valid_length:
            await msg.reply(length_error)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Сегодняшняя дата
        today = datetime.now()
        date_str = today.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Проверяем, что время в будущем
        if scheduled_time <= datetime.now():
            await msg.reply("❌ Время должно быть в будущем! Используйте время позже текущего.")
            return

        # Добавляем в базу
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
            # Обрезаем длинное название для отображения
            display_title = title_text
            if len(display_title) > 100:
                display_title = display_title[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение названия:\n"
                f"📝 Название: {display_title}\n"
                f"⏰ Сегодня в {time_str}\n"
                f"🔄 Повторение: {repeat_text}"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_title_today: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[+]описание'))
async def schedule_description_change(msg: Message):
    """Добавляет запланированное изменение описания."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        success, description_text, date_str, time_str, repeat_type_input = parse_description_command(msg.text)
        if not success:
            await msg.reply(description_text)  # В этом случае description_text содержит сообщение об ошибке
            return

        # Проверяем длину описания
        is_valid_length, length_error = validate_text_length(description_text, 255, "Описание")
        if not is_valid_length:
            await msg.reply(length_error)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Создаем дату и время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.\n📅 Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ")
            return

        if scheduled_time <= datetime.now():
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
            # Обрезаем длинное описание для отображения
            display_desc = description_text
            if len(display_desc) > 100:
                display_desc = display_desc[:97] + "..."

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


#@auto_chat_router.message(F.text.regexp(r'^[+!/.]завтра описание'))
async def schedule_description_tomorrow(msg: Message):
    """Быстрое планирование изменения описания на завтра."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Формат: +завтра описание [время] [тип]\n[описание]
        lines = msg.text.split('\n', 1)
        if len(lines) < 2:
            await msg.reply(
                "❌ Формат: +завтра описание ЧЧ:ММ тип\n"
                "[описание на новой строке]\n"
                "Пример:\n"
                "+завтра описание 14:30 ежедневно\n"
                "Новое описание чата"
            )
            return

        command_line = lines[0].strip()
        description_text = lines[1].strip()

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 4:
            await msg.reply("❌ Неверный формат. Используйте: +завтра описание ЧЧ:ММ тип")
            return

        time_str = parts[2]
        repeat_type_input = parts[3]

        # Проверяем длину описания
        is_valid_length, length_error = validate_text_length(description_text, 255, "Описание")
        if not is_valid_length:
            await msg.reply(length_error)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Завтрашняя дата
        tomorrow = datetime.now() + timedelta(days=1)
        date_str = tomorrow.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Добавляем в базу
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
            # Обрезаем длинное описание для отображения
            display_desc = description_text
            if len(display_desc) > 100:
                display_desc = display_desc[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение описания:\n"
                f"📝 Описание: {display_desc}\n"
                f"⏰ Завтра в {time_str}\n"
                f"🔄 Повторение: {repeat_text}"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_description_tomorrow: {e}", exc_info=True)


#@auto_chat_router.message(F.text.regexp(r'^[+!/.]сегодня описание'))
async def schedule_description_today(msg: Message):
    """Быстрое планирование изменения описания на сегодня."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Формат: +сегодня описание [время] [тип]\n[описание]
        lines = msg.text.split('\n', 1)
        if len(lines) < 2:
            await msg.reply(
                "❌ Формат: +сегодня описание ЧЧ:ММ тип\n"
                "[описание на новой строке]\n"
                "Пример:\n"
                "+сегодня описание 14:30 ежедневно\n"
                "Новое описание чата"
            )
            return

        command_line = lines[0].strip()
        description_text = lines[1].strip()

        # Парсим команду
        parts = command_line.split()
        if len(parts) < 4:
            await msg.reply("❌ Неверный формат. Используйте: +сегодня описание ЧЧ:ММ тип")
            return

        time_str = parts[2]
        repeat_type_input = parts[3]

        # Проверяем длину описания
        is_valid_length, length_error = validate_text_length(description_text, 255, "Описание")
        if not is_valid_length:
            await msg.reply(length_error)
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Сегодняшняя дата
        today = datetime.now()
        date_str = today.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Проверяем, что время в будущем
        if scheduled_time <= datetime.now():
            await msg.reply("❌ Время должно быть в будущем! Используйте время позже текущего.")
            return

        # Добавляем в базу
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
            # Обрезаем длинное описание для отображения
            display_desc = description_text
            if len(display_desc) > 100:
                display_desc = display_desc[:97] + "..."

            await msg.reply(
                f"✅ Запланировано изменение описания:\n"
                f"📝 Описание: {display_desc}\n"
                f"⏰ Сегодня в {time_str}\n"
                f"🔄 Повторение: {repeat_text}"
            )
        else:
            await msg.reply("❌ Не удалось запланировать изменение.")
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_description_today: {e}", exc_info=True)


# Команда для аватарки с поддержкой фото в сообщении
@auto_chat_router.message(F.text.regexp(r'^[+]аватарка') | F.caption.regexp(r'^[+]аватарка'))
async def schedule_avatar_change(msg: Message):
    """Добавляет запланированное изменение аватарки."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Проверяем, есть ли фото в сообщении
        has_photo = bool(msg.photo)
        # Проверяем, есть ли reply с фото
        has_reply_photo = bool(msg.reply_to_message and msg.reply_to_message.photo)

        # Если нет фото, отправляем ошибку
        if not has_photo and not has_reply_photo:
            await msg.reply(
                "❌ Для аватарки необходимо:\n"
                "1. Прикрепить фото к сообщению с командой в подписи\n"
                "2. Или ответить на фото командой\n"
                "Пример подписи:\n"
                "+аватарка 25.12.2024 14:30 ежедневно"
            )
            return

        file_id = None
        file_unique_id = None

        # Получаем file_id из фото в сообщении или reply
        if has_photo:
            photo: PhotoSize = msg.photo[-1]  # Берем фото самого высокого качества
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id
            command_text = msg.caption or ""
        elif has_reply_photo:
            photo: PhotoSize = msg.reply_to_message.photo[-1]
            file_id = photo.file_id
            file_unique_id = photo.file_unique_id
            command_text = msg.text or ""

        if not command_text.strip():
            await msg.reply("❌ Команда не найдена. Убедитесь, что команда указана в подписи к фото или в тексте ответа.")
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

        # Создаем дату и время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Ошибка в формате даты/времени.\n📅 Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ")
            return

        if scheduled_time <= datetime.now():
            await msg.reply("❌ Время должно быть в будущем!")
            return

        # Добавляем в базу
        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='avatar',
            new_value=description if description else "Аватарка из фото",
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id,
            file_id=file_id,
            file_unique_id=file_unique_id
        )

        if success:
            repeat_text = _get_repeat_text(repeat_type)
            response = (
                f"✅ Запланирована смена аватарки:\n"
                f"⏰ Когда: {date_str} {time_str}\n"
                f"🔄 Повторение: {repeat_text}\n"
                f"🆔 Используйте !уддалить аватарку [ID] для отмены"
            )

            if description:
                response += f"\n📝 Описание: {description}"

            await msg.reply_photo(file_id, caption=response)
        else:
            await msg.reply("❌ Не удалось запланировать изменение. Возможно, такое уже существует.")
    except ValueError as e:
        await msg.reply("❌ Ошибка формата. Проверьте правильность введенных данных.")
        logger.error(f"Ошибка формата в schedule_avatar_change: {e}", exc_info=True)
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_avatar_change: {e}", exc_info=True)


# Новая команда: быстрая аватарка (сегодня/завтра)
#@auto_chat_router.message(F.text.regexp(r'^[+!/.](сегодня|завтра) аватарка'))
async def schedule_avatar_quick(msg: Message):
    """Быстрое планирование аватарки на сегодня/завтра."""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    try:
        # Определяем день
        text = msg.text.strip()
        day = 'сегодня' if 'сегодня' in text.lower() else 'завтра'

        # Проверяем, есть ли фото в сообщении
        has_photo = bool(msg.photo)
        has_reply_photo = bool(msg.reply_to_message and msg.reply_to_message.photo)

        # Если нет фото, отправляем ошибку
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
            await msg.reply(time_str)  # В этом случае time_str содержит сообщение об ошибке
            return

        # Валидируем тип повторения
        is_valid, repeat_type_result = validate_repeat_type(repeat_type_input)
        if not is_valid:
            await msg.reply(repeat_type_result)
            return
        repeat_type = repeat_type_result

        # Устанавливаем дату
        today = datetime.now()
        if day == 'завтра':
            target_date = today + timedelta(days=1)
        else:
            target_date = today

        date_str = target_date.strftime("%d.%m.%Y")

        # Создаем полное время
        try:
            scheduled_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            await msg.reply("❌ Неверный формат времени. Используйте: ЧЧ:ММ")
            return

        # Проверяем, что время в будущем (для сегодня)
        if day == 'сегодня' and scheduled_time <= datetime.now():
            await msg.reply("❌ Время должно быть в будущем! Используйте время позже текущего.")
            return

        # Добавляем в базу
        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='avatar',
            new_value=description if description else f"Аватарка на {day}",
            scheduled_time=scheduled_time,
            repeat_type=repeat_type,
            created_by=user_id,
            file_id=file_id,
            file_unique_id=file_unique_id
        )

        if success:
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
    except ValueError as e:
        await msg.reply("❌ Ошибка формата. Проверьте правильность введенных данных.")
        logger.error(f"Ошибка формата в schedule_avatar_quick: {e}", exc_info=True)
    except Exception as e:
        await msg.reply("❌ Произошла ошибка при обработке команды.")
        logger.error(f"Ошибка в schedule_avatar_quick: {e}", exc_info=True)


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

    # Парсим номер страницы
    page = 1
    if msg.text.split()[-1].isdigit():
        page = int(msg.text.split()[-1])

    # Получаем все изменения
    changes = await get_all_active_changes(chat_id)
    if not changes:
        await msg.reply("📭 Нет запланированных изменений для этого чата.")
        return

    # Группируем по дате
    changes_by_date = {}
    for change in changes:
        date_key = change['scheduled_time'].strftime("%d.%m.%Y")
        if date_key not in changes_by_date:
            changes_by_date[date_key] = []
        changes_by_date[date_key].append(change)

    # Сортируем даты
    sorted_dates = sorted(changes_by_date.keys(),
                          key=lambda x: datetime.strptime(x, "%d.%m.%Y"))

    # Пагинация по датам (3 даты на страницу)
    dates_per_page = 3
    total_pages = (len(sorted_dates) + dates_per_page - 1) // dates_per_page
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * dates_per_page
    end_idx = start_idx + dates_per_page
    current_dates = sorted_dates[start_idx:end_idx]

    # Формируем сообщение
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

            # Обрезаем длинный текст для отображения
            display_value = change['new_value']
            if len(display_value) > 50:
                display_value = display_value[:47] + "..."

            response += (f"  {type_emoji} <b>{change['change_type'].capitalize()}</b>\n"
                         f"  ⏰ {time_str} | {repeat_text}\n"
                         f"  📋 {display_value}\n"
                         f"  🆔 ID: {change['id']}\n")

    # Создаем клавиатуру пагинации
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

    # Добавляем кнопки для отдельных типов
    types_row = [
        InlineKeyboardButton(text="🏷️ Названия", callback_data="view_titles_1"),
        InlineKeyboardButton(text="🖼️ Аватарки", callback_data="view_avatars_1"),
        InlineKeyboardButton(text="📝 Описания", callback_data="view_descriptions_1")
    ]
    keyboard.inline_keyboard.append(types_row)

    # Добавляем кнопку статистики
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
    ])

    await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)


# Новая команда: статистика
#@auto_chat_router.message(F.text.regexp(r'^[!/.]статистика изменений$'))
async def view_stats(msg: Message):
    """Показывает статистику по изменениям."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    try:
        # Получаем статистику
        stats = await get_statistics(chat_id)
        if not stats:
            await msg.reply("📭 Нет активных запланированных изменений.")
            return

        response = "📊 <b>Статистика изменений чата:</b>\n"

        # Статистика по типам
        response += "📈 <b>По типам:</b>\n"
        type_names = {'title': '🏷️ Названия', 'avatar': '🖼️ Аватарки', 'description': '📝 Описания'}

        for type_stat in stats.get('type_stats', []):
            change_type = type_stat['change_type']
            active = type_stat.get('active', 0)
            inactive = type_stat.get('inactive', 0)
            response += f"  {type_names.get(change_type, change_type)}: {active} активных"
            if inactive > 0:
                response += f", {inactive} неактивных"
            response += "\n"

        # Статистика по повторениям
        response += "\n🔄 <b>По повторению:</b>\n"
        for repeat_stat in stats.get('repeat_stats', []):
            repeat_name = _get_repeat_text(repeat_stat['repeat_type'])
            response += f"  {repeat_name}: {repeat_stat['count']}\n"

        # Ближайшие изменения
        upcoming_count = stats.get('upcoming_count', 0)
        response += f"\n⏰ <b>Ближайшие изменения (24ч):</b> {upcoming_count}\n"

        # Последние изменения
        recent_changes = stats.get('recent_changes', [])
        if recent_changes:
            response += "\n📋 <b>Последние изменения:</b>\n"
            for i, change in enumerate(recent_changes[:5], 1):
                date_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M") if change.get(
                    'scheduled_time') else "N/A"
                type_emoji = {'title': '🏷️', 'avatar': '🖼️', 'description': '📝'}.get(change.get('change_type', ''), '📌')
                response += f"  {i}. {type_emoji} {date_str}\n"

        # Общее количество
        total_active = sum(stat.get('active', 0) for stat in stats.get('type_stats', []))
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
        # Извлекаем дату из команды
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', msg.text)
        if not date_match:
            await msg.reply("❌ Неверный формат даты. Используйте: !изменения на ДД.ММ.ГГГГ")
            return

        date_str = date_match.group(1)
        target_date = datetime.strptime(date_str, "%d.%m.%Y")

        # Получаем изменения на эту дату
        changes = await get_combined_changes_by_date(chat_id, target_date)
        if not changes:
            await msg.reply(f"📭 На {date_str} нет запланированных изменений.")
            return

        # Группируем изменения по типу
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

                # Обрезаем текст для отображения
                display_value = change['new_value']
                if len(display_value) > 40:
                    display_value = display_value[:37] + "..."

                response += (f"  ⏰ {time_str} | {repeat_text}\n"
                             f"  📋 {display_value}\n"
                             f"  🆔 ID: {change['id']}\n")

        # Кнопка для удаления всех изменений на эту дату
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


# Команда для удаления изменения с поддержкой русского
@auto_chat_router.message(F.text.regexp(r'^[!/.]удалить (название|аватарку|описание)\s+\d+$'))
async def delete_scheduled_change_by_type(msg: Message):
    """Удаляет запланированное изменение по типу и ID."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.from_user.id, 39):
        return

    try:
        # Извлекаем тип и ID
        parts = msg.text.split()
        type_russian = parts[1].lower()
        change_id = int(parts[2])

        # Маппинг русских названий на английские
        type_mapping = {
            'название': 'title',
            'аватарку': 'avatar',
            'описание': 'description'
        }

        change_type = type_mapping.get(type_russian)
        if not change_type:
            await msg.reply("❌ Неверный тип изменения. Используйте: название, аватарку или описание")
            return

        # Получаем информацию об изменении
        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply("❌ Изменение с таким ID не найдено.")
            return

        # Проверяем тип
        if change['change_type'] != change_type:
            await msg.reply(f"❌ Изменение с ID {change_id} не является {type_russian}.")
            return

        # Проверяем, что удаляет создатель или администратор
        if change['created_by'] != user_id:
            # Проверяем права агента
            agent_rang = await check_agent_access(user_id)
            if agent_rang <= 2:  # Только старшие агенты и выше
                await msg.reply("❌ Вы не можете удалить это изменение.")
                return

        # Удаляем изменение
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


# Команда для отключения изменения (мягкое удаление)
#@auto_chat_router.message(F.text.regexp(r'^[!/.]отключить изменение\s+\d+$'))
async def deactivate_scheduled_change(msg: Message):
    """Отключает запланированное изменение (мягкое удаление)."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.from_user.id, 39):
        return

    try:
        change_id = int(msg.text.split()[-1])
        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply("❌ Изменение с таким ID не найдено.")
            return

        if change['created_by'] != user_id:
            agent_rang = await check_agent_access(user_id)
            if agent_rang <= 2:
                await msg.reply("❌ Вы не можете отключить это изменение.")
                return

        # Деактивируем изменение
        success = await deactivate_change(change_id)
        if success:
            type_names = {
                'title': 'название',
                'avatar': 'аватарку',
                'description': 'описание'
            }
            type_name = type_names.get(change['change_type'], 'изменение')
            await msg.reply(f"✅ Запланированная {type_name} (ID: {change_id}) отключена.\n"
                            f"ℹ️ Его можно восстановить из архива.")
        else:
            await msg.reply("❌ Не удалось отключить изменение.")

    except Exception as e:
        await msg.reply("❌ Произошла ошибка при отключении.")
        logger.error(f"Ошибка в deactivate_scheduled_change: {e}", exc_info=True)


# Команда для восстановления отключенных изменений
#@auto_chat_router.message(F.text.regexp(r'^[!/.]архив изменений(\s+\d+)?$'))
async def view_archived_changes(msg: Message):
    """Показывает отключенные (архивированные) изменения."""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 39):
        return

    try:
        page = 1
        if msg.text.split()[-1].isdigit():
            page = int(msg.text.split()[-1])

        # Получаем отключенные изменения
        changes, total = await get_changes_by_status(chat_id, is_active=False, page=page, limit=5)
        if not changes:
            await msg.reply("📭 Нет отключенных изменений в архиве.")
            return

        response = f"📁 Архив отключенных изменений (Страница {page}/{(total + 4) // 5}):\n"

        for change in changes:
            date_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M")
            type_emoji = {
                'title': '🏷️',
                'avatar': '🖼️',
                'description': '📝'
            }.get(change['change_type'], '📌')
            repeat_text = _get_repeat_text(change['repeat_type'])

            # Обрезаем текст
            display_value = change['new_value']
            if len(display_value) > 40:
                display_value = display_value[:37] + "..."

            response += (f"{type_emoji} <b>ID: {change['id']}</b>\n"
                         f"📅 {date_str} | {repeat_text}\n"
                         f"📋 {display_value}\n")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Восстановить", callback_data=f"restore_{page}"),
            InlineKeyboardButton(text="🗑️ Удалить навсегда", callback_data=f"delete_perm_{page}")
        ]])

        await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        await msg.reply("❌ Ошибка при получении архива.")
        logger.error(f"Ошибка в view_archived_changes: {e}", exc_info=True)


# Команда для проверки статуса сервиса
#@auto_chat_router.message(F.text.regexp(r'^[!/.]статус изменений$'))
async def check_service_status(msg: Message):
    """Проверяет статус сервиса автоматических изменений."""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.from_user.id, 40):
        return

    try:
        status = await test_service_status(msg.bot)
        if 'error' in status:
            response = f"❌ Сервис не инициализирован: {status['error']}"
        else:
            response = (
                f"📊 <b>Статус сервиса автоматических изменений:</b>\n"
                f"🔄 Статус: {'✅ Запущен' if status['is_running'] else '⛔ Остановлен'}\n"
                f"⏰ Интервал проверки: {status['check_interval']} сек\n"
                f"📋 Задача проверки: {'✅ Работает' if status['check_task_running'] else '⛔ Не работает'}\n"
                f"🤖 ID бота: {status['bot_id']}\n"
                f"<i>Для принудительной проверки используйте !проверить изменения</i>"
            )

        await msg.reply(response, parse_mode='HTML')
    except Exception as e:
        await msg.reply(f"❌ Ошибка проверки статуса: {e}")
        logger.error(f"Ошибка в check_service_status: {e}", exc_info=True)


#@auto_chat_router.message(F.text.regexp(r'^[!/.]проверить изменения$'))
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

        # Получаем информацию об изменении
        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply(f"❌ Изменение с ID {change_id} не найдено")
            return

        # Применяем изменение
        success = await service.apply_change_now(change_id)
        if success:
            await msg.reply(f"✅ Изменение {change_id} успешно применено")
        else:
            await msg.reply(f"❌ Не удалось применить изменение {change_id}")

    except Exception as e:
        await msg.reply(f"❌ Ошибка тестирования изменения: {e}")
        logger.error(f"Ошибка в test_change_application: {e}", exc_info=True)


# Обработчики callback-запросов
@auto_chat_router.callback_query(
    F.data.startswith(('titles_', 'avatars_', 'descriptions_', 'all_changes_',
                       'delete_all_', 'stats', 'clear_all_', 'restore_', 'delete_perm_',
                       'view_titles_', 'view_avatars_', 'view_descriptions_')))
@rate_limit_with_cleanup(limit=1)
async def handle_pagination_callback(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    """Обрабатывает callback-запросы для пагинации."""

    if not await _check_chat_admin_callback(callback):
        await callback.answer("У вас нет прав для этого действия.")
        return

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
            page = int(data.split('_')[2])
            await _send_changes_page(callback, 'title', page)
        elif data.startswith('view_avatars_'):
            page = int(data.split('_')[2])
            await _send_changes_page(callback, 'avatar', page)
        elif data.startswith('view_descriptions_'):
            page = int(data.split('_')[2])
            await _send_changes_page(callback, 'description', page)
        elif data.startswith('all_changes_'):
            page = int(data.split('_')[2])
            await _send_all_changes_page(callback, page)
        elif data.startswith('delete_all_'):
            date_str = data.split('_')[2].replace('_', '.')
            await _delete_all_changes_on_date(callback, date_str)
        elif data == 'stats':
            await _show_stats_callback(callback)
        elif data == 'clear_all_confirm':
            await _confirm_clear_all(callback)
        elif data.startswith('clear_all_yes'):
            await _clear_all_changes(callback)
        elif data.startswith('restore_'):
            page = int(data.split('_')[1])
            await _show_restore_options(callback, page)
        elif data.startswith('delete_perm_'):
            page = int(data.split('_')[2])
            await _show_delete_permanent_options(callback, page)

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

    # Парсим номер страницы
    page = 1
    parts = msg.text.split()
    if parts[-1].isdigit():
        page = int(parts[-1])

    await _send_changes_page(msg, change_type, page)


async def _send_changes_page(source, change_type: str, page: int = 1):
    """Отправляет страницу с изменениями."""
    chat_id = source.chat.id if isinstance(source, Message) else source.message.chat.id
    limit = 5

    # Получаем изменения
    changes, total = await get_changes_by_type(chat_id, change_type, page, limit)

    if not changes:
        text = "📭 Нет запланированных изменений этого типа."
        if isinstance(source, CallbackQuery):
            await source.message.edit_text(text)
        else:
            await source.reply(text)
        return

    # Типы на русском
    type_names = {
        'title': '🏷️ Названия',
        'avatar': '🖼️ Аватарки',
        'description': '📝 Описания'
    }
    type_name = type_names.get(change_type, change_type.capitalize())

    # Формируем сообщение
    response = f"{type_name} (Страница {page}/{(total + limit - 1) // limit}):\n"

    for i, change in enumerate(changes, start=(page - 1) * limit + 1):
        date_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M")
        repeat_text = _get_repeat_text(change['repeat_type'])

        # Обрезаем длинный текст
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

    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    total_pages = (total + limit - 1) // limit

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

    # Кнопки действий
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

    # Отправляем или редактируем сообщение
    if isinstance(source, CallbackQuery):
        await source.message.edit_text(response, parse_mode='HTML', reply_markup=keyboard)
    else:
        await source.reply(response, parse_mode='HTML', reply_markup=keyboard)


async def _send_all_changes_page(callback: CallbackQuery, page: int):
    """Отправляет страницу со всеми изменениями через callback."""
    chat_id = callback.message.chat.id

    # Получаем все изменения
    changes = await get_all_active_changes(chat_id)
    if not changes:
        await callback.message.edit_text("📭 Нет запланированных изменений для этого чата.")
        return

    # Группируем по дате
    changes_by_date = {}
    for change in changes:
        date_key = change['scheduled_time'].strftime("%d.%m.%Y")
        if date_key not in changes_by_date:
            changes_by_date[date_key] = []
        changes_by_date[date_key].append(change)

    # Сортируем даты
    sorted_dates = sorted(changes_by_date.keys(),
                          key=lambda x: datetime.strptime(x, "%d.%m.%Y"))

    # Пагинация по датам (3 даты на страницу)
    dates_per_page = 3
    total_pages = (len(sorted_dates) + dates_per_page - 1) // dates_per_page
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * dates_per_page
    end_idx = start_idx + dates_per_page
    current_dates = sorted_dates[start_idx:end_idx]

    # Формируем сообщение
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

            # Обрезаем длинный текст для отображения
            display_value = change['new_value']
            if len(display_value) > 50:
                display_value = display_value[:47] + "..."

            response += (f"  {type_emoji} <b>{change['change_type'].capitalize()}</b>\n"
                         f"  ⏰ {time_str} | {repeat_text}\n"
                         f"  📋 {display_value}\n"
                         f"  🆔 ID: {change['id']}\n")

    # Создаем клавиатуру пагинации
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

    # Добавляем кнопки для отдельных типов
    types_row = [
        InlineKeyboardButton(text="🏷️ Названия", callback_data="view_titles_1"),
        InlineKeyboardButton(text="🖼️ Аватарки", callback_data="view_avatars_1"),
        InlineKeyboardButton(text="📝 Описания", callback_data="view_descriptions_1")
    ]
    keyboard.inline_keyboard.append(types_row)

    # Добавляем кнопку статистики
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
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
            success = await delete_change(change['id'], archived_by=callback.from_user.id)
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
        # Получаем статистику
        stats = await get_statistics(chat_id)
        if not stats:
            await callback.message.edit_text("📭 Нет активных запланированных изменений.")
            return

        response = "📊 <b>Статистика изменений чата:</b>\n"

        # Статистика по типам
        response += "📈 <b>По типам:</b>\n"
        type_names = {'title': '🏷️ Названия', 'avatar': '🖼️ Аватарки', 'description': '📝 Описания'}

        for type_stat in stats.get('type_stats', []):
            change_type = type_stat['change_type']
            active = type_stat.get('active', 0)
            inactive = type_stat.get('inactive', 0)
            response += f"  {type_names.get(change_type, change_type)}: {active} активных"
            if inactive > 0:
                response += f", {inactive} неактивных"
            response += "\n"

        # Статистика по повторениям
        response += "\n🔄 <b>По повторению:</b>\n"
        for repeat_stat in stats.get('repeat_stats', []):
            repeat_name = _get_repeat_text(repeat_stat['repeat_type'])
            response += f"  {repeat_name}: {repeat_stat['count']}\n"

        # Ближайшие изменения
        upcoming_count = stats.get('upcoming_count', 0)
        response += f"\n⏰ <b>Ближайшие изменения (24ч):</b> {upcoming_count}\n"

        # Последние изменения
        recent_changes = stats.get('recent_changes', [])
        if recent_changes:
            response += "\n📋 <b>Последние изменения:</b>\n"
            for i, change in enumerate(recent_changes[:5], 1):
                date_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M") if change.get(
                    'scheduled_time') else "N/A"
                type_emoji = {'title': '🏷️', 'avatar': '🖼️', 'description': '📝'}.get(change.get('change_type', ''), '📌')
                response += f"  {i}. {type_emoji} {date_str}\n"

        # Общее количество
        total_active = sum(stat.get('active', 0) for stat in stats.get('type_stats', []))
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


async def _show_restore_options(callback: CallbackQuery, page: int):
    """Показывает опции восстановления."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Восстановить все на странице",
                                 callback_data=f"restore_page_{page}"),
            InlineKeyboardButton(text="📋 Выбрать для восстановления",
                                 callback_data=f"restore_select_{page}")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"archiv_{page}")
        ]
    ])

    await callback.message.edit_text(
        "Выберите действие для восстановления отключенных изменений:",
        reply_markup=keyboard
    )


async def _show_delete_permanent_options(callback: CallbackQuery, page: int):
    """Показывает опции удаления навсегда."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑️ Удалить все на странице",
                                 callback_data=f"delete_page_{page}"),
            InlineKeyboardButton(text="📋 Выбрать для удаления",
                                 callback_data=f"delete_select_{page}")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"archiv_{page}")
        ]
    ])

    await callback.message.edit_text(
        "⚠️ <b>Внимание: удаление навсегда нельзя отменить!</b>\n"
        "Выберите действие:",
        parse_mode='HTML',
        reply_markup=keyboard
    )


# Помощь по командам
@auto_chat_router.message(F.text.regexp(r'^[!/.]помощь изменения$'))
async def show_help(msg: Message):
    """Показывает справку по командам изменений."""
    help_text = """
🤖 <b>Автоматические изменения чата - Справка</b>

<b>📝 Планирование названия:</b>
• <code>+менять название ДД.ММ.ГГГГ ЧЧ:ММ тип</code> [новая строка] [текст названия]
• <code>+сегодня название ЧЧ:ММ тип</code> [новая строка] [текст названия]
• <code>+завтра название ЧЧ:ММ тип</code> [новая строка] [текст названия]

<b>📝 Планирование описания:</b>
• <code>+описание ДД.ММ.ГГГГ ЧЧ:ММ тип</code> [новая строка] [текст описания]
• <code>+сегодня описание ЧЧ:ММ тип</code> [новая строка] [текст описания]
• <code>+завтра описание ЧЧ:ММ тип</code> [новая строка] [текст описания]

<b>🖼️ Планирование аватарки:</b>
• <b>С фото в сообщении:</b> <code>+аватарка [описание?] ДД.ММ.ГГГГ ЧЧ:ММ тип</code> + прикрепить фото
• <b>С reply на фото:</b> Ответить на фото командой <code>+аватарка [описание?] ДД.ММ.ГГГГ ЧЧ:ММ тип</code>
• <b>Быстро сегодня:</b> <code>+сегодня аватарка ЧЧ:ММ тип [описание]</code> + фото
• <b>Быстро завтра:</b> <code>+завтра аватарка ЧЧ:ММ тип [описание]</code> + фото

<b>📊 Просмотр:</b>
• <code>!названия чата</code> - все названия
• <code>!аватарки чата</code> - все аватарки
• <code>!описания чата</code> - все описания
• <code>!изменения чата</code> - все изменения
• <code>!изменения на ДД.ММ.ГГГГ</code> - на дату
• <code>!статистика изменений</code> - статистика
• <code>!архив изменений</code> - отключенные изменения

<b>⚙️ Управление:</b>
• <code>!удалить название [ID]</code>
• <code>!удалить аватарку [ID]</code>
• <code>!удалить описание [ID]</code>
• <code>!отключить изменение [ID]</code>
• <code>!статус изменений</code> - статус сервиса
• <code>!проверить изменения</code> - принудительная проверка
• <code>!тест изменения [ID]</code> - принудительное применение

<b>🔄 Типы повторения:</b>
• <b>Русские:</b> одноразово, ежедневно, еженедельно, ежемесячно, ежегодно
• <b>English:</b> once, daily, weekly, monthly, yearly

<b>📅 Формат даты:</b> ДД.ММ.ГГГГ (например: 25.12.2024)
<b>⏰ Формат времени:</b> ЧЧ:ММ (например: 14:30)
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
            logger.info("Сервис автоматических изменений запущен")


@auto_chat_router.shutdown()
async def on_shutdown():
    """Останавливает сервис при выключении."""
    await shutdown_auto_chat_service()
    logger.info("Сервис автоматических изменений остановлен")