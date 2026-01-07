import logging

from aiogram.enums import ChatMemberStatus

from handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettingsDB import check_antispam_status
from handlers.AdminsTools.ChatSettings.captcha.captchaDB import is_captcha_enabled
from handlers.AdminsTools.ChatSettings.captcha.captcha_main import handle_new_member
from handlers.AdminsTools.ChatSettings.welcome.welcomeDB import (
    add_full_users_chats,
    add_full_users_chats_leave,
    update_full_users_chats_status,
    check_welcome_text
)
from handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEditsDB import check_status_v
from aiogram.types import ChatMemberUpdated



from datetime import datetime
import pytz
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AgentsFeatures.AntiSpam.AntiSpamDB import check_anti_spam
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.universal_bot import bot

logger = logging.getLogger(__name__)

def format_time(time: datetime) -> str:
    """Форматирует время в строку"""
    return time.strftime(f'%d.{time.month}.%Y в %H:%M')

def get_moscow_time() -> datetime:
    moscow = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow)


async def handle_join(event: ChatMemberUpdated):
    try:
        chat_id = event.chat.id
        user = event.new_chat_member.user

        # Проверяем, может ли бот отправлять сообщения
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception as e:
            logger.error(e, exc_info=True)
            return

        admin = event.from_user
        user_id = user.id
        join_time = format_time(get_moscow_time())

        # Обновляем базу данных
        await add_full_users_chats(chat_id, user_id, join_time)

        user_link = await user_link_global(user_id)
        admin_link = await user_link_global(admin.id) if admin else "Система"

        gender = await get_user_gender(user_id)
        gender_admin = await get_user_gender(user_id)

        antispam_status = await check_antispam_status(chat_id)
        if antispam_status == 'on':
            check_antispam = await check_anti_spam(user_id)
            if check_antispam:
                await perform_ban(
                    chat_id=chat_id,
                    user_id=user_id,
                    duration="навсегда",
                    admin_id=bot.id,
                    reason='Пользователь находится в АС'
                )
                await bot.send_message(chat_id,
                                       f'⚠️ {user_link} находится в АС системе.\n{g("он", gender)} {g("был", gender)} заблокиров{g("ан", gender)} в соображениях безопасности.',
                                       disable_web_page_preview=True,
                                       parse_mode='HTML'
                                       )
                return

        # Уведомление о входе
        join_notify = await check_status_v(chat_id)
        if join_notify == "yes":
            if admin and admin.id != user_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"<b>👤 {user_link} добавл{g('ен', gender)} в чат.</b>\n➕ Добав{g('ил', gender_admin)}: {admin_link}",
                    disable_web_page_preview=True,
                    parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"➕ {user_link} присоедини{g('лся', gender)} к чату.",
                    disable_web_page_preview=True,
                    parse_mode='HTML'
                )

        # Проверяем капчу
        captcha_enabled = await is_captcha_enabled(chat_id)

        # Приветствие
        welcome_text = await check_welcome_text(chat_id)

        if welcome_text:
            # Проверяем, содержит ли текст приветствия {имя}
            if '{имя}' not in welcome_text:
                # Если {имя} нет, добавляем user_link в начало
                send_welcome_text = f"{user_link}\n{welcome_text}"
            else:
                # Если {имя} есть, заменяем его на user_link
                send_welcome_text = welcome_text.replace('{имя}', user_link)

            if captcha_enabled:
                send_welcome_text += "\n\n⚠️ <b>В чате установлена капча, пройдите её чтобы общаться в чате.</b>"

            await bot.send_message(
                chat_id=chat_id,
                text=send_welcome_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            if captcha_enabled:
                welcome_msg = f"👋 Добро пожаловать, {user_link}!"
                welcome_msg += "\n\n⚠️ <b>В чате установлена капча, пройдите её чтобы общаться в чате.</b>"

                await bot.send_message(
                    chat_id=chat_id,
                    text=welcome_msg,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                # Если нет текста приветствия и капча выключена
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Добро пожаловать, {user_link}!",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

        # Запускаем капчу если включена
        if captcha_enabled:
            await handle_new_member(event, bot)

    except Exception as e:
        logger.error(f"Ошибка в handle_join: {e}", exc_info=True)



    except Exception as e:
        logger.error(e, exc_info=True)
        import traceback
        traceback.print_exc()


async def handle_leave(event: ChatMemberUpdated):
    try:
        chat_id = event.chat.id
        user = event.old_chat_member.user
        user_id = user.id
        leave_time = format_time(get_moscow_time())


        new_status = event.new_chat_member.status
        admin = event.from_user

        user_link = await user_link_global(user_id)

        # Обновляем базу данных
        await add_full_users_chats_leave(chat_id, user_id, leave_time)

        gender = await get_user_gender(user_id)
        gender_admin = await get_user_gender(admin.id)

        # Определяем тип выхода
        if new_status == ChatMemberStatus.KICKED:
            member_status = "KICKED"
            if admin and admin.id != user_id:
                admin_link = await user_link_global(admin.id)
                action_text = f"<b>⛔ {user_link} {g('был', gender)} удал{g('ён', gender)} из чата.</b>\n👮🏻 Удал{g('ил', gender_admin)}: {admin_link}"
            else:
                action_text = f"⛔ {user_link} был удал{g('ён', gender)} из чата."

        else:  # LEFT
            member_status = "LEAVE"
            if admin and admin.id == user_id:
                action_text = f"🚪 {user_link} покин{g('ул', gender)} чат."
            else:
                admin_link = await user_link_global(admin.id) if admin else "Система"
                action_text = f"<b>⛔ {user_link} был удал{g('ён', gender)} из чата.</b>\n👮🏻 Удал{g('ил', gender_admin)}: {admin_link}"

        # Обновляем статус в базе данных
        await update_full_users_chats_status(chat_id, user_id, member_status)

        # Отправляем уведомление
        leave_notify = await check_status_v(chat_id)
        if leave_notify == str("yes"):
            await bot.send_message(
                chat_id=chat_id,
                text=action_text,
                disable_web_page_preview=True,
                parse_mode='HTML'
            )


    except Exception as e:
        logger.error(e, exc_info=True)
        import traceback
        traceback.print_exc()