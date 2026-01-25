import asyncio
import importlib
import logging
import os
import subprocess
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCleanerAutomatic import periodic_cleaner
from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import cleanup_expired_pins

# Оптимизация asyncio для высоких нагрузок
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
else:
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logging.info("✅ Используется uvloop для максимальной производительности")
    except ImportError:
        pass

# Увеличиваем лимит рекурсии
sys.setrecursionlimit(10000)


# Настройка логирования без дублирования
def setup_logging():
    """Оптимизированная настройка логирования без дублирования"""
    # Получаем корневой логгер
    root_logger = logging.getLogger()

    # Очищаем все существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(logging.INFO)

    # Отключаем propagation для шумных логгеров
    noisy_loggers = [
        'aiogram.event',
        'aiogram.middleware',
        'asyncio',
        'aiohttp',
        'urllib3',
        'httpx'
    ]

    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
        logger.propagate = False  # Важно: отключаем передачу родителю

    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Один обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Добавляем только этот обработчик к корневому логгеру
    root_logger.addHandler(console_handler)

    # Файловый логгер (опционально)
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            'bot_system.log',
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info("✅ Файловый логгер инициализирован")
    except Exception as e:
        logging.debug(f"⚠️ Не удалось создать файловый логгер: {e}")

    return root_logger


# Инициализируем логгер только один раз
if not logging.getLogger().handlers:
    setup_logging()

logger = logging.getLogger(__name__)

# Глобальные флаги
RESTART_SERVER_FLAG = False
RESTART_APP_FLAG = False

# === ГЛОБАЛЬНЫЙ КЭШ ДЛЯ ПАКЕТНОЙ ОБРАБОТКИ ===
_LAST_USER_UPDATE = {}  # (bot_id, user_id) -> timestamp
USER_UPDATE_COOLDOWN = 1.0  # секунд


def _should_skip_user_update(user_id: int, bot_id: str) -> bool:
    """Проверяет, нужно ли пропустить обновление пользователя из-за кулдауна"""
    key = (bot_id, user_id)
    if key not in _LAST_USER_UPDATE:
        return False

    last_update = _LAST_USER_UPDATE[key]
    return (time.time() - last_update) < USER_UPDATE_COOLDOWN


def _mark_user_updated(user_id: int, bot_id: str):
    """Отмечает время обновления пользователя"""
    _LAST_USER_UPDATE[(bot_id, user_id)] = time.time()


async def reload_all_handlers():
    """Перезагрузка хендлеров"""
    modules_to_reload = [
        'handlers.start',
        'handlers.AgentsFeatures.AgentCheckPing',
        'handlers.AgentsFeatures.ManagementAgents.ManagementAgents',
        'handlers.AgentsFeatures.server_info',
        'handlers.AgentsFeatures.AntiSpam.AntiSpam',
        'handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovals',
        'handlers.AgentsFeatures.ManagementAgents.AgentChatsAndChannelsdminsManagement',
        'handlers.AgentsFeatures.add_AntiSpamAndIgnore',
        'handlers.AgentsFeatures.ignoreUsers.ignore_manager',
        'handlers.AgentsFeatures.chat_info.ChatsInfo',
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
        'handlers.AdminsTools.ChatSettings.settings_link_filter.links_filter',
        'handlers.UserCommands.GenderSettings.GenderSettings',
        'handlers.UserCommands.user_profile',
        'handlers.UserCommands.weather',
        'handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettings',
        'handlers.UserCommands.RPCommands'
        'handlers.testDirectiry.chat_settings',
        'handlers.testDirectiry.UpdateChatInfo',
        'handlers.BotAutomaticWork.AddChatsBot.AddChatsBot',
        'handlers.testing',
        'handlers.AgentsFeatures.payment.payment',
        'handlers.testDirectiry.ChatSettingsAutomatic.ChatSettings',
        'handlers.testDirectiry.testing'
    ]

    for module_name in modules_to_reload:
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
        except Exception as e:
            logger.debug(f"⚠️ Не удалось перезагрузить {module_name}: {e}")


async def load_all_routers():
    """Загрузка всех роутеров"""
    routers = []

    # Основные
    from handlers.start import router as start_router
    routers.append(start_router)

    # AgentsFeatures
    from handlers.AgentsFeatures.AgentCheckPing import pingin
    routers.append(pingin)

    from handlers.AgentsFeatures.ManagementAgents.ManagementAgents import aa
    routers.append(aa)

    from handlers.AgentsFeatures.server_info import server_stats_router
    routers.append(server_stats_router)

    from handlers.AgentsFeatures.AntiSpam.AntiSpam import as_router
    routers.append(as_router)

    from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovals import check_text_agents_router
    routers.append(check_text_agents_router)

    from handlers.AgentsFeatures.ManagementAgents.AgentChatsAndChannelsdminsManagement import agent_admin_management
    routers.append(agent_admin_management)

    from handlers.AgentsFeatures.add_AntiSpamAndIgnore import as_ignore_router
    routers.append(as_ignore_router)

    from handlers.AgentsFeatures.ignoreUsers.ignore_manager import ignore_router
    routers.append(ignore_router)


    # AdminsTools
    from handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettings import ACSettings
    routers.append(ACSettings)

    from handlers.AdminsTools.ChatSettings.ChatAdmins.add_tg_admin import tg_admin_management
    routers.append(tg_admin_management)

    from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCommand import UCS
    routers.append(UCS)

    from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import pin_sms
    routers.append(pin_sms)

    from handlers.AdminsTools.ChatSettings.notes.notes import notes_router
    routers.append(notes_router)

    from handlers.AdminsTools.ChatSettings.reports.report_statistics.report_statistics import report_statistics
    routers.append(report_statistics)

    from handlers.AdminsTools.check_views_chats_message import CVCM
    routers.append(CVCM)

    from handlers.AdminsTools.ChatSettings.DkCommands.CheckDkInfo import CheckDk
    routers.append(CheckDk)

    from handlers.AdminsTools.CommandsModerations.bans.ban import bans
    routers.append(bans)

    from handlers.AgentsFeatures.chat_info.ChatsInfo import chat_info_router
    routers.append(chat_info_router)

    from handlers.AdminsTools.ChatSettings.Stats.ChatsUsersStats.chat_users_stats import CUS
    routers.append(CUS)

    from handlers.AdminsTools.CommandsModerations.mute.mute import mute
    routers.append(mute)

    from handlers.AdminsTools.ChatSettings.PuchCommandSettings.puch_command_settings import PushCommandSettings
    routers.append(PushCommandSettings)

    from handlers.AdminsTools.CommandsModerations.warns.warns import warn
    routers.append(warn)

    from handlers.AdminsTools.ChatSettings.welcome.welcome import welcom
    routers.append(welcom)

    from handlers.AdminsTools.ChatSettings.rules.rules import rul
    routers.append(rul)

    from handlers.AdminsTools.ChatSettings.reports.reports import report
    routers.append(report)

    from handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEdits import alerts
    routers.append(alerts)

    from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import chatadmin
    routers.append(chatadmin)

    from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettings import UpdateCommandsSetting
    routers.append(UpdateCommandsSetting)

    from handlers.AdminsTools.ChatSettings.settings_link_filter.links_filter import link_filter
    routers.append(link_filter)

    # UserCommands
    from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettings import GenderSettings
    routers.append(GenderSettings)

    from handlers.UserCommands.user_profile import profile
    routers.append(profile)

    from handlers.AgentsFeatures.payment.payment import sapphires_router
    routers.append(sapphires_router)

    from handlers.UserCommands.weather import weather_router
    routers.append(weather_router)

    from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettings import PseudonymRouter
    routers.append(PseudonymRouter)

    from handlers.UserCommands.RPCommands import RP
    routers.append(RP)

    # Другие
    from handlers.testDirectiry.chat_settings import cs
    routers.append(cs)

    from handlers.testDirectiry.UpdateChatInfo import UpdatesChatInfo
    routers.append(UpdatesChatInfo)

    from handlers.BotAutomaticWork.AddChatsBot.AddChatsBot import chats
    routers.append(chats)

    from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettings import auto_chat_router
    routers.append(auto_chat_router)

    from handlers.testDirectiry.testing import SlechCommands
    routers.append(SlechCommands)

    from handlers.AdminsTools.ChatSettings.captcha.captcha_main import captcha_router
    routers.append(captcha_router)

    return routers


async def initialize_services():
    """Инициализация сервисов"""
    logger.info("🔄 Инициализация сервисов...")

    try:
        # 1. UniversalBot
        from handlers.BotAutomaticWork.universal_bot import bot as universal_bot
        logger.info("✅ UniversalBot инициализирован")

        # 2. БД и кэш
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import init_db_pool
        from handlers.BotAutomaticWork.DataBase.CreateDataBase import create_db
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import init_cache
        from handlers.BotAutomaticWork.DataBase.CreateDataBase import init_commands_structure

        await init_db_pool()
        await create_db()
        await init_cache()
        await init_commands_structure()
        logger.info("✅ База данных и кэш инициализированы")

        # 3. Кэш игноров
        from handlers.BotAutomaticWork.Middleware.MiddlewareCache import init_ignore_cache
        await init_ignore_cache()
        logger.info("✅ Кэш игноров инициализирован")

        # 4. Таймеры для пакетной обработки
        from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import timer_manager
        await timer_manager.start_batch_processing()
        logger.info("✅ Таймеры для пакетной обработки запущены")

        # 5. Фоновый воркер
        from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import start_background_worker
        await start_background_worker()
        logger.info("✅ Фоновый воркер запущен")

        # 6. Мониторинг пингов
        from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
        from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
        from handlers.AgentsFeatures.server_info import start_background_ping_monitor

        bot_instances_by_id = {}
        for cfg in MultiBotConfig.BOTS:
            bot = get_bot_by_token(cfg["TOKEN"])
            if bot:
                bot_instances_by_id[cfg["id"]] = bot

        start_background_ping_monitor(bot_instances_by_id)
        logger.info("✅ Мониторинг пингов запущен")

        # 7. Фоновые задачи
        asyncio.create_task(periodic_cleaner())
        logger.info('✅ Обновление статистики сообщений запущено')

        asyncio.create_task(cleanup_expired_pins())
        logger.info('✅ Проверка анпинов запущена')

        # 8. Глобальные счетчики
        from handlers.BotAutomaticWork.Middleware.GlobalCountersMiddleware import global_counter
        logger.info("✅ Глобальные счетчики инициализированы")

        logger.info("✅ Все сервисы успешно инициализированы")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации сервисов: {e}", exc_info=True)
        return False


async def shutdown_services():
    """Завершение работы сервисов"""
    logger.info("🛑 Завершение работы сервисов...")

    try:
        # 1. Остановка пакетной обработки таймеров
        from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import timer_manager
        await timer_manager.stop_batch_processing()
        logger.info("✅ Пакетная обработка таймеров остановлена")

        # 2. Фоновый воркер
        from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import stop_background_worker
        await stop_background_worker()

        # 3. Кэш игноров
        from handlers.BotAutomaticWork.Middleware.MiddlewareCache import shutdown_ignore_cache
        await shutdown_ignore_cache()

        # 4. Статистика сообщений
        from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.msg_stats_cache import flush_cache_to_db
        await flush_cache_to_db()
        logger.info("💾 Статистика сообщений сохранена")

        # 5. UniversalBot уведомление
        from handlers.BotAutomaticWork.universal_bot import bot as universal_bot
        try:
            await universal_bot.send_message(
                chat_id=-1003346491683,
                text='🛑 Бот выключен!\n\nСервисы завершают работу...'
            )
        except:
            pass

        # 6. Мониторинг пингов
        from handlers.AgentsFeatures.server_info import stop_background_ping_monitor
        stop_background_ping_monitor()

        # 7. Сервис статистики чатов
        from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotChatStatsService import chat_stats_service
        await chat_stats_service.stop()

        # 8. БД
        from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import close_db_pool
        await close_db_pool()

        # 9. Очистка глобального кэша
        global _LAST_USER_UPDATE
        _LAST_USER_UPDATE.clear()

        # 10. UniversalBot
        try:
            await universal_bot.close_all()
        except:
            pass

        logger.info("✅ Все сервисы остановлены")

    except Exception as e:
        logger.error(f"❌ Ошибка при завершении работы: {e}")


async def run_bot_instance(bot_config: dict):



    """Запуск экземпляра бота"""
    bot_token = bot_config.get('TOKEN')
    bot_id = bot_config.get('id')
    bot_name = bot_config.get('name')

    if not bot_token or not bot_id:
        logger.error(f"❌ Некорректный конфиг: {bot_name}")
        return

    try:
        logger.info(f"🚀 Подготовка бота: {bot_name}")

        # 1. Перезагрузка хендлеров
        await reload_all_handlers()

        # 2. Загрузка роутеров
        routers = await load_all_routers()

        # 3. Создание бота и диспетчера
        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode='HTML')
        )

        dp = Dispatcher(storage=MemoryStorage())

        ##asyncio.create_task(start_load_test(dp, bot))

        # 4. Регистрация middleware
        from handlers.BotAutomaticWork.ActiveBotMiddleware import ActiveBotMiddleware
        active_middleware = ActiveBotMiddleware(bot_id)
        dp.update.middleware.register(active_middleware)

        # === ИСПОЛЬЗУЕМ ОПТИМИЗИРОВАННЫЙ MIDDLEWARE ===
        from handlers.BotAutomaticWork.Middleware.MiddlewareCore import UpdateChatUserMiddleware
        update_user_middleware = UpdateChatUserMiddleware(bot_token)
        dp.update.middleware.register(update_user_middleware)

        # PerformanceMonitoringMiddleware теперь в отдельном файле
        from handlers.BotAutomaticWork.Middleware.PerformanceMonitoringMiddleware import PerformanceMonitoringMiddleware
        performance_middleware = PerformanceMonitoringMiddleware(alert_threshold=1.0)
        dp.update.middleware.register(performance_middleware)

        # Глобальные счетчики
        from handlers.BotAutomaticWork.Middleware.GlobalCountersMiddleware import GlobalCountersMiddleware
        dp.update.middleware.register(GlobalCountersMiddleware())
        # ===========================================

        # 5. Регистрация роутеров
        for router in routers:
            dp.include_router(router)

        # 6. Информация о боте
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот {bot_name} запущен как @{bot_info.username}")

        # 7. Уведомление о запуске
        try:
            await bot.send_message(
                chat_id=-1003346491683,
                text=f'✅ Бот запущен!\n👤 @{bot_info.username}'
            )
        except:
            pass

        # 8. Запуск поллинга
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


async def graceful_shutdown():
    """Плавное завершение работы"""
    logger.info("🛑 Плавное завершение работы...")
    await shutdown_services()


async def restart_application():
    """Перезапуск приложения"""
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
    """Обработка перезагрузок"""
    global RESTART_SERVER_FLAG, RESTART_APP_FLAG

    if RESTART_SERVER_FLAG:
        logger.info("🔁 Перезагрузка сервера...")
        if os.name == 'posix':
            subprocess.run(["sudo", "reboot"])
        else:
            logger.warning("⚠️ Перезагрузка сервера поддерживается только на Linux")

    elif RESTART_APP_FLAG:
        logger.info("🔁 Перезапуск приложения...")
        python = sys.executable
        subprocess.Popen([python] + sys.argv)


async def main():
    """Главная функция"""
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

    logger.info("=" * 50)
    logger.info(f"🚀 ЗАПУСК СИСТЕМЫ МНОГОБОТОВОСТИ (PID: {os.getpid()})")
    logger.info("⚡ ИСПОЛЬЗУЕТСЯ ОПТИМИЗИРОВАННЫЙ MIDDLEWARE")
    logger.info("🔄 ПАКЕТНАЯ ОБРАБОТКА КАЖДЫЕ 7 СЕКУНД")
    logger.info("=" * 50)

    # Проверка конфигурации
    if not MultiBotConfig.validate_config():
        logger.error("❌ Невалидная конфигурация ботов!")
        return

    # Инициализация сервисов
    if not await initialize_services():
        logger.error("❌ Не удалось инициализировать сервисы, завершаю работу...")
        return

    # Запуск ботов
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
            await asyncio.sleep(3)

    if not tasks:
        logger.error("❌ Нет ботов для запуска!")
        await shutdown_services()
        return

    logger.info(f"✅ Запущено {len(tasks)} ботов")
    logger.info("=" * 50)
    logger.info("🟢 СИСТЕМА УСПЕШНО ЗАПУЩЕНА")
    logger.info("⚡ Оптимизированный middleware работает как по маслу!")
    logger.info("=" * 50)

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