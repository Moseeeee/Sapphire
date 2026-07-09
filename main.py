
import asyncio

import logging
import os
import sys
import signal
from typing import List

import orjson
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import types, BaseMiddleware


# --- ОПТИМИЗАЦИЯ СЕТИ ---
if sys.platform != 'win32':
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass


# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
def setup_logging():
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        return root_logger

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Тишина для шумных библиотек
    for logger_name in ['aiogram.event', 'asyncio', 'aiohttp', 'urllib3']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return root_logger


logger = setup_logging()


# --- MIDDLEWARES ---

class ForwardBlockerMiddleware(BaseMiddleware):
    """Оптимизированная блокировка пересланных сообщений"""

    def __init__(self, bot_name: str):
        self.bot_name = bot_name
        super().__init__()

    async def __call__(self, handler, event: types.Message, data: dict):
        if not isinstance(event, types.Message):
            return await handler(event, data)

        # 1. Пропускаем авто-постинг из каналов
        if event.is_automatic_forward:
            return await handler(event, data)

        # 2. Проверяем ручной пересыл
        is_forwarded = any([
            event.forward_date, event.forward_from,
            event.forward_from_chat, event.forward_sender_name
        ])

        if is_forwarded:
            # Проверка на связанный канал (опционально, кэшируйте результат get_chat)
            #logger.debug(f"🚫 [{self.bot_name}] Сообщение заблокировано (Forward)")
            return

        return await handler(event, data)


# --- ЗАГРУЗКА КОМПОНЕНТОВ ---

def get_all_routers() -> List:
    from handlers.start import router as start_router
    from handlers.AgentsFeatures.AgentCheckPing import pingin
    from handlers.AgentsFeatures.ManagementAgents.ManagementAgents import aa
    from handlers.AgentsFeatures.help_files.help_users import help_user
    from handlers.sanor_commands.server_info import server_stats_router
    from handlers.AgentsFeatures.AntiSpam.AntiSpam import as_router
    from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovals import check_text_agents_router
    from handlers.AgentsFeatures.ManagementAgents.AgentChatsAndChannelsdminsManagement import agent_admin_management
    from handlers.AgentsFeatures.add_AntiSpamAndIgnore import as_ignore_router
    from handlers.AgentsFeatures.ignoreUsers.ignore_manager import ignore_router
    from handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettings import ACSettings
    from AdminsTools.ChatSettings.rights_participation_cats.add_tg_admin import tg_admin_management
    from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCommand import UCS
    from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import pin_sms
    from handlers.AdminsTools.ChatSettings.notes.notes import notes_router
    from handlers.AdminsTools.ChatSettings.reports.report_statistics.report_statistics import report_statistics
    from handlers.AdminsTools.check_views_chats_message import CVCM
    from handlers.AdminsTools.CommandsModerations.bans.ban import bans
    from handlers.sanor_commands.chat_info.ChatsInfo import chat_info_router
    from handlers.AdminsTools.ChatSettings.Stats.ChatsUsersStats.chat_users_stats import CUS
    from handlers.AdminsTools.CommandsModerations.mute.mute import mute
    from handlers.AdminsTools.ChatSettings.PuchCommandSettings.puch_command_settings import PushCommandSettings
    from handlers.AdminsTools.CommandsModerations.warns.warns import warn
    from handlers.AdminsTools.ChatSettings.welcome.welcome import welcom
    from handlers.AdminsTools.ChatSettings.rules.rules import rul
    from handlers.AdminsTools.ChatSettings.reports.reports import report
    from handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEdits import alerts
    from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import chatadmin
    from handlers.AdminsTools.ChatSettings.settings_link_filter.links_filter import link_filter
    from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettings import GenderSettings
    from handlers.UserCommands.user_profile import profile
    from handlers.UserCommands.weather import weather_router
    from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettings import PseudonymRouter
    from handlers.UserCommands.RPCommands import RP
    from handlers.sanor_commands.CheckPremiumEmodji import CPE
    from handlers.testDirectiry.chat_settings import cs
    from handlers.testDirectiry.UpdateChatInfo import UpdatesChatInfo
    from handlers.BotAutomaticWork.AddChatsBot.AddChatsBot import chats
    from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettings import auto_chat_router
    from handlers.testDirectiry.testing import SlechCommands
    from handlers.AdminsTools.ChatSettings.first_comment.first_comment import first_comment_commands_router
    from handlers.UserCommands.sapphire_commands import sapphire_commands
    #from handlers.AdminsTools.ChatSettings.voice_settings_chat.voice_settings import settings_voice
    #from handlers.AdminsTools.ChatSettings.voice_settings_chat.voice_decoding import decoding
    from handlers.AdminsTools.ChatSettings.first_comment.first_comment_auto import first_comment_auto_router
    from handlers.AdminsTools.ChatSettings.captcha.captcha_main import captcha_router
    from handlers.AdminsTools.ChatSettings.bundle.bundle_group import group_bundle
    from handlers.AdminsTools.ChatSettings.bundle.bundle_private import private_bundle
    from handlers.AdminsTools.ChatSettings.bundle.bundle_admins.bundle_admins import bundle_admins_router
    from handlers.BotAutomaticWork.temporary_periodic_work.start_automatic_check_punishments import \
        start_checking_punishments
    from UserCommands.MarriageStrength.marriage_handlers import marriage
    from UserCommands.payment.agents_payment import agent_sapphires_router
    from UserCommands.payment.user_payment import user_sapphires_router
    from UserCommands.online_privacy_commands import privacy_router
    from AgentsFeatures.help_files.setting_help_online import setting_help_online
    from AdminsTools.ChatSettings.DkCommands.UpdateCommandSettings import DkCommandsRouter
    from AdminsTools.ChatSettings.chats_migrations.command_migration import migration_router
    from AdminsTools.ChatSettings.rights_participation_cats.user_rights_management import tg_user_rights_management
    from AdminsTools.ChatSettings.delete_message_chat import sms_cleanup
    from sanor_commands.agents_chats_channel_filter import tg_channels_links_management


    return [
        start_router, pingin, aa, server_stats_router, as_router,
        check_text_agents_router, agent_admin_management, as_ignore_router,
        ignore_router, ACSettings, tg_admin_management, tg_user_rights_management,
        UCS, pin_sms,
        notes_router, report_statistics, CVCM, bans, help_user,
        chat_info_router, CUS, mute, PushCommandSettings, warn,
        welcom, rul, report, alerts, chatadmin, DkCommandsRouter,
        link_filter, GenderSettings, profile, migration_router,
        weather_router, PseudonymRouter, RP, CPE, cs, UpdatesChatInfo,
        chats, auto_chat_router, SlechCommands, first_comment_commands_router,
        sapphire_commands, group_bundle, private_bundle,
        bundle_admins_router, marriage, user_sapphires_router, agent_sapphires_router,
        privacy_router, setting_help_online, sms_cleanup, tg_channels_links_management,
        first_comment_auto_router, captcha_router, start_checking_punishments,

        #decoding, settings_voice,
    ]

async def initialize_global_services():
    """Инициализация БД и тяжелых ресурсов при старте"""
    logger.info("⚙️ Инициализация глобальных сервисов...")

    from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import init_db_pool
    from handlers.BotAutomaticWork.DataBase.CreateBD.CreateDataBase import create_db
    from handlers.BotAutomaticWork.DataBase.CreateBD.CreateCommandBase import init_commands_structure
    from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import init_cache
    from handlers.BotAutomaticWork.Middleware.MiddlewareCache import init_ignore_cache
    from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import timer_manager
    from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import start_background_worker
    from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsCleanerAutomatic import periodic_cleaner
    from handlers.AdminsTools.ChatSettings.message_pinned.pin_sms import cleanup_expired_pins
    from BotAutomaticWork.temporary_periodic_work.update_period_counter import reset_periodic_counters
    from BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import presence_cleanup_task_loop


    await init_db_pool()
    await create_db()
    await init_cache()
    await init_commands_structure()
    await init_ignore_cache()
    await timer_manager.start_batch_processing()
    await start_background_worker()

    # Запуск фоновых бесконечных задач в цикле событий
    asyncio.create_task(periodic_cleaner())
    asyncio.create_task(cleanup_expired_pins())
    asyncio.create_task(reset_periodic_counters())
    asyncio.create_task(presence_cleanup_task_loop())

    logger.info("✅ Глобальные сервисы готовы")


# --- УПРАВЛЕНИЕ БОТАМИ ---

async def start_bot_instance(config: dict, routers: list):
    """Запуск одного экземпляра бота с оптимизированной сессией"""
    bot_token = config['TOKEN']
    bot_id = config['id']
    bot_name = config.get('name', f"Bot_{bot_id}")

    # --- ОПТИМИЗАЦИЯ СЕРИАЛИЗАЦИИ JSON (orjson) ---
    # --- ОПТИМИЗАЦИЯ СЕРИАЛИЗАЦИИ JSON ---
    def json_dumps(data):
        # orjson.dumps возвращает bytes, aiogram ожидает str
        return orjson.dumps(data).decode('utf-8')

    # Создаем сессию
    session = AiohttpSession(
        json_loads=orjson.loads,
        json_dumps=json_dumps
    )

    # ВАЖНО: Проверим, создается ли бот вообще
    try:
        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode='HTML'),
            session=session
        )
        logger.info(f"✅ Сессия для {bot_name} создана успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка создания бота {bot_name}: {e}")
        return  # Выходим, если бот не создался

    dp = Dispatcher(storage=MemoryStorage())


    # Регистрация Middlewares (Порядок важен!)
    from handlers.BotAutomaticWork.ActiveBotMiddleware import ActiveBotMiddleware
    from handlers.BotAutomaticWork.Middleware.MiddlewareCore import UpdateChatUserMiddleware
    from handlers.BotAutomaticWork.Middleware.PerformanceMonitoringMiddleware import PerformanceMonitoringMiddleware
    from handlers.BotAutomaticWork.Middleware.GlobalCountersMiddleware import GlobalCountersMiddleware

    dp.update.middleware.register(ActiveBotMiddleware(bot_id))
    dp.update.middleware.register(UpdateChatUserMiddleware(bot_token))
    dp.message.outer_middleware.register(ForwardBlockerMiddleware(bot_name))
    dp.update.middleware.register(PerformanceMonitoringMiddleware(alert_threshold=1.0))
    dp.update.middleware.register(GlobalCountersMiddleware())

    # Подключаем роутеры
    for router in routers:
        dp.include_router(router)

    try:
        bot_info = await bot.get_me()
        logger.info(f"🚀 Запущен @{bot_info.username} (ID: {bot_id})")

        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=[]
        )
    except Exception as e:
        logger.error(f"💥 Ошибка в боте {bot_name}: {e}")
    finally:
        await bot.session.close()


# --- ЖИЗНЕННЫЙ ЦИКЛ ПРИЛОЖЕНИЯ ---

def restart_process():
    """Полный перезапуск процесса (очищает всю память)"""
    logger.info("🔄 Перезапуск процесса...")
    python = sys.executable
    os.execv(python, [python] + sys.argv)


async def main():
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

    if not MultiBotConfig.validate_config():
        logger.error("❌ Ошибка конфигурации!")
        return

    # 1. Глобальная инициализация
    await initialize_global_services()

    # 2. Предзагрузка роутеров (один раз в памяти)
    routers = get_all_routers()

    # 3. Запуск всех ботов
    tasks = []
    for bot_cfg in MultiBotConfig.BOTS:
        tasks.append(asyncio.create_task(start_bot_instance(bot_cfg, routers)))
        await asyncio.sleep(0.5)  # Плавный запуск для снижения нагрузки на CPU

    logger.info(f"🟢 Система запущена. Ботов: {len(tasks)}")

    # Обработка сигналов завершения
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("⚠️ Получен сигнал остановки...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass  # Для Windows

    try:
        # Ждем либо отмены задач, либо сигнала остановки
        await stop_event.wait()
    finally:
        logger.info("🛑 Завершение работы...")
        # Здесь можно вызвать shutdown_services() если нужно
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("👋 До свидания!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Критический сбой: {e}", exc_info=True)