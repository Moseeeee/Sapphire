import asyncio
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import logging
import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import time
from collections import defaultdict


# --- Конфигурация ---
@dataclass
class Config:
    BOT_TOKEN: str = "8020015583:AAG9OrL9l8QNwzcgqCWnd9LmapVMFGKU8Ag"
    MODEL_NAME: str = "NeuroSpaceX/ruSpamNS_v6"
    SPAM_THRESHOLD: float = 0.7
    MAX_MESSAGE_LENGTH: int = 512
    RATE_LIMIT: int = 1000  # сообщений в минуту
    CACHE_SIZE: int = 1000  # размер кэша для результатов


class SpamLevel(Enum):
    HAM = "ham"
    SUSPICIOUS = "suspicious"
    SPAM = "spam"


# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- Кэш для модели ---
class SpamCache:
    def __init__(self, maxsize: int = 1000):
        self.cache = {}
        self.maxsize = maxsize
        self.access_times = {}

    def get(self, text: str) -> Optional[bool]:
        if text in self.cache:
            self.access_times[text] = time.time()
            return self.cache[text]
        return None

    def set(self, text: str, value: bool):
        if len(self.cache) >= self.maxsize:
            # Удаляем самую старую запись
            oldest = min(self.access_times, key=self.access_times.get)
            del self.cache[oldest]
            del self.access_times[oldest]

        self.cache[text] = value
        self.access_times[text] = time.time()


# --- Модель для определения спама ---
class SpamDetector:
    def __init__(self, model_name: str, threshold: float = 0.7):
        self.threshold = threshold
        self.device = torch.device('cpu')
        self.cache = SpamCache()

        logger.info(f"Загрузка модели {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()
        logger.info("Модель успешно загружена")

    def preprocess_text(self, text: str) -> str:
        """Очистка текста перед обработкой"""
        if not text:
            return ""
        # Удаляем лишние пробелы, приводим к нижнему регистру
        text = " ".join(text.split())
        # Ограничиваем длину
        return text[:1000]

    def analyze(self, text: str) -> tuple[SpamLevel, float]:
        """
        Анализирует текст и возвращает уровень спама и уверенность
        """
        text = self.preprocess_text(text)
        if not text:
            return SpamLevel.HAM, 0.0

        # Проверяем кэш
        cached = self.cache.get(text)
        if cached is not None:
            return SpamLevel.SPAM if cached else SpamLevel.HAM, 1.0

        try:
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )
            inputs = {key: value.to(self.device) for key, value in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)

            probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
            spam_score = probabilities[0][1].item()

            # Определяем уровень спама
            if spam_score > self.threshold:
                level = SpamLevel.SPAM
                is_spam = True
            elif spam_score > self.threshold * 0.7:  # 70% от порога
                level = SpamLevel.SUSPICIOUS
                is_spam = False
            else:
                level = SpamLevel.HAM
                is_spam = False

            # Сохраняем в кэш
            self.cache.set(text, is_spam)

            return level, spam_score

        except Exception as e:
            logger.error(f"Ошибка при анализе текста: {e}", exc_info=True)
            return SpamLevel.HAM, 0.0


# --- Rate limiter ---
class RateLimiter:
    def __init__(self, rate_limit: int = 5):
        self.rate_limit = rate_limit
        self.user_messages = defaultdict(list)

    def is_rate_limited(self, user_id: int) -> bool:
        now = time.time()
        minute_ago = now - 60

        # Очищаем старые сообщения
        self.user_messages[user_id] = [
            msg_time for msg_time in self.user_messages[user_id]
            if msg_time > minute_ago
        ]

        # Проверяем лимит
        if len(self.user_messages[user_id]) >= self.rate_limit:
            return True

        self.user_messages[user_id].append(now)
        return False


# --- Основной класс бота ---
class SpamBot:
    def __init__(self, config: Config):
        self.config = config
        self.bot = Bot(token=config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.detector = SpamDetector(config.MODEL_NAME, config.SPAM_THRESHOLD)
        self.rate_limiter = RateLimiter(config.RATE_LIMIT)

        # Регистрируем обработчики
        self._register_handlers()

    def _register_handlers(self):
        @self.dp.message(Command(commands=["start", "help"]))
        async def cmd_start(message: Message):
            await message.reply(
                "🤖 Бот для определения спама\n\n"
                "Просто отправьте любое сообщение, и я проверю его на спам.\n"
                f"Порог срабатывания: {self.config.SPAM_THRESHOLD}"
            )

        @self.dp.message(Command(commands=["stats"]))
        async def cmd_stats(message: Message):
            stats = f"📊 Статистика:\n"
            stats += f"Размер кэша: {len(self.detector.cache.cache)}/{self.config.CACHE_SIZE}\n"
            stats += f"Порог спама: {self.config.SPAM_THRESHOLD}"
            await message.reply(stats)

        @self.dp.message(Command(commands=["threshold"]))
        async def cmd_threshold(message: Message):
            try:
                new_threshold = float(message.text.split()[1])
                if 0 <= new_threshold <= 1:
                    self.config.SPAM_THRESHOLD = new_threshold
                    self.detector.threshold = new_threshold
                    await message.reply(f"✅ Порог изменен на {new_threshold}")
                else:
                    await message.reply("❌ Порог должен быть от 0 до 1")
            except (IndexError, ValueError):
                await message.reply(f"Текущий порог: {self.config.SPAM_THRESHOLD}")

        @self.dp.message()
        async def handle_message(message: Message):
            # Проверяем rate limit
            if self.rate_limiter.is_rate_limited(message.from_user.id):
                await message.reply("⏰ Слишком много сообщений. Подождите минуту.")
                return

            # Получаем текст из сообщения
            text = message.text or message.caption or ""

            # Анализируем на спам
            level, confidence = self.detector.analyze(text)

            logger.info(
                f"User {message.from_user.id}: '{text[:50]}...' | "
                f"Level: {level.value}, Confidence: {confidence:.3f}"
            )

            # Реагируем в зависимости от уровня спама
            if level == SpamLevel.SPAM:
                try:
                    await message.delete()
                    await message.answer(
                        f"🚫 Обнаружен спам!\n"
                        f"Уверенность: {confidence:.1%}"
                    )
                except Exception as e:
                    logger.error(f"Не удалось удалить сообщение: {e}")
                    await message.reply("🚫 Обнаружен спам")

            elif level == SpamLevel.SUSPICIOUS:
                await message.reply(
                    f"⚠️ Подозрительное сообщение\n"
                    f"Уверенность: {confidence:.1%}"
                )

            else:
                await message.reply("✅ Сообщение безопасно")

            await asyncio.sleep(2.5)


# --- Запуск ---
async def main():
    # Проверяем наличие токена

    config = Config()
    bot = SpamBot(config)

    logger.info("Бот запущен...")
    await bot.dp.start_polling(bot.bot)


if __name__ == "__main__":
    asyncio.run(main())