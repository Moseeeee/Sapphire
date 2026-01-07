
import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.types import *
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from datetime import datetime

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_admin_for_rang
from handlers.AdminsTools.CommandsModerations.warns.warnsDB import (
    add_warn, remove_warn, get_user_warns_count, get_user_warns,
    get_all_warns, get_total_warns_count,
    set_default_warn_duration,
    set_warn_action, get_warn_action, set_warn_limit, get_warn_limit,
    clear_user_warns, parse_warn_duration, get_default_warn_duration
)

# Импортируем функции для мута и бана
from handlers.AdminsTools.CommandsModerations.bans.banDB import get_default_ban_duration
from handlers.AdminsTools.CommandsModerations.mute.muteDB import get_default_mute_duration
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AdminsTools.CommandsModerations.mute.mute import perform_mute

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import is_telegram_owner
from handlers.BotAutomaticWork.SeasonsEmojiUtils import get_emoji
from handlers.BotAutomaticWork.parse_time_auto import format_duration, parse_time_string
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import get_random_text, rate_limit_with_cleanup
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.universal_bot import bot
from pytz import timezone as pytz_timezone

logger = logging.getLogger(__name__)

warn = Router()
MOSCOW_TZ = pytz_timezone('Europe/Moscow')

# Константы для пагинации
WARNS_PER_PAGE = 10



async def perform_warn_action(chat_id: int, user_id: int, action: str, admin_id: int,
                              reason: str = "Достигнут лимит варнов"):
    """Выполняет действие при достижении лимита варнов"""
    try:
        if action == 'ban':
            # Получаем длительность бана по умолчанию
            default_duration = await get_default_ban_duration(chat_id)

            # Если default_duration is None - значит бан навсегда
            duration = default_duration if default_duration is not None else 'навсегда'

            # Вызываем стандартную функцию бана
            success, result = await perform_ban(
                chat_id=chat_id,
                user_id=user_id,
                duration=duration,
                admin_id=admin_id,
                reason=reason
            )

            if success:
                # result уже должен быть отформатированной строкой из функции perform_ban
                return result
            else:
                logger.error(f"Error performing ban from warn action: {result}")
                return None

        elif action == 'mute':
            # Получаем длительность мута по умолчанию
            default_duration = await get_default_mute_duration(chat_id)

            # Если default_duration is None - значит мут навсегда
            duration = default_duration if default_duration is not None else 'навсегда'

            # Вызываем стандартную функцию мута
            success, result = await perform_mute(
                chat_id=chat_id,
                user_id=user_id,
                duration=duration,
                admin_id=admin_id,
                reason=reason
            )

            if success:
                # result уже должен быть отформатированной строкой из функции perform_mute
                return result
            else:
                logger.error(f"Error performing mute from warn action: {result}")
                return None

        elif action == 'kick':
            # Кик при достижении лимита варнов
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await asyncio.sleep(1)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            return "кик"
        else:
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def enforce_warn_limits(chat_id: int):
    """Проверяет всех пользователей и применяет наказание, если варнов больше лимита"""
    warn_limit = await get_warn_limit(chat_id)
    action = await get_warn_action(chat_id)

    # Получаем всех пользователей с варнами
    all_warns = await get_all_warns(chat_id, offset=0)

    violators = []  # Список для хранения информации о нарушителях
    action_messages = []  # Для сбора результатов действий

    for user_id, warn_count in all_warns:
        if warn_count > warn_limit:
            try:
                # Получаем причину
                warns_detail = await get_user_warns(chat_id, user_id)
                reason = "Превышен лимит варнов после его изменения"
                if warns_detail:
                    reason = warns_detail[-1][2] or reason

                # Применяем действие
                action_result = await perform_warn_action(
                    chat_id=chat_id,
                    user_id=user_id,
                    action=action,
                    admin_id=bot.id,
                    reason=reason
                )

                if action_result:
                    # Собираем информацию о нарушителе
                    user_link = await user_link_global(user_id)
                    violators.append({
                        'user_link': user_link,
                        'user_id': user_id,
                        'warn_count': warn_count,
                        'action_result': action_result
                    })

                    action_messages.append(action_result)

                # Сбрасываем варны после наказания
                await clear_user_warns(chat_id, user_id)

            except Exception as e:
                logger.error(f"Ошибка при обработке пользователя {user_id}: {e}")
                continue

    # Отправляем одно сообщение со всеми нарушителями
    if violators:
        message_lines = ["⚠️ <b>Автоматическое применение наказаний:</b>\n"]

        for i, violator in enumerate(violators, 1):
            message_lines.append(
                f"{i}. {violator['user_link']} - "
                f"{violator['warn_count']} варнов > лимит {warn_limit}\n"
                f"   Действие: {violator['action_result']}"
            )

        # Добавляем статистику
        unique_actions = set(action_messages)
        stats_line = f"\n📊 <b>Статистика:</b> наказано {len(violators)} пользователей"
        if len(unique_actions) == 1:
            stats_line += f" ({action_messages[0]})"
        else:
            stats_line += f" ({', '.join(unique_actions)})"

        message_lines.append(stats_line)

        final_message = "\n".join(message_lines)

        try:
            await bot.send_message(
                chat_id,
                final_message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            # Пробуем отправить без форматирования
            try:
                await bot.send_message(
                    chat_id,
                    final_message,
                    disable_web_page_preview=True
                )
            except Exception as e2:
                logger.error(f"Критическая ошибка отправки: {e2}")

    return len(violators)  # Возвращаем количество наказанных пользователей


# ======================
# Хендлеры команд варнов
# ======================

@warn.message(F.text.regexp(re.compile(r'^[!/.]варнлист(\s|$)', re.IGNORECASE)))
async def warn_list(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 30):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    page = 0
    parts = text.split()
    if len(parts) > 1 and parts[1].isdigit():
        page = max(0, int(parts[1]) - 1)

    offset = page * WARNS_PER_PAGE
    warns_list = await get_all_warns(m.chat.id, offset, WARNS_PER_PAGE)
    total_warns = await get_total_warns_count(m.chat.id)
    total_pages = (total_warns + WARNS_PER_PAGE - 1) // WARNS_PER_PAGE

    if not warns_list:
        await m.answer("📝 В этом чате нет пользователей с варнами.")
        return

    response = f"📋 <b>Список варнов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, warn_count) in enumerate(warns_list, start=offset + 1):
        user_link = await user_link_global(user_id)
        warn_limit = await get_warn_limit(m.chat.id)

        response += f"{i}. {user_link} - {warn_count}/{warn_limit} варнов\n"

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"warnlist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"warnlist_{page + 1}"))
        if row:
            keyboard.append(row)

    await m.reply(response,
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                   parse_mode='HTML',
                   disable_web_page_preview=True)


@warn.message(F.text.regexp(re.compile(r'^[!/.]варны исход\s+\S+', re.IGNORECASE)))
async def set_warn_outcome(m: Message):


    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 33):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "❌ Укажите исход при достижении лимита варнов.\n"
            "Доступные варианты: <code>бан</code>, <code>мут</code>, <code>кик</code>\n"
            "Пример: <code>варны исход бан</code>",
            parse_mode="HTML"
        )
        return

    action = parts[2].lower().strip()
    if action not in ['бан', 'мут', 'кик']:
        await m.answer(
            "❌ Неверный исход. Используйте: <code>бан</code>, <code>мут</code> или <code>кик</code>",
            parse_mode="HTML"
        )
        return

    # Преобразуем в английский для хранения в БД
    action_map = {'бан': 'ban', 'мут': 'mute', 'кик': 'kick'}
    action_db = action_map[action]

    await set_warn_action(m.chat.id, action_db)

    # Получаем информацию о длительности для бана/мута
    duration_info = ""
    if action == 'бан':
        default_duration = await get_default_ban_duration(m.chat.id)
        if default_duration is None:
            duration_info = " (навсегда)"
        else:
            duration_info = f" (на {format_duration(default_duration)})"
    elif action == 'мут':
        default_duration = await get_default_mute_duration(m.chat.id)
        if default_duration is None:
            duration_info = " (навсегда)"
        else:
            duration_info = f" (на {format_duration(default_duration)})"

    await m.answer(f"✅ Исход при достижении лимита варнов установлен: <b>{action}{duration_info}</b>",
                   parse_mode="HTML")


@warn.message(F.text.regexp(re.compile(r'^[!/.]варны период\s+\S+', re.IGNORECASE)))
async def set_default_warn_period(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 31):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "❌ Укажите длительность варна по умолчанию.\n"
            "Пример: <code>варны период 3 дня</code>\n"
            "Или: <code>варны период 1 неделя</code>",
            parse_mode="HTML"
        )
        return

    duration_input = parts[2].strip()
    parsed_duration = parse_time_string(duration_input)

    if parsed_duration is None:
        await m.answer(
            "❌ Не удалось распознать время. Используйте формат: <code>1 день 2 часа 30 минут</code>",
            parse_mode="HTML"
        )
        return

    await set_default_warn_duration(m.chat.id, duration_input)
    formatted = format_duration(parsed_duration)
    await m.answer(f"✅ Время варна по умолчанию установлено: <b>{formatted}</b>", parse_mode="HTML")


@warn.message(F.text.regexp(re.compile(r'^[!/.]варны лимит\s+\S+', re.IGNORECASE)))
async def set_warn_limit_cmd(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 32):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "❌ Укажите лимит варнов (от 1 до 100).\n"
            "Пример: <code>варн лимит 5</code>",
            parse_mode="HTML"
        )
        return

    try:
        limit = int(parts[2])
        if limit < 1 or limit > 100:
            await m.answer("❌ Лимит варнов должен быть от 1 до 100.")
            return

        old_limit = await get_warn_limit(m.chat.id)
        await set_warn_limit(m.chat.id, limit)

        current_action = await get_warn_action(m.chat.id)
        action_map = {'ban': 'бан', 'mute': 'мут', 'kick': 'кик'}
        action_text = action_map.get(current_action, 'бан')

        await m.answer(f"✅ Лимит варнов установлен: <b>{limit}</b>\n"
                       f"При достижении лимита: <b>{action_text}</b>",
                       parse_mode="HTML")

        # === НОВОЕ: ЗАПУСК ЛЕНИВОЙ ПЕРЕПРОВЕРКИ ===
        if limit < old_limit:  # Только если лимит УМЕНЬШИЛИ — иначе смысла нет
            await m.answer("🔄 Запускаю проверку пользователей, превысивших новый лимит...")
            try:
                await enforce_warn_limits(m.chat.id)
            except Exception as e:
                logger.error(f"Ошибка при enforce_warn_limits: {e}", exc_info=True)
                await m.answer("⚠️ Ошибка при автоматической проверке варнов.")

    except ValueError:
        await m.answer("❌ Укажите корректное число для лимита.")


@warn.message(F.text.regexp(re.compile(r'^[-]варн(\s|$)', re.IGNORECASE)))
@warn.message(F.text.regexp(re.compile(r'^[!./]снять варн(\s|$)', re.IGNORECASE)))
async def unwarn_user(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 29):
        return

    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./снять':
        text = text[1:].strip()

    parts = text.split()

    # Определяем UserId и warn_id
    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
        warn_id = None
        if len(parts) > 1 and parts[1].isdigit():
            warn_id = int(parts[1])
    else:
        if len(parts) < 2:
            await m.answer(
                "❌ Неверный формат!\nИспользуйте: <code>-варн {@username} [номер_варна]</code> или ответьте на сообщение",
                parse_mode="HTML"
            )
            return

        mention = parts[1]
        UserId = await resolve_id(m, mention)
        warn_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)

    # Проверяем существование варнов
    current_warns = await get_user_warns_count(m.chat.id, UserId)

    if current_warns == 0:
        await m.answer(f"❌ У пользователя {user_link} нет активных варнов.")
        return

    if warn_id and (warn_id < 1 or warn_id > current_warns):
        await m.answer(f"❌ Неверный номер варна. У пользователя {user_link} всего {current_warns} варн(ов).")
        return

    # Снимаем варн
    new_warn_count = await remove_warn(m.chat.id, UserId, warn_id)

    gender_admin = await get_user_gender(m.from_user.id)

    if warn_id:
        await m.answer(f"✅ С пользователя {user_link} снят варн #{warn_id} (теперь {new_warn_count} варнов)\n"
                       f"👮‍♂️ Сн{g('ял', gender_admin)}: {admin_link}",
                       parse_mode='HTML', disable_web_page_preview=True)
    else:
        await m.answer(f"✅ С пользователя {user_link} снят последний варн (теперь {new_warn_count} варнов)\n"
                       f"👮‍♂️ Сн{g('ял', gender_admin)}: {admin_link}",
                       parse_mode='HTML', disable_web_page_preview=True)


@warn.message(F.text.regexp(re.compile(r'^[!/.]варны\s+\S+', re.IGNORECASE)))
async def user_warns(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 60):
        return
    # Удаляем префикс из команды
    text = m.text.strip()
    if text[0] in '!./':
        text = text[1:].strip()

    # Проверяем, что это не команда "варны период"
    if text.startswith("варны период"):
        return

    # Проверяем, что это не команда "варны исход"
    if text.startswith("варны исход"):
        return

    # Проверяем, что это не команда "варны лимит"
    if text.startswith("варны лимит"):
        return

    parts = text.split(maxsplit=2)  # Изменено с 1 на 2 для получения номера страницы

    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
        page = 0
        if len(parts) > 1 and parts[1].isdigit():
            page = max(0, int(parts[1]) - 1)
    else:
        if len(parts) < 2:
            await m.answer(
                "❌ Неверный формат!\nИспользуйте: <code>варны {@username} [страница]</code> или ответьте на сообщение",
                parse_mode="HTML"
            )
            return

        mention = parts[1]
        UserId = await resolve_id(m, mention)
        page = 0
        if len(parts) > 2 and parts[2].isdigit():
            page = max(0, int(parts[2]) - 1)

    user_link = await user_link_global(UserId)
    warn_count = await get_user_warns_count(m.chat.id, UserId)
    warn_limit = await get_warn_limit(m.chat.id)

    # Получаем все варны пользователя
    all_warns = await get_user_warns(m.chat.id, UserId)

    if not all_warns:
        await m.answer(f"📋 <b>Варны пользователя {user_link}</b>\n"
                       f"📊 Всего варнов: {warn_count}/{warn_limit}\n\n"
                       f"✅ Нет активных варнов",
                       parse_mode='HTML', disable_web_page_preview=True)
        return

    # Пагинация
    WARNS_PER_PAGE_USER = 10  # Количество варнов на страницу
    total_pages = (len(all_warns) + WARNS_PER_PAGE_USER - 1) // WARNS_PER_PAGE_USER
    page = min(page, total_pages - 1)  # Ограничиваем страницу

    # Вычисляем начало и конец для текущей страницы
    start_idx = page * WARNS_PER_PAGE_USER
    end_idx = min(start_idx + WARNS_PER_PAGE_USER, len(all_warns))
    current_warns = all_warns[start_idx:end_idx]

    response = f"📋 <b>Варны пользователя {user_link}</b>\n"
    response += f"📊 Всего варнов: {warn_count}/{warn_limit}\n"
    response += f"📄 Страница {page + 1}/{total_pages}\n\n"

    # Отображаем варны для текущей страницы
    for i, (warn_id, admin_id, reason, created_at, expires_at, real_id) in enumerate(current_warns,
                                                                                     start=start_idx + 1):
        admin_link = await user_link_global(admin_id)

        # Теперь created_at и expires_at уже должны быть datetime объектами с московской таймзоной
        now_moscow = datetime.now(MOSCOW_TZ)
        time_left = expires_at - now_moscow

        gender_admin = await get_user_gender(admin_id)

        if time_left.total_seconds() > 86400 * 365 * 50:  # Если больше 50 лет (условно "навсегда")
            response += (f"{i}. Варн навсегда\n"
                         f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                         f"   💬 Причина: {reason}\n\n")
        elif time_left.total_seconds() > 0:
            time_left_str = format_duration(time_left)
            response += (f"{i}. Варн истечет через {time_left_str}\n"
                         f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                         f"   💬 Причина: {reason}\n\n")
        else:
            response += (f"{i}. Варн истек\n"
                         f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                         f"   💬 Причина: {reason}\n\n")

    # Создаем клавиатуру для пагинации, если есть больше одной страницы
    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"user_warns_{UserId}_{page - 1}"
            ))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"user_warns_{UserId}_{page + 1}"
            ))
        if row:
            keyboard.append(row)

    await m.reply(
        response,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    )


@warn.message(F.text.regexp(re.compile(r'^[+!/.]варн(\s|$)', re.IGNORECASE)))
async def warn_user(m: Message):

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 29):
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
    # logger.info(f"Части команды варн: {parts}")

    # Определяем пользователя и время варна
    UserId = None
    duration = None  # None означает "использовать по умолчанию" или "навсегда" если строка
    duration_str = None  # Для хранения строкового представления

    # Если это ответ на сообщение
    if m.reply_to_message:
        UserId = m.reply_to_message.from_user.id
        # Ищем время в частях после команды (если есть)
        time_parts = []
        if len(parts) > 1:
            time_parts = parts[1:]
        time_str = ' '.join(time_parts) if time_parts else None

        if time_str:
            # Пытаемся найти время в оставшихся частях
            # Проверяем специальные случаи "навсегда"
            if time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
                duration_str = "навсегда"
                duration = None
            else:
                # Пытаемся найти время
                parsed = parse_warn_duration(time_str)
                if parsed is not None:
                    duration = parsed
                    duration_str = time_str
                elif "навсегда" in time_str.lower():
                    duration_str = "навсегда"
                    duration = None
    else:
        # Если не ответ на сообщение - анализируем команду
        if len(parts) < 2:
            await m.reply('⚠️ Пользователь не указан!\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/варн @username 1ч</code>\n'
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
                # Пробуем распарсить время
                if time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
                    duration_str = "навсегда"
                    duration = None
                else:
                    parsed = parse_warn_duration(time_str)
                    if parsed is not None:
                        duration = parsed
                        duration_str = time_str
        else:
            # Первый элемент не пользователь - может быть сначала время, потом пользователь
            # Например: "варн 4 часа @user"
            # Пробуем найти пользователя дальше
            for i in range(2, len(parts)):
                potential_user = parts[i]
                resolved_id = await resolve_id(m, potential_user)
                if resolved_id:
                    UserId = resolved_id
                    # Время - это часть перед пользователем
                    time_str = ' '.join(parts[1:i]) if i > 1 else None
                    if time_str:
                        if time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
                            duration_str = "навсегда"
                            duration = None
                        else:
                            parsed = parse_warn_duration(time_str)
                            if parsed is not None:
                                duration = parsed
                                duration_str = time_str
                    break

        # Если не нашли пользователя
        if not UserId:
            # Пробуем последний элемент как пользователя
            potential_user = parts[-1]
            resolved_id = await resolve_id(m, potential_user)
            if resolved_id:
                UserId = resolved_id
                # Время - это всё перед последним элементом
                time_str = ' '.join(parts[1:-1]) if len(parts) > 2 else None
                if time_str:
                    if time_str.lower() in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
                        duration_str = "навсегда"
                        duration = None
                    else:
                        parsed = parse_warn_duration(time_str)
                        if parsed is not None:
                            duration = parsed
                            duration_str = time_str

        # Если все еще не нашли пользователя
        if not UserId:
            await m.reply('⚠️ Пользователь не указан или не найден!\n\n'
                          'Используйте один из способов:\n'
                          '1. Ответьте на сообщение пользователя\n'
                          '2. Укажите @username или ID пользователя\n'
                          'Пример: <code>/варн @username 1ч</code>\n'
                          '<code>причина с новой строки</code>',
                          parse_mode='HTML')
            return

    # Логируем найденные данные
    # logger.info(f"UserID: {UserId}, Duration: {duration}, Duration string: '{duration_str}', Reason: '{reason}'")

    # Если причина указана с новой строки, обрезаем ее до 200 символов
    if reason != "Не указана":
        reason = reason[:200]
        msg_text = f'\n💬 Причина: {reason}'
    else:
        msg_text = ""

    # ========== ПРОВЕРКА РАНГОВ ДЛЯ ВАРНА ==========
    try:
        ManagementAdminId = m.from_user.id
        UserRang = await check_admin_for_rang(UserId, m.chat.id)
        ManagementRang = await check_admin_for_rang(ManagementAdminId, m.chat.id)

        if UserRang > 0:
            if ManagementAdminId not in boss_agent:
                is_tg_owner = await is_telegram_owner(bot, m.chat.id, ManagementAdminId)

                if not is_tg_owner:
                    if UserRang >= ManagementRang:
                        admin_link = await user_link_global(ManagementAdminId)

                        if UserRang == ManagementRang:
                            await m.answer(
                                f"{admin_link}, вы не имеете право наказать равного себе админа!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        else:
                            await m.answer(
                                f"{admin_link}, вы пытаетесь выдать варн администратору выше вашего статуса!\n",
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                        return
    except Exception as e:
        logger.error(f"Ошибка при проверке рангов для варна: {e}", exc_info=True)

    # ========== КОНЕЦ ПРОВЕРКИ РАНГОВ ДЛЯ ВАРНА ==========

    # ========== ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ ==========
    chat_id = m.chat.id
    # Получаем информацию об администраторах чата
    try:
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        creator_id = [admin.user.id for admin in admins if admin.status == 'creator']

        # Проверяем, не пытается ли админ выдать варн боту
        if UserId == bot.id:
            await m.answer_sticker(
                sticker='CAACAgIAAxkBAAEPgyNo4WXlQeKd729gw8WbZ_AFUJjSsQACCwEAAladvQpOseemCPvtSTYE')
            return

        # Проверяем, является ли пользователь создателем чата
        if creator_id and UserId == creator_id[0]:
            await m.reply('❎ На владельца чата нельзя выдавать варн.')
            return

        # Проверяем, является ли пользователь администратором
        if UserId in admin_ids:
            await m.reply('❎ Нельзя выдать варн администратору!')
            return
    except Exception as e:
        logger.error(f"Ошибка при получении администраторов чата: {e}")
        # Продолжаем выполнение, если не удалось получить администраторов

    # Проверяем, не пытается ли админ выдать варн самому себе
    if UserId == m.from_user.id:
        await m.answer_sticker(
            sticker='CAACAgIAAxkBAAEQJO9pVAa9CKGYy1Pvar3772FgMGwDmgAC_wADVp29Ctqt-n3kvEAkOAQ')
        return

    # Проверка привязанного канала
    try:
        chat_info = await bot.get_chat(chat_id)
        linked_chat_id = chat_info.linked_chat_id

        if (
                m.reply_to_message and
                m.reply_to_message.sender_chat and
                m.reply_to_message.sender_chat.id == linked_chat_id
        ):
            await m.reply('❎ Нельзя выдать варн привязанному каналу!')
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке привязанного канала: {e}")

    # Проверяем, не забанен ли пользователь в чате
    try:
        member = await bot.get_chat_member(chat_id, UserId)
        if member.status == 'kicked':
            await m.answer("❌ Нельзя выдать варн забаненному пользователю!")
            return
        if member.status == 'left':
            await m.answer("❌ Нельзя выдать варн пользователю, которого нет в чате!")
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса пользователя: {e}")

    # ========== КОНЕЦ ДОПОЛНИТЕЛЬНЫХ ПРОВЕРОК ==========

    user_link = await user_link_global(UserId)
    admin_link = await user_link_global(m.from_user.id)

    # Добавляем варн с указанной длительностью
    # Если duration = None, это означает "навсегда"
    warn_count = await add_warn(m.chat.id, UserId, m.from_user.id, reason, duration)

    gender = await get_user_gender(UserId)
    gender_admin = await get_user_gender(m.from_user.id)

    if warn_count > 0:
        warn_limit = await get_warn_limit(m.chat.id)

        # Формируем информацию о времени
        if duration is None:
            if duration_str == "навсегда":
                time_info = "навсегда"
            else:
                # Используем время по умолчанию
                default_duration = await get_default_warn_duration(m.chat.id)
                time_info = f"на {format_duration(default_duration)}"
        else:
            time_info = f"на {format_duration(duration)}"

        response = (
            f"{get_emoji('warn_emoji')} {user_link} получ{g('ил', gender)} варн {time_info} ({warn_count}/{warn_limit})\n"
            f"👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}")

        if msg_text:
            response += msg_text

        # Проверяем, достигнут ли лимит варнов
        if warn_count >= warn_limit:
            action = await get_warn_action(m.chat.id)
            action_result = await perform_warn_action(m.chat.id, UserId, action, m.from_user.id, reason)

            if action_result:
                # Разбираем результат для корректного отображения
                action_parts = action_result.split()
                action_type = action_parts[0]  # "бан", "мут" или "кик"
                duration_text = " ".join(action_parts[2:]) if len(action_parts) > 2 else ""

                if action_type == "кик":
                    response += f"\n\n{get_emoji('warn_emoji')} Достигнут лимит варнов, {user_link} получ{g('ил', gender)} наказание!."
                elif duration_text == "навсегда":
                    response += f"\n\n{get_emoji('warn_emoji')} Достигнут лимит варнов, {user_link} получ{g('ил', gender)} наказание!"
                else:
                    response += f"\n\n{get_emoji('warn_emoji')} Достигнут лимит варнов, {user_link} получ{g('ил', gender)} наказание!"

                # Сбрасываем варны после применения наказания
                await clear_user_warns(m.chat.id, UserId)
            else:
                response += f"\n\n⚠️ Достигнут лимит варнов, но выполнить действие не удалось."

        await m.answer(response, parse_mode='HTML', disable_web_page_preview=True)
    else:
        await m.answer("❌ Ошибка при выдаче варна")


@warn.callback_query(lambda c: c.data.startswith('warnlist_'))
@rate_limit_with_cleanup(limit=1)
async def warn_list_pagination(c: CallbackQuery):
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return

    page = int(c.data.split('_')[1])
    chat_id = c.message.chat.id

    offset = page * WARNS_PER_PAGE
    warns_list = await get_all_warns(chat_id, offset, WARNS_PER_PAGE)
    total_warns = await get_total_warns_count(chat_id)
    total_pages = (total_warns + WARNS_PER_PAGE - 1) // WARNS_PER_PAGE

    response = f"📋 <b>Список варнов</b> (Страница {page + 1}/{max(1, total_pages)})\n\n"

    for i, (user_id, warn_count) in enumerate(warns_list, start=offset + 1):
        user_link = await user_link_global(user_id)
        warn_limit = await get_warn_limit(chat_id)

        response += f"{i}. {user_link} - {warn_count}/{warn_limit} варнов\n"

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"warnlist_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"warnlist_{page + 1}"))
        if row:
            keyboard.append(row)

    await c.message.edit_text(response,
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                              parse_mode='HTML')
    await c.answer()


@warn.callback_query(lambda c: c.data.startswith('user_warns_'))
@rate_limit_with_cleanup(limit=1)
async def user_warns_pagination(c: CallbackQuery):
    """Обработчик пагинации для списка варнов пользователя"""
    try:
        # Проверяем, что пользователь, который нажал кнопку, тот же, что и запросил список
        # (можете адаптировать эту проверку под ваши нужды)
        if (not c.message.reply_to_message or
                c.from_user.id != c.message.reply_to_message.from_user.id):
            random_text = get_random_text()
            await c.answer(f"{random_text}", show_alert=True)
            return

        parts = c.data.split('_')
        if len(parts) != 4:
            await c.answer("❌ Ошибка данных", show_alert=True)
            return

        UserId = int(parts[2])
        page = int(parts[3])

        user_link = await user_link_global(UserId)
        chat_id = c.message.chat.id

        warn_count = await get_user_warns_count(chat_id, UserId)
        warn_limit = await get_warn_limit(chat_id)

        # Получаем все варны пользователя
        all_warns = await get_user_warns(chat_id, UserId)

        if not all_warns:
            await c.message.edit_text(
                f"📋 <b>Варны пользователя {user_link}</b>\n"
                f"📊 Всего варнов: {warn_count}/{warn_limit}\n\n"
                f"✅ Нет активных варнов",
                parse_mode='HTML'
            )
            await c.answer()
            return

        # Пагинация
        WARNS_PER_PAGE_USER = 10
        total_pages = (len(all_warns) + WARNS_PER_PAGE_USER - 1) // WARNS_PER_PAGE_USER
        page = min(max(0, page), total_pages - 1)  # Ограничиваем страницу

        # Вычисляем начало и конец для текущей страницы
        start_idx = page * WARNS_PER_PAGE_USER
        end_idx = min(start_idx + WARNS_PER_PAGE_USER, len(all_warns))
        current_warns = all_warns[start_idx:end_idx]

        response = f"📋 <b>Варны пользователя {user_link}</b>\n"
        response += f"📊 Всего варнов: {warn_count}/{warn_limit}\n"
        response += f"📄 Страница {page + 1}/{total_pages}\n\n"

        # Отображаем варны для текущей страницы
        for i, (warn_id, admin_id, reason, created_at, expires_at, real_id) in enumerate(current_warns,
                                                                                         start=start_idx + 1):
            admin_link = await user_link_global(admin_id)

            now_moscow = datetime.now(MOSCOW_TZ)
            time_left = expires_at - now_moscow

            gender_admin = await get_user_gender(admin_id)

            if time_left.total_seconds() > 86400 * 365 * 50:
                response += (f"{i}. Варн навсегда\n"
                             f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                             f"   💬 Причина: {reason}\n\n")
            elif time_left.total_seconds() > 0:
                time_left_str = format_duration(time_left)
                response += (f"{i}. Варн истечет через {time_left_str}\n"
                             f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                             f"   💬 Причина: {reason}\n\n")
            else:
                response += (f"{i}. Варн истек\n"
                             f"   👮‍♂️ Выд{g('ал', gender_admin)}: {admin_link}\n"
                             f"   💬 Причина: {reason}\n\n")

        # Создаем клавиатуру для пагинации
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"user_warns_{UserId}_{page - 1}"
                ))
            if page < total_pages - 1:
                row.append(InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"user_warns_{UserId}_{page + 1}"
                ))
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
        logger.error(f"Ошибка в пагинации варнов пользователя: {e}", exc_info=True)
        await c.answer("❌ Произошла ошибка", show_alert=True)


@warn.message(F.text.regexp(r'^[!/.](?:кнопочка)'))
async def tap_keyboard(m: Message):
    text = 'просто тапни кнопочку!'

    # Создаем кнопку
    button = InlineKeyboardButton(text="🔘 Тапни меня!", callback_data="tap_button")

    # Создаем клавиатуру с кнопкой
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])

    await m.reply(
        text,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=keyboard
    )

@warn.callback_query(lambda c: c.data.startswith('tap_button'))
@rate_limit_with_cleanup(limit=1)
async def handle_tap_button(c: CallbackQuery):
    """Обработчик нажатия на кнопку"""
    try:
        # Проверяем, что пользователь, который нажал кнопку, тот же, что и запросил
        if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
            random_text = get_random_text()
            await c.answer(f"{random_text}", show_alert=True)
            return

        await c.answer('ТАП ТАП ТАП!')

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await c.answer("❌ Произошла ошибка", show_alert=True)