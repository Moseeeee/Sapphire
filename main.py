

import asyncio
import importlib
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import cleanup_expired_pins
from handlers.AgentsFeatures.server_info import start_background_ping_monitor, stop_background_ping_monitor
from handlers.BotAutomaticWork.ActiveBotMiddleware import ActiveBotMiddleware
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_system.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


async def reload_all_handlers():
    """Перезагрузить все хендлеры"""
    modules_to_reload = [
        # Основные
        'handlers.start',

        # AgentsFeatures
        'handlers.AgentsFeatures.AgentCheckPing',
        'handlers.AgentsFeatures.ManagementAgents.ManagementAgents',
        'handlers.AgentsFeatures.server_info',
        'handlers.AgentsFeatures.AntiSpam.AntiSpam',
        'handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovals',
        'handlers.AgentsFeatures.ManagementAgents.AgentChatsAndChannelsdminsManagement',
        'handlers.AgentsFeatures.add_AntiSpamAndIgnore',
        'handlers.AgentsFeatures.ignoreUsers.ignore_manager',

        # AdminsTools
        'handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettings',
        'handlers.AdminsTools.ChatSettings.ChatAdmins.add_tg_admin',
        'handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCommand',
        'handlers.AdminsTools.ChatSettings.delete_message_chat',
        'handlers.AdminsTools.ChatSettings.message_pinned.pin_sms',
        'handlers.AdminsTools.ChatSettings.notes.notes',
        'handlers.AdminsTools.ChatSettings.reports.report_statistics.report_statistics',
        'handlers.AdminsTools.check_views_chats_message',
        'handlers.AdminsTools.ChatSettings.DkCommands.CheckDkInfo',
        'handlers.AdminsTools.CommandsModerations.bans.ban',
        'handlers.AdminsTools.ChatSettings.captcha.captcha_main',
        'handlers.AdminsTools.ChatSettings.Stats.ChatsUsersStats.chat_users_stats',
        'handlers.AdminsTools.CommandsModerations.mute.mute',
        'handlers.AdminsTools.ChatSettings.PuchCommandSettings.puch_command_settings',
        'handlers.AdminsTools.CommandsModerations.warns.warns',
        'handlers.AdminsTools.ChatSettings.welcome.welcome',
        'handlers.AdminsTools.ChatSettings.rules.rules',
        'handlers.AdminsTools.ChatSettings.reports.reports',
        'handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEdits',
        'handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins',
        'handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettings',

        # UserCommands
        'handlers.UserCommands.GenderSettings.GenderSettings',
        'handlers.UserCommands.user_profile',
        'from handlers.UserCommands.weather'

        # Другие
        'handlers.testDirectiry.chat_settings',
        'handlers.testDirectiry.UpdateChatInfo',
        'handlers.BotAutomaticWork.AddChatsBot.AddChatsBot',
        'handlers.testing',
        'handlers.AgentsFeatures.payment.payment',
        'handlers.testDirectiry.ChatSettingsAutomatic.ChatSettings'
        'from handlers.testDirectiry.testing'
    ]

    for module_name in modules_to_reload:
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            logger.debug(f"✅ Перезагружен: {module_name}")
        except Exception as e:
            logger.debug(f"⚠️ Не удалось перезагрузить {module_name}: {e}")


async def load_all_routers():
    """Загрузить все роутеры после перезагрузки"""
    # Основные
    from handlers.start import router as start_router

    # AgentsFeatures
    from handlers.AgentsFeatures.AgentCheckPing import pingin
    from handlers.AgentsFeatures.ManagementAgents.ManagementAgents import aa
    from handlers.AgentsFeatures.server_info import server_stats_router
    from handlers.AgentsFeatures.AntiSpam.AntiSpam import as_router
    from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovals import check_text_agents_router
    from handlers.AgentsFeatures.ManagementAgents.AgentChatsAndChannelsdminsManagement import agent_admin_management
    from handlers.AgentsFeatures.add_AntiSpamAndIgnore import as_ignore_router
    from handlers.AgentsFeatures.ignoreUsers.ignore_manager import ignore_router

    # AdminsTools
    from handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettings import ACSettings
    from handlers.AdminsTools.ChatSettings.ChatAdmins.add_tg_admin import tg_admin_management
    from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCommand import UCS
    #from handlers.AdminsTools.ChatSettings.delete_message_chat import sms_cleanup
    from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import pin_sms
    from handlers.AdminsTools.ChatSettings.notes.notes import notes_router
    from handlers.AdminsTools.ChatSettings.reports.report_statistics.report_statistics import report_statistics
    from handlers.AdminsTools.check_views_chats_message import CVCM
    from handlers.AdminsTools.ChatSettings.DkCommands.CheckDkInfo import CheckDk
    from handlers.AdminsTools.CommandsModerations.bans.ban import bans
    from handlers.AdminsTools.ChatSettings.captcha.captcha_main import captcha_router
    from handlers.AdminsTools.ChatSettings.Stats.ChatsUsersStats.chat_users_stats import CUS
    from handlers.AdminsTools.CommandsModerations.mute.mute import mute
    from handlers.AdminsTools.ChatSettings.PuchCommandSettings.puch_command_settings import PushCommandSettings
    from handlers.AdminsTools.CommandsModerations.warns.warns import warn
    from handlers.AdminsTools.ChatSettings.welcome.welcome import welcom
    from handlers.AdminsTools.ChatSettings.rules.rules import rul
    from handlers.AdminsTools.ChatSettings.reports.reports import report
    from handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEdits import alerts
    from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import chatadmin
    from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettings import UpdateCommandsSetting

    # UserCommands
    from handlers.UserCommands.GenderSettings.GenderSettings import GenderSettings
    from handlers.UserCommands.user_profile import profile
    from handlers.AgentsFeatures.payment.payment import sapphires_router
    from handlers.UserCommands.weather import weather_router

    # Другие
    from handlers.testDirectiry.chat_settings import cs
    from handlers.testDirectiry.UpdateChatInfo import UpdatesChatInfo
    from handlers.BotAutomaticWork.AddChatsBot.AddChatsBot import chats

    from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettings import auto_chat_router
    from handlers.testDirectiry.testing import SlechCommands

    return [

        auto_chat_router,
        sapphires_router,
        weather_router,
        pingin, aa, server_stats_router, as_router, check_text_agents_router,
        agent_admin_management, as_ignore_router, ignore_router,
        ACSettings, tg_admin_management, UCS, pin_sms,
        notes_router, report_statistics, CVCM, CheckDk, bans, start_router,
        CUS, mute,  PushCommandSettings, warn,  welcom, rul,  report,  alerts,
        chatadmin,  UpdateCommandsSetting,  GenderSettings,  cs,
        UpdatesChatInfo, SlechCommands, profile, captcha_router, chats
    ]


async def initialize_services():
    """Инициализировать все сервисы"""
    logger.info("🔄 Инициализация сервисов...")

    try:
        # 1. Инициализируем UniversalBot
        from handlers.BotAutomaticWork.universal_bot import bot as universal_bot
        logger.info("✅ UniversalBot инициализирован")

        # 2. Инициализируем БД и кэш
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import init_db_pool
        from handlers.BotAutomaticWork.DataBase.CreateDataBase import create_db
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import init_cache
        from handlers.BotAutomaticWork.DataBase.CreateDataBase import init_commands_structure

        await init_db_pool()
        await create_db()
        await init_cache()
        await init_commands_structure()

        # 3. Инициализируем кэш игноров
        from handlers.BotAutomaticWork.Middleware.MiddlewareCache import init_ignore_cache
        await init_ignore_cache()

        # 4. Запускаем фонового воркера
        from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import start_background_worker
        await start_background_worker()

        # 5. Автопроверка пингов
        bot_instances_by_id = {}
        for cfg in MultiBotConfig.BOTS:
            bot = get_bot_by_token(cfg["TOKEN"])

            if bot:
                bot_instances_by_id[cfg["id"]] = bot
        start_background_ping_monitor(bot_instances_by_id)
        print(11)


        # 5. Показываем активные чаты
        from handlers.BotAutomaticWork.active_bot_registry import registry
        active_chats = registry.get_all_chats()
        if active_chats:
            logger.info("📊 Активные чаты из active_bots.json:")
            for chat_id, bot_id in active_chats.items():
                logger.info(f"  Чат {chat_id} → бот {bot_id}")
        else:
            logger.info("📊 Активных чатов пока нет")

        await init_commands_structure()
        logger.info('бд оттрахана!')

        asyncio.create_task(cleanup_expired_pins())
        logger.info('проверка анпинов запущена!')

        logger.info("✅ Все сервисы инициализированы")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации сервисов: {e}", exc_info=True)
        return False


async def shutdown_services():
    """Завершить работу всех сервисов"""
    logger.info("🛑 Завершение работы сервисов...")

    try:
        # 1. Останавливаем фонового воркера
        from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import stop_background_worker
        await stop_background_worker()

        # 2. Закрываем кэш игноров
        from handlers.BotAutomaticWork.Middleware.MiddlewareCache import shutdown_ignore_cache
        await shutdown_ignore_cache()

        # 3. Сохраняем статистику сообщений
        from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import flush_cache_to_db
        await flush_cache_to_db()
        logger.info("💾 Статистика сообщений сохранена")

        # 4. Закрываем UniversalBot
        from handlers.BotAutomaticWork.universal_bot import bot as universal_bot

        # Отправляем уведомление о выключении через UniversalBot
        try:
            await universal_bot.send_message(
                chat_id=-1003346491683,  # Тот же чат для уведомлений
                text='🛑 Бот выключен!\n\n'
                     'Сервисы завершают работу...'
            )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить уведомление о выключении: {e}")

        await universal_bot.close_all()

        # 5. Закрываем БД и кэш
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import close_db_pool
        await close_db_pool()

        # 6. Автопроверка пингов
        stop_background_ping_monitor()


        logger.info("✅ Все сервисы остановлены")

    except Exception as e:
        logger.error(f"❌ Ошибка при завершении работы: {e}")


async def run_bot_instance(bot_config: dict):
    """Запустить один экземпляр бота"""
    bot_token = bot_config.get('TOKEN')
    bot_id = bot_config.get('id')
    bot_name = bot_config.get('name')

    if not bot_token or not bot_id:
        logger.error(f"❌ Некорректный конфиг: {bot_name}")
        return

    try:
        logger.info(f"🚀 Подготовка бота: {bot_name}")

        # 1. Перезагружаем хендлеры
        await reload_all_handlers()

        # 2. Загружаем роутеры
        routers = await load_all_routers()

        # 3. Создаём бота и диспетчер
        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode='HTML')
        )

        dp = Dispatcher(storage=MemoryStorage())

        # 4. Регистрируем middleware
        from handlers.BotAutomaticWork.Middleware.MiddlewareCore import UpdateChatUserMiddleware
        from handlers.BotAutomaticWork.Middleware.MiddlewarePerformance import PerformanceMonitoringMiddleware

        # Middleware для обновления active_bots.json
        active_middleware = ActiveBotMiddleware(bot_id)
        dp.update.middleware.register(active_middleware)

        # Middleware для обновления пользователей (передаём токен)
        update_user_middleware = UpdateChatUserMiddleware(bot_token)
        dp.update.middleware.register(update_user_middleware)

        # Middleware для мониторинга производительности
        performance_middleware = PerformanceMonitoringMiddleware(alert_threshold=1.0)
        dp.update.middleware.register(performance_middleware)

        # 5. Регистрируем все роутеры
        for router in routers:
            dp.include_router(router)

        # 6. Получаем информацию о боте
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот {bot_name} запущен как @{bot_info.username}")

        # 7. Отправляем уведомление о запуске
        try:
            await bot.send_message(
                chat_id=-1003346491683,  # Ваш чат для уведомлений
                text=f'✅ Бот запущен!\n'
                     f'👤 @{bot_info.username}\n'
            )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить уведомление о запуске: {e}")

        # 8. Запускаем поллинг
        logger.info(f"🔄 Начинаю поллинг для {bot_name}...")
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=[
                "message",
                "callback_query",
                "inline_query",
                "chat_member",
                "my_chat_member",
                "chat_join_request"
            ]
        )

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в боте {bot_name}: {e}", exc_info=True)
    finally:
        if 'bot' in locals():
            await bot.session.close()
            logger.info(f"🔌 Бот {bot_name} остановлен")


# Добавьте этот импорт в начало файла
import os
import subprocess

# Добавьте глобальные переменные после импортов
RESTART_SERVER_FLAG = False
RESTART_APP_FLAG = False
current_process = None


async def graceful_shutdown():
    """Плавное завершение работы"""
    logger.info("🛑 Плавное завершение работы...")
    await shutdown_services()


async def restart_application():
    """Перезапуск приложения (только main.py)"""
    global RESTART_APP_FLAG
    logger.info("🔄 Запуск перезагрузки приложения...")
    RESTART_APP_FLAG = True
    await graceful_shutdown()


async def restart_server():
    """Перезагрузка сервера"""
    global RESTART_SERVER_FLAG
    logger.info("🔄 Запуск перезагрузки сервера...")
    RESTART_SERVER_FLAG = True
    await graceful_shutdown()


async def handle_restart():
    """Обработка перезагрузок после завершения работы"""
    global RESTART_SERVER_FLAG, RESTART_APP_FLAG

    if RESTART_SERVER_FLAG:
        logger.info("🔁 Перезагрузка сервера...")
        if os.name == 'posix':  # Linux/Unix
            subprocess.run(["sudo", "reboot"])
        else:
            logger.warning("⚠️ Перезагрузка сервера поддерживается только на Linux")

    elif RESTART_APP_FLAG:
        logger.info("🔁 Перезапуск приложения...")
        # Запускаем новый экземпляр
        python = sys.executable
        subprocess.Popen([python] + sys.argv)


async def main():
    """Главная функция"""
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

    logger.info("=" * 50)
    logger.info(f"🚀 ЗАПУСК СИСТЕМЫ МНОГОБОТОВОСТИ (PID: {os.getpid()})")
    logger.info("=" * 50)

    # Проверяем конфигурацию
    if not MultiBotConfig.validate_config():
        logger.error("❌ Невалидная конфигурация ботов!")
        return

    # Инициализируем сервисы
    if not await initialize_services():
        logger.error("❌ Не удалось инициализировать сервисы, завершаю работу...")
        return

    # Запускаем всех ботов
    tasks = []
    for bot_config in MultiBotConfig.BOTS:
        token = bot_config.get('TOKEN')
        bot_id = bot_config.get('id')

        if token and bot_id:
            task = asyncio.create_task(
                run_bot_instance(bot_config),
                name=f"bot_{bot_id}"
            )
            tasks.append(task)

            # Небольшая пауза между запусками ботов
            await asyncio.sleep(3)

    if not tasks:
        logger.error("❌ Нет ботов для запуска!")
        await shutdown_services()
        return

    logger.info(f"✅ Запущено {len(tasks)} ботов")
    logger.info("=" * 50)
    logger.info("🟢 СИСТЕМА УСПЕШНО ЗАПУЩЕНА")
    logger.info("=" * 50)

    # Обработка завершения (кросс-платформенная)
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⏹️ Получен сигнал Ctrl+C, завершаю работу...")
    except SystemExit:
        logger.info("")
        logger.info("⏹️ Получен сигнал завершения...")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка в основном цикле: {e}")
    finally:
        # Завершаем работу сервисов
        await shutdown_services()

        logger.info("")
        logger.info("=" * 50)
        logger.info("👋 СИСТЕМА ОСТАНОВЛЕНА")
        logger.info("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске: {e}", exc_info=True)
