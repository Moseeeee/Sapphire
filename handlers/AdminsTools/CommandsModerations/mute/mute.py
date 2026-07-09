
import logging
import re
from typing import Union
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.types import *
from pytz import timezone

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_admin_for_rang
from handlers.AdminsTools.CommandsModerations.mute.muteDB import update_mute_info_type, update_mute_info, \
    remove_mute_info, set_default_mute_duration, get_default_mute_duration, get_mute_info, get_all_mutes, \
    get_total_mutes_count, get_mute_details, MUTES_PER_PAGE  # Импортируем MUTES_PER_PAGE
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import is_telegram_owner
from handlers.BotAutomaticWork.parse_time_auto import format_duration, parse_time_string
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)

mute = Router()


# Удалите это определение, так как MUTES_PER_PAGE импортируется из muteDB
# MUTES_PER_PAGE = 10


async def get_chat_permissions(chat_id: int) -> ChatPermissions:
    """Получает текущие права чата по умолчанию"""
    try:
        chat = await bot.get_chat(chat_id)
        return chat.permissions
    except Exception as e:
        print(f'get_chat_permissions error: {e}')
        # Возвращаем стандартные права, если не удалось получить
        return ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )


async def perform_mute(chat_id: int, user_id: int, duration: Union[timedelta, str], admin_id: int,
                       reason: str = "Не указана"):
    try:
        from pytz import timezone
        MOSCOW_TZ = timezone('Europe/Moscow')

        # Определяем тип мута и соответствующие параметры
        if duration == 'навсегда' or duration is None:
            # Вечный мут
            duration_text = "навсегда"
            until_date = None  # для вечного мута в Telegram API

            # Для вечного мута НЕ вызываем update_mute_info_type
            # Только сохраняем информацию в mutes таблице через update_mute_info
        else:
            # Временный мут
            duration_text = format_duration(duration)
            until_date = int((datetime.now(MOSCOW_TZ) + duration).timestamp())

            # Сохраняем время окончания только для временного мута
            time_end = (datetime.now(MOSCOW_TZ) + duration).isoformat()
            await update_mute_info_type(chat_id, user_id, time_end)

        # Обновляем основную информацию о муте
        await update_mute_info(chat_id, user_id, admin_id, reason, duration_text)

        # Мут в Telegram (ограничение прав отправки сообщений)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            ),
            until_date=until_date
        )

        return True, duration_text
    except Exception as e:
        logger.error(e, exc_info=True)
        return False, str(e)


async def perform_unmute(chat_id: int, user_id: int):
    try:
        await remove_mute_info(chat_id, user_id)

        # Получаем текущие права чата по умолчанию
        chat_permissions = await get_chat_permissions(chat_id)

        # Восстановление прав согласно настройкам чата
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=chat_permissions
        )
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def parse_time_improved(time_str: str):
    """
    Улучшенный парсер времени для русских обозначений
    """
    import re
    from datetime import timedelta

    if not time_str:
        return None

    time_str = time_str.lower().strip()
    logger.info(f"Парсинг улучшенный: '{time_str}'")

    # Специальные случаи
    if time_str in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
        return 'навсегда'

    # Пробуем стандартный парсинг
    parsed = parse_time_string(time_str)
    if parsed is not None:
        return parsed

    # Ручной парсинг русских обозначений
    patterns = [
        # Минуты: 5 минут, 5 мин, 5 м
        (r'(\d+)\s*(?:минут[ыуа]?|мин|м(?![её]))', 60, 'минут'),
        # Часы: 2 часа, 2 час, 2 ч, 2х (опечатка)
        (r'(\d+)\s*(?:час[ауов]?|ч|х\b)', 3600, 'часов'),
        # Дни: 3 дня, 3 дн, 3 д
        (r'(\d+)\s*(?:день|дня|дней|дн|д\b)', 86400, 'дней'),
        # Недели: 2 недели, 2 нед, 2 н
        (r'(\d+)\s*(?:недел[яиьюе]|нед|н\b)', 604800, 'недель'),
        # Месяцы: 1 месяц, 1 мес
        (r'(\d+)\s*(?:месяц[аев]?|мес)', 2592000, 'месяцев'),  # ~30 дней
        # Секунды: 30 секунд, 30 сек, 30 с
        (r'(\d+)\s*(?:секунд[ыу]?|сек|с\b)', 1, 'секунд'),
    ]

    total_seconds = 0

    for pattern, multiplier, unit_name in patterns:
        matches = re.findall(pattern, time_str)
        for match in matches:
            try:
                value = int(match)
                total_seconds += value * multiplier
                #logger.info(f"Найдено: {value} {unit_name} = {value * multiplier} секунд")
            except ValueError:
                continue

    # Также ищем числовые значения с последующими буквами (например, "4ч", "5м")
    # Это обрабатывается выше, но для надежности:

    # Если нашли хотя бы одно совпадение
    if total_seconds > 0:
        return timedelta(seconds=total_seconds)

    # Пробуем еще раз стандартный парсинг на очищенной строке
    # Убираем лишние слова и оставляем только числа и буквы времени
    cleaned = re.sub(r'[^\d\sчмндсекгуаяитль]', '', time_str)
    if cleaned != time_str:
        parsed = parse_time_string(cleaned)
        if parsed is not None:
            return parsed

    #logger.warning(f"Не удалось распарсить время: '{time_str}'")
    return None
update_mute_info_type
# ======================
# Хендлеры команд мутов
# ======================

@mute.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?муты период\s+\S+', re.IGNORECASE)))
async def set_default_mute_period(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 28):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "<b>Укажите длительность мута по умолчанию.</b>\n"
            "Пример: <code>муты период 3 дня</code>\n"
            "Или: <code>муты период навсегда</code>",
            parse_mode="HTML"
        )
        return

    duration_input = parts[2].strip()

    if duration_input.lower() in ["навсегда", "permanent", "forever"]:
        await set_default_mute_duration(m.chat.id, "permanent")
        await m.answer("✅ Время мута по умолчанию установлено: <b>навсегда</b>", parse_mode="HTML")
        return

    parsed_duration = parse_time_string(duration_input)
    if parsed_duration is None:
        await m.answer(
            "<b>Не удалось распознать время.</b>\nИспользуйте формат: <code>1 день 2 часа 30 минут</code>",
            parse_mode="HTML"
        )
        return

    await set_default_mute_duration(m.chat.id, duration_input)
    formatted = format_duration(parsed_duration)
    await m.answer(f"✅ Время мута по умолчанию установлено: <b>{formatted}</b>", parse_mode="HTML")


@mute.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?размут(\s|$)', re.IGNORECASE)))
async def unmute_users(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 25):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=1)

    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
    else:
        if len(parts) < 2 or not parts[1].strip():
            await m.answer(
                "<b>Неверный формат команды!</b>\nИспользуйте: размут {@username} или ответьте на сообщение",
                parse_mode='HTML'
            )
            return
        mention = parts[1].strip()
        UserId = await resolve_id(m, mention)

    # ========== ПРОВЕРКА РАНГОВ ДЛЯ РАЗМУТА ==========
    try:

        # Предполагаем, что boss_agent определен где-то в конфигурации
        boss_agent = []  # Замените на реальный список босс-агентов если есть

        ManagementAdminId = m.from_user.id
        ManagementRang = await check_admin_for_rang(ManagementAdminId, m.chat.id)

        # Получаем информацию о том, кто замутил пользователя
        mute_details = await get_mute_details(m.chat.id, UserId)
        if mute_details:
            admin_who_muted_id, reason, duration_text = mute_details
            AdminWhoMutedRang = await check_admin_for_rang(admin_who_muted_id, m.chat.id)

            # Если пользователя замутил администратор с более высоким рангом
            if AdminWhoMutedRang > 0 and AdminWhoMutedRang > ManagementRang:
                # Босс-агенты имеют полную власть
                if ManagementAdminId not in boss_agent:
                    # Проверяем, является ли управляющий Telegram-владельцем
                    is_tg_owner = await is_telegram_owner(bot, m.chat.id, ManagementAdminId)

                    if not is_tg_owner:
                        admin_who_muted_link = await user_link_global(admin_who_muted_id)
                        admin_link = await user_link_global(ManagementAdminId)

                        await m.answer(
                            f"{admin_link}, вы пытаетесь размутить пользователя, которого замутил администратор высшего ранга ({admin_who_muted_link})!\n",
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                        return
    except Exception as e:
        logger.error(e, exc_info=True)
        # В случае ошибки продолжаем выполнение
    # ========== КОНЕЦ ПРОВЕРКИ РАНГОВ ДЛЯ РАЗМУТА ==========

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)

    # Проверяем мут в базе данных
    mute_info = await get_mute_info(m.chat.id, UserId)

    # Проверяем фактический мут в Telegram
    try:
        chat_member = await m.bot.get_chat_member(m.chat.id, UserId)
        is_muted_in_tg = chat_member.status == ChatMemberStatus.RESTRICTED and not chat_member.can_send_messages
    except Exception:
        is_muted_in_tg = False

    # Если пользователь не замутен ни в БД, ни в ТГ
    if not mute_info and not is_muted_in_tg:
        await m.answer(
            f"ℹ️ Пользователь {user_link} уже размучен.",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return

    # Выполняем размут
    success = await perform_unmute(m.chat.id, UserId)

    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(m.from_user.id)

    if success:
        await m.answer(
            f"🔊 {user_link} размуч{g('ен', gender)}\n"
            f"👮‍♂️ Размьют{g('ил', gender_admin)}: {admin_link}",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        await m.answer("Ошибка при размуте")


@mute.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?мутлист(\s|$)', re.IGNORECASE)))
async def mute_list(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 26):
        return

    MOSCOW_TZ = timezone('Europe/Moscow')

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    # Добавляем диагностику
    #logger.info(f"=== КОМАНДА МУТЛИСТ ===")
    #logger.info(f"Чат ID: {m.chat.id}, Тип чата: {m.chat.type}")

    page = 0
    parts = text.split()
    if len(parts) > 1 and parts[1].isdigit():
        page = max(0, int(parts[1]) - 1)

    offset = page * MUTES_PER_PAGE
    #logger.info(f"Получаем мутлист: offset={offset}, MUTES_PER_PAGE={MUTES_PER_PAGE}")

    mutes_list = await get_all_mutes(m.chat.id, offset, MUTES_PER_PAGE)
    #logger.info(f"Получено записей из get_all_mutes: {len(mutes_list)}")

    total_mutes = await get_total_mutes_count(m.chat.id)
    #logger.info(f"Общее количество мутов (total_mutes): {total_mutes}")

    total_pages = (total_mutes + MUTES_PER_PAGE - 1) // MUTES_PER_PAGE if total_mutes > 0 else 1
    #logger.info(f"Всего страниц: {total_pages}")

    if not mutes_list:

        await m.answer("В этом чате нет замученных пользователей.")
        return

    response = f"📋 <b>Список мутов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, time_end) in enumerate(mutes_list, start=offset + 1):
        mute_details = await get_mute_details(m.chat.id, user_id)

        admin_link = "Неизвестен"
        reason = "Не указана"
        duration_text = "Неизвестно"

        if mute_details:
            admin_id, reason, duration_text = mute_details
            if admin_id:
                admin_link = await user_link_global(admin_id)

        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)
        gender_admin = await get_user_gender(admin_id) if admin_id else 0

        if duration_text.lower() == 'навсегда':
            duration_reply = f'замуч{g("ен", gender)} навсегда'
        else:
            if time_end:
                try:
                    time_end_dt = datetime.fromisoformat(time_end)
                    current_time = datetime.now(MOSCOW_TZ)

                    # Приводим к одному часовому поясу
                    if time_end_dt.tzinfo is None:
                        time_end_dt = MOSCOW_TZ.localize(time_end_dt)
                    elif str(time_end_dt.tzinfo) != str(MOSCOW_TZ):
                        time_end_dt = time_end_dt.astimezone(MOSCOW_TZ)

                    time_left = time_end_dt - current_time
                    actual_time_left = format_duration(time_left)
                    duration_reply = f'до размута {actual_time_left}'
                except Exception as e:
                    logger.error(f"Error parsing time: {e}")
                    duration_reply = 'ошибка времени'
            else:
                duration_reply = 'время не указано'

        response += (f"{i}. {user_link} ({duration_reply})\n"
                     f"👮🏻‍♂️ Замьют{g('ил', gender_admin)}: {admin_link}\n"
                     f"💬 Причина: {reason}\n\n")

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mutelist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mutelist_{page + 1}"))
        if row:
            keyboard.append(row)

    await m.reply(response,
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                   parse_mode='HTML',
                   disable_web_page_preview=True)


@mute.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?мут инфо(\s|$)', re.IGNORECASE)))
async def mute_info(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 27):
        return

    MOSCOW_TZ = timezone('Europe/Moscow')

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)

    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
    else:
        if len(parts) < 2:
            await m.answer(
                "<b>Неверный формат команды!</b>\nИспользуйте: мут инфо {@username} или ответьте на сообщение",
                parse_mode='HTML'
            )
            return
        mention = parts[2] if len(parts) > 2 else parts[1]
        UserId = await resolve_id(m, mention)

    if not UserId:
        await m.answer('Укажите пользователя.')
        return

    mute_info_db = await get_mute_info(m.chat.id, UserId)
    mute_details = await get_mute_details(m.chat.id, UserId)

    if not mute_details:
        await m.answer("ℹ️ Пользователь не замучен в этом чате.")
        return

    admin_id, reason, duration_text = mute_details
    user_link = await user_link_global(UserId)

    admin_link = "Неизвестен"
    if admin_id:
        admin_link = await user_link_global(admin_id)

    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(admin_id) if admin_id else 0

    if duration_text.lower() == 'навсегда':
        time_text = f'замуч{g("ен", gender)} навсегда'
        status = '⛔'
    else:
        # Для временных мутов проверяем время
        if not mute_info_db:
            time_text = "Время мута не указано"
            status = "⚠️"
        else:
            try:
                time_end = datetime.fromisoformat(mute_info_db)
                current_time = datetime.now(MOSCOW_TZ)

                # Приводим к одному часовому поясу
                if time_end.tzinfo is None:
                    time_end = MOSCOW_TZ.localize(time_end)
                elif str(time_end.tzinfo) != str(MOSCOW_TZ):
                    time_end = time_end.astimezone(MOSCOW_TZ)

                time_left = time_end - current_time

                if time_left.total_seconds() <= 0:
                    time_text = "Мут истек"
                    status = "🟢"
                else:
                    actual_time_left = format_duration(time_left)
                    time_text = f"Размут через: {actual_time_left}"
                    status = "🔴"
            except Exception as e:
                logger.error(f"Error parsing time: {e}")
                time_text = "Ошибка расчёта времени"
                status = "⚠️"

    response = (
        f"{status} <b>Информация о муте {user_link}</b>\n"
        f"⏰ {time_text}\n"
        f"👮‍♂️ Замьют{g('ил', gender_admin)}: {admin_link}\n"
        f"💬 Причина: {reason}"
    )

    await m.reply(response,
                   parse_mode='HTML',
                   disable_web_page_preview=True)



@mute.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?мут(\s|$)', re.IGNORECASE)))
async def mute_users(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 25):
        return

    # Удаляем префикс из команды (!мут, /мут, .мут -> мут)
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    # Разделяем команду и причину по новой строке
    command_part, _, reason_part = text.partition('\n')

    # Убираем начальные/конечные пробелы
    command_part = command_part.strip()
    reason = reason_part.strip() if reason_part.strip() else "Не указана"

    # Разбиваем команду на части
    parts = command_part.split()
    # logger.info(f"Части команды: {parts}")

    # Если это ответ на сообщение
    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
        # Ищем время в частях после команды (если есть)
        time_parts = []
        if len(parts) > 1:
            time_parts = parts[1:]
        time_str = ' '.join(time_parts) if time_parts else None
    else:
        # Если не ответ на сообщение - анализируем команду
        UserId = None
        time_str = None

        if len(parts) < 2:
            await m.reply('<b>Пользователь не указан!</b>\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/мут @username 1ч</code>\n'
                          '<code>причина с новой строки</code>',
                          parse_mode='HTML')
            return

        # Пробуем найти пользователя в разных позициях
        # Сначала смотрим первый элемент после команды
        potential_user = parts[1]
        resolved_id = await resolve_id(m, potential_user)
        if resolved_id:
            UserId = resolved_id
            # Время может быть дальше
            if len(parts) > 2:
                time_str = ' '.join(parts[2:])
        else:
            # Может быть сначала время, потом пользователь
            # Например: "мут 4 часа @user"
            # Пробуем найти пользователя дальше
            for i in range(2, len(parts)):
                potential_user = parts[i]
                resolved_id = await resolve_id(m, potential_user)
                if resolved_id:
                    UserId = resolved_id
                    # Время - это часть перед пользователем
                    time_str = ' '.join(parts[1:i])
                    break

        # Если не нашли пользователя
        if not UserId:
            # Пробуем последний элемент как пользователя
            potential_user = parts[-1]
            resolved_id = await resolve_id(m, potential_user)
            if resolved_id:
                UserId = resolved_id
                # Время - это всё перед последним элементом
                time_str = ' '.join(parts[1:-1])

        # Если все еще не нашли пользователя
        if not UserId:
            await m.reply('<b>Пользователь не указан или не найден!</b>\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/мут @username 1ч</code>\n'
                          '<code>причина с новой строки</code>',
                          parse_mode='HTML')
            return

    # Логируем найденные данные
    # logger.info(f"UserID: {UserId}, Time string: '{time_str}', Reason: '{reason}'")

    # Если причина указана с новой строки, обрезаем ее до 200 символов
    if reason != "Не указана":
        reason = reason[:200]
        msg_text = f'\n💬 Причина: {reason}'
    else:
        msg_text = ""

    # ========== ПРОВЕРКА РАНГОВ ДЛЯ МУТА ==========
    try:
        boss_agent = []  # Замените на реальный список босс-агентов если есть

        ManagementAdminId = m.from_user.id
        UserRang = await check_admin_for_rang(UserId, m.chat.id)
        ManagementRang = await check_admin_for_rang(ManagementAdminId, m.chat.id)

        # Если целевой пользователь является администратором
        if UserRang > 0:
            # Босс-агенты имеют полную власть
            if ManagementAdminId not in boss_agent:
                # Проверяем, является ли управляющий Telegram-владельцем
                is_tg_owner = await is_telegram_owner(bot, m.chat.id, ManagementAdminId)

                if not is_tg_owner:
                    if UserRang >= ManagementRang:
                        user_link = await user_link_global(UserId)
                        admin_link = await user_link_global(ManagementAdminId)

                        # Шутливые ответы в зависимости от ситуации
                        if UserRang == ManagementRang:
                            await m.answer(
                                f"{admin_link}, вы пытаетесь замутить администратора такого же ранга, как вы!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        else:
                            await m.answer(
                                f"{admin_link}, вы пытаетесь замутить администратора высшего ранга!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        return
    except Exception as e:
        logger.error(e, exc_info=True)
        # В случае ошибки продолжаем выполнение
    # ========== КОНЕЦ ПРОВЕРКИ РАНГОВ ДЛЯ МУТА ==========

    # ========== ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ ==========
    chat_id = m.chat.id

    # Проверка администраторов чата
    admins = await bot.get_chat_administrators(chat_id)

    if UserId in [admin.user.id for admin in admins if admin.status == 'creator']:
        await m.reply('❎ Владельца чата нельзя замутить.')
        return

    if UserId in [admin.user.id for admin in admins]:
        await m.reply('❎ Нельзя замутить администратора!')
        return

    if UserId == m.from_user.id:
        await m.reply('❎ Вы пытались замутить себя.')
        await m.answer_sticker(
            sticker='CAACAgIAAxkBAAEPgyNo4WXlQeKd729gw8WbZ_AFUJjSsQACCwEAAladvQpOseemCPvtSTYE')
        return

    if UserId == chat_id:
        await m.reply('❎ Нельзя замутить чат.')
        return

    # Проверка привязанного канала
    chat_info = await bot.get_chat(chat_id)
    linked_chat_id = chat_info.linked_chat_id

    if (
            m.reply_to_message and
            m.reply_to_message.sender_chat and
            m.reply_to_message.sender_chat.id == linked_chat_id
    ):
        await m.reply('❎ Нельзя замутить привязанный канал!')
        return
    # ========== КОНЕЦ ДОПОЛНИТЕЛЬНЫХ ПРОВЕРОК ==========

    # Определяем длительность мута
    mute_duration = None
    if time_str:
        # logger.info(f"Парсим время: '{time_str}'")

        # Проверяем специальные случаи "навсегда"
        if time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
            mute_duration = 'навсегда'
            # logger.info("Установлен вечный мут")
        else:
            # Пробуем распарсить время
            mute_duration = parse_time_string(time_str)

            if mute_duration is None:
                # Пробуем улучшенный парсинг
                # logger.info("Стандартный парсинг не удался, пробуем улучшенный")
                mute_duration = await parse_time_improved(time_str)

    # Если время не указано или не распознано, используем настройки по умолчанию
    if mute_duration is None:
        default_duration_str = await get_default_mute_duration(m.chat.id)
        # logger.info(f"Используем настройку по умолчанию: {default_duration_str}")

        if default_duration_str is None:
            mute_duration = 'навсегда'
        elif default_duration_str == "permanent":
            mute_duration = 'навсегда'
        else:
            mute_duration = parse_time_string(default_duration_str)
            if mute_duration is None:
                mute_duration = 'навсегда'

    # Если все еще не определили длительность
    if mute_duration is None:
        # logger.error(f"Не удалось определить длительность для: '{time_str}'")
        await m.answer(f"Не удалось распознать время: {time_str}")
        return

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)

    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(m.from_user.id)

    success, result = await perform_mute(
        chat_id=m.chat.id,
        user_id=UserId,
        duration=mute_duration,
        admin_id=m.from_user.id,
        reason=reason
    )

    if success:
        if mute_duration == 'навсегда' or mute_duration is None:
            duration_text = "навсегда"
            duration_display = "навсегда"
        else:
            duration_text = result
            duration_display = f'на {duration_text}'

        response = f"🔇 {user_link} замуч{g('ен', gender)} {duration_display}\n"
        response += f"👮‍♂️ Замьют{g('ил', gender_admin)}: {admin_link}"

        if msg_text:
            response += msg_text

        await m.answer(
            response,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        await m.answer(f"Ошибка при муте: {result}")


@mute.callback_query(lambda c: c.data.startswith('mutelist_'))
@rate_limit_with_cleanup(limit=1)
async def mute_list_pagination(c: CallbackQuery):
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return

    page = int(c.data.split('_')[1])
    chat_id = c.message.chat.id

    offset = page * MUTES_PER_PAGE
    mutes_list = await get_all_mutes(chat_id, offset, MUTES_PER_PAGE)
    total_mutes = await get_total_mutes_count(chat_id)
    total_pages = (total_mutes + MUTES_PER_PAGE - 1) // MUTES_PER_PAGE

    response = f"📋 <b>Список мутов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, time_end) in enumerate(mutes_list, start=offset + 1):
        user_link = await user_link_global(user_id)

        mute_details = await get_mute_details(chat_id, user_id)

        admin_link = "Неизвестен"
        reason = "Не указана"
        duration_text = "Неизвестно"

        if mute_details:
            admin_id, reason, duration_text = mute_details
            admin_link = await user_link_global(admin_id)

        # Логирование актуального времени до размута
        time_end_dt = datetime.fromisoformat(time_end)
        time_left = time_end_dt - datetime.now()
        actual_time_left = format_duration(time_left)

        gender_admin = await get_user_gender(admin_id)

        response += (f"{i}. {user_link} (до размута {actual_time_left})\n"
                     f"👮🏻‍♂️ Замьют{g('ил', gender_admin)}: {admin_link}\n"
                     f"💬 Причина: {reason}\n\n")

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mutelist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mutelist_{page + 1}"))
        if row:
            keyboard.append(row)

    await c.message.edit_text(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='HTML')
    await c.answer()





#@mute.message(lambda m: m.text and m.text.lower() == "тестмуты")
async def test_mutes_command(m: Message):
    """Тестовая команда для проверки мутов"""
    try:
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

        logger.info(f"=== ТЕСТ МУТОВ ДЛЯ ЧАТА {m.chat.id} ===")

        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Проверим структуру таблицы punishment_time
            columns = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'punishment_time'
                ORDER BY ordinal_position
            """)

            column_info = "Структура punishment_time:\n"
            for col in columns:
                column_info += f"{col['column_name']}: {col['data_type']}\n"

            # Проверим существующие записи
            records = await conn.fetch("""
                SELECT chat_id, user_id, types, time_end 
                FROM punishment_time 
                WHERE chat_id = $1
                ORDER BY time_end DESC
                LIMIT 10
            """, m.chat.id)

            records_info = f"\nНайдено записей для чата {m.chat.id}: {len(records)}\n"

            for i, record in enumerate(records):
                records_info += f"\n{i + 1}. user_id={record['user_id']}, types={record['types']}, time_end={record['time_end']}"

            # Проверим через функции
            all_mutes = await get_all_mutes(m.chat.id, 0, 10)
            total_mutes = await get_total_mutes_count(m.chat.id)

            functions_info = f"\n\nРезультаты функций:\n"
            functions_info += f"get_all_mutes: {len(all_mutes)} записей\n"
            functions_info += f"get_total_mutes_count: {total_mutes}"

            response = column_info + records_info + functions_info

            # Отправляем ответ частями, если слишком длинный
            if len(response) > 4000:
                await m.answer(response[:4000])
                if len(response) > 4000:
                    await m.answer(response[4000:8000] if len(response) > 8000 else response[4000:])
            else:
                await m.answer(response)

    except Exception as e:
        logger.error(f"Ошибка в тестовой команде: {e}")
        await m.answer(f"Ошибка: {str(e)}")