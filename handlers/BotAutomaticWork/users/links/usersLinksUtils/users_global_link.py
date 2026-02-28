import html
import logging

from handlers.AdminsTools.ChatSettings.reports.reportsDB import search_user_name
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_linkDB import search_username
from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name

from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettingsDB import get_user_pseudonym
from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettings import format_pseudonym_for_display


logger = logging.getLogger(__name__)


async def user_link_global(UserId: int) -> str:
    try:
        username = await search_username(UserId)
        UserName = await search_user_name(UserId)
        CleanName = clean_name(UserName)

        # Определяем отображаемое имя с приоритетами
        display_name = CleanName

        if username:
            return f"<a href='https://t.me/{username}'>{display_name}</a>"
        else:
            return f"<a href='tg://openmessage?user_id={UserId}'>{display_name}</a>"

    except Exception as e:
        logger.error(e, exc_info=True)
        return f"<a href='tg://openmessage?user_id={UserId}'>{UserId}</a>"


async def user_link_with_pseudonym(user_id: int, chat_id: int) -> str:
    """
    Создает ссылку на пользователя с учетом псевдонима.
    Извлекает премиум эмодзи, создает ссылку на оставшийся текст,
    затем вставляет эмодзи обратно на их оригинальные позиции.
    """
    try:
        # Получаем псевдоним пользователя в этом чате
        pseudonym = await get_user_pseudonym(chat_id, user_id)

        if pseudonym:
            # Форматируем псевдоним с поддержкой эмодзи
            display_text = format_pseudonym_for_display(pseudonym)
            username = await search_username(user_id)

            # Если есть премиум эмодзи
            if '<tg-emoji' in display_text:
                import re

                # Находим все эмодзи и их позиции
                emoji_pattern = r'(<tg-emoji[^>]*>.*?</tg-emoji>)'

                # Разделяем текст на части: текст и эмодзи
                parts = re.split(emoji_pattern, display_text)

                # Собираем результат
                result_parts = []

                for part in parts:
                    if not part:
                        continue

                    if part.startswith('<tg-emoji'):
                        # Это эмодзи - добавляем как есть
                        result_parts.append(part)
                    else:
                        # Это текст - делаем ссылку (если текст не пустой)
                        if part.strip():
                            if username:
                                linked_text = f"<a href='https://t.me/{username}'>{part}</a>"
                            else:
                                linked_text = f"<a href='tg://openmessage?user_id={user_id}'>{part}</a>"
                            result_parts.append(linked_text)
                        else:
                            # Пустой текст (пробелы между эмодзи)
                            result_parts.append(part)

                return ''.join(result_parts)
            else:
                # Нет эмодзи - обычная ссылка
                if username:
                    return f"<a href='https://t.me/{username}'>{display_text}</a>"
                else:
                    return f"<a href='tg://openmessage?user_id={user_id}'>{display_text}</a>"
        else:
            # Если нет псевдонима, используем стандартную функцию
            return await user_link_global(user_id)

    except Exception as e:
        logger.error(f"Ошибка в user_link_with_pseudonym: {e}", exc_info=True)
        return await user_link_global(user_id)