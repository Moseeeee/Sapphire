import logging
from datetime import datetime

from aiogram import *
from aiogram.enums import ChatType
from aiogram.types import *

from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsDB import get_user_stats
from handlers.BotAutomaticWork.parse_time_auto import format_time_ago
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.checks.user_online_status import get_user_status
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.BotAutomaticWork.users.usersDB import get_user_first_seen, get_user_full_data
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)

profile = Router()


@profile.message(lambda m: m.text and m.text.lower().startswith("!профиль"))
@profile.message(lambda m: m.text and m.text.lower().startswith(".профиль"))
@profile.message(lambda m: m.text and m.text.lower().startswith("/профиль"))
async def check_user_profile(m: Message):
    if m.chat.type == 'private':
        return

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 58):
        return

    try:
        # Получаем упоминание/ID из текста
        parts = m.text.split(maxsplit=1)
        UserId = None

        if len(parts) > 1:
            mention = parts[1].strip()
            UserId = await resolve_id(m, mention)

        # Если упоминания нет или не удалось распознать ID
        if not UserId:
            if m.reply_to_message and m.reply_to_message.from_user:
                UserId = m.reply_to_message.from_user.id
            else:
                UserId = m.from_user.id

        # Проверяем, существует ли пользователь в БД
        user_data = await get_user_full_data(UserId)
        if not user_data:
            await m.answer("❌ Пользователь не найден в базе данных")
            return

        status = await get_user_status(UserId)
        first_seen = await get_user_first_seen(UserId)

        date_str = 'неизвестно'
        time_ago = 'неизвестно'

        if first_seen:
            if isinstance(first_seen, str):
                try:
                    first_seen = datetime.fromisoformat(first_seen)
                except ValueError:
                    # Если формат даты неправильный, используем текущее время
                    first_seen = datetime.now()
            elif isinstance(first_seen, (int, float)):
                # Если это timestamp
                first_seen = datetime.fromtimestamp(first_seen)

            # Форматируем дату
            date_str = first_seen.strftime("%d.%m.%Y")
            time_ago = format_time_ago(first_seen)

        UserLink = await user_link_global(UserId)
        gender = await get_user_gender(UserId)

        # Получаем статистику сообщений пользователя
        user_stats = await get_user_stats(m.chat.id, UserId)

        # Форматируем статистику
        stats_text = ""
        if user_stats:
            stats_text = (
                f"✍️ Статистика: "
                f"{user_stats.get('daily', 0)} | "
                f"{user_stats.get('weekly', 0)} | "
                f"{user_stats.get('monthly', 0)} | "
                f"{user_stats.get('yearly', 0)} | "
                f"{user_stats.get('total', 0)}"
            )

        # Собираем сообщение
        message_parts = [
            f'{status} {UserLink}',
            f'⏱️ Первое появление в боте: {date_str} ({time_ago})',
            f'{g("пол_эмод", gender)}Пол: {g("пол", gender)}'
        ]

        if stats_text:
            message_parts.append(stats_text)

        await m.answer(
            '\n'.join(message_parts),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Ошибка в check_user_profile: {e}", exc_info=True)
        await m.answer("❌ Произошла ошибка при поиске пользователя")