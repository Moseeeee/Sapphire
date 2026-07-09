from datetime import datetime, timedelta

import pytz
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import get_user_activity
from BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
import logging

help_user = Router()
logger = logging.getLogger(__name__)

@help_user.message(Command("help"))
@help_user.message(F.text.lower().startswith((
        "помощь", ".помощь",
        "!помощь", "/помощь"
)))
async def help_command(message: Message):
    """Обработчик команды /help — копия обычного /start без административного функционала"""
    try:
        if message.chat.type != 'private':
            if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 97):
                return

        moscow_tz = pytz.timezone('Europe/Moscow')
        now_msk = datetime.now(moscow_tz)
        time = now_msk.hour
        day = now_msk.day
        mon = now_msk.month

        # Новогодняя ночь: 31 декабря, с 18:00 до 23:59
        if mon == 12 and day == 31 and 18 <= time < 24:
            time1 = '🎄 Новогодняя ночь прекрасна!'
        # Новый год: 1 января, до обеда
        elif mon == 1 and day == 1 and 0 <= time < 14:
            time1 = '🎆 С Новым Годом!'
        elif 6 <= time < 12:
            time1 = '<tg-emoji emoji-id="5866054599026152490">🌄</tg-emoji> Доброе утро,'
        elif 12 <= time < 18:
            time1 = '<tg-emoji emoji-id="5402477260982731644">🌄</tg-emoji> Доброго времени суток,'
        elif 18 <= time < 21:
            time1 = '<tg-emoji emoji-id="5924646916540337386">🌇</tg-emoji> Добрый вечер,'
        else:
            time1 = '<tg-emoji emoji-id="5451942498115020652">🌃</tg-emoji> Доброй ночи,'

        user = message.from_user
        if not user:
            return

        user_id = user.id
        user_link = await user_link_global(user_id)

        # =========================================================
        # ГЕНЕРАТОР СПИСКОВ ОНЛАЙН / ОФФЛАЙН АГЕНТОВ
        # =========================================================
        online_agents_list = []
        offline_agents_list = []

        try:
            pool = get_db_pool()
            async with pool.acquire() as conn:
                agent_rows = await conn.fetch('SELECT acting_agent_id FROM acting_agents WHERE online = TRUE')

            for row in agent_rows:
                ag_id = row['acting_agent_id']

                # 1. Формируем красивую ссылку
                try:
                    ag_link = await user_link_global(ag_id)
                    display_str = f"{ag_link}"
                except Exception:
                    display_str = f"агент не найден."

                # 2. Проверяем активность через горячий кэш RAM / БД
                last_act = await get_user_activity(ag_id)

                # Если проявлял активность в последние 15 минут — считаем, что онлайн
                if last_act and (now_msk - last_act) <= timedelta(minutes=15):
                    online_agents_list.append(display_str)
                else:
                    offline_agents_list.append(display_str)

        except Exception as e:
            logger.error(f"Ошибка проверки онлайна агентов в /help: {e}", exc_info=True)

        online_agents = "\n".join(online_agents_list) if online_agents_list else "\n"
        offline_agents = "\n".join(offline_agents_list) if offline_agents_list else ""
        # =========================================================

        await message.answer(
            f"""<b>{time1} {user_link}!</b>
Я Сапфир — помощник для ваших чатов.

<b>Агенты технической поддержки</b>
☀️ Готовы помочь прямо сейчас:
{online_agents}
🌑 Сейчас не в сети (ответят позже):
{offline_agents}

<tg-emoji emoji-id="5282843764451195532">📋</tg-emoji> <a href='https://teletype.in/@sap_sp/commands'>Список команд «Sapphire | Chat Mavay»</a>
<tg-emoji emoji-id="5197670259414277578">📝</tg-emoji> <a href='https://teletype.in/@sap_sp/terms-of-use'>Пользовательское соглашение</a>
<tg-emoji emoji-id="5424818078833715060">📣</tg-emoji> <a href='https://t.me/sapphire_sp'>Официальный канал</a> 
<tg-emoji emoji-id="5471930335312747865">💬</tg-emoji> <a href='https://t.me/sap_sp_chat'>Наш чат поддержки и простого общения</a>
""",
            parse_mode='HTML',
            disable_web_page_preview=True
        )


    except Exception as e:
        logger.error(f"Ошибка в help_command: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")