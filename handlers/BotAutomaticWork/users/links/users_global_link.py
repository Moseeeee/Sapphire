import logging

from handlers.AdminsTools.ChatSettings.reports.reportsDB import search_user_name
from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name
from handlers.BotAutomaticWork.users.links.users_global_linkDB import search_username
from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettingsDB import get_user_pseudonym

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
    Приоритет отображения: псевдоним > имя пользователя > user_id
    """
    try:
        # Получаем псевдоним пользователя в этом чате
        pseudonym = await get_user_pseudonym(chat_id, user_id)

        if pseudonym:
            username = await search_username(user_id)

            if username:
                # Есть username - делаем ссылку на username
                return f"<a href='https://t.me/{username}'>{pseudonym}</a>"
            else:
                # Нет username - делаем ссылку по user_id
                return f"<a href='tg://openmessage?user_id={user_id}'>{pseudonym}</a>"
        else:
            # Если нет псевдонима, используем стандартную функцию
            return await user_link_global(user_id)

    except Exception as e:
        logger.error(f"Ошибка в user_link_with_pseudonym: {e}", exc_info=True)
        # В случае ошибки возвращаем стандартную ссылку
        return await user_link_global(user_id)