# handlers/BotAutomaticWork/universal_bot.py
import logging
from typing import Dict, Optional, Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
from handlers.BotAutomaticWork.active_bot_registry import registry

logger = logging.getLogger(__name__)


class UniversalBot:
    """
    УНИВЕРСАЛЬНЫЙ БОТ - использует active_bots.json
    """

    _bots: Dict[str, Bot] = {}

    def __init__(self):
        self._init_all_bots()
        logger.info("🌐 UniversalBot готов! Используйте 'bot.method()'")

    def _init_all_bots(self):
        """Создать всех ботов из конфига"""
        for bot_config in MultiBotConfig.BOTS:
            token = bot_config.get('TOKEN')
            bot_id = bot_config.get('id')
            name = bot_config.get('name')

            if token and bot_id:
                try:
                    bot_instance = Bot(
                        token=token,
                        default=DefaultBotProperties(parse_mode='HTML')
                    )
                    self._bots[bot_id] = bot_instance
                    logger.info(f"✅ Создан: {name} ({bot_id})")
                except Exception as e:
                    logger.error(f"❌ Ошибка создания {name}: {e}")

    def _get_bot_instance(self, bot_id: str) -> Optional[Bot]:
        """Получить экземпляр бота"""
        return self._bots.get(bot_id)

    def _find_bot_for_chat(self, chat_id: Any) -> Optional[Bot]:
        """Найти правильного бота для чата"""
        # Преобразуем chat_id в int если это строка с числами
        try:
            if isinstance(chat_id, str):
                chat_id = int(chat_id)
        except (ValueError, TypeError):
            pass

        # 1. Смотрим в active_bots.json
        bot_id = registry.get_bot_for_chat(chat_id)

        if bot_id:
            bot = self._get_bot_instance(bot_id)
            if bot:
                return bot

        # 2. Если нет в файле - автоматически назначаем
        logger.info(f"🔍 Чат {chat_id} не в active_bots.json, назначаем бота...")

        # Находим бота с наименьшим количеством чатов
        selected_bot = None
        min_chats = float('inf')

        for bot_id, bot_instance in self._bots.items():
            chat_count = registry.get_chat_count(bot_id)
            if chat_count < min_chats:
                min_chats = chat_count
                selected_bot = (bot_id, bot_instance)

        if selected_bot:
            bot_id, bot_instance = selected_bot
            # Сохраняем в active_bots.json
            registry.set_bot_for_chat(chat_id, bot_id)
            logger.info(f"🎯 Чат {chat_id} назначен боту {bot_id}")
            return bot_instance

        # 3. Если вообще нет ботов
        return None

    def _get_bot_for_call(self, chat_id: Optional[Any], method_name: str) -> Optional[Bot]:
        """Получить бота для вызова"""
        # Если есть chat_id - ищем бота для этого чата
        if chat_id is not None:
            return self._find_bot_for_chat(chat_id)

        # Если нет chat_id, но метод его не требует
        # Используем первого бота как fallback
        if self._bots:
            # Всегда возвращаем первого бота для системных вызовов
            return next(iter(self._bots.values()))

        return None

    def __getattr__(self, method_name: str):
        """Магия - перехватываем ЛЮБОЙ вызов"""

        async def method_wrapper(*args, **kwargs):
            # Шаг 1: Находим chat_id из аргументов метода
            chat_id = None

            # Для send_message и подобных методов ищем chat_id в kwargs
            if method_name in ['send_message', 'forward_message', 'send_photo', 'send_document',
                               'send_animation', 'send_video', 'send_audio', 'send_voice']:
                # Ищем chat_id в kwargs
                chat_id = kwargs.get('chat_id')

                # Если нет в kwargs, пробуем в args
                if chat_id is None and args:
                    # Первый аргумент может быть chat_id
                    first_arg = args[0]
                    if isinstance(first_arg, (int, str)):
                        # Проверяем, может ли быть это chat_id
                        try:
                            # Если это число (int) или строка с числами
                            num_value = int(str(first_arg))
                            # Любой числовой ID может быть chat_id (не только отрицательные!)
                            chat_id = num_value
                        except (ValueError, TypeError):
                            pass

            # Шаг 2: Находим правильного бота
            bot = self._get_bot_for_call(chat_id, method_name)
            if not bot:
                # Если не нашли бота, используем первого из списка
                if self._bots:
                    bot = next(iter(self._bots.values()))
                    logger.warning(f"⚠️ Используем первого бота для {method_name}, chat_id={chat_id}")
                else:
                    raise ValueError(f"❌ Не найден бот для вызова {method_name}")

            # Шаг 3: Вызываем метод
            method = getattr(bot, method_name)
            return await method(*args, **kwargs)

        return method_wrapper

    async def close_all(self):
        """Закрыть всех ботов"""
        for bot_id, bot_instance in self._bots.items():
            try:
                await bot_instance.session.close()
                logger.info(f"🔌 Закрыт бот {bot_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия {bot_id}: {e}")

        self._bots.clear()


# ГЛОБАЛЬНЫЙ ОБЪЕКТ
bot = UniversalBot()