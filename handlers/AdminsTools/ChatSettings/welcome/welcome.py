import logging

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated, Message
from datetime import datetime
import pytz


from handlers.BotAutomaticWork.Gonfig.config import AGENT_CHAT_ID_CheckTextApprovals
from handlers.AdminsTools.ChatSettings.welcome.check_join_left import handle_join, handle_leave
from handlers.AdminsTools.ChatSettings.welcome.welcomeDB import (
add_welcome_text,
delete_welcome_text,
check_welcome_text
)
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsDB import get_pending_moderation, add_pending_moderation
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsUtils import contains_links, get_moderation_keyboard
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.BotAutomaticWork.universal_bot import bot


welcom = Router()

logger = logging.getLogger(__name__)

# Форматирование времени
def format_time(time: datetime) -> str:
    """Форматирует время в строку"""
    return time.strftime(f'%d.{time.month}.%Y в %H:%M')

# Получение московского времени
def get_moscow_time() -> datetime:
    """Возвращает текущее время в московском часовом поясе"""
    moscow = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow)




@welcom.message(F.text.startswith("+приветствие"))
async def new_welcome_text(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 49):
            return

        parts = msg.html_text.split("\n", 1)
        if len(parts) < 2:
            await msg.reply('Укажите текст приветствия после команды, начиная с новой строки.')
            return

        welcome_text = parts[1].strip()
        chat_id = msg.chat.id
        user_id = msg.from_user.id

        chat_link = await chat_global_link(chat_id)
        user_link = await user_link_global(user_id)

        if contains_links(welcome_text):
            admin_message = await msg.bot.send_message(
                AGENT_CHAT_ID_CheckTextApprovals,
                f"📝 <b>Новое приветствие на проверку</b>\n\n"
                f"<b>Текст:</b>\n{welcome_text}\n\n"
                f"ℹ️ Некая информация:\n"
                f"<b>Чат:</b> {chat_link}\n"
                f"<b>Пользователь:</b> {user_link}",
                reply_markup=get_moderation_keyboard(chat_id, user_id, "welcome"),
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            await msg.reply('Текст отправлен на проверку, ожидайте.')

            existing = await get_pending_moderation(chat_id, 'welcome')
            if existing:
                try:
                    await msg.bot.delete_message(AGENT_CHAT_ID_CheckTextApprovals, existing['admin_message_id'])
                except Exception:
                    pass

            await add_pending_moderation(chat_id, 'welcome', welcome_text, msg.message_id, admin_message.message_id, user_id)
        else:
            await add_welcome_text(chat_id, welcome_text)
            await msg.reply('✅ Приветствие изменено')

    except IndexError:
        await msg.reply('Укажите текст приветствия после команды, начиная с новой строки.')
    except Exception as e:
        logger.error(e, exc_info=True)
        await msg.reply('❌ Произошла ошибка')



@welcom.message(F.text.split("\n", 1)[0].lower() == "-приветствие")
async def del_welcome_text(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 49):
            return

        ChatId = msg.chat.id
        che_welcome_text = await check_welcome_text(ChatId)
        if che_welcome_text:
            await delete_welcome_text(ChatId)
            await msg.reply('✅ Приветствие чата удалено')
        else:
            await msg.reply('Приветствие не установлено')
            return
    except Exception as e:
        logger.error(e, exc_info=True)



@welcom.message(F.text.split("\n", 1)[0].lower().in_(['!приветствие', '.приветствие', '/приветствие']))
async def welcome_text(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 50):
            return

        ChatId = msg.chat.id

        welcome_text = await check_welcome_text(ChatId)

        if welcome_text:
            await bot.send_message(
                chat_id=ChatId,
                text=f'👋🏻 <b>Приветствие чата:</b>\n{welcome_text}',
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await bot.send_message(
                chat_id=ChatId,
                text='Приветствие чата не установлено'
            )
    except Exception as e:
        logger.error(e, exc_info=True)





# --- Обработчики событий входа/выхода пользователей ---
#@welcom.chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated):
    try:
        old_status = event.old_chat_member.status if hasattr(event, 'old_chat_member') else None
        new_status = event.new_chat_member.status
        user = event.new_chat_member.user



        # Игнорируем ботов
        if user.is_bot:
            print("🤖 Ignoring bot update")
            return

        # Определяем тип события - ТОЛЬКО ВХОДЫ/ВЫХОДЫ/КИКИ(БАНЫ)
        is_join = False
        is_leave = False

        # ВХОД: пользователь стал участником (из left/kicked)
        if (old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and
                new_status == ChatMemberStatus.MEMBER):
            is_join = True


        # ВЫХОД: пользователь покинул чат сам
        elif (old_status == ChatMemberStatus.MEMBER and
              new_status == ChatMemberStatus.LEFT):
            is_leave = True


        # КИК/БАН: пользователь был кикнут/забанен
        elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED, ChatMemberStatus.ADMINISTRATOR] and
              new_status == ChatMemberStatus.KICKED):
            is_leave = True


        # ОСОБЫЙ СЛУЧАЙ: restricted пользователь вошел/вышел (меняется is_member)
        elif old_status == ChatMemberStatus.RESTRICTED and new_status == ChatMemberStatus.RESTRICTED:
            old_is_member = getattr(event.old_chat_member, 'is_member', False)
            new_is_member = getattr(event.new_chat_member, 'is_member', False)



            if old_is_member and not new_is_member:
                # Restricted пользователь покинул чат
                is_leave = True

            elif not old_is_member and new_is_member:
                # Restricted пользователь вернулся в чат
                is_join = True


        # ВЫЗЫВАЕМ ОБРАБОТЧИКИ
        if is_join:
            await handle_join(event)
        elif is_leave:
            await handle_leave(event)
        else:
            return

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(e, exc_info=True)