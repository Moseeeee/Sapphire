import logging

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import check_admin_for_rang
from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettingsDB import check_command_chat
from handlers.AdminsTools.ChatSettings.PuchCommandSettings.push_command_settingsDB import check_push_status
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rangDB import check_command_chat_rang, \
    check_command_rang, get_user_rank
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot

logger = logging.getLogger(__name__)


async def auto_check_AccessLevel_for_rang(UserId, ChatId, CommandId):
    try:
        CheckCommandRangTrue = await check_command_chat(CommandId, ChatId)

        if CheckCommandRangTrue == True:
            AccessLevel = await check_command_chat_rang(CommandId, ChatId)

        else:
            AccessLevel = await check_command_rang(CommandId)

        UserRang = await check_admin_for_rang(UserId, ChatId)


        if int(UserRang) >= int(AccessLevel):
            return True
        else:
            push_status = await check_push_status(ChatId)
            if push_status == 'on':
                await send_push(ChatId, AccessLevel)
            return False

    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def send_push(ChatId, AccessLevel):
    try:
        if AccessLevel == 6:
            await bot.send_message(chat_id=ChatId, text='❌ Команда отключена.')

        else:
            await bot.send_message(chat_id=ChatId, text='❌ Данная команда вам не доступна!')
    except Exception as e:
        logger.error(e, exc_info=True)



async def check_agent_access(user_id):
    """Проверяет права доступа пользователя"""
    rank = await get_user_rank(user_id)
    if rank is not None and rank:
        return rank
    else:
        return 0

async def check_user_access(user_id: int, min_rank: int) -> bool:
    """Проверяет доступ пользователя"""
    try:
        rank = await check_agent_access(user_id)
        return rank >= min_rank
    except:
        return False



