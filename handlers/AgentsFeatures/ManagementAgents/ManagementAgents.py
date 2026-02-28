import logging

from aiogram import *
from aiogram.types import *
from datetime import datetime
from pytz import timezone
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.AgentsFeatures.ManagementAgents.ManagementAgentsDB import (
    add_agents,
    edit_status,
    check_agents,
    user_for_status,
    agent_history_db,
    check_agent_history_db,
    check_agent_appointed,
    add_acting_agent,
    delete_acting_agent,
    search_acting_agents
)
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)

aa = Router()  # appoint + agents = aa

time_zona = timezone('Europe/Moscow')
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')


@aa.message(F.text.regexp(r'^[+]агент\s+\d+'))
async def appoint_agents(msg: Message):
    user_id = msg.from_user.id

    if user_id not in boss_agent:
        return

    try:
        args = msg.text.split(maxsplit=2)
        if len(args) < 2:
            await msg.reply('❌ Пропишите команду правильно!\n+агент {ранг} [@/ID/ссылка] или ответьте на сообщение')
            return

        status = int(args[1])
        mention = args[2] if len(args) > 2 else None

        if status not in [1, 2, 3, 4]:
            await msg.reply('🔢 Введите ранг ОТ 1 ДО 4, пожалуйста.')
            return

        # Если есть упоминание - используем его, иначе проверяем реплай
        if mention:
            agent_id = await resolve_id(msg, mention)
        elif msg.reply_to_message:
            agent_id = msg.reply_to_message.from_user.id
        else:
            await msg.reply('❌ Укажите пользователя или ответьте на сообщение!\nФормат: +агент {ранг} [@/ID/ссылка]')
            return

        agent_link = await user_link_global(agent_id)

        old_status = await user_for_status(agent_id)
        new_status = status
        remove_agent_id = agent_id
        agent_appointed_id = msg.from_user.id
        date_appointed = time

        check = await user_for_status(agent_id)

        check_agent = await check_agents(agent_id)

        if status == check:
            await msg.answer(f'{agent_link} уже на этом ранге.', parse_mode='HTML', disable_web_page_preview=True)
            return
        else:
            if check_agent:
                await edit_status(agent_id, status)
                await add_acting_agent(agent_id, status)
            else:
                await add_agents(agent_id, agent_appointed_id, date_appointed)
                await add_acting_agent(agent_id, status)

        gender = await get_user_gender(user_id)

        if check < status:
            user_status = f'был повыш{g("ен", gender)} с {check} до {status} ранга.'
            emodji = '🆙'
        if check > status:
            user_status = f'был пониж{g("ен", gender)} с {check} до {status} ранга.'
            emodji = '✅'

        if check < status:
            user_status1 = f'Вы были повышены с {check} до {status} ранга.'
            emodji1 = '🥳'
        if check > status:
            user_status1 = f'Вы были понижены с {check} до {status} ранга.'
            emodji1 = '☹️'

        await agent_history_db(remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status)
        await msg.reply(f'{emodji} <b>{agent_link}</b> {user_status}', parse_mode='HTML', disable_web_page_preview=True)

        if check_agent:
            await bot.send_message(chat_id=agent_id,
                                   text=f'{emodji1} <b>{agent_link}</b>, {user_status1}', parse_mode='HTML',
                                   disable_web_page_preview=True)
        else:
            await bot.send_message(chat_id=agent_id,
                                   text=f'🎉 <b>Поздравляем, Вы стали агентом бота!</b>\nВаш ранг в боте на данный момент {status}\n\n🫶🏻 Пользуйтесь своими полномочиями на благо пользователям!',
                                   parse_mode='HTML', disable_web_page_preview=True)


    except IndexError:
        await msg.reply('❌ Введите команду так: +агент {ранг} [@/ID/ссылка] или ответьте на сообщение')
    except ValueError as e:
        await msg.reply('❌ Проверьте данные которые вы ввели.')
        logger.error(e, exc_info=True)


@aa.message(F.text.regexp(r'^[-]агент\s+'))
async def remove_agent(msg: Message):
    user_id = msg.from_user.id

    # Проверка на главных агентов
    if user_id not in boss_agent:
        return

    try:
        args = msg.text.split(maxsplit=1)

        # Получаем упоминание (если есть)
        mention = args[1] if len(args) > 1 else None

        # Определяем ID пользователя
        if mention:
            remove_agent_id = await resolve_id(msg, mention)
        elif msg.reply_to_message:
            remove_agent_id = msg.reply_to_message.from_user.id
        else:
            await msg.reply('❌ Укажите пользователя или ответьте на сообщение!\nФормат: -агент [@/ID/ссылка]')
            return

        check = await user_for_status(remove_agent_id)
        if 0 < check:
            remove_agent_link = await user_link_global(remove_agent_id)

            # Оставшаяся работа с бд
            old_status = await user_for_status(remove_agent_id)
            new_status = 0
            agent_appointed_id = msg.from_user.id
            date_appointed = time

            await delete_acting_agent(remove_agent_id)
            await agent_history_db(remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status)
            await msg.reply(f'❌ Пользователь {remove_agent_link} был снят со статуса агента.', parse_mode='HTML',
                            disable_web_page_preview=True)
            await bot.send_message(chat_id=remove_agent_id,
                                   text='⚠️ <b>Вы были сняты со статуса агента.</b>\nБольше вы не сможете пользоваться командами агентов и будете считаться за обычного пользователя.',
                                   parse_mode='HTML')
        else:
            await msg.reply('❌ Пользователь не является агентом.')

    except Exception as e:
        logger.error(f"Error in remove_agent: {e}", exc_info=True)
        await msg.reply('❌ Произошла ошибка при выполнении команды.')


@aa.message(F.text.regexp(r'^[!/.]агент история'))
async def history_agent(msg: Message):
    user_id = msg.from_user.id

    if user_id not in boss_agent:
        return

    try:
        args = msg.text.split(maxsplit=1)
        mention = args[1] if len(args) > 1 else None

        # Определяем ID пользователя
        if mention:
            remove_agent_id = await resolve_id(msg, mention)
        elif msg.reply_to_message:
            remove_agent_id = msg.reply_to_message.from_user.id
        else:
            await msg.reply('❌ Укажите пользователя или ответьте на сообщение!\nФормат: !агент история [@/ID/ссылка]')
            return

        remove_agent_link = await user_link_global(remove_agent_id)
        history = await check_agent_history_db(remove_agent_id)  # Ищем историю пользователя в бд

        if not history:
            await msg.reply(f'📃 {remove_agent_link} никогда не был агентом.', parse_mode='HTML')
            return

        i = 0
        user_history = f'📃 История агента {remove_agent_link}:\n'
        for AH in history:  # AH - история агента
            remove_agent_id, agent_appointed_id, date_appointed, old_status, new_status = AH

            boss_user_link = await user_link_global(agent_appointed_id)

            gender = await get_user_gender(agent_appointed_id)

            if old_status < new_status:
                users = f'Повыс{g("ил", gender)}'
            elif old_status > new_status:
                users = f'Пониз{g("ил", gender)}'
            else:
                continue

            i += 1
            user_history += (
                f'{i}. <b>👤 {users}: {boss_user_link}, с {old_status} до {new_status}</b>\n'
                f'📅 Когда: {date_appointed}\n\n'
            )

        await msg.reply(user_history, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in history_agent: {e}", exc_info=True)
        await msg.reply('❌ Произошла ошибка при получении истории.')


@aa.message(F.text.regexp(r'^[!/.]агент инфо'))
async def check_agent(msg: Message):
    user_id = msg.from_user.id
    agents_check = await search_acting_agents(user_id)
    acting_agent_id = agents_check if agents_check else None

    # Более безопасная проверка
    if user_id not in boss_agent and not acting_agent_id:
        return

    try:
        args = msg.text.split(maxsplit=1)
        mention = args[1] if len(args) > 1 else None

        # Определяем ID пользователя
        if mention:
            agent_id = await resolve_id(msg, mention)
        elif msg.reply_to_message:
            agent_id = msg.reply_to_message.from_user.id
        else:
            await msg.reply('❌ Укажите пользователя или ответьте на сообщение!\nФормат: !агент инфо [@/ID/ссылка]')
            return

        agent_link = await user_link_global(agent_id)
        agent_info = await check_agent_appointed(agent_id)

        if not agent_info:
            await msg.reply(f'❌ {agent_link} никогда не был агентом', parse_mode='HTML')
            return

        for AI in agent_info:  # AI - agent info
            agent_id, agent_appointed_id, date_appointed = AI

        user_agent_link = await user_link_global(agent_appointed_id)

        text = (f'👤<b>Пользователь:</b> {agent_link}\n'
                f'👮🏻‍♂️ <b>Назначил(-а):</b> {user_agent_link}\n'
                f'📅 <b>Дата:</b> {date_appointed}')

        await msg.reply(text, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in check_agent: {e}", exc_info=True)
        await msg.reply('❌ Произошла ошибка при получении информации.')