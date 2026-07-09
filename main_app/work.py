import os
import sys

from aiogram.enums import UpdateType

# Определяем путь к папке main_app
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Добавляем в пути поиска саму main_app и корень проекта
sys.path.insert(0, CURRENT_DIR)
sys.path.insert(0, os.path.dirname(CURRENT_DIR))

import asyncio
import logging
import sys
import hashlib
import hmac
from typing import List
from contextlib import asynccontextmanager

import orjson
import uvicorn
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage


# --- Импорты вебхук-архитектуры ---
# Стало:
from main_app.webhooks_worker.GetWebhook import webhook_router
from main_app.webhooks_worker.FilterWebhook import optimizer

# --- КРИПТОГРАФИЧЕСКАЯ ЗАЩИТА (Мастер-соль) ---
# ВАЖНО: Эта строка должна СТРОГО совпадать с солью в файле GetWebhook.py!
SECRET_SALT = "SuperSecureSalt_SapphireProject_2026_Protected"

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

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

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

        if event.is_automatic_forward:
            return await handler(event, data)

        is_forwarded = any([
            event.forward_date, event.forward_from,
            event.forward_from_chat, event.forward_sender_name
        ])

        if is_forwarded:
            logger.debug(f"🚫 [{self.bot_name}] Сообщение заблокировано (Forward)")
            return

        return await handler(event, data)


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
        privacy_router, setting_help_online,
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
    from handlers.BotAutomaticWork.temporary_periodic_work.update_period_counter import reset_periodic_counters
    from handlers.BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import presence_cleanup_task_loop


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


# --- ГЛОБАЛЬНЫЕ СТРУКТУРЫ ХРАНЕНИЯ ---
dp = Dispatcher(storage=MemoryStorage())
bots_dict = {}
WEBHOOK_DOMAIN = "https://sapsp.site"



def json_dumps(data):
    return orjson.dumps(data).decode('utf-8')


def generate_bot_secure_credentials(bot_token: str) -> tuple[str, str]:
    """Генерирует криптографически стойкие URL-префикс и Secret Token для конкретного бота"""
    # URL-хэш: Запутывает роутинг от сканирования директорий эндпоинтов
    url_hash = hmac.new(SECRET_SALT.encode(), bot_token.encode(), hashlib.sha256).hexdigest()[:32]
    # Secret-токен: Обязательный заголовок X-Telegram-Bot-Api-Secret-Token, проверяемый при коннекте
    secret_token = hmac.new((SECRET_SALT + "_headers").encode(), bot_token.encode(), hashlib.sha256).hexdigest()
    return url_hash, secret_token




async def setup_bot(config: dict):
    """Инициализация сущности бота, регистрация Middleware и установка защищенного вебхука"""
    bot_token = config['TOKEN']
    bot_id = config['id']
    bot_name = config.get('name', f"Bot_{bot_id}")

    session = AiohttpSession(
        json_loads=orjson.loads,
        json_dumps=json_dumps
    )

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode='HTML'), session=session)
    bots_dict[bot_token] = bot

    # Регистрация цепочки Middleware на диспетчер
    from handlers.BotAutomaticWork.ActiveBotMiddleware import ActiveBotMiddleware
    from handlers.BotAutomaticWork.Middleware.MiddlewareCore import UpdateChatUserMiddleware
    from handlers.BotAutomaticWork.Middleware.PerformanceMonitoringMiddleware import PerformanceMonitoringMiddleware
    from handlers.BotAutomaticWork.Middleware.GlobalCountersMiddleware import GlobalCountersMiddleware

    dp.update.outer_middleware.register(ActiveBotMiddleware(bot_id))
    dp.update.outer_middleware.register(UpdateChatUserMiddleware(bot_token))
    dp.message.outer_middleware.register(ForwardBlockerMiddleware(bot_name))
    dp.update.outer_middleware.register(PerformanceMonitoringMiddleware(alert_threshold=1.0))
    dp.update.outer_middleware.register(GlobalCountersMiddleware())

    # Криптографическая генерация параметров вебхука
    url_hash, secret_token = generate_bot_secure_credentials(bot_token)
    webhook_url = f"{WEBHOOK_DOMAIN}/api/v3/ingress/secure_tunnel/route_obfuscation_{url_hash}/{bot_token}"

    # === 2. ПОЛУЧАЕМ АБСОЛЮТНО ВСЕ АПДЕЙТЫ ===
    allowed_updates = [update_type.value for update_type in UpdateType]

    # Регистрация вебхука на серверах Telegram
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=allowed_updates,  # Telegram начнет слать вообще всё!
        secret_token=secret_token,
        drop_pending_updates=False
    )
    logger.info(f"🛡️ Сверхзащищенный вебхук успешно установлен для {bot_name} (Подключено апдейтов: {len(allowed_updates)})")

# --- ЖИЗНЕННЫЙ ЦИКЛ ПРИЛОЖЕНИЯ (FastAPI Lifespan) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

    if not MultiBotConfig.validate_config():
        logger.error("❌ Критическая ошибка конфигурации в MultiBotConfig!")
        return

    # 1. Запуск внутренних систем и подключение пулов баз данных
    await initialize_global_services()

    # 2. Единовременная регистрация дерева хэндлеров aiogram
    routers = get_all_routers()
    for router in routers:
        dp.include_router(router)

    # 3. Делегация ссылок на объекты диспетчера внутрь стейта FastAPI для модуля GetWebhook
    app.state.bots_dict = bots_dict
    app.state.dp = dp

    # 4. Инициализация асинхронного буфера-оптимизатора пиковых нагрузок
    await optimizer.start()

    # 5. Циклическая регистрация и развертывание всех ботов из конфигурации
    for bot_cfg in MultiBotConfig.BOTS:
        await setup_bot(bot_cfg)

    logger.info(f"🟢 Сборка Sapphire успешно запущена. Активных ботов в пуле: {len(bots_dict)}")

    yield  # === ТОЧКА РАБОТЫ FastAPI-СЕРВЕРА (ОБРАБОТКА ЗАПРОСОВ) ===

    # --- GRACEFUL SHUTDOWN (БЕЗОПАСНАЯ ОСТАНОВКА СЕРВИСОВ) ---
    logger.info("🛑 Запущен процесс корректного завершения работы ядра...")
    await optimizer.stop()

    for bot in bots_dict.values():
        try:
            await bot.delete_webhook()
            await bot.session.close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии сессии бота: {e}")
    logger.info("✅ Все сессии закрыты. Сервер остановлен.")


# --- СБОРКА И ЗАПУСК FASTAPI ПРИЛОЖЕНИЯ ---
app = FastAPI(lifespan=lifespan)

# Регистрация защищенного эндпоинта из папки webhooks_worker
app.include_router(webhook_router)

if __name__ == "__main__":
    # Запускаем Uvicorn локально на новом порту 8005
    uvicorn.run("work:app", host="127.0.0.1", port=8005)