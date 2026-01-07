import asyncio
import logging
import os
import sys
import subprocess
import psutil
import platform
from datetime import datetime
import pytz

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import load_full_db_to_cache
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender

router = Router()
logger = logging.getLogger(__name__)

moscow_time = pytz.timezone('Europe/Moscow')
now = datetime.now(moscow_time)
time = now.hour
day = now.day
mon = now.month

# Новогодняя ночь: 31 декабря, с 18:00 до 23:59
if mon == 12 and day == 31 and 18 <= time < 24:
    time1 = '🎄 Новогодняя ночь прекрасна!'
# Новый год: 1 января, до обеда
elif mon == 1 and day == 1 and 0 <= time < 14:
    time1 = '🎆 С Новым Годом!'
elif 6 <= time < 12:
    time1 = '🌄 Доброе утро,'
elif 12 <= time < 18:
    time1 = '👋🏻 Доброго времени суток,'
elif 18 <= time < 21:
    time1 = '🌆 Добрый вечер,'
else:
    time1 = '🌃 Доброй ночи,'


# ============ КОМАНДЫ ============
@router.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    try:
        if message.chat.type == 'private':
            user_id = message.from_user.id
            user_link = await user_link_global(user_id)

            if user_id in boss_agent:
                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='🔄️ Перезагрузить бота', callback_data='restart_bot')],
                    [InlineKeyboardButton(text='🐝 Перезагрузить кеш', callback_data='reload_cache')],
                    [InlineKeyboardButton(text='⚙️ Управление системой', callback_data='system_menu')]
                ])

                await message.answer(
                    f"""<b>{time1} {user_link}!</b>
                    
<a href="https://t.me/+iwWRkgyHOwQ3ZjMy">Официальный канал</a> | <a href="https://teletype.in/@sap_sp/commands">Мой функционал</a>                    
<blockquote>⚠️ Бот только-только запустился, поэтому есть некоторые неточности.
Большая просьба сообщать о найденных ошибках в <a href="https://t.me/sap_sp_chat">Sapphire | Chat</a></blockquote>
""",
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=markup
                )
            else:
                await message.answer(
                    f"""<b>{time1} {user_link}!</b>
                    
<a href="https://t.me/+iwWRkgyHOwQ3ZjMy">Официальный канал</a> | <a href="https://teletype.in/@sap_sp/commands">Мой функционал</a>                    
<blockquote>⚠️ Бот только-только запустился, поэтому есть некоторые неточности.
Большая просьба сообщать о найденных ошибках в <a href="https://t.me/sap_sp_chat">Sapphire | Chat</a></blockquote>
""",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

    except Exception as e:
        logger.error(f"Ошибка в start_command: {e}", exc_info=True)


@router.message(Command("system"))
async def system_command(message: Message):
    """Команда /system - меню управления"""
    if message.from_user.id not in boss_agent:
        return

    await show_system_menu(message)


@router.message(Command("status"))
async def status_command(message: Message):
    """Команда /status - статус системы"""
    if message.from_user.id not in boss_agent:
        return

    await show_system_status(message)


@router.message(Command("restart"))
async def restart_command(message: Message):
    """Команда /restart - меню перезагрузки"""
    if message.from_user.id not in boss_agent:
        return

    await show_restart_menu(message)


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
    """Перезагрузка бота (старая кнопка)"""
    try:
        await call.answer("🔄 Перезагружаем...")
        subprocess.run(["sudo", "reboot"])

    except Exception as e:
        logger.error(f"Ошибка перезагрузки бота: {e}")
        await call.answer("❌ Ошибка перезагрузки", show_alert=True)


@router.callback_query(F.data == 'reload_cache')
async def reload_cache_handler(call: CallbackQuery):
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
    """Возврат к главному меню"""
    try:
        await call.answer()

        user_id = call.from_user.id
        user_link = await user_link_global(user_id)

        if user_id in boss_agent:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🔄️ Перезагрузить бота', callback_data='restart_bot')],
                [InlineKeyboardButton(text='🐝 Перезагрузить кеш', callback_data='reload_cache')],
                [InlineKeyboardButton(text='⚙️ Управление системой', callback_data='system_menu')]
            ])

            await call.message.edit_text(
                f"""<b>{time1} {user_link}</b>,
На данный момент я нахожусь в бета тесте.""",
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=markup
            )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка возврата: {e}")
            await call.answer("❌ Ошибка", show_alert=True)


# ============ ОБРАБОТКА ОШИБОК ============
#@router.callback_query()
async def unknown_callback(call: CallbackQuery):
    """Обработка неизвестных callback'ов"""
    await call.answer("⚠️ Эта функция временно недоступна", show_alert=True)