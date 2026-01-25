import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_with_pseudonym
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

# Настройка логирования
logger = logging.getLogger(__name__)

RP = Router()

# Константы
DISABLED_RATING = -1
MAX_COMMENT_LENGTH = 256
MAX_CLARIFICATION_LENGTH = 100
COMMAND_PREFIXES = ('!', '.', '/')
CACHE_CLEANUP_INTERVAL = 3600  # 1 час в секундах
CACHE_MAX_AGE = 7200  # 2 часа в секундах (максимальное время жизни кэша)


class AgeRating(Enum):
    """Возрастные рейтинги"""
    ZERO_PLUS = 0
    THIRTEEN_PLUS = 13
    EIGHTEEN_PLUS = 18
    DISABLED = DISABLED_RATING


class RPCommand:
    """Класс для представления RP команды"""

    def __init__(self, base_command: str, data: Dict[str, Any]):
        self.base_command = base_command
        self.emoji = data["emoji"]
        self.action_template = data["action"]
        self.rating = data["rating"]

    def get_action(self, gender: str) -> str:
        """Получить действие с учетом пола"""
        return re.sub(r"g\('([^']+)'\)", lambda m: g(m.group(1), gender), self.action_template)


# Словарь всех RP-команд
RP_COMMANDS_DATA = {
    # Физические действия
    'пнуть': {"emoji": "👢", "action": "пну'ул'", "rating": AgeRating.ZERO_PLUS.value},
    'кик': {"emoji": "👢", "action": "пнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'ударить': {"emoji": "👊", "action": "ударg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'шлепнуть': {"emoji": "👋", "action": "шлёпнg('ул')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'толкнуть': {"emoji": "🤜", "action": "толкнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'погладить': {"emoji": "🤗", "action": "погладg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'укусить': {"emoji": "🦷", "action": "укусg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'пощечина': {"emoji": "😮", "action": "даg('ал') пощечину", "rating": AgeRating.THIRTEEN_PLUS.value},
    'дать_пощёчину': {"emoji": "😮", "action": "даg('ал') пощечину", "rating": AgeRating.THIRTEEN_PLUS.value},

    # Ласковые действия
    'обнять': {"emoji": "🫂", "action": "обнg('ял')", "rating": AgeRating.ZERO_PLUS.value},
    'поцеловать': {"emoji": "💋", "action": "поцеловg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'обрыгать': {"emoji": "🤢", "action": "обрыгg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'приласкать': {"emoji": "🥰", "action": "приласкg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'понюхать': {"emoji": "👃", "action": "понюхg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'посадить_на_ручки': {"emoji": "👑", "action": "посадg('ил') на ручки", "rating": AgeRating.ZERO_PLUS.value},
    'покормить': {"emoji": "🍕", "action": "покормg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'согреть': {"emoji": "🔥", "action": "согреg('л')", "rating": AgeRating.ZERO_PLUS.value},

    # Весёлые действия
    'подмигнуть': {"emoji": "😉", "action": "подмигнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'пощекотать': {"emoji": "😆", "action": "пощекотg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'испугать': {"emoji": "😱", "action": "испугаg('л')", "rating": AgeRating.ZERO_PLUS.value},
    'пожать_руку': {"emoji": "🤝", "action": "пожg('ал') руку", "rating": AgeRating.ZERO_PLUS.value},
    'подставить_щёку': {"emoji": "😊", "action": "подставg('ил') щёку", "rating": AgeRating.ZERO_PLUS.value},

    # Драматические действия
    'предать': {"emoji": "🗡️", "action": "предаg('л')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'простить': {"emoji": "🤍", "action": "простg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'спасти': {"emoji": "🛡️", "action": "спасg('ла')", "rating": AgeRating.ZERO_PLUS.value},
    'вылечить': {"emoji": "💊", "action": "вылечg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'пленить': {"emoji": "🦊", "action": "пленg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},

    # Еда/напитки
    'напоить': {"emoji": "🍵", "action": "напоg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'угостить': {"emoji": "🍰", "action": "угостg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'угостить_чаем': {"emoji": "☕", "action": "угостg('ил') чаем", "rating": AgeRating.ZERO_PLUS.value},

    # Специальные
    'похвалить': {"emoji": "⭐", "action": "похвалg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'поблагодарить': {"emoji": "🙏", "action": "поблагодарg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'поздравить': {"emoji": "🎉", "action": "поздравg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'пригласить_на_свидание': {"emoji": "💌", "action": "пригласg('ил') на свидание",
                               "rating": AgeRating.THIRTEEN_PLUS.value},
    'сделать_предложение': {"emoji": "💍", "action": "сделg('ал') предложение", "rating": AgeRating.THIRTEEN_PLUS.value},
}

# Создаем объекты команд
RP_COMMANDS = {key: RPCommand(key, value) for key, value in RP_COMMANDS_DATA.items()}

# Карта рейтингов для отображения
RATING_DISPLAY = {
    DISABLED_RATING: "❌ отключены",
    0: "0+ (для всех)",
    13: "13+ (для подростков)",
    18: "18+ (для взрослых)"
}

# Допустимые значения рейтингов
ALLOWED_RATINGS = [DISABLED_RATING, 0, 13, 18]


class CacheManager:
    """Менеджер кэша с автоматической очисткой"""

    def __init__(self):
        self.cache_usage = defaultdict(dict)  # Статистика использования кэша
        self.last_cleanup = datetime.now()
        self.cache_stats = {"hits": 0, "misses": 0, "cleared": 0}
        self.ratings_cache = {}  # Кэш рейтингов чатов
        self.cache_lock = asyncio.Lock()

    async def start_cleanup_task(self):
        """Запустить задачу автоматической очистки кэша"""
        asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """Периодическая очистка устаревшего кэша"""
        while True:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
                await self.cleanup_old_cache()
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки кэша: {e}")

    async def cleanup_old_cache(self):
        """Очистка устаревших записей кэша"""
        try:
            current_time = datetime.now()

            async with self.cache_lock:
                # Удаляем устаревшие записи из кэша
                keys_to_remove = []
                for chat_id, cache_data in self.ratings_cache.items():
                    if "timestamp" in cache_data:
                        cache_age = current_time - cache_data["timestamp"]
                        if cache_age > timedelta(seconds=CACHE_MAX_AGE):
                            keys_to_remove.append(chat_id)

                for key in keys_to_remove:
                    del self.ratings_cache[key]
                    self.cache_stats["cleared"] += 1

                if keys_to_remove:
                    logger.info(f"Кэш очищен. Очищено записей: {len(keys_to_remove)}")
                    self.last_cleanup = current_time

            # Логируем статистику
            self.log_cache_stats()

        except Exception as e:
            logger.error(f"Ошибка при очистке кэша: {e}")

    def log_cache_stats(self):
        """Логирование статистики использования кэша"""
        try:
            cache_size = len(self.ratings_cache)
            logger.debug(
                f"Кэш статистика: hits={self.cache_stats['hits']}, misses={self.cache_stats['misses']}, "
                f"cleared={self.cache_stats['cleared']}, currsize={cache_size}"
            )
        except Exception as e:
            logger.error(f"Ошибка логирования статистики кэша: {e}")

    def record_cache_hit(self, chat_id: int):
        """Запись попадания в кэш"""
        self.cache_stats["hits"] += 1
        self.cache_usage[chat_id]["last_access"] = datetime.now()

    def record_cache_miss(self, chat_id: int):
        """Запись промаха кэша"""
        self.cache_stats["misses"] += 1
        self.cache_usage[chat_id]["last_access"] = datetime.now()

    async def get_cached_rating(self, chat_id: int) -> Optional[int]:
        """Получить рейтинг из кэша"""
        async with self.cache_lock:
            cache_data = self.ratings_cache.get(chat_id)
            if cache_data and "rating" in cache_data:
                self.record_cache_hit(chat_id)
                return cache_data["rating"]
        return None

    async def set_cached_rating(self, chat_id: int, rating: int):
        """Установить рейтинг в кэш"""
        async with self.cache_lock:
            self.ratings_cache[chat_id] = {
                "rating": rating,
                "timestamp": datetime.now()
            }

    async def invalidate_cache(self, chat_id: int = None):
        """Инвалидировать кэш"""
        async with self.cache_lock:
            if chat_id is None:
                self.ratings_cache.clear()
            elif chat_id in self.ratings_cache:
                del self.ratings_cache[chat_id]


# Инициализируем менеджер кэша
cache_manager = CacheManager()


class RPInputParser:
    """Парсер ввода для RP команд"""

    @staticmethod
    def clean_command(text: str) -> str:
        """Очистка команды от префиксов"""
        for prefix in COMMAND_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return text.strip()

    @staticmethod
    def is_mention(part: str) -> bool:
        """Проверяет, является ли часть упоминанием"""
        if not part:
            return False

        # Проверяем различные форматы упоминаний
        return (part.startswith('@') or
                part.startswith('{') or
                part.startswith('[') or
                part.isdigit() or
                part.startswith('tg://user?id=') or
                'id=' in part or
                'user=' in part)

    @staticmethod
    def parse_text(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Парсит текст команды формата:
        {команда} {@/ссылка/ответ} {уточнение}\n{комментарий}

        Возвращает: (команда, упоминание, уточнение, комментарий)
        """
        try:
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
            if not lines:
                return None, None, None, None

            # Обрабатываем первую строку (команда с аргументами)
            command_line = RPInputParser.clean_command(lines[0])
            parts = command_line.split()

            if not parts:
                return None, None, None, None

            # Ищем команду
            base_command = parts[0].lower()

            # Нормализуем команду (заменяем пробелы на подчеркивания для поиска)
            normalized_command = base_command.replace(' ', '_')

            # Ищем соответствующую команду
            command_obj = None
            for cmd_key, cmd_obj in RP_COMMANDS.items():
                if normalized_command.startswith(cmd_key):
                    command_obj = cmd_obj
                    base_command = cmd_key  # Используем каноническое имя
                    break

            if not command_obj:
                return None, None, None, None

            # Обрабатываем остальные части
            mention = None
            clarification_parts = []

            for i, part in enumerate(parts[1:], 1):
                if mention is None and RPInputParser.is_mention(part):
                    # Если это первое упоминание - сохраняем его КАК ЕСТЬ
                    mention = part
                    continue

                # Всё остальное - часть уточнения
                clarification_parts.append(part)

            clarification = ' '.join(clarification_parts) if clarification_parts else None

            # Извлекаем комментарий (все строки после первой)
            comment = '\n'.join(lines[1:]) if len(lines) > 1 else None

            return base_command, mention, clarification, comment

        except Exception as e:
            logger.error(f"Ошибка парсинга RP команды: {e}", exc_info=True)
            return None, None, None, None


class RPChecker:
    """Класс для проверок RP команд"""

    @staticmethod
    async def ensure_rp_rating_column(pool) -> None:
        """Убедиться, что колонка min_rp_rating существует в таблице chats"""
        try:
            async with pool.acquire() as conn:
                column_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'chats' 
                        AND column_name = 'min_rp_rating'
                    )
                """)

                if not column_exists:
                    await conn.execute('''
                        ALTER TABLE chats 
                        ADD COLUMN IF NOT EXISTS min_rp_rating INTEGER DEFAULT 0
                    ''')
                    await conn.execute('''
                        UPDATE chats SET min_rp_rating = 0 WHERE min_rp_rating IS NULL
                    ''')
        except Exception as e:
            logger.error(f"Ошибка при проверке колонки min_rp_rating: {e}")
            raise

    @staticmethod
    async def get_cached_chat_rating(chat_id: int) -> int:
        """Получить кэшированный рейтинг чата"""
        # Пробуем получить из кэша
        cached_rating = await cache_manager.get_cached_rating(chat_id)
        if cached_rating is not None:
            return cached_rating

        cache_manager.record_cache_miss(chat_id)

        pool = get_db_pool()
        await RPChecker.ensure_rp_rating_column(pool)

        async with pool.acquire() as conn:
            rating = await conn.fetchval('''
                SELECT min_rp_rating FROM chats WHERE chat_id = $1
            ''', chat_id)

            if rating is None:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, 0)
                    ON CONFLICT (chat_id) DO NOTHING
                ''', chat_id)
                rating = 0

            if rating not in ALLOWED_RATINGS:
                rating = 0
                await conn.execute('''
                    UPDATE chats SET min_rp_rating = $1 WHERE chat_id = $2
                ''', rating, chat_id)

        # Сохраняем в кэш
        await cache_manager.set_cached_rating(chat_id, rating)
        return rating

    @staticmethod
    async def get_chat_rating_uncached(chat_id: int) -> int:
        """Получить рейтинг чата без использования кэша"""
        pool = get_db_pool()
        await RPChecker.ensure_rp_rating_column(pool)

        async with pool.acquire() as conn:
            rating = await conn.fetchval('''
                SELECT min_rp_rating FROM chats WHERE chat_id = $1
            ''', chat_id)

            if rating is None:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, 0)
                    ON CONFLICT (chat_id) DO NOTHING
                ''', chat_id)
                rating = 0

            if rating not in ALLOWED_RATINGS:
                rating = 0
                await conn.execute('''
                    UPDATE chats SET min_rp_rating = $1 WHERE chat_id = $2
                ''', rating, chat_id)

        # Инвалидируем кэш для этого чата и обновляем его
        await cache_manager.invalidate_cache(chat_id)
        await cache_manager.set_cached_rating(chat_id, rating)

        return rating

    @staticmethod
    async def is_command_allowed(chat_id: int, command_rating: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверяет, разрешена ли RP-команда с данным рейтингом в чате.

        Возвращает: (разрешено, сообщение_об_ошибке)
        """
        try:
            chat_min_rating = await RPChecker.get_cached_chat_rating(chat_id)

            if chat_min_rating == DISABLED_RATING:
                return False, await RPChecker.get_rp_disabled_message(command_rating, chat_id)

            if command_rating <= chat_min_rating:
                return True, None

            return False, await RPChecker.get_rp_disabled_message(command_rating, chat_id)

        except Exception as e:
            logger.error(f"Ошибка проверки команды: {e}", exc_info=True)
            return False, {"text": "❌ Произошла ошибка при проверке разрешений"}

    @staticmethod
    async def get_rp_disabled_message(rating: int, chat_id: int) -> Dict[str, Any]:
        """Получить сообщение о том, что RP отключены"""
        rating_display = RATING_DISPLAY.get(rating, f"{rating}+")

        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Включить РП {rating_display}",
            callback_data=f"enable_rp:{rating}:{chat_id}"
        )
        builder.adjust(1)

        return {
            "text": f"❌ РП-команды отключены в этом чате.\nХотите включить РП-команды с рейтингом {rating_display}?",
            "reply_markup": builder.as_markup()
        }

    @staticmethod
    def validate_comment(comment: str) -> Tuple[bool, Optional[str]]:
        """Проверка комментария"""
        if len(comment) > MAX_COMMENT_LENGTH:
            return False, f'❌ Длина комментария не должна превышать {MAX_COMMENT_LENGTH} символов!'
        return True, None

    @staticmethod
    def validate_clarification(clarification: str) -> Tuple[bool, Optional[str]]:
        """Проверка уточнения"""
        if len(clarification) > MAX_CLARIFICATION_LENGTH:
            return False, f'❌ Длина уточнения не должна превышать {MAX_CLARIFICATION_LENGTH} символов!'
        return True, None


class RPUserResolver:
    """Класс для разрешения пользователей в RP командах"""

    @staticmethod
    async def resolve_target_user(m: Message, mention: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Получить целевого пользователя для RP-команды

        Приоритет:
        1. Ответ на сообщение (reply)
        2. Упоминание в тексте (все типы) - ВСЕГДА через resolve_id

        Возвращает словарь с ID пользователя и объектом пользователя
        """
        try:
            target_id = None
            user_obj = None

            # 1. Проверяем reply
            if m.reply_to_message and m.reply_to_message.from_user:
                target_id = m.reply_to_message.from_user.id
                user_obj = m.reply_to_message.from_user
                logger.debug(f"Найден target_id из reply: {target_id}")

            # 2. Если есть упоминание - ВСЕГДА пропускаем через resolve_id КАК ЕСТЬ
            elif mention:
                logger.debug(f"Пытаемся разрешить упоминание через resolve_id: {mention}")

                # Передаем упоминание КАК ЕСТЬ, без очистки
                target_id = await resolve_id(m, mention)

                if target_id:
                    logger.debug(f"resolve_id вернул ID: {target_id}")
                    try:
                        chat = await m.bot.get_chat(target_id)
                        # Создаем минимальный объект пользователя
                        user_obj = type('MinimalUser', (), {
                            'id': chat.id,
                            'first_name': chat.first_name or "",
                            'last_name': chat.last_name or "",
                            'username': chat.username
                        })()
                    except Exception as e:
                        logger.error(f"Ошибка получения данных пользователя {target_id}: {e}")
                else:
                    logger.warning(f"resolve_id не смог разрешить упоминание: {mention}")

            if target_id:
                return {
                    'id': target_id,
                    'user_obj': user_obj
                }

            logger.debug("Не удалось определить целевого пользователя")
            return None

        except Exception as e:
            logger.error(f"Ошибка разрешения пользователя: {e}", exc_info=True)
            return None

    @staticmethod
    def validate_users(admin_user, target_user) -> Tuple[bool, Optional[str]]:
        """Проверка пользователей"""
        if not target_user:
            return False, "❌ Не удалось определить пользователя"

        if admin_user.id == target_user['id']:
            return False, "❌ Нельзя взаимодействовать с самим собой!"

        return True, None


class RPFormatter:
    """Класс для форматирования RP сообщений"""

    @staticmethod
    async def format_rp_message(
            command: RPCommand,
            admin_id: int,
            target_user: Dict[str, Any],
            chat_id: int,
            clarification: Optional[str] = None,
            comment: Optional[str] = None
    ) -> str:
        """Форматировать RP-сообщение"""
        try:
            # Получаем пол администратора
            admin_gender = await get_user_gender(admin_id)

            # Получаем действие с учетом пола
            action = command.get_action(admin_gender)

            # Создаем ссылки через user_link_with_pseudonym
            admin_link = await user_link_with_pseudonym(admin_id, chat_id)
            target_link = await user_link_with_pseudonym(target_user['id'], chat_id)

            # Формируем сообщение
            message_parts = [f"{command.emoji} | {admin_link} {action} {target_link}"]

            # Добавляем уточнение
            if clarification:
                RPFormatter._add_clarification(message_parts, clarification)

            # Добавляем комментарий
            if comment:
                RPFormatter._add_comment(message_parts, comment)

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"Ошибка форматирования сообщения: {e}", exc_info=True)
            return "❌ Произошла ошибка при создании сообщения"

    @staticmethod
    def _add_clarification(message_parts: List[str], clarification: str) -> None:
        """Добавить уточнение к сообщению"""
        # Обрабатываем предлоги
        preposition_pattern = r'^(по|на|за|в|с|к|у|о|об|от|до|из|без|под|над|перед|при|про|через)\s+'

        if re.match(preposition_pattern, clarification.lower()):
            message_parts[0] += f" {clarification}"
        else:
            message_parts[0] += f". {clarification.capitalize()}"

    @staticmethod
    def _add_comment(message_parts: List[str], comment: str) -> None:
        """Добавить комментарий к сообщению"""
        if len(comment) > MAX_COMMENT_LENGTH:
            comment = comment[:MAX_COMMENT_LENGTH - 3] + "..."
        message_parts.append(f"💬 Комментарий: {comment}")


class RPSettingsHandler:
    """Обработчик настроек RP"""

    @staticmethod
    async def set_rp_rating(chat_id: int, rating: int) -> bool:
        """Установить рейтинг RP для чата"""
        try:
            if rating not in ALLOWED_RATINGS:
                return False

            pool = get_db_pool()
            await RPChecker.ensure_rp_rating_column(pool)

            async with pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id) 
                    DO UPDATE SET min_rp_rating = $2
                ''', chat_id, rating)

            # Инвалидируем кэш для этого чата
            await cache_manager.invalidate_cache(chat_id)

            return True

        except Exception as e:
            logger.error(f"Ошибка установки рейтинга RP: {e}", exc_info=True)
            return False

    @staticmethod
    def parse_rating_argument(arg: str) -> Tuple[bool, Optional[int]]:
        """Парсинг аргумента рейтинга"""
        try:
            rating_str = arg.strip()

            if not rating_str.isdigit():
                return False, None

            rating = int(rating_str)

            # Определяем в какую группу попадает рейтинг
            if rating >= 18:
                return True, 18
            elif rating >= 13:
                return True, 13
            else:
                return True, 0

        except Exception:
            return False, None


async def cleanup_cache_on_startup():
    """Запустить очистку кэша при старте"""
    await cache_manager.start_cleanup_task()
    logger.info("Задача автоматической очистки кэша запущена")


# Основной обработчик RP команд
async def handle_rp_command(m: Message) -> None:
    """Основной обработчик RP команд"""
    try:
        chat_id = m.chat.id
        text = m.text.strip()

        logger.debug(f"Обработка RP команды: {text[:50]}...")

        # Парсим команду
        base_command, mention, clarification, comment = RPInputParser.parse_text(text)

        if not base_command:
            logger.debug("Не удалось распарсить базовую команду")
            return

        logger.debug(f"Распаршено: команда={base_command}, упоминание={mention}, уточнение={clarification}")

        # Получаем объект команды
        command = RP_COMMANDS.get(base_command)
        if not command:
            logger.debug(f"Команда {base_command} не найдена в RP_COMMANDS")
            return

        # Проверяем ограничения по рейтингу
        allowed, error_message = await RPChecker.is_command_allowed(chat_id, command.rating)

        if not allowed:
            if error_message:
                await m.answer(**error_message)
            return

        # Валидируем комментарий
        if comment:
            is_valid, error_msg = RPChecker.validate_comment(comment)
            if not is_valid:
                await m.answer(error_msg)
                return

        # Валидируем уточнение
        if clarification:
            is_valid, error_msg = RPChecker.validate_clarification(clarification)
            if not is_valid:
                await m.answer(error_msg)
                return

        # Получаем целевого пользователя
        target_user_data = await RPUserResolver.resolve_target_user(m, mention)

        if not target_user_data:
            await m.answer("❌ Не удалось определить пользователя. Укажите пользователя через ответ или упоминание.")
            return

        logger.debug(f"Целевой пользователь определен: ID={target_user_data['id']}")

        # Проверяем валидность пользователей
        is_valid, error_msg = RPUserResolver.validate_users(m.from_user, target_user_data)
        if not is_valid:
            await m.answer(error_msg)
            return

        # Форматируем и отправляем сообщение
        formatted_message = await RPFormatter.format_rp_message(
            command=command,
            admin_id=m.from_user.id,
            target_user=target_user_data,
            chat_id=chat_id,
            clarification=clarification,
            comment=comment
        )

        await m.answer(formatted_message, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка обработки RP команды: {e}", exc_info=True)
        await m.answer("❌ Произошла ошибка при обработке команды")


@RP.message(F.text.regexp(r'^[+\-]?рп\b'))
async def handle_rp_settings_command(m: Message):
    """Обработчик команд управления настройками RP"""
    try:
        text = m.text.strip().lower()

        # Команда отключения RP
        if text.startswith('-рп'):
            success = await RPSettingsHandler.set_rp_rating(m.chat.id, DISABLED_RATING)
            if success:
                await m.answer("✅ РП-команды отключены в этом чате")
            else:
                await m.answer("❌ Произошла ошибка при отключении РП")
            return

        # Убираем префикс + если есть
        if text.startswith('+рп'):
            text = 'рп' + text[3:]

        # Обработка команды установки рейтинга
        pattern = r'^рп\s+(.+)$'
        match = re.match(pattern, text, re.IGNORECASE)

        if not match:
            # Показываем текущие настройки
            current_rating = await RPChecker.get_cached_chat_rating(m.chat.id)
            current_display = RATING_DISPLAY.get(current_rating, f"{current_rating}+")

            # Создаем клавиатуру с быстрыми действиями
            builder = InlineKeyboardBuilder()
            builder.button(text="🔴 Отключить РП", callback_data="rp_settings:disable")
            builder.button(text="🟢 0+", callback_data="rp_settings:0")
            builder.button(text="🟡 13+", callback_data="rp_settings:13")
            builder.button(text="🔴 18+", callback_data="rp_settings:18")
            builder.adjust(2, 2)

            await m.answer(
                f"📊 Текущие настройки РП:\n"
                f"Рейтинг: {current_display}\n\n"
                f"Доступные команды:\n"
                f"• <code>+рп 0</code> - только детские команды\n"
                f"• <code>+рп 13</code> - + подростковые команды\n"
                f"• <code>+рп 18</code> - все РП команды\n"
                f"• <code>-рп</code> - отключить все РП",
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            return

        args = match.group(1).strip()

        # Парсим рейтинг
        success, rating = RPSettingsHandler.parse_rating_argument(args.split()[0])

        if not success:
            await m.answer(
                "❌ Некорректный формат команды.\n\n"
                "Используйте:\n"
                "• <code>+рп 18</code> - разрешить все РП\n"
                "• <code>+рп 13</code> - разрешить РП 13+\n"
                "• <code>+рп 0</code> - разрешить только РП 0+\n"
                "• <code>-рп</code> - отключить все РП",
                parse_mode="HTML"
            )
            return

        # Устанавливаем новый рейтинг
        success = await RPSettingsHandler.set_rp_rating(m.chat.id, rating)

        if success:
            rating_display = RATING_DISPLAY.get(rating, f"{rating}+")
            await m.answer(f"✅ Установлен рейтинг РП: {rating_display}")
        else:
            await m.answer("❌ Произошла ошибка при установке рейтинга")

    except Exception as e:
        logger.error(f"Ошибка обработки настроек RP: {e}", exc_info=True)
        await m.answer("❌ Произошла ошибка при обработке команды")


@RP.callback_query(F.data.startswith("enable_rp:"))
async def handle_enable_rp_callback(callback: CallbackQuery):
    """Обработчик callback для включения RP"""
    try:
        # Разбираем callback_data: enable_rp:{rating}:{chat_id}
        data_parts = callback.data.split(":")
        if len(data_parts) != 3:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        _, rating_str, chat_id_str = data_parts
        rating = int(rating_str)
        chat_id = int(chat_id_str)

        # Устанавливаем новый рейтинг
        success = await RPSettingsHandler.set_rp_rating(chat_id, rating)

        if not success:
            await callback.answer("❌ Ошибка при включении РП", show_alert=True)
            return

        # Обновляем сообщение
        rating_display = RATING_DISPLAY.get(rating, f"{rating}+")
        admin_mention = callback.from_user.mention_html(callback.from_user.first_name)

        try:
            await callback.message.edit_text(
                f"✅ РП-команды включены!\n"
                f"Текущий рейтинг: {rating_display}\n\n"
                f"👮🏻 Администратор: {admin_mention}",
                parse_mode="HTML",
                reply_markup=None
            )
        except TelegramBadRequest:
            # Если сообщение уже было изменено, просто отвечаем
            pass

        await callback.answer(f"✅ РП рейтинг установлен: {rating_display}")

    except ValueError:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка обработки enable_rp callback: {e}", exc_info=True)
        await callback.answer(f"❌ Произошла ошибка: {str(e)}", show_alert=True)


@RP.callback_query(F.data.startswith("rp_settings:"))
async def handle_rp_settings_callback(callback: CallbackQuery):
    """Обработчик callback для быстрой настройки RP"""
    try:
        action = callback.data.split(":")[1]

        if action == "disable":
            rating_to_set = DISABLED_RATING
            rating_display = "отключены"
        else:
            rating_to_set = int(action)
            rating_display = RATING_DISPLAY.get(rating_to_set, f"{rating_to_set}+")

        # Устанавливаем новый рейтинг
        success = await RPSettingsHandler.set_rp_rating(callback.message.chat.id, rating_to_set)

        if not success:
            await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)
            return

        # Обновляем сообщение
        await callback.message.edit_text(
            f"✅ Настройки РП обновлены!\n"
            f"Новый рейтинг: {rating_display}\n\n"
            f"👮🏻 Администратор: {callback.from_user.mention_html(callback.from_user.first_name)}",
            parse_mode="HTML",
            reply_markup=None
        )

        await callback.answer(f"✅ РП установлен: {rating_display}")

    except Exception as e:
        logger.error(f"Ошибка обработки rp_settings callback: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# Регистрируем обработчик для всех RP команд
ALL_RP_COMMANDS = '|'.join(RP_COMMANDS.keys())
RP_PATTERN = rf'^[!./]?({ALL_RP_COMMANDS})(?:\s|$)'


@RP.message(F.text.regexp(RP_PATTERN, flags=re.IGNORECASE))
async def handle_all_rp_commands(m: Message):
    """Обработчик всех RP-команд"""
    await handle_rp_command(m)