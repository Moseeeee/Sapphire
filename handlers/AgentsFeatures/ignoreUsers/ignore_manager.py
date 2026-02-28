# Добавляем эти функции в handlers/AntiSpam/anti_spam_handlers.py
import logging
from datetime import datetime

import pytz
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from handlers.AgentsFeatures.AntiSpam.AntiSpam import user_pagination_states
from handlers.AgentsFeatures.ignoreUsers.ignore_managerDB import check_ignore, add_to_ignore, get_ignore_info, \
    remove_from_ignore, get_ignore_history
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)

ignore_router = Router()

time_zona = pytz.timezone("Europe/Moscow")
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')


@ignore_router.message(Command(commands=['игнор'], prefix='+'))
async def add_ignore(msg: Message):
    user_id = msg.from_user.id
    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        # Получаем причину из текста сообщения (после команды)
        try:
            reason = msg.text.split(maxsplit=1)[1] if len(msg.text.split(maxsplit=1)) > 1 else "Причина не указана"
        except IndexError:
            reason = "Причина не указана"

        # Проверяем, не в игноре ли уже пользователь
        if await check_ignore(target_user_id):
            await msg.reply(f'❌ {target_user_link} уже находится в игноре.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        # Добавляем в игнор
        await add_to_ignore(target_user_id, user_id, time, reason)

        gender = await get_user_gender(user_id)

        await msg.reply(
            f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} в игнор.\n📝 Причина: {reason}',
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        try:
            args = msg.text.split(maxsplit=2)
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n+игнор @\nпричина')
                return

            mention = args[1]
            reason = msg.html_text.split("\n", 1)[1]

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Проверяем, не в игноре ли уже пользователь
            if await check_ignore(target_user_id):
                await msg.reply(f'❌ {target_user_link} уже находится в игноре.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            # Добавляем в игнор
            await add_to_ignore(target_user_id, user_id, time, reason)

            gender = await get_user_gender(user_id)

            await msg.reply(
                f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} в игнор.\n📝 Причина: {reason}',
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except IndexError:
            await msg.reply('❌ Введите команду так: +игнор @ причина')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при добавлении в игнор.')
            logger.error(e, exc_info=True)


@ignore_router.message(Command(commands=['игнор'], prefix='-'))
async def remove_ignore(msg: Message):
    user_id = msg.from_user.id

    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        # Проверяем, в игноре ли пользователь
        if not await check_ignore(target_user_id):
            await msg.reply(f'❌ {target_user_link} не находится в игноре.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        # Получаем оригинальную причину из базы данных
        ignore_info = await get_ignore_info(target_user_id)
        original_reason = ignore_info['reason'] if ignore_info else "Причина не указана"

        # Удаляем из игнора, передавая оригинальную причину
        await remove_from_ignore(target_user_id, user_id, time, original_reason)

        gender = await get_user_gender(user_id)

        await msg.reply(
            f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из игнора.\n',
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        try:
            args = msg.text.split(maxsplit=2)
            if len(args) < 2:
                await msg.reply('❌ Пропишите команду правильно!\n-игнор @')
                return

            mention = args[1]

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Проверяем, в игноре ли пользователь
            if not await check_ignore(target_user_id):
                await msg.reply(f'❌ {target_user_link} не находится в игноре.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            # Получаем оригинальную причину из базы данных
            ignore_info = await get_ignore_info(target_user_id)
            original_reason = ignore_info['reason'] if ignore_info else "Причина не указана"

            # Удаляем из игнора, передавая оригинальную причину
            await remove_from_ignore(target_user_id, user_id, time, original_reason)

            gender = await get_user_gender(user_id)

            await msg.reply(
                f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из игнора.\n',
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except IndexError:
            await msg.reply('❌ Введите команду так: -игнор @')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при удалении из игнора.')
            logger.error(e, exc_info=True)





@ignore_router.message(F.text.lower().startswith('!игнор чек'))
@ignore_router.message(F.text.lower().startswith('.игнор чек'))
@ignore_router.message(F.text.lower().startswith('/игнор чек'))
async def check_ignore_user(msg: Message):
    user_id = msg.from_user.id

    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        ignore_info = await get_ignore_info(target_user_id)

        if ignore_info:
            agent_link = await user_link_global(ignore_info['agent_id'])
            gender = await get_user_gender(user_id)

            response = (
                f'🔴 <b>{target_user_link} находится в игноре</b>\n\n'
                f'👮🏻‍♂️ <b>Добав{g("ил", gender)}:</b> {agent_link}\n'
                f'📅 <b>Дата добавления:</b> {ignore_info["date_added"]}\n'
                f'📝 <b>Причина:</b> {ignore_info["reason"]}'
            )
        else:
            response = f'🟢 <b>{target_user_link} не находится в игноре</b>'

        await msg.reply(response, parse_mode='HTML', disable_web_page_preview=True)
    else:
        try:
            args = msg.text.split(maxsplit=2)
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n!игнор чек @')
                return

            mention = args[2]
            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            ignore_info = await get_ignore_info(target_user_id)

            if ignore_info:
                agent_link = await user_link_global(ignore_info['agent_id'])
                gender = await get_user_gender(user_id)

                response = (
                    f'🔴 <b>{target_user_link} находится в игноре</b>\n\n'
                    f'👮🏻‍♂️ <b>Добав{g("ил", gender)}:</b> {agent_link}\n'
                    f'📅 <b>Дата добавления:</b> {ignore_info["date_added"]}\n'
                    f'📝 <b>Причина:</b> {ignore_info["reason"]}'
                )
            else:
                response = f'🟢 <b>{target_user_link} не находится в игноре</b>'

            await msg.reply(response, parse_mode='HTML', disable_web_page_preview=True)

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при проверке игнора.')
            logging.error(e)




@ignore_router.message(F.text.lower().startswith('!игнор история'))
@ignore_router.message(F.text.lower().startswith('.игнор история'))
@ignore_router.message(F.text.lower().startswith('/игнор история'))
async def ignore_history(msg: Message, page: int = 1):
    user_id = msg.from_user.id

    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        history, total = await get_ignore_history(target_user_id, page)

        if not history:
            await msg.reply(f'📃 У {target_user_link} нет записей в истории игнора.', parse_mode='HTML')
            return

        user_pagination_states[user_id] = {
            'command': 'ignore_history',
            'target_user_id': target_user_id,
            'page': page,
            'total_pages': (total + 9) // 10
        }

        i = (page - 1) * 10
        history_text = f'📃 История игнора {target_user_link} (Страница {page}):\n\n'

        for record in history:
            i += 1
            user_id, agent_id_added, agent_id_removed, date_added, date_removed, reason = record

            agent_added_link = await user_link_global(agent_id_added)

            gender = await get_user_gender(user_id)

            if agent_id_removed:
                agent_removed_link = await user_link_global(agent_id_removed)
                action_text = (
                    f'❌ Удал{g("ён", gender)} агентом: {agent_removed_link}\n'
                    f'📅 Дата удаления: {date_removed}\n'
                    f'📝 Причина удаления: {reason}'
                )
            else:
                action_text = '🟡 В настоящее время в игноре'

            history_text += (
                f'{i}. <b>Добавл{g("ен", gender)}:</b> {agent_added_link}\n'
                f'📅 Дата добавления: {date_added}\n'
                f'{action_text}\n\n'
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ignore_history_{target_user_id}_{page - 1}"))

        if page < (total + 9) // 10:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"ignore_history_{target_user_id}_{page + 1}"))

        if row:
            keyboard.inline_keyboard.append(row)

        await msg.reply(history_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)
    else:
        try:
            args = msg.text.split(maxsplit=3)  # Увеличиваем maxsplit до 3
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n!игнор история @ (страница - опционально)')
                return

            # Первые два аргумента - команда, третий - упоминание
            mention = args[2]

            # Парсим номер страницы, если он есть (четвертый аргумент)
            if len(args) > 3 and args[3].isdigit():
                page = int(args[3])

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            history, total = await get_ignore_history(target_user_id, page)

            if not history:
                await msg.reply(f'📃 У {target_user_link} нет записей в истории игнора.', parse_mode='HTML')
                return

            user_pagination_states[user_id] = {
                'command': 'ignore_history',
                'target_user_id': target_user_id,
                'page': page,
                'total_pages': (total + 9) // 10
            }

            i = (page - 1) * 10
            history_text = f'📃 История игнора {target_user_link} (Страница {page}):\n\n'

            for record in history:
                i += 1
                user_id, agent_id_added, agent_id_removed, date_added, date_removed, reason = record

                agent_added_link = await user_link_global(agent_id_added)

                gender = await get_user_gender(user_id)

                if agent_id_removed:
                    agent_removed_link = await user_link_global(agent_id_removed)
                    action_text = (
                        f'❌ Удал{g("ён", gender)} агентом: {agent_removed_link}\n'
                        f'📅 Дата удаления: {date_removed}\n'
                        f'📝 Причина удаления: {reason}'
                    )
                else:
                    action_text = '🟡 В настоящее время в игноре'

                history_text += (
                    f'{i}. <b>Добавл{g("ен", gender)}:</b> {agent_added_link}\n'
                    f'📅 Дата добавления: {date_added}\n'
                    f'{action_text}\n\n'
                )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            row = []

            if page > 1:
                row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ignore_history_{target_user_id}_{page - 1}"))

            if page < (total + 9) // 10:
                row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"ignore_history_{target_user_id}_{page + 1}"))

            if row:
                keyboard.inline_keyboard.append(row)

            await msg.reply(history_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при получении истории игнора.')
            logger.error(e, exc_info=True)