import asyncio
import logging
import os
import subprocess
import psutil
import platform
from datetime import datetime, timedelta
import pytz
from typing import List

from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BotCommand, \
    BotCommandScopeChat, Update
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from handlers.BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import get_user_activity
from handlers.AdminsTools.ChatSettings.captcha.captchaDB import is_captcha_enabled, get_user_last_successful_captcha, \
    get_captcha_settings
from handlers.BotAutomaticWork.Gonfig.config import boss_agent, sanor_ID
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import load_full_db_to_cache, get_db_pool
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
#from test import create_rps_chart

router = Router()
logger = logging.getLogger(__name__)




#@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Убедитесь, что ссылка сформирована верно согласно документации вашего Mini App
    link = "https://t.me/newbot/bot_for_testing_sapp_hire_bot/saaaaaaaaap_sp_testtt_bot?startapp=name_mya"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать управляемого бота", url=link)]
    ])
    await message.answer("Нажмите кнопку для создания бота:", reply_markup=kb)


# ИСПРАВЛЕННЫЙ ХЕНДЛЕР
# В aiogram 3.x мы ловим конкретный тип события.
# Если ваше окружение поддерживает F.managed_bot, то это обычно объект типа Message или ChatMemberUpdated.

#@router.message(F.managed_bot)
async def handle_managed_bot(message: types.Message):
    # Данные берем из объекта message, который прислал сервер
    mb = message.managed_bot

    token = mb.token
    user_id = mb.manager_user_id
    username = mb.username

    # Отправляем подтверждение
    await message.answer(
        text=(
            f"✅ Бот **@{username}** успешно создан!\n\n"
            f"Ваш токен: `{token}`\n"
            f"ID владельца: `{user_id}`"
        ),
        parse_mode="Markdown"
    )






# ============ ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ СТАТИСТИКИ ============
async def get_users_count() -> int:
    """Получить количество пользователей в базе"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM users')
            return count or 0
    except Exception as e:
        logger.error(f"Ошибка получения количества пользователей: {e}", exc_info=True)
        return 0


async def get_chats_count() -> int:
    """Получить количество чатов в базе"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM chats')
            return count or 0
    except Exception as e:
        logger.error(f"Ошибка получения количества чатов: {e}", exc_info=True)
        return 0


async def get_ignore_users_count() -> int:
    """Получить количество пользователей в игноре"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM ignore_users')
            return count or 0
    except Exception as e:
        logger.error(f"Ошибка получения количества игнорируемых пользователей: {e}", exc_info=True)
        return 0


async def get_anti_spam_users_count() -> int:
    """Получить количество пользователей в антиспаме"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM anti_spam_users')
            return count or 0
    except Exception as e:
        logger.error(f"Ошибка получения количества пользователей в антиспаме: {e}", exc_info=True)
        return 0


async def get_acting_agents() -> List[str]:
    """Получить список активных агентов"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем только ID активных агентов
            rows = await conn.fetch('SELECT acting_agent_id FROM acting_agents')

            agents = []
            for row in rows:
                agent_id = row['acting_agent_id']
                # Пытаемся получить ссылку на агента
                try:
                    agent_link = await user_link_global(agent_id)
                    agents.append(f'{agent_link} (<code>{agent_id}</code>)')
                except:
                    agents.append(f"ID: {agent_id}")

            return agents
    except Exception as e:
        logger.error(f"Ошибка получения активных агентов: {e}", exc_info=True)
        return []


async def get_system_stats() -> str:
    """Получить статистику системы"""
    try:
        # Получаем статистику параллельно для скорости
        users_count, chats_count, ignore_count, anti_spam_count, agents = await asyncio.gather(
            get_users_count(),
            get_chats_count(),
            get_ignore_users_count(),
            get_anti_spam_users_count(),
            get_acting_agents()
        )

        # Форматируем список агентов
        if agents:
            agents_list = "\n".join([f"• {agent}" for agent in agents])
            agents_text = f"<tg-emoji emoji-id='5201876149088558587'>👷</tg-emoji> <b>Активные агенты:</b>\n{agents_list}"
        else:
            agents_text = "<tg-emoji emoji-id='5201876149088558587'>👷</tg-emoji> <b>Активные агенты:</b> Нет активных агентов"

        stats_text = f"""
<blockquote><b><tg-emoji emoji-id='5231200819986047254'>📊</tg-emoji> СТАТИСТИКА СИСТЕМЫ:</b>

<tg-emoji emoji-id="5323381955008415410">👤</tg-emoji> <b>Юзеров в базе:</b> {users_count}
<tg-emoji emoji-id="5465300082628763143">💬</tg-emoji> <b>Чатов в базе:</b> {chats_count}
<tg-emoji emoji-id="5346131202774409949">😶</tg-emoji> <b>Юзеров в игноре:</b> {ignore_count}
<tg-emoji emoji-id="5260293700088511294">🛡️</tg-emoji> <b>Юзеров в антиспаме:</b> {anti_spam_count}

{agents_text}</blockquote>
"""
        return stats_text

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}", exc_info=True)
        return "<blockquote>❌ <b>Ошибка получения статистики</b></blockquote>"











# ============ КОМАНДЫ ============
@router.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start — поддерживает обычный запуск и капчу"""
    try:
        if message.chat.type != 'private':
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

        # === Обработка deep link для капчи ===
        if message.text and message.text.startswith("/start captcha_"):
            payload = message.text.split(" ", 1)[1]
            parts = payload.split("_")

            if len(parts) == 3 and parts[0] == "captcha":
                try:
                    chat_id = int(parts[1])
                    target_user_id = int(parts[2])
                except (ValueError, IndexError):
                    await message.answer("❌ Неверная ссылка для капчи.")
                    return

                if user_id != target_user_id:
                    await message.answer("❌ Эта капча предназначена другому пользователю.")
                    return

                if not await is_captcha_enabled(chat_id):
                    await message.answer("ℹ️ Капча в этом чате больше не требуется.")
                    return

                last_successful = await get_user_last_successful_captcha(chat_id, user_id)
                if last_successful:
                    difficulty_levels = {'легкая': 1, 'средняя': 2, 'тяжелая': 3, 'хардкорд': 4}
                    current_difficulty = (await get_captcha_settings(chat_id))[1]
                    current_level = difficulty_levels.get(current_difficulty, 1)
                    previous_level = difficulty_levels.get(last_successful[0], 1)
                    if current_level <= previous_level:
                        await message.answer("✅ Вы уже прошли капчу в этом чате!")
                        return

                time_limit_str, difficulty, attempts_limit, _ = await get_captcha_settings(chat_id)
                time_limit = parse_time_string(time_limit_str) or timedelta(minutes=5)

                from handlers.AdminsTools.ChatSettings.captcha.captcha_main import send_captcha_to_user
                await send_captcha_to_user(
                    bot=message.bot,
                    user_id=user_id,
                    chat_id=chat_id,
                    difficulty=difficulty,
                    attempts_limit=attempts_limit,
                    time_limit=time_limit
                )
                return

        # === Обычный запуск (/start без аргументов) ===

        if user_id == sanor_ID:
            stats_text = await get_system_stats()
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🔄️ Перезагрузить бота', callback_data='restart_bot')],
                [InlineKeyboardButton(text='🐝 Перезагрузить кеш', callback_data='reload_cache')],
                [InlineKeyboardButton(text='⚙️ Управление системой', callback_data='system_menu')]
            ])
            await message.answer(
                f"""<b>{time1} {user_link}!</b>
<a href="https://t.me/+iwWRkgyHOwQ3ZjMy">Официальный канал</a> | <a href="https://teletype.in/@sap_sp/commands">Мой функционал</a>
{stats_text}""",
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=markup
            )

            inline_commands = [
                BotCommand(command="start", description="🔄 Запустить или перезапустить бота"),
                BotCommand(command="commands", description="📖 Список команд бота"),
                BotCommand(command="bot_active_5_min", description="🚀 Актив бота за 5 минут"),
                BotCommand(command="ping", description="⏱️ Проверка отклика бота"),
                BotCommand(command="full_chats_ids", description="🔗 Все чаты во вселенной Sapphire"),
            ]
        else:
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
                logger.error(f"Ошибка проверки онлайна агентов в /start: {e}", exc_info=True)

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

            inline_commands = [
                BotCommand(command="start", description="🔄 Запустить или перезапустить бота"),
                BotCommand(command="commands", description="📖 Список команд бота"),
                BotCommand(command="my_bans", description="⛔️ Список ваших банов во вселенной сапфира"),
            ]

        chat_id = message.chat.id

        await bot.set_my_commands(
            commands=inline_commands,
            scope=BotCommandScopeChat(chat_id=chat_id)
        )

    except Exception as e:
        logger.error(f"Ошибка в start_command: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")








# ============ ФУНКЦИИ ПОКАЗА МЕНЮ ============
async def show_system_menu(message: Message):
    """Показать системное меню"""
    user_link = await user_link_global(message.from_user.id)

    keyboard = [
        [InlineKeyboardButton(text="📊 Статус системы", callback_data="system_status")],
        [InlineKeyboardButton(text="🔄 Перезапуск приложения", callback_data="restart_app_menu")],
        [InlineKeyboardButton(text="🚀 Перезагрузка сервера", callback_data="restart_server_menu")],
        [InlineKeyboardButton(text="🧹 Очистка кэша", callback_data="clear_cache_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    text = f"""
⚙️ <b>Панель управления системой</b>

👤 <b>Пользователь:</b> {user_link}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

Выберите раздел:
"""

    try:
        await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        logger.error(f"Ошибка отправки меню: {e}")
        await message.answer("❌ Ошибка отображения меню. Попробуйте еще раз.")


async def show_restart_menu(message: Message):
    """Показать меню перезагрузки"""
    user_link = await user_link_global(message.from_user.id)

    keyboard = [
        [InlineKeyboardButton(text="🔄 Перезапуск приложения", callback_data="restart_app_menu")],
        [InlineKeyboardButton(text="🚀 Перезагрузка сервера", callback_data="restart_server_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="system_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    text = f"""
🔄 <b>Меню перезагрузки</b>

👤 <b>Пользователь:</b> {user_link}

Выберите тип перезагрузки:
• Перезапуск приложения (только бот)
• Перезагрузка сервера (вся система)

<b>⚠️ Внимание:</b> Перезагрузка сервера требует прав sudo.
"""

    await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_system_status(message: Message):
    """Показать статус системы"""
    try:
        # Получаем информацию о системе
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Информация о процессе
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        uptime = datetime.now() - datetime.fromtimestamp(process.create_time())

        # Форматируем время работы
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_str = f"{days}д {hours}ч {minutes}м {seconds}с" if days > 0 else f"{hours}ч {minutes}м {seconds}с"

        # Собираем текст
        text = f"""
📊 <b>Статус системы</b>

<b>📈 Производительность:</b>
🖥 <b>CPU:</b> {cpu_percent:.1f}%
🧠 <b>RAM:</b> {memory.percent}% ({memory.used // (1024 * 1024)}/{memory.total // (1024 * 1024)} MB)
💾 <b>Память процесса:</b> {memory_usage:.1f} MB
💿 <b>Диск:</b> {disk.percent}%

<b>📊 Система:</b>
🆔 <b>PID:</b> {os.getpid()}
⏱ <b>Время работы:</b> {uptime_str}
🐧 <b>ОС:</b> {platform.system()} {platform.release()}
🐍 <b>Python:</b> {platform.python_version()}

<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>
"""

        keyboard = [
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="system_status")],
            [InlineKeyboardButton(text="⚙️ Меню", callback_data="system_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await message.answer(text, parse_mode='HTML', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        await message.answer("❌ Ошибка получения статуса системы.")


# ============ CALLBACK ОБРАБОТЧИКИ ============
@router.callback_query(F.data == 'system_menu')
async def system_menu_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Главное меню управления системой"""
    try:
        await call.answer()

        keyboard = [
            [InlineKeyboardButton(text="📊 Статус системы", callback_data="system_status")],
            [InlineKeyboardButton(text="🔄 Перезапуск приложения", callback_data="restart_app_menu")],
            [InlineKeyboardButton(text="🚀 Перезагрузка сервера", callback_data="restart_server_menu")],
            [InlineKeyboardButton(text="🧹 Очистка кэша", callback_data="clear_cache_menu")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await call.message.edit_text(
            "⚙️ <b>Панель управления системой</b>\n\n"
            "Выберите действие:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка редактирования: {e}")
            await call.answer("❌ Ошибка обновления меню", show_alert=True)


@router.callback_query(F.data == 'system_status')
async def system_status_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Показать статус системы"""
    try:
        await call.answer("🔄 Получаем данные...")

        # Получаем информацию о системе
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Информация о процессе
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        uptime = datetime.now() - datetime.fromtimestamp(process.create_time())

        # Форматируем время работы
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_str = f"{days}д {hours}ч {minutes}м {seconds}с" if days > 0 else f"{hours}ч {minutes}м {seconds}с"

        # Собираем текст
        text = f"""
📊 <b>Статус системы</b>

<b>📈 Производительность:</b>
🖥 <b>CPU:</b> {cpu_percent:.1f}%
🧠 <b>RAM:</b> {memory.percent}% ({memory.used // (1024 * 1024)}/{memory.total // (1024 * 1024)} MB)
💾 <b>Память процесса:</b> {memory_usage:.1f} MB
💿 <b>Диск:</b> {disk.percent}%

<b>📊 Система:</b>
🆔 <b>PID:</b> {os.getpid()}
⏱ <b>Время работы:</b> {uptime_str}
🐧 <b>ОС:</b> {platform.system()} {platform.release()}
🐍 <b>Python:</b> {platform.python_version()}

<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>
"""

        keyboard = [
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="system_status")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="system_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await call.message.edit_text(text, parse_mode='HTML', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        await call.answer("❌ Ошибка получения статуса", show_alert=True)


@router.callback_query(F.data == 'restart_app_menu')
async def restart_app_menu_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Меню перезапуска приложения"""
    try:
        await call.answer()

        keyboard = [
            [InlineKeyboardButton(text="✅ Подтвердить перезапуск", callback_data="confirm_restart_app")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="system_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await call.message.edit_text(
            "🔄 <b>Перезапуск приложения</b>\n\n"
            "<i>Это перезапустит только бота:</i>\n"
            "• Все процессы будут остановлены\n"
            "• Бот перезапустится автоматически\n"
            "• Сервер останется запущенным\n\n"
            "<b>⚠️ Вы уверены?</b>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка меню перезапуска: {e}")
        await call.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == 'confirm_restart_app')
async def confirm_restart_app_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Подтверждение перезапуска приложения"""
    try:
        user_link = await user_link_global(call.from_user.id)

        await call.message.edit_text(
            f"🔄 <b>{user_link}</b>, перезапуск приложения запущен...\n\n"
            f"Бот будет перезапущен через несколько секунд.",
            parse_mode='HTML'
        )

        await call.answer("🔄 Перезапуск...")

        # Используем существующую функцию перезагрузки
        subprocess.run(["sudo", "reboot"])

    except Exception as e:
        logger.error(f"Ошибка перезапуска приложения: {e}")
        await call.answer("❌ Ошибка перезапуска", show_alert=True)


@router.callback_query(F.data == 'restart_server_menu')
async def restart_server_menu_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Меню перезагрузки сервера"""
    try:
        await call.answer()

        keyboard = [
            [InlineKeyboardButton(text="⚠️ Подтвердить перезагрузку сервера", callback_data="confirm_restart_server")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="system_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await call.message.edit_text(
            "🚨 <b>Перезагрузка сервера</b>\n\n"
            "<i>Это перезагрузит всю систему:</i>\n"
            "• Все процессы будут остановлены\n"
            "• Сервер будет перезагружен\n"
            "• Все данные сохранятся\n\n"
            "<b>⚠️ Требуются права sudo!</b>\n"
            "<b>⚠️ Вы уверены?</b>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка меню перезагрузки сервера: {e}")
        await call.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == 'confirm_restart_server')
async def confirm_restart_server_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Подтверждение перезагрузки сервера"""
    try:
        user_link = await user_link_global(call.from_user.id)

        await call.message.edit_text(
            f"🚨 <b>{user_link}</b>, перезагрузка сервера запущена...\n\n"
            f"Сервер будет перезагружен через 5 секунд.\n"
            f"<i>Все процессы будут остановлены.</i>",
            parse_mode='HTML'
        )

        await call.answer("🚨 Перезагрузка сервера...")

        # Отложенная перезагрузка
        await asyncio.sleep(5)
        subprocess.run(["sudo", "reboot"])

    except Exception as e:
        logger.error(f"Ошибка перезагрузки сервера: {e}")
        await call.answer("❌ Ошибка перезагрузки", show_alert=True)


@router.callback_query(F.data == 'clear_cache_menu')
async def clear_cache_menu_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Меню очистки кэша"""
    try:
        await call.answer()

        keyboard = [
            [InlineKeyboardButton(text="🧹 Очистить все кэши", callback_data="clear_all_cache")],
            [InlineKeyboardButton(text="📊 Статистика кэша", callback_data="cache_stats")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="system_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await call.message.edit_text(
            "🧹 <b>Управление кэшем</b>\n\n"
            "<i>Выберите действие:</i>\n"
            "• Очистить все кэши\n"
            "• Посмотреть статистику\n\n"
            "<b>⚠️ Очистка кэша может временно увеличить нагрузку на БД.</b>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка меню кэша: {e}")
        await call.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == 'clear_all_cache')
async def clear_all_cache_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Очистка всех кэшей"""
    try:
        await call.answer("🧹 Очищаем кэш...")

        # Загружаем кэш заново (это очистит старый)
        await load_full_db_to_cache()

        await call.message.edit_text(
            "✅ <b>Кэш успешно очищен и перезагружен!</b>\n\n"
            "Все данные были загружены заново из базы данных.",
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {e}")
        await call.message.edit_text(
            "❌ <b>Ошибка очистки кэша!</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


# ============ СТАРЫЕ КНОПКИ ============
@router.callback_query(F.data == 'restart_bot')
async def restart_bot_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Перезагрузка бота (старая кнопка)"""
    try:
        await call.answer("🔄 Перезагружаем...")
        subprocess.run(["sudo", "reboot"])

    except Exception as e:
        logger.error(f"Ошибка перезагрузки бота: {e}")
        await call.answer("❌ Ошибка перезагрузки", show_alert=True)


@router.callback_query(F.data == 'reload_cache')
async def reload_cache_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Перезагрузка кэша (старая кнопка)"""
    try:
        await call.answer("🐝 Перезагружаем кэш...")
        await load_full_db_to_cache()
        await call.answer("✅ Кэш перезагружен!", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка перезагрузки кэша: {e}")
        await call.answer("❌ Ошибка перезагрузки кэша", show_alert=True)


@router.callback_query(F.data == 'back_to_main')
async def back_to_main_handler(call: CallbackQuery):

    if call.from_user.id != sanor_ID:
        return

    """Возврат к главному меню"""
    try:
        await call.answer()

        user_id = call.from_user.id
        user_link = await user_link_global(user_id)

        if call.from_user.id == sanor_ID:
            # Получаем статистику для администраторов
            stats_text = await get_system_stats()

            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🔄️ Перезагрузить бота', callback_data='restart_bot')],
                [InlineKeyboardButton(text='🐝 Перезагрузить кеш', callback_data='reload_cache')],
                [InlineKeyboardButton(text='⚙️ Управление системой', callback_data='system_menu')]
            ])

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

            await call.message.edit_text(
                f"""<b>{time1} {user_link}</b>

{stats_text}

<i>На данный момент я нахожусь в бета тесте.</i>""",
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=markup
            )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка возврата: {e}")
            await call.answer("❌ Ошибка", show_alert=True)


# ============ ОБРАБОТКА ОШИБОК ============
# @router.callback_query()
async def unknown_callback(call: CallbackQuery):
    """Обработка неизвестных callback'ов"""
    await call.answer("⚠️ Эта функция временно недоступна", show_alert=True)


# ============ КОМАНДА ДЛЯ СТАТИСТИКИ ============
@router.message(Command("stats"))
async def stats_command(message: Message):
    """Показать статистику системы (только для администраторов)"""
    try:
        if message.from_user.id in sanor_ID:
            stats_text = await get_system_stats()
            await message.answer(stats_text, parse_mode='HTML')
        else:
            await message.answer("❌ Эта команда доступна только администраторам.")
    except Exception as e:
        logger.error(f"Ошибка в stats_command: {e}", exc_info=True)