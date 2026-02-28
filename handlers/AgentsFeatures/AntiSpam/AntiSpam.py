# handlers/BotAutomaticWork/AgentsFeatures/AntiSpam/anti_spam_handlers.py
import logging

from aiogram import *
from aiogram.types import *
from aiogram.filters import *
from datetime import datetime
from pytz import timezone


from handlers.AgentsFeatures.AntiSpam.AntiSpamDB import check_anti_spam, add_to_anti_spam, remove_from_anti_spam, \
    get_anti_spam_history, get_anti_spam_info, get_all_anti_spam_users

from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender


as_router = Router()  # anti-spam router

time_zona = timezone('Europe/Moscow')
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')

logger = logging.getLogger(__name__)

# Словарь для хранения состояний пагинации
user_pagination_states = {}



@as_router.message(Command(commands=['ас'], prefix='+'))
async def add_anti_spam(msg: Message):
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

        # Проверяем, не в АС ли уже пользователь
        if await check_anti_spam(target_user_id):
            await msg.reply(f'❌ {target_user_link} уже находится в АС.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        # Добавляем в АС
        await add_to_anti_spam(target_user_id, user_id, time, reason)

        gender = await get_user_gender(user_id)

        await msg.reply(
            f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} в АС.\n📝 Причина: {reason}',
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        try:
            args = msg.text.split(maxsplit=2)
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n+ас @\nпричина')
                return

            mention = args[1]
            reason = msg.html_text.split("\n", 1)[1]

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Проверяем, не в АС ли уже пользователь
            if await check_anti_spam(target_user_id):
                await msg.reply(f'❌ {target_user_link} уже находится в АС.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            # Добавляем в АС
            await add_to_anti_spam(target_user_id, user_id, time, reason)

            gender = await get_user_gender(user_id)

            await msg.reply(
                f'✅ <b>{target_user_link}</b> добавл{g("ен", gender)} в АС.\n📝 Причина: {reason}',
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except IndexError:
            await msg.reply('❌ Введите команду так: +ас @ причина')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при добавлении в АС.')
            logger.error(e, exc_info=True)



#@as_router.message(Command(commands=['ас'], prefix='-'))
async def remove_anti_spam(msg: Message):
    user_id = msg.from_user.id
    await check_user_access(user_id, 1)

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        # Проверяем, в АС ли пользователь
        if not await check_anti_spam(target_user_id):
            await msg.reply(f'❌ {target_user_link} не находится в АС.', parse_mode='HTML',
                            disable_web_page_preview=True)
            return

        # Получаем оригинальную причину из базы данных
        as_info = await get_anti_spam_info(target_user_id)
        original_reason = as_info['reason'] if as_info else "Причина не указана"

        # Удаляем из АС, передавая оригинальную причину
        await remove_from_anti_spam(target_user_id, user_id, time, original_reason)

        gender = await get_user_gender(user_id)

        await msg.reply(
            f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из АС.\n',
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    else:
        try:
            args = msg.text.split(maxsplit=2)
            if len(args) < 2:
                await msg.reply('❌ Пропишите команду правильно!\n-ас @')
                return

            mention = args[1]

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            # Проверяем, в АС ли пользователь
            if not await check_anti_spam(target_user_id):
                await msg.reply(f'❌ {target_user_link} не находится в АС.', parse_mode='HTML',
                                disable_web_page_preview=True)
                return

            # Получаем оригинальную причину из базы данных
            as_info = await get_anti_spam_info(target_user_id)
            original_reason = as_info['reason'] if as_info else "Причина не указана"

            # Удаляем из АС, передавая оригинальную причину
            await remove_from_anti_spam(target_user_id, user_id, time, original_reason)

            gender = await get_user_gender(user_id)

            await msg.reply(
                f'✅ <b>{target_user_link}</b> удал{g("ён", gender)} из АС.\n',
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        except IndexError:
            await msg.reply('❌ Введите команду так: -ас @')
        except Exception as e:
            await msg.reply('❌ Произошла ошибка при удалении из АС.')
            logger.error(e, exc_info=True)



@as_router.message(F.text.lower().startswith('!ас история'))
@as_router.message(F.text.lower().startswith('.ас история'))
@as_router.message(F.text.lower().startswith('/ас история'))
async def anti_spam_history(msg: Message, page: int = 1):
    user_id = msg.from_user.id
    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        history, total = await get_anti_spam_history(target_user_id, page)

        if not history:
            await msg.reply(f'📃 У {target_user_link} нет записей в истории АС.', parse_mode='HTML')
            return

        user_pagination_states[user_id] = {
            'command': 'as_history',
            'target_user_id': target_user_id,
            'page': page,
            'total_pages': (total + 9) // 10
        }

        i = (page - 1) * 10
        history_text = f'📃 История АС {target_user_link} (Страница {page}):\n\n'

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
                action_text = '🟡 В настоящее время в АС'

            history_text += (
                f'{i}. <b>Добавл{g("ен", gender)}:</b> {agent_added_link}\n'
                f'📅 Дата добавления: {date_added}\n'
                f'{action_text}\n\n'
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"as_history_{target_user_id}_{page - 1}"))

        if page < (total + 9) // 10:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"as_history_{target_user_id}_{page + 1}"))

        if row:
            keyboard.inline_keyboard.append(row)

        await msg.reply(history_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)
    else:
        try:
            args = msg.text.split(maxsplit=3)  # Увеличиваем maxsplit до 3
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n!ас история @ (страница - опционально)')
                return

            # Первые два аргумента - команда, третий - упоминание
            mention = args[2]

            # Парсим номер страницы, если он есть (четвертый аргумент)
            if len(args) > 3 and args[3].isdigit():
                page = int(args[3])

            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            history, total = await get_anti_spam_history(target_user_id, page)

            if not history:
                await msg.reply(f'📃 У {target_user_link} нет записей в истории АС.', parse_mode='HTML')
                return

            user_pagination_states[user_id] = {
                'command': 'as_history',
                'target_user_id': target_user_id,
                'page': page,
                'total_pages': (total + 9) // 10
            }

            i = (page - 1) * 10
            history_text = f'📃 История АС {target_user_link} (Страница {page}):\n\n'

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
                    action_text = '🟡 В настоящее время в АС'

                history_text += (
                    f'{i}. <b>Добавл{g("ен", gender)}:</b> {agent_added_link}\n'
                    f'📅 Дата добавления: {date_added}\n'
                    f'{action_text}\n\n'
                )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            row = []

            if page > 1:
                row.append(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"as_history_{target_user_id}_{page - 1}"))

            if page < (total + 9) // 10:
                row.append(
                    InlineKeyboardButton(text="Вперед ➡️", callback_data=f"as_history_{target_user_id}_{page + 1}"))

            if row:
                keyboard.inline_keyboard.append(row)

            await msg.reply(history_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при получении истории АС.')
            logger.error(e, exc_info=True)


@as_router.message(F.text.lower().startswith('!ас чек'))
@as_router.message(F.text.lower().startswith('.ас чек'))
@as_router.message(F.text.lower().startswith('/ас чек'))
async def check_anti_spam_user(msg: Message):
    user_id = msg.from_user.id

    if not await check_user_access(msg.from_user.id, 1):
        return

    if msg.reply_to_message:
        target_user_id = msg.reply_to_message.from_user.id
        target_user_link = await user_link_global(target_user_id)

        as_info = await get_anti_spam_info(target_user_id)

        if as_info:
            agent_link = await user_link_global(as_info['agent_id'])
            gender = await get_user_gender(user_id)

            response = (
                f'🔴 <b>{target_user_link} находится в АС</b>\n\n'
                f'👮🏻‍♂️ <b>Добав{g("ил", gender)}:</b> {agent_link}\n'
                f'📅 <b>Дата добавления:</b> {as_info["date_added"]}\n'
                f'📝 <b>Причина:</b> {as_info["reason"]}'
            )
        else:
            response = f'🟢 <b>{target_user_link} не находится в АС</b>'

        await msg.reply(response, parse_mode='HTML', disable_web_page_preview=True)
    else:
        try:
            args = msg.text.split(maxsplit=2)  # Уменьшаем maxsplit до 2
            if len(args) < 3:
                await msg.reply('❌ Пропишите команду правильно!\n!ас чек @')
                return

            # Первые два аргумента - команда, третий - упоминание
            mention = args[2]
            target_user_id = await resolve_id(msg, mention)
            target_user_link = await user_link_global(target_user_id)

            as_info = await get_anti_spam_info(target_user_id)

            if as_info:
                agent_link = await user_link_global(as_info['agent_id'])
                gender = await get_user_gender(user_id)

                response = (
                    f'🔴 <b>{target_user_link} находится в АС</b>\n\n'
                    f'👮🏻‍♂️ <b>Добав{g("ил", gender)}:</b> {agent_link}\n'
                    f'📅 <b>Дата добавления:</b> {as_info["date_added"]}\n'
                    f'📝 <b>Причина:</b> {as_info["reason"]}'
                )
            else:
                response = f'🟢 <b>{target_user_link} не находится в АС</b>'

            await msg.reply(response, parse_mode='HTML', disable_web_page_preview=True)

        except Exception as e:
            await msg.reply('❌ Произошла ошибка при проверке АС.')
            logging.error(e)


@as_router.message(F.text.lower().startswith('!ас список'))
@as_router.message(F.text.lower().startswith('.ас список'))
@as_router.message(F.text.lower().startswith('/ас список'))
async def anti_spam_list(msg: Message, page: int = 1):

    user_id = msg.from_user.id
    if not await check_user_access(msg.from_user.id, 1):
        return

    try:
        args = msg.text.split(maxsplit=2)  # Уменьшаем maxsplit до 2

        # Парсим номер страницы, если он есть (третий аргумент)
        if len(args) > 2 and args[2].isdigit():
            page = int(args[2])

        users, total = await get_all_anti_spam_users(page)

        if not users:
            await msg.reply('📃 Список АС пуст.')
            return

        user_pagination_states[user_id] = {
            'command': 'as_list',
            'page': page,
            'total_pages': (total + 9) // 10
        }

        list_text = f'📃 Список пользователей в АС (Страница {page}):\n\n'

        i = (page - 1) * 10
        for user_data in users:
            i += 1
            user_id, agent_id, date_added, reason = user_data

            user_link = await user_link_global(user_id)
            agent_link = await user_link_global(agent_id)

            gender = await get_user_gender(user_id)

            list_text += (
                f'{i}. {user_link}\n'
                f'   👮🏻‍♂️ Добав{g("ил", gender)}: {agent_link}\n'
                f'   📅 Дата: {date_added}\n'
                f'   📝 Причина: {reason}\n\n'
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"as_list_{page - 1}"))

        if page < (total + 9) // 10:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"as_list_{page + 1}"))

        if row:
            keyboard.inline_keyboard.append(row)

        await msg.reply(list_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)

    except Exception as e:
        await msg.reply('❌ Произошла ошибка при получении списка АС.')
        logger.error(e, exc_info=True)


# Обработчик callback для пагинации
@as_router.callback_query(lambda c: c.data.startswith(('as_history_', 'as_list_')))
@rate_limit_with_cleanup(limit=1)
async def handle_pagination(callback: CallbackQuery):
    user_id = callback.from_user.id

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    try:
        data_parts = callback.data.split('_')
        command_type = f"{data_parts[1]}_{data_parts[2]}"  # as_history или as_list

        if command_type == "as_history":
            target_user_id = int(data_parts[3])
            page = int(data_parts[4])

            # Создаем фиктивное сообщение для повторного использования функции
            class FakeMessage:
                def __init__(self, user_id, text):
                    self.from_user = type('obj', (object,), {'id': user_id})
                    self.text = text

            fake_msg = FakeMessage(user_id, f"!ас история {target_user_id} {page}")
            await anti_spam_history(fake_msg, page)

        elif command_type == "as_list":
            page = int(data_parts[3])

            class FakeMessage:
                def __init__(self, user_id, text):
                    self.from_user = type('obj', (object,), {'id': user_id})
                    self.text = text

            fake_msg = FakeMessage(user_id, f"!ас список {page}")
            await anti_spam_list(fake_msg, page)

        await callback.answer()

    except Exception as e:
        await callback.answer("Ошибка при переключении страницы.")
        logger.error(e, exc_info=True)