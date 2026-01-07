# handlers/BotAutomaticWork/BotCreatedGlobal.py
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from typing import Dict, Optional
import logging
import threading

from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig

logger = logging.getLogger(__name__)

# Глобальное хранилище всех ботов
_all_bots: Dict[str, Bot] = {}  # token -> Bot instance

# Локальное хранилище для thread-local контекста
_thread_local = threading.local()


def init_all_bots():
    """Инициализировать всех ботов на основе конфигурации"""
    global _all_bots

    # Очищаем существующих ботов
    _all_bots.clear()

    for bot_config in MultiBotConfig.BOTS:
        token = bot_config['TOKEN']
        name = bot_config['name']

        if not token or token in _all_bots:
            continue

        try:
            # Создаем экземпляр бота
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode='HTML')
            )

            _all_bots[token] = bot
            logger.info(f"✅ Бот инициализирован: {name}")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота {name}: {e}")

    logger.info(f"✅ Всего инициализировано {len(_all_bots)} ботов")


def get_bot_by_token(token: str) -> Optional[Bot]:
    """Получить экземпляр бота по токену"""
    if not _all_bots:
        init_all_bots()

    return _all_bots.get(token)


def get_all_bots() -> Dict[str, Bot]:
    """Получить словарь всех ботов (token -> Bot instance)"""
    if not _all_bots:
        init_all_bots()

    return _all_bots.copy()


def get_bot_for_chat(chat_id: int) -> Optional[Bot]:
    """Получить бота, назначенного на чат (ВАЖНАЯ ФУНКЦИЯ)"""
    bot_config = MultiBotConfig.get_active_bot_for_chat(chat_id)
    if bot_config:
        bot = get_bot_by_token(bot_config['TOKEN'])
        if bot:
            logger.debug(f"✅ Найден активный бот для чата {chat_id}: {bot_config['name']}")
            return bot

    # Если чат не назначен, назначаем бота с наименьшей нагрузкой
    new_bot_config = MultiBotConfig.get_least_loaded_bot()
    if new_bot_config:
        # Автоматически назначаем чат этому боту
        MultiBotConfig.assign_chat_to_bot(chat_id, new_bot_config['id'])
        logger.info(f"📝 Чат {chat_id} автоматически назначен боту {new_bot_config['name']}")
        return get_bot_by_token(new_bot_config['TOKEN'])

    logger.warning(f"⚠️ Не найден бот для чата {chat_id}")
    return None


def set_current_chat_context(chat_id: int):
    """Установить текущий контекст chat_id для этого потока"""
    if not hasattr(_thread_local, 'chat_context'):
        _thread_local.chat_context = {}
    _thread_local.chat_context['chat_id'] = chat_id


def get_current_chat_context() -> Optional[int]:
    """Получить текущий контекст chat_id"""
    if hasattr(_thread_local, 'chat_context'):
        return _thread_local.chat_context.get('chat_id')
    return None


def get_bot() -> Optional[Bot]:
    """Получить бота для текущего контекста (для обратной совместимости)"""
    # 1. Пытаемся получить chat_id из контекста
    chat_id = get_current_chat_context()

    if chat_id is not None:
        bot = get_bot_for_chat(chat_id)
        if bot:
            logger.debug(f"🔍 get_bot() вернул бота для чата {chat_id} (из контекста)")
            return bot

    # 2. Если нет контекста, возвращаем первого бота
    if not _all_bots:
        init_all_bots()

    if _all_bots:
        first_bot = next(iter(_all_bots.values()))
        logger.debug(f"⚠️ get_bot() вернул первого бота (контекст не установлен)")
        return first_bot

    return None


async def close_all_bots():
    """Закрыть сессии всех ботов"""
    global _all_bots

    logger.info(f"🔌 Закрываю сессии {len(_all_bots)} ботов...")

    for token, bot in list(_all_bots.items()):
        try:
            # Закрываем сессию бота
            await bot.session.close()
            logger.info(f"🔌 Закрыта сессия бота {token[:10]}...")

        except Exception as e:
            logger.error(f"❌ Ошибка закрытия сессии бота: {e}")

        finally:
            # Удаляем бота из словаря
            if token in _all_bots:
                del _all_bots[token]

    logger.info("✅ Все сессии ботов закрыты")


# Функция для обратной совместимости со старым кодом
def get_bot_for_event(event) -> Optional[Bot]:
    """Получить бота для события (универсальная функция)"""
    chat_id = None

    # Извлекаем chat_id из события
    if hasattr(event, 'chat') and hasattr(event.chat, 'id'):
        chat_id = event.chat.id
    elif hasattr(event, 'message') and hasattr(event.message, 'chat'):
        chat_id = event.message.chat.id
    elif hasattr(event, 'callback_query') and event.callback_query and event.callback_query.message:
        chat_id = event.callback_query.message.chat.id

    if chat_id:
        return get_bot_for_chat(chat_id)

    return get_bot()