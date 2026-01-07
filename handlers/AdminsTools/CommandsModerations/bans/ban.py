import re
from typing import Union

from aiogram import Router, F
from aiogram.types import *
from pytz import timezone

from handlers.AgentsFeatures.payment.payment import check_user_access
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from datetime import datetime, timedelta
import logging
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_admin_for_rang
from handlers.AdminsTools.CommandsModerations.bans.banDB import (update_ban_info_type,
                                                                 update_ban_info,
                                                                 remove_ban_info,
                                                                 set_default_ban_duration,
                                                                 get_default_ban_duration,
                                                                 get_ban_info,
                                                                 get_all_bans,
                                                                 get_total_bans_count,
                                                                 get_ban_details, get_user_bans_all_chats,
                                                                 get_user_active_bans_count)
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import is_telegram_owner
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.parse_time_auto import format_duration, parse_time_string
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.universal_bot import bot

bans = Router()

# Константы для пагинации
BANS_PER_PAGE = 10
MOSCOW_TZ = timezone('Europe/Moscow')

logger = logging.getLogger(__name__)


async def perform_ban(chat_id: int, user_id: int, duration: Union[timedelta, str], admin_id: int,
                      reason: str = "Не указана"):
    try:
        from pytz import timezone
        MOSCOW_TZ = timezone('Europe/Moscow')

        # Определяем тип бана и соответствующие параметры
        if duration == 'навсегда' or duration is None:
            # Вечный бан
            duration_text = "навсегда"
            until_date = None  # для вечного бана в Telegram API

            # Для вечного бана НЕ вызываем update_ban_info_type
            # Только сохраняем информацию в bans таблице через update_ban_info
        else:
            # Временный бан
            duration_text = format_duration(duration)
            until_date = int((datetime.now(MOSCOW_TZ) + duration).timestamp())

            # Сохраняем время окончания только для временного бана
            time_end = (datetime.now(MOSCOW_TZ) + duration).isoformat()
            await update_ban_info_type(chat_id, user_id, time_end)

        # Обновляем основную информацию о бане
        await update_ban_info(chat_id, user_id, admin_id, reason, duration_text)

        # Выполняем бан в чате
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until_date)

        return True, duration_text
    except Exception as e:
        logger.error(e, exc_info=True)
        return False, str(e)


async def perform_unban(chat_id: int, user_id: int):
    try:
        await remove_ban_info(chat_id, user_id)
        await bot.unban_chat_member(chat_id=chat_id,
                                    user_id=user_id,
                                    only_if_banned=True)
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False




async def parse_time_improved_ban(time_str: str):
    """
    Улучшенный парсер времени для русских обозначений (для банов)
    """
    import re
    from datetime import timedelta

    if not time_str:
        return None

    time_str = time_str.lower().strip()
    logger.info(f"Парсинг улучшенный (бан): '{time_str}'")

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
                logger.info(f"Найдено: {value} {unit_name} = {value * multiplier} секунд")
            except ValueError:
                continue

    # Если нашли хотя бы одно совпадение
    if total_seconds > 0:
        return timedelta(seconds=total_seconds)

    # Пробуем еще раз стандартный парсинг на очищенной строке
    cleaned = re.sub(r'[^\d\sчмнднсекгуаяитль]', '', time_str)
    if cleaned != time_str:
        parsed = parse_time_string(cleaned)
        if parsed is not None:
            return parsed

    logger.warning(f"Не удалось распарсить время (бан): '{time_str}'")
    return None

# ======================
# Хендлеры команд
# ======================

@bans.message(F.text.regexp(re.compile(r'^[!/.]баны период(\s|$)', re.IGNORECASE)))
async def set_default_ban_period(m: Message):

    chat_id = m.chat.id
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, chat_id, 24):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "❌ Укажите длительность бана по умолчанию.\n"
            "Пример: <code>баны период 3 дня</code>\n"
            "Или: <code>баны период навсегда</code>",
            parse_mode="HTML"
        )
        return

    duration_input = parts[2].strip()

    if duration_input.lower() in ["навсегда", "permanent", "forever"]:
        await set_default_ban_duration(m.chat.id, "permanent")
        await m.answer("✅ Время бана по умолчанию установлено: <b>навсегда</b>", parse_mode="HTML")
        return

    parsed_duration = parse_time_string(duration_input)
    if parsed_duration is None:
        await m.answer(
            "❌ Не удалось распознать время. Используйте формат: <code>1 день 2 часа 30 минут</code>",
            parse_mode="HTML"
        )
        return

    await set_default_ban_duration(m.chat.id, duration_input)
    formatted = format_duration(parsed_duration)
    await m.answer(f"✅ Время бана по умолчанию установлено: <b>{formatted}</b>", parse_mode="HTML")


@bans.message(F.text.regexp(re.compile(r'^[!/.](?:чс|бан)(\s|$)', re.IGNORECASE)))
async def ban_users(m: Message):
    chat_id = m.chat.id

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, chat_id, 21):
        return

    # Удаляем префикс из команды
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

    UserId = None
    time_str = None

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
        if len(parts) < 2:
            await m.reply('⚠️ Пользователь не указан!\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/бан @username 1ч</code>\n'
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
            # Первый элемент не пользователь - может быть сначала время, потом пользователь
            # Например: "бан 4 часа @user"
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
            await m.reply('⚠️ Пользователь не указан или не найден!\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/бан @username 1ч</code>\n'
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

    # ========== ПРОВЕРКА РАНГОВ ==========
    try:
        ManagementAdminId = m.from_user.id
        UserRang = await check_admin_for_rang(UserId, chat_id)
        ManagementRang = await check_admin_for_rang(ManagementAdminId, chat_id)

        # Если целевой пользователь является администратором
        if UserRang > 0:
            # Босс-агенты имеют полную власть
            if ManagementAdminId not in boss_agent:
                # Проверяем, является ли управляющий Telegram-владельцем
                is_tg_owner = await is_telegram_owner(bot, chat_id, ManagementAdminId)

                if not is_tg_owner:
                    if UserRang >= ManagementRang:
                        user_link = await user_link_global(UserId)
                        admin_link = await user_link_global(ManagementAdminId)

                        # Шутливые ответы в зависимости от ситуации
                        if UserRang == ManagementRang:
                            await m.answer(
                                f"😂 {admin_link}, вы пытаетесь заблокировать администратора такого же ранга, как вы!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        else:
                            await m.answer(
                                f"😏 {admin_link}, вы пытаетесь заблокировать администратора высшего ранга!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        return
    except Exception as e:
        logger.error(e, exc_info=True)
        # В случае ошибки продолжаем выполнение
    # ========== КОНЕЦ ПРОВЕРКИ РАНГОВ ==========

    # Остальная логика проверок (админы, владелец и т.д.)
    admins = await bot.get_chat_administrators(chat_id)

    if not UserId:
        await m.reply('⚠️ Пользователь не указан или указан не верно.\nПравильный вид команды: бан @')
        return

    if UserId in [admin.user.id for admin in admins if admin.status == 'creator']:
        await m.reply('❎ Владельца чата нельзя заблокировать.')
        return

    if UserId in [admin.user.id for admin in admins]:
        await m.reply('❎ Этот администратор не может быть заблокирован.')
        return

    if UserId == m.from_user.id:
        await m.reply('❎ Вы пытались заблокировать себя.')
        await m.answer_sticker(
            sticker='CAACAgIAAxkBAAEPgyNo4WXlQeKd729gw8WbZ_AFUJjSsQACCwEAAladvQpOseemCPvtSTYE')
        return

    if UserId == chat_id:
        await m.reply('❎ Нельзя заблокировать чат.')
        return

    chat_info = await bot.get_chat(chat_id)
    linked_chat_id = chat_info.linked_chat_id

    if (
            m.reply_to_message and m.reply_to_message.sender_chat
            and m.reply_to_message.sender_chat.id == linked_chat_id
    ):
        await m.reply('❎ Нельзя забанить привязанный канал!')
        return

    # Определяем длительность бана
    ban_duration = None
    if time_str:
        logger.info(f"Парсим время: '{time_str}'")

        # Проверяем специальные случаи "навсегда"
        if isinstance(time_str, str) and time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
            ban_duration = 'навсегда'
            logger.info("Установлен вечный бан")
        else:
            # Пробуем распарсить время
            ban_duration = parse_time_string(time_str)

            if ban_duration is None:
                # Пробуем улучшенный парсинг (как в мутах)
                logger.info("Стандартный парсинг не удался, пробуем улучшенный")
                ban_duration = await parse_time_improved_ban(time_str)

    # Если время не указано или не распознано, используем настройки по умолчанию
    if ban_duration is None:
        default_duration_str = await get_default_ban_duration(m.chat.id)
        logger.info(f"Используем настройку по умолчанию: {default_duration_str}")

        if default_duration_str is None:
            ban_duration = 'навсегда'
        elif default_duration_str == "permanent":
            ban_duration = 'навсегда'
        else:
            # ФИКС: Проверяем тип данных
            from datetime import timedelta
            if isinstance(default_duration_str, timedelta):
                # Преобразуем timedelta в строку
                total_seconds = default_duration_str.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)

                if hours > 0:
                    if minutes > 0:
                        default_duration_str = f"{hours}ч {minutes}м"
                    else:
                        default_duration_str = f"{hours}ч"
                elif minutes > 0:
                    default_duration_str = f"{minutes}м"
                else:
                    default_duration_str = f"{int(total_seconds)}с"

            ban_duration = parse_time_string(default_duration_str)
            if ban_duration is None:
                ban_duration = 'навсегда'

    # Если все еще не определили длительность
    if ban_duration is None:
        logger.error(f"Не удалось определить длительность для: '{time_str}'")
        await m.answer(f"❌ Не удалось распознать время: {time_str}")
        return

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)

    success, result = await perform_ban(
        chat_id=chat_id,
        user_id=UserId,
        duration=ban_duration,
        admin_id=m.from_user.id,
        reason=reason
    )

    if success:
        if ban_duration == 'навсегда' or ban_duration is None:
            duration_text = "навсегда"
            duration_display = "навсегда"
        else:
            duration_text = result
            duration_display = f'на {duration_text}'

        gender = await get_user_gender(UserId)
        gender_admin = await get_user_gender(m.from_user.id)

        response = f"✅ {user_link} забан{g('ен', gender)} {duration_display}\n"
        response += f"👮‍♂️ Забан{g('ил', gender_admin)}: {admin_link}"

        if msg_text:
            response += msg_text

        await m.answer(
            response,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        await m.answer(f"❌ Ошибка при бане: {result}",
                       parse_mode='HTML',
                       disable_web_page_preview=True
                       )


@bans.message(F.text.regexp(re.compile(r'^[!/.]разбан(\s|$)', re.IGNORECASE)))
async def unban_users(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 21):
        return
    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=1)

    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
    else:
        if len(parts) < 2:
            await m.answer(
                "❌ <b>Неверный формат команды!</b>\nИспользуйте: разбан {@username} или ответьте на сообщение",
                parse_mode='HTML'
            )
            return
        mention = parts[1]
        UserId = await resolve_id(m, mention)

    if not UserId:
        await m.answer("❌ Пользователь не найден.")
        return

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)
    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(m.from_user.id)

    # ========== ПРОВЕРКА РАНГОВ ДЛЯ РАЗБАНА ==========
    try:
        ManagementAdminId = m.from_user.id

        # Получаем информацию о том, кто забанил пользователя
        ban_details = await get_ban_details(m.chat.id, UserId)
        if ban_details:
            admin_who_banned_id, reason, duration_text = ban_details

            if admin_who_banned_id:
                # Получаем ранги обоих администраторов
                ManagementRang = await check_admin_for_rang(ManagementAdminId, m.chat.id)
                AdminWhoBannedRang = await check_admin_for_rang(admin_who_banned_id, m.chat.id)

                # Если пользователя забанил администратор с более высоким рангом
                if AdminWhoBannedRang > 0 and AdminWhoBannedRang > ManagementRang:
                    # Босс-агенты имеют полную власть
                    if ManagementAdminId not in boss_agent:
                        # Проверяем, является ли управляющий Telegram-владельцем
                        is_tg_owner = await is_telegram_owner(bot, m.chat.id, ManagementAdminId)

                        if not is_tg_owner:
                            admin_who_banned_link = await user_link_global(admin_who_banned_id)
                            admin_link = await user_link_global(ManagementAdminId)

                            await m.answer(
                                f"😏 {admin_link}, вы пытаетесь разблокировать пользователя, которого забанил администратор высшего ранга ({admin_who_banned_link})!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                            return
    except Exception as e:
        logger.error(e, exc_info=True)
        # В случае ошибки продолжаем выполнение
    # ========== КОНЕЦ ПРОВЕРКИ РАНГОВ ДЛЯ РАЗБАНА ==========

    # Проверяем, есть ли бан в БД
    ban_in_db = await get_ban_info(m.chat.id, UserId)

    try:
        # Проверяем реальный статус пользователя в Telegram
        chat_member = await bot.get_chat_member(m.chat.id, UserId)

        # Если пользователь не забанен в Telegram
        if chat_member.status != 'kicked':
            # Удаляем запись из БД если есть
            if ban_in_db:
                await remove_ban_info(m.chat.id, UserId)
                await m.answer(
                    f"✅ {user_link} не заблокирован, но я выполнил удаление из бд.\n"
                    f"👮‍♂️ Удал{g('ил', gender)}: {admin_link}",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await m.answer(
                    f"✅ {user_link} не забан{g('ен', gender)}.",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            return

    except Exception as e:
        logger.error(e, exc_info=True)

        if "user not found" in str(e).lower() or "user not participant" in str(e).lower():
            # Пользователь не найден или не участник чата
            # Удаляем запись из БД если есть
            if ban_in_db:
                await remove_ban_info(m.chat.id, UserId)
                await m.answer(
                    f"ℹ️ Пользователь {user_link} не найден в чате.\n"
                    f"👮‍♂️ Удал{g('ил', gender)}: {admin_link}",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await m.answer(
                    f"ℹ️ Пользователь {user_link} не найден в чате.",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            return
        else:
            # Другая ошибка
            logger.error(e, exc_info=True)
            await m.answer("❌ Ошибка при проверке статуса пользователя")
            return

    # Если пользователь забанен в Telegram, выполняем разбан
    success = await perform_unban(m.chat.id, UserId)

    if success:
        # Дополнительная проверка: если в БД не было записи, но в Telegram бан есть
        if not ban_in_db:
            await m.answer(
                f"✅ {user_link} разбан{g('ен', gender)}.\n"
                f"👮‍♂️ Разбан{g('ил', gender)}: {admin_link}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await m.answer(
                f"✅ {user_link} разбан{g('ен', gender)}\n"
                f"👮‍♂️ Разбан{g('ил', gender)}: {admin_link}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
    else:
        # Если не удалось разбанить в Telegram, но запись в БД есть - удаляем ее
        if ban_in_db:
            await remove_ban_info(m.chat.id, UserId)
            await m.answer(
                f"⚠️ Не удалось разбанить {user_link}.\n"
                f"👮‍♂️ Попытал{g('лся', gender)} разбанить: {admin_link}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await m.answer("❌ Ошибка при разбане")


@bans.message(F.text.regexp(re.compile(r'^[!/.]банлист(\s|$)', re.IGNORECASE)))
async def ban_list(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 22):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    page = 0
    parts = text.split()
    if len(parts) > 1 and parts[1].isdigit():
        page = max(0, int(parts[1]) - 1)

    offset = page * BANS_PER_PAGE
    bans_list = await get_all_bans(m.chat.id, offset, BANS_PER_PAGE)
    total_bans = await get_total_bans_count(m.chat.id)
    total_pages = (total_bans + BANS_PER_PAGE - 1) // BANS_PER_PAGE

    if not bans_list:
        await m.answer("📝 В этом чате нет забаненных пользователей.")
        return

    response = f"📋 <b>Список банов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, time_end) in enumerate(bans_list, start=offset + 1):
        ban_details = await get_ban_details(m.chat.id, user_id)

        admin_link = "Неизвестен"
        reason = "Не указана"
        duration_text = "Неизвестно"

        if ban_details:
            admin_id, reason, duration_text = ban_details
            if admin_id:
                admin_link = await user_link_global(admin_id)

        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if duration_text.lower() == 'навсегда':
            duration_reply = f'забан{g("ен", gender)} навсегда'
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
                    duration_reply = f'до разбана {actual_time_left}'
                except Exception as e:
                    logger.error(f"Error parsing time: {e}")
                    duration_reply = 'ошибка времени'
            else:
                duration_reply = 'время не указано'

        response += (f"{i}. {user_link} ({duration_reply})\n"
                     f"👮🏻‍♂️ Модератор: {admin_link}\n"
                     f"💬 Причина: {reason}\n\n")

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"banlist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"banlist_{page + 1}"))
        if row:
            keyboard.append(row)

    await m.reply(response,
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                   parse_mode='HTML',
                   disable_web_page_preview=True)


@bans.message(F.text.regexp(re.compile(r'^[!/.]бан инфо(\s|$)', re.IGNORECASE)))
async def ban_info(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 23):
        return

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
                "❌ <b>Неверный формат команды!</b>\nИспользуйте: бан инфо {@username} или ответьте на сообщение",
                parse_mode='HTML'
            )
            return
        mention = parts[2] if len(parts) > 2 else parts[1]
        UserId = await resolve_id(m, mention)

    if not UserId:
        await m.answer('Укажите пользователя.')
        return

    ban_info_db = await get_ban_info(m.chat.id, UserId)
    ban_details = await get_ban_details(m.chat.id, UserId)

    if not ban_details:
        await m.answer("ℹ️ Пользователь не забанен в этом чате.")
        return

    admin_id, reason, duration_text = ban_details
    user_link = await user_link_global(UserId)

    admin_link = "Неизвестен"
    if admin_id:
        admin_link = await user_link_global(admin_id)

    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(admin_id) if admin_id else 0

    if duration_text.lower() == 'навсегда':
        time_text = f'забан{g("ен", gender)} навсегда'
        status = '⛔'
    else:
        # Для временных банов проверяем время
        if not ban_info_db:
            time_text = "Время бана не указано"
            status = "⚠️"
        else:
            try:
                time_end = datetime.fromisoformat(ban_info_db)
                current_time = datetime.now(MOSCOW_TZ)

                # Приводим к одному часовому поясу
                if time_end.tzinfo is None:
                    time_end = MOSCOW_TZ.localize(time_end)
                elif str(time_end.tzinfo) != str(MOSCOW_TZ):
                    time_end = time_end.astimezone(MOSCOW_TZ)

                time_left = time_end - current_time

                if time_left.total_seconds() <= 0:
                    time_text = "⏰ Бан истек"
                    status = "🟢"
                else:
                    actual_time_left = format_duration(time_left)
                    time_text = f"Разбан через: {actual_time_left}"
                    status = "🔴"
            except Exception as e:
                logger.error(f"Error parsing time: {e}")
                time_text = "⚠️ Ошибка времени"
                status = "⚠️"

    response = (
        f"{status} <b>Информация о бане {user_link}</b>\n"
        f"⏰ {time_text}\n"
        f"👮‍♂️ Забан{g('ил', gender_admin)}: {admin_link}\n"
        f"💬 Причина: {reason}"
    )

    await m.answer(response,
                   parse_mode='HTML',
                   disable_web_page_preview=True)


# ======================
# Новые команды для просмотра банов пользователя во всех чатах
# ======================

@bans.message(F.text.regexp(re.compile(r'^[!/.]мои баны(\s|$)', re.IGNORECASE)))
async def my_bans(m: Message):

    if m.chat.type != 'private':
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    user_id = m.from_user.id
    user_link = await user_link_global(user_id)
    gender = await get_user_gender(user_id)

    # Определяем страницу
    page = 0
    parts = text.split()
    if len(parts) > 2 and parts[2].isdigit():
        page = max(0, int(parts[2]) - 1)

    # Получаем все баны пользователя (ТОЛЬКО где был в чате через full_users_chats)
    bans_list = await get_user_bans_all_chats(user_id, check_membership=True)

    if not bans_list:
        await m.answer(
            f"✅ {user_link}, у вас нет активных банов ни в одном чате где вы были!",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return

    # Пагинация
    total_pages = (len(bans_list) + BANS_PER_PAGE - 1) // BANS_PER_PAGE
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * BANS_PER_PAGE
    end_idx = min(start_idx + BANS_PER_PAGE, len(bans_list))

    response = f"📋 <b>Ваши баны во всех чатах</b>\n"
    response += f"📊 Всего банов: {len(bans_list)}\n"

    current_time = datetime.now(MOSCOW_TZ)

    for i, ban_info in enumerate(bans_list[start_idx:end_idx], start_idx + 1):
        chat_id = ban_info['chat_id']

        time_end_dt = ban_info['time_end_dt']
        duration_text = ban_info['duration']
        reason = ban_info['reason'][:50] + "..." if len(ban_info['reason']) > 50 else ban_info['reason']

        # Рассчитываем оставшееся время
        if duration_text.lower() == 'навсегда':
            status = "⛔ Навсегда"
            time_text = ""
        else:
            try:
                if time_end_dt:
                    # Убедимся, что time_end_dt в московском часовом поясе
                    if time_end_dt.tzinfo is None:
                        time_end_dt = MOSCOW_TZ.localize(time_end_dt)
                    elif str(time_end_dt.tzinfo) != str(MOSCOW_TZ):
                        time_end_dt = time_end_dt.astimezone(MOSCOW_TZ)

                    time_left = time_end_dt - current_time

                    if time_left.total_seconds() <= 0:
                        status = "🟢 Истек"
                        time_text = ""
                    else:
                        actual_time_left = format_duration(time_left)
                        status = "🔴 Активен"
                        time_text = f"{actual_time_left}"
                else:
                    status = "⚠️ Неизвестно"
                    time_text = ""
            except Exception as e:
                logger.error(f"Error calculating time left: {e}")
                status = "⚠️ Ошибка"
                time_text = ""
        chat_link = await chat_global_link(chat_id)

        response += (
            f"{i}. «{chat_link}» {status}\n"
            f"   📝 Срок: {duration_text} ({time_text})"
            f"   💬 Причина: {reason}\n"
            f"   ──────────────────────────\n"
        )

    # Создаем клавиатуру для пагинации
    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mybans_{user_id}_{page - 1}"))

        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mybans_{user_id}_{page + 1}"))

        if row:
            keyboard.append(row)

    await m.reply(
        response,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    )


@bans.message(F.text.regexp(re.compile(r'^[!/.]баны\s+\S+', re.IGNORECASE)))
async def user_bans_all_chats(m: Message):

    if not await check_user_access(m.from_user.id, 1):
        return

    """Показать все баны указанного пользователя во всех чатах (полный список)"""
    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    MOSCOW_TZ = timezone('Europe/Moscow')

    parts = text.split(maxsplit=2)

    # Определяем страницу
    page = 0
    user_mention = parts[1] if len(parts) > 1 else ""

    # Проверяем, есть ли номер страницы
    if len(parts) > 2 and parts[2].isdigit():
        page = max(0, int(parts[2]) - 1)
    elif len(parts) == 2:
        # Только команда и упоминание
        user_mention = parts[1]

    # Разрешаем ID пользователя
    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
    else:
        UserId = await resolve_id(m, user_mention)

    if not UserId:
        await m.answer("❌ Пользователь не найден.")
        return


    user_link = await user_link_global(UserId)
    requester_link = await user_link_global(m.from_user.id)
    gender = await get_user_gender(UserId)

    # Получаем ВСЕ баны пользователя (без проверки на участие в чате)
    bans_list = await get_user_bans_all_chats(UserId, check_membership=False)
    active_bans_count = await get_user_active_bans_count(UserId, check_membership=False)

    if not bans_list:
        await m.answer(
            f"✅ {user_link} не имеет активных банов ни в одном чате!\n"
            f"👮‍♂️ Запросил: {requester_link}",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return

    # Фильтруем: показываем сначала баны где был в чате, потом где не был
    bans_in_chat = []
    bans_not_in_chat = []

    for ban in bans_list:
        if ban.get('was_in_chat', True):
            bans_in_chat.append(ban)
        else:
            bans_not_in_chat.append(ban)

    # Объединяем: сначала те, где был в чате
    sorted_bans_list = bans_in_chat + bans_not_in_chat

    # Пагинация
    total_pages = (len(sorted_bans_list) + BANS_PER_PAGE - 1) // BANS_PER_PAGE
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * BANS_PER_PAGE
    end_idx = min(start_idx + BANS_PER_PAGE, len(sorted_bans_list))

    response = f"📋 <b>Все баны пользователя {user_link}</b>\n"
    response += f"📊 Всего банов: {len(sorted_bans_list)} ({len(bans_in_chat)} в чатах где был, {len(bans_not_in_chat)} где не был)\n"

    current_time = datetime.now(MOSCOW_TZ)

    for i, ban_info in enumerate(sorted_bans_list[start_idx:end_idx], start_idx + 1):
        chat_id = ban_info['chat_id']

        time_end_dt = ban_info['time_end_dt']
        duration_text = ban_info['duration']
        reason = ban_info['reason'][:50] + "..." if len(ban_info['reason']) > 50 else ban_info['reason']
        was_in_chat = ban_info.get('was_in_chat', True)

        # Получаем информацию о том, кто забанил
        admin_id = ban_info['admin_id']
        if admin_id:
            try:
                admin_link = await user_link_global(admin_id)
            except:
                admin_link = f"ID: {admin_id}"
        else:
            admin_link = "Неизвестен"

        # Рассчитываем оставшееся время
        if duration_text.lower() == 'навсегда':
            status = "⛔ Навсегда"
            time_text = ""
        else:
            try:
                if time_end_dt:
                    # Убедимся, что time_end_dt в московском часовом поясе
                    if time_end_dt.tzinfo is None:
                        time_end_dt = MOSCOW_TZ.localize(time_end_dt)
                    elif str(time_end_dt.tzinfo) != str(MOSCOW_TZ):
                        time_end_dt = time_end_dt.astimezone(MOSCOW_TZ)

                    time_left = time_end_dt - current_time

                    if time_left.total_seconds() <= 0:
                        status = "🟢 Истек"
                        time_text = ""
                    else:
                        actual_time_left = format_duration(time_left)
                        status = "🔴 Активен"
                        time_text = f"⏳ Осталось: {actual_time_left}"
                else:
                    status = "⚠️ Неизвестно"
                    time_text = ""
            except Exception as e:
                logger.error(f"Error calculating time left: {e}")
                status = "⚠️ Ошибка"
                time_text = ""

        # Иконка статуса участия в чате
        if was_in_chat:
            chat_status = "👤"
            # chat_status_text = "Был в чате"
        else:
            chat_status = "❌ ✖️"
            # chat_status_text = "Не был в чате"

        chat_link = await chat_global_link(chat_id)

        response += (
            f"{i}. ({chat_status}) «{chat_link}» \n"
            f"   📝 Срок: {duration_text} ({time_text})\n"
            f"   👮‍♂️ Забанил: {admin_link}\n"
            f"   💬 Причина: {reason}\n"
            f"   ─────────────\n"
        )

    # Создаем клавиатуру для пагинации
    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"userbans_{UserId}_{page - 1}"))

        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"userbans_{UserId}_{page + 1}"))

        if row:
            keyboard.append(row)

    await m.reply(
        response,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    )


# ======================
# Обработчики пагинации для новых команд
# ======================

@bans.callback_query(lambda c: c.data.startswith('mybans_'))
@rate_limit_with_cleanup(limit=1)
async def my_bans_pagination(c: CallbackQuery):
    """ИСПРАВЛЕННЫЙ - Текст как в команде 'мои баны'"""
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return


    try:
        parts = c.data.split('_')
        user_id = int(parts[1])
        page = int(parts[2])

        # Проверяем, что запрос от того же пользователя
        if c.from_user.id != user_id:
            await c.answer("❌ Это не ваши баны!", show_alert=True)
            return

        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        # Получаем все баны пользователя (ТОЛЬКО где был в чате)
        bans_list = await get_user_bans_all_chats(user_id, check_membership=True)

        if not bans_list:
            await c.message.edit_text(
                f"✅ {user_link}, у вас нет активных банов ни в одном чате где вы были!",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            await c.answer()
            return

        # Пагинация
        total_pages = (len(bans_list) + BANS_PER_PAGE - 1) // BANS_PER_PAGE
        page = min(page, total_pages - 1) if total_pages > 0 else 0
        start_idx = page * BANS_PER_PAGE
        end_idx = min(start_idx + BANS_PER_PAGE, len(bans_list))

        # ТЕПЕРЬ ТЕКСТ КАК В КОМАНДЕ 'мои баны'
        response = f"📋 <b>Ваши баны во всех чатах</b>\n"
        response += f"📊 Всего банов: {len(bans_list)}\n"

        current_time = datetime.now(MOSCOW_TZ)

        for i, ban_info in enumerate(bans_list[start_idx:end_idx], start_idx + 1):
            chat_id = ban_info['chat_id']

            time_end_dt = ban_info['time_end_dt']
            duration_text = ban_info['duration']
            reason = ban_info['reason'][:50] + "..." if len(ban_info['reason']) > 50 else ban_info['reason']

            # Рассчитываем оставшееся время
            if duration_text.lower() == 'навсегда':
                status = "⛔ Навсегда"
                time_text = ""
            else:
                try:
                    if time_end_dt:
                        # Убедимся, что time_end_dt в московском часовом поясе
                        if time_end_dt.tzinfo is None:
                            time_end_dt = MOSCOW_TZ.localize(time_end_dt)
                        elif str(time_end_dt.tzinfo) != str(MOSCOW_TZ):
                            time_end_dt = time_end_dt.astimezone(MOSCOW_TZ)

                        time_left = time_end_dt - current_time

                        if time_left.total_seconds() <= 0:
                            status = "🟢 Истек"
                            time_text = ""
                        else:
                            actual_time_left = format_duration(time_left)
                            status = "🔴 Активен"
                            time_text = f"{actual_time_left}\n"
                    else:
                        status = "⚠️ Неизвестно"
                        time_text = ""
                except Exception as e:
                    logger.error(f"Error calculating time left: {e}")
                    status = "⚠️ Ошибка"
                    time_text = ""

            chat_link = await chat_global_link(chat_id)

            response += (
                f"{i}. «{chat_link}» {status}\n"
                f"   📝 Срок: {duration_text} ({time_text})"
                f"   💬 Причина: {reason}\n"
                f"   ──────────────────────────\n"
            )

        # Создаем клавиатуру для пагинации (оставляем как было)
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mybans_{user_id}_{page - 1}"))

            if page < total_pages - 1:
                row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mybans_{user_id}_{page + 1}"))

            if row:
                keyboard.append(row)

        await c.message.edit_text(
            response,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        )
        await c.answer()

    except Exception as e:
        logger.error(f"Error in my_bans_pagination: {e}", exc_info=True)
        await c.answer("❌ Ошибка при обновлении списка", show_alert=True)


@bans.callback_query(lambda c: c.data.startswith('userbans_'))
@rate_limit_with_cleanup(limit=1)
async def user_bans_pagination(c: CallbackQuery):
    """ИСПРАВЛЕННЫЙ - Текст как в команде 'баны @'"""
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return

    try:
        parts = c.data.split('_')
        target_user_id = int(parts[1])
        page = int(parts[2])

        # Проверяем права доступа
        requester_id = c.from_user.id

        user_link = await user_link_global(target_user_id)
        requester_link = await user_link_global(requester_id)
        gender = await get_user_gender(target_user_id)

        # Получаем ВСЕ баны пользователя (без проверки на участие в чате)
        bans_list = await get_user_bans_all_chats(target_user_id, check_membership=False)
        active_bans_count = await get_user_active_bans_count(target_user_id, check_membership=False)

        if not bans_list:
            await c.message.edit_text(
                f"✅ {user_link} не имеет активных банов ни в одном чате!\n"
                f"👮‍♂️ Запросил: {requester_link}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            await c.answer()
            return

        # Фильтруем: показываем сначала баны где был в чате, потом где не был
        bans_in_chat = []
        bans_not_in_chat = []

        for ban in bans_list:
            if ban.get('was_in_chat', True):
                bans_in_chat.append(ban)
            else:
                bans_not_in_chat.append(ban)

        # Объединяем: сначала те, где был в чате
        sorted_bans_list = bans_in_chat + bans_not_in_chat

        # Пагинация
        total_pages = (len(sorted_bans_list) + BANS_PER_PAGE - 1) // BANS_PER_PAGE
        page = min(page, total_pages - 1) if total_pages > 0 else 0
        start_idx = page * BANS_PER_PAGE
        end_idx = min(start_idx + BANS_PER_PAGE, len(sorted_bans_list))

        # ТЕПЕРЬ ТЕКСТ КАК В КОМАНДЕ 'баны @'
        response = f"📋 <b>Все баны пользователя {user_link}</b>\n"
        response += f"📊 Всего банов: {len(sorted_bans_list)} ({len(bans_in_chat)} в чатах где был, {len(bans_not_in_chat)} где не был)\n"

        current_time = datetime.now(MOSCOW_TZ)

        for i, ban_info in enumerate(sorted_bans_list[start_idx:end_idx], start_idx + 1):
            chat_id = ban_info['chat_id']

            time_end_dt = ban_info['time_end_dt']
            duration_text = ban_info['duration']
            reason = ban_info['reason'][:50] + "..." if len(ban_info['reason']) > 50 else ban_info['reason']
            was_in_chat = ban_info.get('was_in_chat', True)

            # Получаем информацию о том, кто забанил
            admin_id = ban_info['admin_id']
            if admin_id:
                try:
                    admin_link = await user_link_global(admin_id)
                except:
                    admin_link = f"ID: {admin_id}"
            else:
                admin_link = "Неизвестен"

            # Рассчитываем оставшееся время
            if duration_text.lower() == 'навсегда':
                status = "⛔ Навсегда"
                time_text = ""
            else:
                try:
                    if time_end_dt:
                        # Убедимся, что time_end_dt в московском часовом поясе
                        if time_end_dt.tzinfo is None:
                            time_end_dt = MOSCOW_TZ.localize(time_end_dt)
                        elif str(time_end_dt.tzinfo) != str(MOSCOW_TZ):
                            time_end_dt = time_end_dt.astimezone(MOSCOW_TZ)

                        time_left = time_end_dt - current_time

                        if time_left.total_seconds() <= 0:
                            status = "🟢 Истек"
                            time_text = ""
                        else:
                            actual_time_left = format_duration(time_left)
                            status = "🔴 Активен"
                            time_text = f"⏳ Осталось: {actual_time_left}\n"
                    else:
                        status = "⚠️ Неизвестно"
                        time_text = ""
                except Exception as e:
                    logger.error(f"Error calculating time left: {e}")
                    status = "⚠️ Ошибка"
                    time_text = ""

            # Иконка статуса участия в чате
            if was_in_chat:
                chat_status = "✅"
                # chat_status_text = "Был в чате"
            else:
                chat_status = "❌"
                # chat_status_text = "Не был в чате"

            chat_link = await chat_global_link(chat_id)

            response += (
                f"{i}. «{chat_link}» ({chat_status})\n"
                f"   📝 Срок: {duration_text} ({time_text})\n"
                f"   👮‍♂️ Забанил: {admin_link}\n"
                f"   💬 Причина: {reason}\n"
                f"   ─────────────\n"
            )

        # Создаем клавиатуру для пагинации (оставляем как было)
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"userbans_{target_user_id}_{page - 1}"))

            if page < total_pages - 1:
                row.append(
                    InlineKeyboardButton(text="Вперед ➡️", callback_data=f"userbans_{target_user_id}_{page + 1}"))

            if row:
                keyboard.append(row)

        await c.message.edit_text(
            response,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        )
        await c.answer()

    except Exception as e:
        logger.error(f"Error in user_bans_pagination: {e}", exc_info=True)
        await c.answer("❌ Ошибка при обновлении списка", show_alert=True)


@bans.callback_query(lambda c: c.data.startswith('banlist_'))
@rate_limit_with_cleanup(limit=1)
async def ban_list_pagination(c: CallbackQuery):
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return

    page = int(c.data.split('_')[1])
    chat_id = c.message.chat.id

    offset = page * BANS_PER_PAGE
    bans_list = await get_all_bans(chat_id, offset, BANS_PER_PAGE)
    total_bans = await get_total_bans_count(chat_id)
    total_pages = (total_bans + BANS_PER_PAGE - 1) // BANS_PER_PAGE

    response = f"📋 <b>Список банов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, time_end) in enumerate(bans_list, start=offset + 1):
        ban_details = await get_ban_details(chat_id, user_id)

        admin_link = "Неизвестен"
        reason = "Не указана"
        duration_text = "Неизвестно"

        if ban_details:
            admin_id, reason, duration_text = ban_details
            admin_link = await user_link_global(admin_id)

        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if duration_text == 'навсегда':
            duration_reply = f'забан{g("ен", gender)} навсегда'
        else:
            time_end_dt = datetime.fromisoformat(time_end)
            time_left = time_end_dt - datetime.now()
            actual_time_left = format_duration(time_left)
            duration_reply = f'до разбана {actual_time_left}'

        response += (f"{i}. {user_link} ({duration_reply})\n"
                     f"👮🏻‍♂️ Модератор: {admin_link}\n"
                     f"💬 Причина: {reason}\n\n")

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"banlist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"banlist_{page + 1}"))
        if row:
            keyboard.append(row)

    await c.message.edit_text(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='HTML')
    await c.answer()