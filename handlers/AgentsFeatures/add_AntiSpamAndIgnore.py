import logging

from aiogram import *
from aiogram.types import *
from aiogram.filters import *
from datetime import datetime
from pytz import timezone
from sqlalchemy.sql.functions import current_time


from handlers.AgentsFeatures.AntiSpam.AntiSpam import add_anti_spam, remove_anti_spam
from handlers.AgentsFeatures.AntiSpam.AntiSpamDB import check_anti_spam, add_to_anti_spam, get_anti_spam_info, \
    remove_from_anti_spam
from handlers.AgentsFeatures.ignoreUsers.ignore_managerDB import check_ignore, \
    add_to_ignore, get_ignore_info, remove_from_ignore
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

as_ignore_router = Router()  # anti-spam router

time_zona = timezone('Europe/Moscow')
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')

logger = logging.getLogger(__name__)

# Словарь для хранения состояний пагинации
user_pagination_states = {}


@as_ignore_router.message(Command(commands=['ас'], prefix='+'))
async def add_anti_spam_from_ignore_cmd(msg: Message):
    """Команда +ас игнор - добавляет пользователя одновременно в АС и в игнор"""
    user_id = msg.from_user.id
    if not await check_user_access(msg.from_user.id, 1):
        return

    # Проверяем, содержит ли команду "игнор"
    if 'игнор' not in msg.text.lower():
        # Если нет, используем стандартную функцию добавления в АС
        await add_anti_spam(msg)
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        # Получаем причину из текста сообщения
        try:
            # Убираем "игнор" из текста и берем оставшуюся часть как причину
            reason_text = msg.text.lower().replace('игнор', '').strip()
            reason = reason_text.split(maxsplit=1)[1] if len(
                reason_text.split(maxsplit=1)) > 1 else "Причина не указана"
        except IndexError:
            reason = "Причина не указана"

        # Проверяем, не в АС ли уже пользователь
        if await check_anti_spam(target_user_id):
            await msg.reply(f'❌ {target_user_link} уже находится в АС.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        # Проверяем, не в игноре ли уже пользователь
        if await check_ignore(target_user_id):
            await msg.reply(f'❌ {target_user_link} уже находится в игноре.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        try:
            # Добавляем в АС
            await add_to_anti_spam(target_user_id, user_id, time, reason)

            # Добавляем в игнор
            await add_to_ignore(target_user_id, user_id, time, reason)

            gender = await get_user_gender(user_id)

            await msg.reply(
                f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} одновременно в АС и в игнор.\n📝 Причина: {reason}',
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при добавлении в АС и игнор.')
            logger.error(e, exc_info=True)

    else:
        try:
            args = msg.text.split(maxsplit=3)
            if len(args) < 4:
                await msg.reply('❌ Пропишите команду правильно!\n+ас игнор @\nпричина')
                return

            # Проверяем, что второй аргумент - "игнор"
            if args[1].lower() != 'игнор':
                await add_anti_spam(msg)
                return

            mention = args[2]
            reason = msg.html_text.split("\n", 1)[1] if "\n" in msg.html_text else "Причина не указана"

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Проверяем, не в АС ли уже пользователь
            if await check_anti_spam(target_user_id):
                await msg.reply(f'❌ {target_user_link} уже находится в АС.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            # Проверяем, не в игноре ли уже пользователь
            if await check_ignore(target_user_id):
                await msg.reply(f'❌ {target_user_link} уже находится в игноре.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            try:
                # Добавляем в АС
                await add_to_anti_spam(target_user_id, user_id, time, reason)

                # Добавляем в игнор
                await add_to_ignore(target_user_id, user_id, time, reason)

                gender = await get_user_gender(user_id)

                await msg.reply(
                    f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} одновременно в АС и в игнор.\n📝 Причина: {reason}',
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

            except Exception as e:
                await msg.reply('❌ Произошла ошибка при добавлении в АС и игнор.')
                logger.error(e, exc_info=True)

        except IndexError:
            await msg.reply('❌ Введите команду так: +ас игнор @ причина')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при добавлении в АС и игнор.')
            logger.error(e, exc_info=True)



@as_ignore_router.message(Command(commands=['ас'], prefix='-'))
async def remove_anti_spam_and_ignore_cmd(msg: Message):
    """Команда -ас игнор - удаляет пользователя одновременно из АС и из игнора"""
    user_id = msg.from_user.id

    if not await check_user_access(msg.from_user.id, 1):
        return

    # Проверяем, содержит ли команду "игнор"
    if 'игнор' not in msg.text.lower():
        # Если нет, используем стандартную функцию удаления из АС
        await remove_anti_spam(msg)
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        # Получаем информацию о пользователе
        as_info = await get_anti_spam_info(target_user_id)
        ignore_info = await get_ignore_info(target_user_id)

        # Проверяем, находится ли пользователь хотя бы в одной из систем
        is_in_as = as_info is not None
        is_in_ignore = ignore_info is not None

        if not is_in_as and not is_in_ignore:
            await msg.reply(f'❌ {target_user_link} не находится ни в АС, ни в игноре.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        try:
            # Получаем причины для записи в историю
            as_reason = as_info['reason'] if as_info else "Причина не указана"
            ignore_reason = ignore_info['reason'] if ignore_info else "Причина не указана"

            # Удаляем из АС (если был в АС)
            if is_in_as:
                await remove_from_anti_spam(target_user_id, user_id, current_time, as_reason)

            # Удаляем из игнора (если был в игноре)
            if is_in_ignore:
                await remove_from_ignore(target_user_id, user_id, current_time, ignore_reason)

            gender = await get_user_gender(user_id)

            # Формируем ответ в зависимости от того, откуда был удален
            if is_in_as and is_in_ignore:
                response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} одновременно из АС и из игнора.'
            elif is_in_as:
                response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из АС (не был в игноре).'
            else:
                response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из игнора (не был в АС).'

            await msg.reply(
                response,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при удалении из АС и игнора.')
            logger.error(e, exc_info=True)

    else:
        try:
            args = msg.text.split(maxsplit=3)
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n-ас игнор @')
                return

            # Проверяем, что второй аргумент - "игнор"
            if args[1].lower() != 'игнор':
                await remove_anti_spam(msg)
                return

            mention = args[2]
            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Получаем информацию о пользователе
            as_info = await get_anti_spam_info(target_user_id)
            ignore_info = await get_ignore_info(target_user_id)

            # Проверяем, находится ли пользователь хотя бы в одной из систем
            is_in_as = as_info is not None
            is_in_ignore = ignore_info is not None

            if not is_in_as and not is_in_ignore:
                await msg.reply(f'❌ {target_user_link} не находится ни в АС, ни в игноре.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            try:
                # Получаем причины для записи в историю
                as_reason = as_info['reason'] if as_info else "Причина не указана"
                ignore_reason = ignore_info['reason'] if ignore_info else "Причина не указана"

                # Удаляем из АС (если был в АС)
                if is_in_as:
                    await remove_from_anti_spam(target_user_id, user_id, current_time, as_reason)

                # Удаляем из игнора (если был в игноре)
                if is_in_ignore:
                    await remove_from_ignore(target_user_id, user_id, current_time, ignore_reason)

                gender = await get_user_gender(user_id)

                # Формируем ответ в зависимости от того, откуда был удален
                if is_in_as and is_in_ignore:
                    response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} одновременно из АС и из игнора.'
                elif is_in_as:
                    response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из АС (не был в игноре).'
                else:
                    response = f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из игнора (не был в АС).'

                await msg.reply(
                    response,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

            except Exception as e:
                await msg.reply('❌ Произошла ошибка при удалении из АС и игнора.')
                logger.error(e, exc_info=True)

        except IndexError:
            await msg.reply('❌ Введите команду так: -ас игнор @')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при удалении из АС и игнора.')
            logger.error(e, exc_info=True)