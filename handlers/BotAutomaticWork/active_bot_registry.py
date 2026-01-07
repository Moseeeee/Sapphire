# handlers/BotAutomaticWork/active_bot_registry.py
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
import os

logger = logging.getLogger(__name__)


class ActiveBotRegistry:
    """Работа с существующим active_bots.json"""

    def __init__(self, filename: str = "data/active_bots.json"):
        self.filename = Path(filename)
        self._ensure_directory()
        self.data: Dict[str, str] = self._load()
        logger.info(f"📋 Загружено {len(self.data)} активных чатов")

    def _ensure_directory(self):
        """Создать папку data если её нет"""
        self.filename.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, str]:
        """Загрузить данные из файла"""
        if self.filename.exists():
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки active_bots.json: {e}")
                return {}
        return {}

    def _save(self):
        """Сохранить данные в файл"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения active_bots.json: {e}")

    def get_bot_for_chat(self, chat_id: int) -> Optional[str]:
        """Получить bot_id для чата"""
        return self.data.get(str(chat_id))

    def set_bot_for_chat(self, chat_id: int, bot_id: str):
        """Установить бота для чата"""
        self.data[str(chat_id)] = bot_id
        self._save()
        #logger.info(f"📝 Чат {chat_id} → бот {bot_id}")

    def remove_chat(self, chat_id: int):
        """Удалить чат"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.data:
            del self.data[chat_id_str]
            self._save()
            #logger.info(f"🗑️ Удалён чат {chat_id}")

    def get_all_chats_for_bot(self, bot_id: str) -> List[int]:
        """Получить все чаты бота"""
        return [int(chat_id) for chat_id, bid in self.data.items() if bid == bot_id]

    def get_chat_count(self, bot_id: str) -> int:
        """Сколько чатов у бота"""
        return len(self.get_all_chats_for_bot(bot_id))

    def get_all_chats(self) -> Dict[str, str]:
        """Получить все записи"""
        return self.data.copy()


# Глобальный экземпляр
registry = ActiveBotRegistry()