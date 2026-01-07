import logging

from handlers.AdminsTools.ChatSettings.reports.reportsDB import search_user_name
from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name
from handlers.BotAutomaticWork.users.links.users_global_linkDB import search_username

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