# handlers/BotAutomaticWork/Gonfig/multi_bot_config.py
import logging
import os
from typing import Dict, List
import json

logger = logging.getLogger(__name__)


class MultiBotConfig:
    """Конфигурация для автоматической передачи чатов между ботами"""

    # ТОКЕНЫ БОТОВ
    BOTS = [
        #{
           # 'id': 'bot_1',
          #  'name': 'Sapphire | Chat Manager',
         #   'TOKEN': "8277713159:AAHUN9FtoPX02G2bNaOUb3HMRuE4LcZRYbY",
        #},
        {
            'id': 'bot_2',
            'name': '🛠️ Sapphire Test Bot',
            'TOKEN': "8020015583:AAG9OrL9l8QNwzcgqCWnd9LmapVMFGKU8Ag",
        },
        #{
            #'id': 'bot_3',
            #'name': '👁️‍🗨️ Sanor Test Bot',
            #'TOKEN': "7779546434:AAHmLdtTreqDL2OUjyzKSe-nXrnsAvWvHYk",
        #}
    ]

    # Файл для хранения активного бота в чате
    ACTIVE_BOT_FILE = 'data/active_bots.json'

    @classmethod
    def get_bot_by_token(cls, token: str) -> Dict:
        """Найти конфигурацию бота по токену"""
        for bot in cls.BOTS:
            if bot['TOKEN'] == token:
                return bot
        return {}

    @classmethod
    def get_bot_by_id(cls, bot_id: str) -> Dict:
        """Найти конфигурацию бота по ID"""
        for bot in cls.BOTS:
            if bot['id'] == bot_id:
                return bot
        return {}

    @classmethod
    def get_active_bot_for_chat(cls, chat_id: int) -> Dict:
        """Получить активного бота для чата"""
        mapping = cls.load_active_bots()
        bot_id = mapping.get(str(chat_id))
        if bot_id:
            return cls.get_bot_by_id(bot_id)
        return {}

    @classmethod
    def set_active_bot_for_chat(cls, chat_id: int, bot_id: str):
        """Установить активного бота для чата"""
        mapping = cls.load_active_bots()
        mapping[str(chat_id)] = bot_id

        # Создаем папку data если её нет
        os.makedirs('data', exist_ok=True)

        with open(cls.ACTIVE_BOT_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)

        logger.info(f"📝 Чат {chat_id} передан боту {bot_id}")

    @classmethod
    def remove_bot_from_chat(cls, chat_id: int, bot_id: str):
        """Удалить бота из чата (когда он выходит)"""
        mapping = cls.load_active_bots()
        chat_id_str = str(chat_id)

        if mapping.get(chat_id_str) == bot_id:
            # Если этот бот был активным, очищаем запись
            del mapping[chat_id_str]

            with open(cls.ACTIVE_BOT_FILE, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)

            logger.info(f"🗑️ Бот {bot_id} удален из чата {chat_id}")

    @classmethod
    def load_active_bots(cls) -> Dict:
        """Загрузить маппинг активных ботов из файла"""
        if os.path.exists(cls.ACTIVE_BOT_FILE):
            try:
                with open(cls.ACTIVE_BOT_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки active_bots.json: {e}")
                return {}
        return {}

    @classmethod
    def get_assigned_bot_for_chat(cls, chat_id: int) -> Dict:
        """Получить назначенного бота для чата (синоним для обратной совместимости)"""
        return cls.get_active_bot_for_chat(chat_id)

    @classmethod
    def assign_chat_to_bot(cls, chat_id: int, bot_id: str):
        """Назначить чат боту (синоним для обратной совместимости)"""
        cls.set_active_bot_for_chat(chat_id, bot_id)

    @classmethod
    def get_least_loaded_bot(cls) -> Dict:
        """Получить бота с наименьшей нагрузкой (по количеству чатов)"""
        mapping = cls.load_active_bots()

        # Считаем сколько чатов у каждого бота
        bot_loads = {}
        for bot in cls.BOTS:
            bot_loads[bot['id']] = 0

        for chat_bot_id in mapping.values():
            if chat_bot_id in bot_loads:
                bot_loads[chat_bot_id] += 1

        # Находим бота с минимальной нагрузкой
        if not bot_loads:
            return cls.BOTS[0] if cls.BOTS else None

        min_bot_id = min(bot_loads, key=bot_loads.get)
        return cls.get_bot_by_id(min_bot_id)

    @classmethod
    def get_all_tokens(cls) -> List[str]:
        """Получить все токены ботов"""
        return [bot['TOKEN'] for bot in cls.BOTS if bot.get('TOKEN')]

    @classmethod
    def validate_config(cls) -> bool:
        """Проверить конфигурацию"""
        if not cls.BOTS:
            logger.error("❌ Список ботов пуст!")
            return False

        valid_bots = 0
        for bot in cls.BOTS:
            token = bot.get('TOKEN', '').strip()
            if token and len(token) > 30:  # Простая проверка что токен не пустой
                valid_bots += 1
                logger.info(f"✅ Бот {bot.get('name')} - токен валиден")
            else:
                logger.warning(f"⚠️ Бот {bot.get('name')} - неверный или отсутствующий токен")

        if valid_bots == 0:
            logger.error("❌ Нет валидных токенов ботов!")
            return False

        logger.info(f"✅ Конфигурация валидна. Найдено {valid_bots} валидных ботов")
        return True