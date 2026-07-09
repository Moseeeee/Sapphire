import io
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Tuple, Optional, Dict, List, Any

import aiohttp
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from cachetools import TTLCache

from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettingsDB import (
    add_scheduled_change, get_all_active_changes, get_change_by_id, delete_change, get_changes_by_type,
    create_scheduled_changes_table,
    get_statistics
)
from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.chat_settings_service import (
    get_auto_chat_service, init_auto_chat_service, shutdown_auto_chat_service,
    test_service_status, force_check_now
)
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_by_token
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string, MOSCOW_TZ
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_agent_access, \
    auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup

logger = logging.getLogger(__name__)
auto_chat_router = Router()

# ==================== КОНСТАНТЫ И НАСТРОЙКИ ====================

# Только команды для автоматических изменений
AUTO_CHANGE_COMMANDS = {
    'название': 'title',
    'имя': 'title',
    'описание': 'description',
    'аватарка': 'avatar',
    'аватар': 'avatar'
}

TYPE_DISPLAY = {
    'title': {'nom': 'название', 'gen': 'названия', 'acc': 'название', 'emoji': '🏷️'},
    'description': {'nom': 'описание', 'gen': 'описания', 'acc': 'описание', 'emoji': '📝'},
    'avatar': {'nom': 'аватарка', 'gen': 'аватарки', 'acc': 'аватарку', 'emoji': '🖼️'}
}

REPEAT_TYPE_MAPPING = {
    'одноразово': 'once', 'разово': 'once', 'раз': 'once', 'однократно': 'once',
    'ежедневно': 'daily', 'каждый день': 'daily', 'день': 'daily',
    'еженедельно': 'weekly', 'каждую неделю': 'weekly', 'неделя': 'weekly', 'неделю': 'weekly',
    'ежемесячно': 'monthly', 'каждый месяц': 'monthly', 'месяц': 'monthly',
    'ежегодно': 'yearly', 'каждый год': 'yearly', 'год': 'yearly',
    'once': 'once', 'daily': 'daily', 'weekly': 'weekly', 'monthly': 'monthly', 'yearly': 'yearly'
}

REPEAT_TYPE_DISPLAY = {
    'once': 'одноразово', 'daily': 'ежедневно',
    'weekly': 'еженедельно', 'monthly': 'ежемесячно', 'yearly': 'ежегодно'
}

RELATIVE_DAYS = {'сегодня': 0, 'завтра': 1, 'послезавтра': 2, 'послезавтр': 2}

# Лимиты
CHANGE_LIMIT_MINUTES = 5
USER_COMMAND_LIMIT = 10
USER_COMMAND_WINDOW = 60
CACHE_CLEANUP_INTERVAL = 3600
BATCH_SIZE = 10
BATCH_FLUSH_INTERVAL = 5


async def check_change_time_conflict(chat_id: int, change_type: str, target_time: datetime) -> Tuple[
    bool, Optional[str]]:
    """
    Проверяет, нет ли конфликта по времени для данного типа изменения.
    Интервал между изменениями одного типа должен быть не менее CHANGE_LIMIT_MINUTES.
    """
    # Приводим целевое время к naive в Московском часовом поясе для корректного сравнения с БД
    target_naive = target_time.astimezone(MOSCOW_TZ).replace(tzinfo=None)
    type_name = TYPE_DISPLAY[change_type]['nom']

    # 1. Проверяем кэш недавно выполненных изменений (защита для немедленных "+команд")
    cache_key = f"last_executed:{chat_id}:{change_type}"
    last_executed = change_cache.get(cache_key)
    if last_executed:
        last_executed_naive = last_executed.astimezone(MOSCOW_TZ).replace(tzinfo=None)
        time_diff = abs((target_naive - last_executed_naive).total_seconds()) / 60
        if time_diff < CHANGE_LIMIT_MINUTES:
            return False, (
                f"❌ Слишком близко к недавнему изменению!\n"
                f"Интервал между сменой {TYPE_DISPLAY[change_type]['gen']} должен быть не менее {CHANGE_LIMIT_MINUTES} минут.\n"
                f"Предыдущее изменение было/запланировано около: {last_executed_naive.strftime('%H:%M')}"
            )

    # 2. Проверяем запланированные изменения в базе данных
    active_changes = await get_all_active_changes(chat_id)
    for change in active_changes:
        if change['change_type'] == change_type:
            sched_time = change['scheduled_time']  # Из БД приходит уже naive в MOSCOW_TZ
            time_diff = abs((target_naive - sched_time).total_seconds()) / 60

            # Строго меньше 5 минут — значит конфликт. Если ровно 5 минут (12:55 и 13:00), то пропустит.
            if time_diff < CHANGE_LIMIT_MINUTES:
                return False, (
                    f"❌ Конфликт времени! На {sched_time.strftime('%d.%m в %H:%M')} уже запланировано "
                    f"{type_name}.\n"
                    f"⏳ Установите время с разницей как минимум в {CHANGE_LIMIT_MINUTES} минут от этой даты."
                )

    return True, None


async def update_change_time(chat_id: int, change_type: str, execution_time: Optional[datetime] = None):
    """Обновляет время последнего выполненного изменения в кэше."""
    cache_key = f"last_executed:{chat_id}:{change_type}"
    exec_time = execution_time or datetime.now(MOSCOW_TZ)
    change_cache.set(cache_key, exec_time, CHANGE_LIMIT_MINUTES * 60)





# ==================== ОПТИМИЗИРОВАННЫЙ МЕНЕДЖЕР СЕССИЙ ====================

class BotSessionPool:
    """Пул соединений для всех ботов"""
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.sessions = {}
            cls._instance.connectors = {}
            cls._instance.stats = defaultdict(int)
        return cls._instance

    async def get_session(self, bot_token: str) -> aiohttp.ClientSession:
        """Получает или создаёт сессию для бота"""
        if bot_token not in self.sessions or self.sessions[bot_token].closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,
                sock_read=20
            )
            self.sessions[bot_token] = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'Connection': 'keep-alive'}
            )
            self.stats['sessions_created'] += 1

        self.stats['sessions_used'] += 1
        return self.sessions[bot_token]

    async def close_all(self):
        """Закрывает все сессии"""
        for session in self.sessions.values():
            await session.close()
        for connector in self.connectors.values():
            await connector.close()
        self.sessions.clear()
        self.connectors.clear()
        logger.info(f"Сессии закрыты. Статистика: {dict(self.stats)}")


session_pool = BotSessionPool()


# ==================== КЭШИРОВАНИЕ ====================

class OptimizedCache:
    """Многоуровневое кэширование с автоматической очисткой"""

    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        self.l1_cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.stats = defaultdict(int)
        self._cleanup_task = None

    async def start_cleanup_task(self):
        """Запускает фоновую очистку"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """Периодическая очистка"""
        while True:
            await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
            self.l1_cache.expire()
            self.stats['cleanups'] += 1
            logger.debug(f"Кэш очищен. Размер: {len(self.l1_cache)}")

    def get(self, key: str) -> Any:
        """Получает значение из кэша"""
        self.stats['gets'] += 1
        return self.l1_cache.get(key)

    def set(self, key: str, value: Any, ttl: int = None):
        """Устанавливает значение в кэш"""
        self.stats['sets'] += 1
        self.l1_cache[key] = value

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Массовое получение значений"""
        return {k: self.l1_cache.get(k) for k in keys if k in self.l1_cache}

    def clear(self):
        """Очищает кэш"""
        self.l1_cache.clear()
        self.stats['manual_clears'] += 1


# Глобальные экземпляры кэша
change_cache = OptimizedCache(maxsize=5000, ttl=300)
avatar_cache = OptimizedCache(maxsize=1000, ttl=3600)
user_rate_cache = OptimizedCache(maxsize=10000, ttl=60)


# ==================== ОПТИМИЗИРОВАННЫЙ МЕНЕДЖЕР АВАТАРОК ====================

class AvatarManager:
    """Оптимизированный менеджер для работы с аватарками"""

    def __init__(self):
        self._pending = asyncio.Queue()
        self._batch = []
        self._processor_task = None
        self._stats = defaultdict(int)
        self._file_cache = TTLCache(maxsize=500, ttl=600)
        self._avatar_previews = TTLCache(maxsize=200, ttl=300)

    async def start(self):
        """Запускает фоновый процессор батчей"""
        self._processor_task = asyncio.create_task(self._batch_processor())
        logger.info("AvatarManager запущен")

    async def stop(self):
        """Останавливает процессор"""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        await self._flush_batch()
        logger.info(f"AvatarManager остановлен. Статистика: {dict(self._stats)}")

    async def _batch_processor(self):
        """Обрабатывает батчи аватарок"""
        while True:
            try:
                while len(self._batch) < BATCH_SIZE:
                    try:
                        item = await asyncio.wait_for(
                            self._pending.get(),
                            timeout=BATCH_FLUSH_INTERVAL
                        )
                        self._batch.append(item)
                    except asyncio.TimeoutError:
                        break

                if self._batch:
                    await self._process_batch(self._batch)
                    self._batch.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в batch_processor: {e}")
                await asyncio.sleep(1)

    async def _flush_batch(self):
        """Принудительно обрабатывает текущий батч"""
        if self._batch:
            await self._process_batch(self._batch)
            self._batch.clear()

    async def apply_avatar(self, bot: Bot, chat_id: int, file_id: str,
                           priority: bool = False) -> bool:
        """Применяет изменение аватарки с приоритетами"""
        try:
            cache_key = f"avatar:{chat_id}"
            cached = avatar_cache.get(cache_key)
            if cached == file_id:
                self._stats['cache_hits'] += 1
                return True

            if priority:
                self._stats['priority_applies'] += 1
                return await self._apply_single(bot, chat_id, file_id)

            await self._pending.put((bot, chat_id, file_id))
            self._stats['queued'] += 1
            return True

        except Exception as e:
            self._stats['errors'] += 1
            logger.error(f"Ошибка в apply_avatar: {e}")
            return False

    async def get_avatar_preview(self, bot: Bot, file_id: str) -> Optional[BufferedInputFile]:
        """Получает превью аватарки для просмотра"""
        cache_key = f"preview:{file_id}"

        if cache_key in self._avatar_previews:
            self._stats['preview_cache_hits'] += 1
            return self._avatar_previews[cache_key]

        try:
            file_content = await self._get_file_content_cached(bot, file_id)
            if file_content:
                photo_file = BufferedInputFile(
                    file=file_content,
                    filename=f"avatar_{file_id}.jpg"
                )
                self._avatar_previews[cache_key] = photo_file
                self._stats['preview_cache_misses'] += 1
                return photo_file
        except Exception as e:
            self._stats['preview_errors'] += 1
            logger.error(f"Ошибка получения превью: {e}")

        return None

    async def _process_batch(self, batch: List[tuple]):
        """Обрабатывает группу аватарок"""
        self._stats['batches_processed'] += 1
        self._stats['batch_size'] += len(batch)

        by_bot = defaultdict(list)
        for bot, chat_id, file_id in batch:
            by_bot[bot.token].append((bot, chat_id, file_id))

        tasks = []
        for token, items in by_bot.items():
            tasks.append(self._process_bot_batch(token, items))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_bot_batch(self, token: str, items: List[tuple]):
        """Обрабатывает батч для конкретного бота"""
        session = await session_pool.get_session(token)

        for bot, chat_id, file_id in items:
            try:
                file_content = await self._get_file_content_cached(bot, file_id)
                if not file_content:
                    continue

                data = aiohttp.FormData()
                data.add_field('chat_id', str(chat_id))
                data.add_field('photo', file_content,
                               filename='avatar.jpg',
                               content_type='image/jpeg')

                async with session.post(
                        f"https://api.telegram.org/bot{token}/setChatPhoto",
                        data=data
                ) as response:
                    result = await response.json()

                    if result.get('ok'):
                        avatar_cache.set(f"avatar:{chat_id}", file_id, 3600)
                        self._stats['applies'] += 1
                    else:
                        self._stats['api_errors'] += 1
                        logger.error(f"API ошибка: {result}")

            except Exception as e:
                self._stats['batch_errors'] += 1
                logger.error(f"Ошибка в батче: {e}")

            await asyncio.sleep(0.05)

    async def _get_file_content_cached(self, bot: Bot, file_id: str) -> Optional[bytes]:
        """Получает контент файла с кэшированием"""
        cache_key = f"file:{file_id}"

        if cache_key in self._file_cache:
            self._stats['file_cache_hits'] += 1
            return self._file_cache[cache_key]

        try:
            file = await bot.get_file(file_id)
            file_content = io.BytesIO()
            await bot.download_file(file.file_path, file_content)
            file_content.seek(0)
            data = file_content.read()

            self._file_cache[cache_key] = data
            self._stats['file_cache_misses'] += 1

            return data

        except Exception as e:
            self._stats['file_errors'] += 1
            logger.error(f"Ошибка получения файла: {e}")
            return None

    async def _apply_single(self, bot: Bot, chat_id: int, file_id: str) -> bool:
        """Немедленное применение одного изменения"""
        try:
            file_content = await self._get_file_content_cached(bot, file_id)
            if not file_content:
                return False

            session = await session_pool.get_session(bot.token)

            data = aiohttp.FormData()
            data.add_field('chat_id', str(chat_id))
            data.add_field('photo', file_content,
                           filename='avatar.jpg',
                           content_type='image/jpeg')

            async with session.post(
                    f"https://api.telegram.org/bot{bot.token}/setChatPhoto",
                    data=data
            ) as response:
                result = await response.json()

                if result.get('ok'):
                    avatar_cache.set(f"avatar:{chat_id}", file_id, 3600)
                    self._stats['single_applies'] += 1
                    return True
                else:
                    self._stats['single_errors'] += 1
                    return False

        except Exception as e:
            self._stats['single_exceptions'] += 1
            logger.error(f"Ошибка в apply_single: {e}")
            return False

    def get_stats(self) -> dict:
        """Возвращает статистику"""
        return dict(self._stats)


avatar_manager = AvatarManager()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def validate_repeat_type(repeat_type: str) -> Tuple[bool, str]:
    """Проверяет и нормализует тип повторения."""
    if not repeat_type or repeat_type.strip() == '':
        return True, 'once'

    normalized = REPEAT_TYPE_MAPPING.get(repeat_type.lower(), 'once')
    valid_types = ['once', 'daily', 'weekly', 'monthly', 'yearly']

    if normalized not in valid_types:
        russian_types = ['одноразово', 'еженедельно', 'ежемесячно', 'ежегодно']
        return False, f"<b>Неверный тип повторения.</b>\nДоступные: {', '.join(russian_types)}"

    return True, normalized


def validate_text_length(text: str, max_length: int, field_name: str) -> Tuple[bool, str]:
    """Валидирует длину текста."""
    if len(text) > max_length:
        return False, f"❌ {field_name} не может превышать {max_length} символов (сейчас: {len(text)})"
    return True, ""


def get_help_text() -> str:
    """Возвращает справку по командам."""
    return f"""
🤖 <b>Автоматические изменения чата</b>

<b>📝 Команды:</b>
<code>+название [дата/время?] [повторение?]</code>
<code>Текст названия</code>

<code>+описание [дата/время?] [повторение?]</code>
<code>Текст описания</code>

<code>+аватарка [дата/время?] [повторение?]</code>
(с фото в сообщении или в ответ на фото)

<b>⚡ Если дата не указана - изменение применяется СЕЙЧАС!</b>

<b>📅 Форматы даты/времени:</b>
• <code>завтра 14:30</code>
• <code>через 2 часа</code>
• <code>25.12 15:00</code>
• <code>25.12.2024 18:30</code>
• <code>послезавтра</code> (00:00)
• <code>через 30 минут</code>
• <code>через 10 дней</code>

<b>🔄 Типы повторения:</b>
• <code>одноразово</code> - ТОЛЬКО один раз 
• <code>еженедельно</code> - каждую неделю
• <code>ежемесячно</code> - каждый месяц
• <code>ежегодно</code> - каждый год

<b>🖼️ Просмотр аватарок:</b>
<code>аватарки чата</code> - список всех запланированных аватарок
(можно листать и просматривать превью)

<b>✅ Примеры:</b>
<code>+название завтра 14:30
Мой новый чат</code>

<code>+название
Новый чат сейчас</code>

<code>+аватарка 25.12 15:00</code> + фото

⚙️ <b>Управление:</b>
• <code>названия чата</code> - список названий
• <code>аватарки чата</code> - список аватарок (с превью)
• <code>описания чата</code> - список описаний
• <code>изменения чата</code> - все изменения

⚠️ <b>Важно:</b> Каждый тип можно менять не чаще {CHANGE_LIMIT_MINUTES} минут!
"""


# ==================== ОПТИМИЗИРОВАННЫЕ ФУНКЦИИ ПРОВЕРКИ ЛИМИТОВ ====================

async def check_change_rate_limit(chat_id: int, change_type: str) -> Tuple[bool, Optional[str]]:
    """Оптимизированная проверка лимита с кэшированием"""
    cache_key = f"rate_limit:{chat_id}:{change_type}"

    last_change = change_cache.get(cache_key)
    if last_change:
        now = datetime.now(MOSCOW_TZ)
        time_diff = (now - last_change).total_seconds() / 60

        if time_diff < CHANGE_LIMIT_MINUTES:
            minutes_left = int(CHANGE_LIMIT_MINUTES - time_diff)
            type_name = TYPE_DISPLAY[change_type]['acc']
            return False, (
                f"❌ Слишком часто! {type_name.capitalize()} можно менять "
                f"не чаще раза в {CHANGE_LIMIT_MINUTES} минут.\n"
                f"⏳ Следующее изменение через {minutes_left} мин"
            )

    return True, None



async def check_user_rate_limit(user_id: int) -> Tuple[bool, Optional[str]]:
    """Проверяет лимит команд от пользователя с кэшированием"""
    cache_key = f"user_rate:{user_id}"

    count = user_rate_cache.get(cache_key) or 0

    if count >= USER_COMMAND_LIMIT:
        return False, f"❌ Слишком много команд! Подождите {USER_COMMAND_WINDOW} секунд."

    user_rate_cache.set(cache_key, count + 1, USER_COMMAND_WINDOW)
    return True, None


# ==================== ОПТИМИЗИРОВАННЫЙ ПАРСЕР ====================

@lru_cache(maxsize=1000)
def parse_command_type(command: str) -> Optional[str]:
    """Кэшированный парсер типа команды"""
    return AUTO_CHANGE_COMMANDS.get(command.lower())


@lru_cache(maxsize=500)
def parse_repeat_type_cached(repeat_str: str) -> str:
    """Кэшированный парсер типа повторения"""
    if not repeat_str:
        return 'once'
    return REPEAT_TYPE_MAPPING.get(repeat_str.lower(), 'once')


def parse_datetime_natural(text: str) -> Tuple[Optional[datetime], Optional[str], bool]:
    """Парсит дату и время из текста."""
    if not text:
        return None, None, False

    text = text.lower().strip()
    now = datetime.now(MOSCOW_TZ)

    if text == 'сейчас':
        return now, None, True

    for day, offset in RELATIVE_DAYS.items():
        if text.startswith(day):
            if len(text) == len(day):
                dt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
                return dt, None, True
            else:
                time_part = text[len(day):].strip()
                time_match = re.search(r'(\d{1,2}):(\d{1,2})', time_part)
                if time_match:
                    hour, minute = map(int, time_match.groups())
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=offset)
                        return dt, None, True

    date_patterns = [
        (r'^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{1,2}))?$', 'full'),
        (r'^(\d{1,2})\.(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2}))?$', 'short'),
        (r'^(\d{1,2}):(\d{1,2})$', 'time'),
    ]

    for pattern, pattern_type in date_patterns:
        match = re.match(pattern, text)
        if match:
            groups = match.groups()

            if pattern_type == 'full':
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                if groups[3] and groups[4]:
                    hour, minute = int(groups[3]), int(groups[4])
                else:
                    hour, minute = 0, 0

                try:
                    dt = datetime(year, month, day, hour, minute)
                    dt = MOSCOW_TZ.localize(dt)
                    return dt, None, False
                except ValueError:
                    return None, f"❌ Неверная дата: {day}.{month}.{year}", False

            elif pattern_type == 'short':
                day, month = int(groups[0]), int(groups[1])
                year = now.year

                if groups[2] and groups[3]:
                    hour, minute = int(groups[2]), int(groups[3])
                else:
                    hour, minute = 0, 0

                try:
                    dt = datetime(year, month, day, hour, minute)
                    dt = MOSCOW_TZ.localize(dt)

                    if dt < now:
                        dt = datetime(year + 1, month, day, hour, minute)
                        dt = MOSCOW_TZ.localize(dt)

                    return dt, None, False
                except ValueError:
                    return None, f"❌ Неверная дата: {day}.{month}", False

            elif pattern_type == 'time':
                hour, minute = int(groups[0]), int(groups[1])
                dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if dt <= now:
                    dt += timedelta(days=1)

                return dt, None, True

    if text.startswith('через'):
        delta = parse_time_string(text[5:].strip())
        if delta:
            return now + delta, None, True

    delta = parse_time_string(text)
    if delta:
        return now + delta, None, True

    return None, f"❌ Не удалось распарсить дату: {text}", False


def parse_schedule_command(text: str, command_word: str, has_photo: bool = False) -> Optional[Dict]:
    """Парсер команд для автоматических изменений"""
    try:
        change_type = parse_command_type(command_word)
        if not change_type:
            return None

        result = {
            'type': change_type,
            'datetime': None,
            'repeat': 'once',
            'description': '',
            'content': None,
            'has_photo': has_photo
        }

        if not text:
            return result

        parts = text.split('\n', 1)
        first_line = parts[0].strip()
        content = parts[1].strip() if len(parts) > 1 else None

        if first_line:
            dt, error, is_relative = parse_datetime_natural(first_line)

            if dt:
                result['datetime'] = dt
            else:
                words = first_line.split()

                repeat = parse_repeat_type_cached(words[0])
                if repeat != 'once':
                    result['repeat'] = repeat
                    if len(words) > 1:
                        remaining = ' '.join(words[1:])
                        dt2, _, _ = parse_datetime_natural(remaining)
                        if dt2:
                            result['datetime'] = dt2
                        else:
                            result['description'] = remaining
                else:
                    dt2, _, _ = parse_datetime_natural(first_line)
                    if dt2:
                        result['datetime'] = dt2
                    else:
                        result['description'] = first_line

        if content:
            result['content'] = content
        elif change_type in ['title', 'description'] and result['description']:
            result['content'] = result['description']
            result['description'] = ''

        return result

    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}", exc_info=True)
        return None


# ==================== ОСНОВНЫЕ ФУНКЦИИ ПРИМЕНЕНИЯ ====================

async def apply_title_change(bot, chat_id: int, new_title: str) -> bool:
    """Оптимизированное применение названия"""
    try:
        await bot.set_chat_title(chat_id, new_title)
        return True
    except Exception as e:
        logger.error(f"Ошибка при изменении названия: {e}")
        return False


async def apply_description_change(bot, chat_id: int, new_description: str) -> bool:
    """Оптимизированное применение описания"""
    try:
        await bot.set_chat_description(chat_id, new_description)
        return True
    except Exception as e:
        logger.error(f"Ошибка при изменении описания: {e}")
        return False


async def apply_avatar_change(bot, chat_id: int, file_id: str, priority: bool = False) -> bool:
    """Оптимизированное применение аватарки через менеджер"""
    return await avatar_manager.apply_avatar(bot, chat_id, file_id, priority)


# ==================== ОСНОВНОЙ ОБРАБОТЧИК ====================

@auto_chat_router.message(
    F.text.startswith(('+название', '+описание', '+аватарка')) |
    F.caption.startswith(('+название', '+описание', '+аватарка'))
)
@rate_limit_with_cleanup(limit=2)
async def handle_auto_change_command(msg: Message):
    """Обработчик команд автоматических изменений"""
    user_id = msg.from_user.id
    chat_id = msg.chat.id

    # Проверка уровня доступа (ранг 39)
    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 39):
        return

    # Защита от спама командами (общий флуд-контроль)
    can_proceed, limit_message = await check_user_rate_limit(user_id)
    if not can_proceed:
        await msg.reply(limit_message)
        return

    try:
        # Извлекаем текст из сообщения или подписи к фото
        text = msg.text or msg.caption
        if not text:
            return

        # Парсим команду и аргументы
        space_pos = text.find(' ')
        if space_pos == -1:
            command = text[1:].lower()
            args = ""
        else:
            command = text[1:space_pos].lower()
            args = text[space_pos + 1:].strip()

        # Проверяем наличие фотографии в самом сообщении или в реплае
        has_photo = bool(msg.photo) or bool(msg.reply_to_message and msg.reply_to_message.photo)
        cmd_data = parse_schedule_command(args, command, has_photo)

        if not cmd_data:
            await msg.reply("❌ Неизвестная команда")
            return

        # 1. Определяем целевое время изменения (сейчас или в будущем)
        target_time = cmd_data['datetime'] if cmd_data['datetime'] is not None else datetime.now(MOSCOW_TZ)

        # 2. Проверяем на конфликт времени с другими задачами в БД или кэше
        can_change, conflict_message = await check_change_time_conflict(chat_id, cmd_data['type'], target_time)
        if not can_change:
            await msg.reply(conflict_message)
            return

        # Исполнение или планирование команды
        if cmd_data['datetime'] is None:
            await _apply_immediate_change(msg, chat_id, cmd_data)
        else:
            await _schedule_future_change(msg, chat_id, user_id, cmd_data)

    except Exception as e:
        await msg.reply("❌ Произошла ошибка")
        logger.error(f"Ошибка в handle_auto_change_command: {e}", exc_info=True)


async def _apply_immediate_change(msg: Message, chat_id: int, cmd_data: dict):
    """Применяет изменение немедленно"""
    if cmd_data['type'] in ['title', 'description']:
        if not cmd_data['content']:
            type_name = TYPE_DISPLAY[cmd_data['type']]['acc']
            await msg.reply(f"❌ Укажите {type_name} на новой строке")
            return

        value = cmd_data['content']
        type_display = TYPE_DISPLAY[cmd_data['type']]

        valid, error = validate_text_length(value, 255, type_display['nom'].capitalize())
        if not valid:
            await msg.reply(error)
            return

        if cmd_data['type'] == 'title':
            success = await apply_title_change(msg.bot, chat_id, value)
        else:
            success = await apply_description_change(msg.bot, chat_id, value)

        if success:
            await update_change_time(chat_id, cmd_data['type'])
            display_text = value
            await msg.reply(f"✅ {type_display['nom'].capitalize()} изменено:\n📝 {display_text}")
        else:
            await msg.reply(f"❌ Не удалось изменить {type_display['acc']}")

    elif cmd_data['type'] == 'avatar':
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
        elif msg.reply_to_message and msg.reply_to_message.photo:
            file_id = msg.reply_to_message.photo[-1].file_id
        else:
            await msg.reply("❌ Прикрепите фото или ответьте на фото")
            return

        success = await apply_avatar_change(msg.bot, chat_id, file_id, priority=True)

        if success:
            await update_change_time(chat_id, 'avatar')
            response = "✅ Аватарка изменена"
            if cmd_data['description']:
                response += f"\n📝 {cmd_data['description']}"
            await msg.reply_photo(file_id, caption=response)
        else:
            await msg.reply("❌ Не удалось изменить аватарку")


async def _schedule_future_change(msg: Message, chat_id: int, user_id: int, cmd_data: dict):
    """Планирует изменение на будущее"""
    now = datetime.now(MOSCOW_TZ)
    if cmd_data['datetime'] <= now:
        await msg.reply("❌ Время должно быть в будущем!")
        return

    if cmd_data['type'] in ['title', 'description']:
        if not cmd_data['content']:
            type_name = TYPE_DISPLAY[cmd_data['type']]['acc']
            await msg.reply(f"❌ Укажите {type_name} на новой строке")
            return

        type_display = TYPE_DISPLAY[cmd_data['type']]
        valid, error = validate_text_length(cmd_data['content'], 255, type_display['nom'].capitalize())
        if not valid:
            await msg.reply(error)
            return

        repeat_type = parse_repeat_type_cached(cmd_data['repeat'])

        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type=cmd_data['type'],
            new_value=cmd_data['content'],
            scheduled_time=cmd_data['datetime'],
            repeat_type=repeat_type,
            created_by=user_id
        )

        if success:
            await update_change_time(chat_id, cmd_data['type'])
            date_str = cmd_data['datetime'].strftime("%d.%m.%Y %H:%M")

            await msg.reply(
                f"<b>✅ Запланировано изменение {type_display['gen']}:</b>\n"
                f"⏰ <b> На когда:</b> {date_str} ({REPEAT_TYPE_DISPLAY[repeat_type]})\n"
                f"🗑️ <b>Чтобы удалить:</b> <code>!удалить {type_display['acc']} [ID]</code>\n\n"
                f"📝 {type_display['nom']}:\n{cmd_data['content']}\n"
            )
        else:
            await msg.reply("❌ Ошибка при планировании")

    elif cmd_data['type'] == 'avatar':
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
        elif msg.reply_to_message and msg.reply_to_message.photo:
            file_id = msg.reply_to_message.photo[-1].file_id
        else:
            await msg.reply("❌ Прикрепите фото")
            return

        repeat_type = parse_repeat_type_cached(cmd_data['repeat'])

        success = await add_scheduled_change(
            chat_id=chat_id,
            change_type='avatar',
            new_value=cmd_data['description'] or "Аватарка",
            scheduled_time=cmd_data['datetime'],
            repeat_type=repeat_type,
            created_by=user_id,
            file_id=file_id,
            notes=cmd_data['description']
        )

        if success:
            await update_change_time(chat_id, 'avatar')
            date_str = cmd_data['datetime'].strftime("%d.%m.%Y %H:%M")

            response = (f"✅ Запланирована смена аватарки:\n"
                        f"⏰ {date_str} ({REPEAT_TYPE_DISPLAY[repeat_type]})")
            if cmd_data['description']:
                response += f"\n\n📝 {cmd_data['description']}"

            await msg.reply_photo(file_id, caption=response)


# ==================== ПРОСМОТР АВАТАРОК С ПРЕВЬЮ ====================

@auto_chat_router.message(F.text.regexp(r'^[!.]?аватарки чата(\s+\d+)?$'))
async def view_avatars_with_preview(msg: Message):
    """Просмотр аватарок с превью и листанием"""
    await _view_avatar_changes(msg)


async def _view_avatar_changes(msg: Message):
    """Просмотр аватарок с превью и листанием"""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    # Парсим номер страницы
    page = 1
    if msg.text:
        text_parts = msg.text.split()
        if len(text_parts) > 1 and text_parts[-1].isdigit():
            if len(text_parts) > 2 or (len(text_parts) == 2 and text_parts[0].startswith(('!', '.'))):
                page = int(text_parts[-1])

    limit = 5
    avatar_changes, total = await get_changes_by_type(chat_id, 'avatar', page, limit)

    if not avatar_changes:
        await msg.reply("🖼️ Нет запланированных аватарок")
        return

    await _send_avatar_preview(msg, avatar_changes, page, total, limit)


async def _send_avatar_preview(msg: Message, changes: List[Dict], page: int, total: int, limit: int):
    """Отправляет превью аватарок"""
    if not changes:
        return

    current_index = 0
    change = changes[current_index]
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    if not change.get('file_id'):
        await msg.reply(f"❌ У аватарки ID: {change['id']} отсутствует файл")
        return

    preview_data = await avatar_manager.get_avatar_preview(msg.bot, change['file_id'])

    if not preview_data:
        await msg.reply(f"❌ Не удалось загрузить аватарку ID: {change['id']}")
        return

    time_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M") if change['scheduled_time'] else "Не указано"
    text = (
        f"🖼️ <b>Аватарки чата</b> (стр. {page}/{total_pages})\n\n"
        f"<b>ID:</b> {change['id']}\n"
        f"<b>⏰ Время:</b> {time_str}\n"
        f"<b>🔄 Повторение:</b> {REPEAT_TYPE_DISPLAY.get(change['repeat_type'], change['repeat_type'])}\n"
    )

    if change.get('notes'):
        text += f"<b>📝 Описание:</b> {change['notes']}\n"

    text += f"\n<b>📊 Всего:</b> {total} изменений"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️", callback_data=f"avatar_prev_{change['id']}_{page}_{current_index}"),
            InlineKeyboardButton(text=f"{current_index + 1}/{len(changes)}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"avatar_next_{change['id']}_{page}_{current_index}")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"avatar_refresh_{page}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"avatar_delete_{change['id']}")
        ]
    ])

    if total_pages > 1:
        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton(text="⬅️ Страница", callback_data=f"avatar_page_{page - 1}"))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton(text="Страница ➡️", callback_data=f"avatar_page_{page + 1}"))

        if page_buttons:
            keyboard.inline_keyboard.append(page_buttons)

    await msg.reply_photo(
        photo=preview_data,
        caption=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


# ==================== CALLBACK ОБРАБОТЧИК НАВИГАЦИИ ====================

@auto_chat_router.callback_query(lambda c: c.data.startswith(('avatar_', 'noop')))
@rate_limit_with_cleanup(limit=1)
async def handle_avatar_navigation(callback: CallbackQuery):
    """Обработка навигации по аватаркам с заменой сообщения"""
    if callback.data == 'noop':
        await callback.answer()
        return

    if not await _check_chat_admin_callback(callback):
        await callback.answer("❌ Нет прав для просмотра", show_alert=True)
        return

    try:
        await callback.answer()

        data_parts = callback.data.split('_')
        action = data_parts[0]

        if action == 'avatar':
            sub_action = data_parts[1]

            if sub_action in ['prev', 'next']:
                change_id = int(data_parts[2])
                page = int(data_parts[3])
                current_index = int(data_parts[4])

                limit = 5
                changes, total = await get_changes_by_type(callback.message.chat.id, 'avatar', page, limit)

                if not changes:
                    await callback.message.edit_caption("🖼️ Нет доступных аватарок", reply_markup=None)
                    return

                if sub_action == 'prev':
                    new_index = current_index - 1 if current_index > 0 else len(changes) - 1
                else:
                    new_index = (current_index + 1) % len(changes)

                new_change = changes[new_index]

                if not new_change.get('file_id'):
                    await callback.message.edit_caption(f"❌ У аватарки ID: {new_change['id']} отсутствует файл")
                    return

                preview_data = await avatar_manager.get_avatar_preview(callback.bot, new_change['file_id'])

                if not preview_data:
                    await callback.message.edit_caption(f"❌ Не удалось загрузить аватарку ID: {new_change['id']}")
                    return

                time_str = new_change['scheduled_time'].strftime("%d.%m.%Y %H:%M") if new_change[
                    'scheduled_time'] else "Не указано"
                total_pages = (total + limit - 1) // limit
                text = (
                    f"🖼️ <b>Аватарки чата</b> (стр. {page}/{total_pages})\n\n"
                    f"<b>ID:</b> {new_change['id']}\n"
                    f"<b>⏰ Время:</b> {time_str}\n"
                    f"<b>🔄 Повторение:</b> {REPEAT_TYPE_DISPLAY.get(new_change['repeat_type'], new_change['repeat_type'])}\n"
                )

                if new_change.get('notes'):
                    text += f"<b>📝 Описание:</b> {new_change['notes']}\n"

                text += f"\n<b>📊 Всего:</b> {total} изменений"

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="◀️",
                                             callback_data=f"avatar_prev_{new_change['id']}_{page}_{new_index}"),
                        InlineKeyboardButton(text=f"{new_index + 1}/{len(changes)}", callback_data="noop"),
                        InlineKeyboardButton(text="▶️",
                                             callback_data=f"avatar_next_{new_change['id']}_{page}_{new_index}")
                    ],
                    [
                        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"avatar_refresh_{page}"),
                        InlineKeyboardButton(text="❌ Удалить", callback_data=f"avatar_delete_{new_change['id']}")
                    ]
                ])

                if total_pages > 1:
                    page_buttons = []
                    if page > 1:
                        page_buttons.append(
                            InlineKeyboardButton(text="⬅️ Страница", callback_data=f"avatar_page_{page - 1}"))
                    if page < total_pages:
                        page_buttons.append(
                            InlineKeyboardButton(text="Страница ➡️", callback_data=f"avatar_page_{page + 1}"))

                    if page_buttons:
                        keyboard.inline_keyboard.append(page_buttons)

                # Заменяем медиа и текст существующего сообщения
                await callback.message.edit_media(
                    media=preview_data,
                    reply_markup=keyboard
                )
                await callback.message.edit_caption(
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

            elif sub_action == 'delete':
                change_id = int(data_parts[2])

                change = await get_change_by_id(change_id)
                if not change:
                    await callback.message.edit_caption("❌ Аватарка уже удалена", reply_markup=None)
                    return

                if change['created_by'] != callback.from_user.id:
                    agent_rang = await check_agent_access(callback.from_user.id)
                    if agent_rang <= 2:
                        await callback.answer("❌ Вы не можете удалить это изменение", show_alert=True)
                        return

                success = await delete_change(change_id)

                if success:
                    await callback.message.delete()
                    await _view_avatar_changes(callback.message)
                else:
                    await callback.answer("❌ Не удалось удалить", show_alert=True)

            elif sub_action == 'refresh':
                await _view_avatar_changes(callback.message)

            elif sub_action == 'page':
                page = int(data_parts[2])
                await _view_avatar_changes(callback.message)

    except Exception as e:
        logger.error(f"Ошибка в навигации по аватаркам: {e}", exc_info=True)
        try:
            await callback.message.edit_caption("❌ Произошла ошибка", reply_markup=None)
        except:
            pass


# ==================== ПРОСМОТР ТЕКСТОВЫХ ИЗМЕНЕНИЙ ====================

@auto_chat_router.message(F.text.regexp(r'^[!.]?(названия чата|описания чата)(\s+\d+)?$'))
async def view_changes_by_type(msg: Message):
    """Просмотр изменений по типу"""
    text = msg.text
    command_text = text.split()[0].replace('!', '').replace('.', '')

    change_type = None
    if 'названия' in command_text:
        change_type = 'title'
    elif 'описания' in command_text:
        change_type = 'description'

    if change_type:
        await _view_text_changes(msg, change_type)


@auto_chat_router.message(F.text.regexp(r'^[!.]?(изменения чата)(\s+\d+)?$'))
async def view_all_changes(msg: Message):
    """Просмотр всех изменений"""
    await _view_text_changes(msg, None)


async def _view_text_changes(msg: Message, change_type: Optional[str]):
    """Просмотр текстовых изменений"""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    page = 1
    text_parts = msg.text.split()
    if len(text_parts) > 1 and text_parts[-1].isdigit():
        if len(text_parts) > 2 or (len(text_parts) == 2 and text_parts[0].startswith(('!', '.'))):
            page = int(text_parts[-1])

    limit = 10
    if change_type:
        changes, total = await get_changes_by_type(chat_id, change_type, page, limit)
        type_display = TYPE_DISPLAY[change_type]
        title = f"{type_display['emoji']} {type_display['gen'].capitalize()}"
    else:
        changes = await get_all_active_changes(chat_id)
        total = len(changes)
        title = "📅 Все изменения"

    if not changes:
        await msg.reply("📭 Нет запланированных изменений")
        return

    response = f"{title} (стр. {page}/{(total + limit - 1) // limit}):\n\n"

    for i, change in enumerate(changes, (page - 1) * limit + 1):
        type_info = TYPE_DISPLAY[change['change_type']]
        time_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M")

        response += (f"{i}. {type_info['emoji']} <b>ID:{change['id']}</b>\n"
                     f"   ⏰ {time_str} ({REPEAT_TYPE_DISPLAY[change['repeat_type']]})\n"
                     f"   📋 {change['new_value']}\n")

    keyboard = None
    if total > limit:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}_{change_type}"),
                InlineKeyboardButton(text=f"{page}/{(total + limit - 1) // limit}", callback_data="noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}_{change_type}")
            ]
        ])

    await msg.reply(response, parse_mode='HTML', reply_markup=keyboard)


# ==================== УДАЛЕНИЕ ИЗМЕНЕНИЙ ====================

@auto_chat_router.message(F.text.regexp(r'^[!/.]удалить (название|аватарку|описание)\s+\d+$'))
async def delete_scheduled_change(msg: Message):
    """Удаляет запланированное изменение"""
    user_id = msg.from_user.id

    if not await auto_check_AccessLevel_for_rang(user_id, msg.chat.id, 39):
        return

    try:
        parts = msg.text.split()
        type_russian = parts[1].lower()
        change_id = int(parts[2])

        type_mapping = {'название': 'title', 'аватарку': 'avatar', 'описание': 'description'}
        change_type = type_mapping.get(type_russian)

        if not change_type:
            await msg.reply("❌ Неверный тип изменения")
            return

        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply("❌ Изменение не найдено")
            return

        if change['change_type'] != change_type:
            await msg.reply(f"❌ Это не {type_russian}")
            return

        if change['created_by'] != user_id:
            agent_rang = await check_agent_access(user_id)
            if agent_rang <= 2:
                await msg.reply("❌ Нет прав на удаление")
                return

        success = await delete_change(change_id)
        if success:
            type_name = TYPE_DISPLAY[change_type]['acc']
            await msg.reply(f"✅ {type_name.capitalize()} (ID: {change_id}) удалена")
        else:
            await msg.reply("❌ Ошибка при удалении")

    except ValueError:
        await msg.reply("❌ Неверный формат ID")
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await msg.reply("❌ Произошла ошибка")


# ==================== ДРУГИЕ КОМАНДЫ ====================

@auto_chat_router.message(Command(commands=['помощь изменения']))
async def show_help(msg: Message):
    """Показывает справку"""
    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 39):
        return
    await msg.reply(get_help_text(), parse_mode='HTML')


@auto_chat_router.message(F.text.regexp(r'^[!/.]статистика изменений$'))
async def view_stats(msg: Message):
    """Показывает статистику по изменениям"""
    chat_id = msg.chat.id

    if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 40):
        return

    try:
        stats = await get_statistics(chat_id)
        if not stats or not stats.get('type_stats'):
            await msg.reply("📭 Нет активных запланированных изменений.")
            return

        response = "📊 <b>Статистика изменений чата:</b>\n\n"
        response += "📈 <b>По типам:</b>\n"

        for type_stat in stats.get('type_stats', []):
            change_type = type_stat['change_type']
            type_info = TYPE_DISPLAY.get(change_type, {'emoji': '📌', 'gen': change_type})
            response += f"  {type_info['emoji']} {type_info['gen'].capitalize()}: {type_stat['count']}\n"

        response += "\n🔄 <b>По повторению:</b>\n"
        for repeat_stat in stats.get('repeat_stats', []):
            response += f"  {REPEAT_TYPE_DISPLAY[repeat_stat['repeat_type']]}: {repeat_stat['count']}\n"

        response += f"\n⏰ <b>Ближайшие изменения (24ч):</b> {stats.get('upcoming_count', 0)}\n"

        avatar_stats = avatar_manager.get_stats()
        response += f"\n🖼️ <b>Статистика аватарок:</b>\n"
        response += f"  Кэш попаданий: {avatar_stats.get('cache_hits', 0)}\n"
        response += f"  Применено: {avatar_stats.get('applies', 0) + avatar_stats.get('single_applies', 0)}\n"
        response += f"  В очереди: {avatar_manager._pending.qsize()}\n"

        await msg.reply(response, parse_mode='HTML')

    except Exception as e:
        await msg.reply("❌ Ошибка при получении статистики.")
        logger.error(f"Ошибка в view_stats: {e}", exc_info=True)


@auto_chat_router.message(F.text.regexp(r'^[!/.]статус изменений$'))
async def check_service_status(msg: Message):
    """Проверяет статус сервиса"""
    if msg.from_user.id != sanor_ID:
        return

    try:
        status = await test_service_status(msg.bot)
        if 'error' in status:
            response = f"❌ Сервис не инициализирован: {status['error']}"
        else:
            response = (
                f"📊 <b>Статус сервиса:</b>\n"
                f"🔄 Статус: {'✅ Запущен' if status['is_running'] else '⛔ Остановлен'}\n"
                f"⏰ Интервал: {status['check_interval']} сек\n"
                f"🤖 ID бота: {status['bot_id']}\n\n"
                f"📈 <b>Производительность:</b>\n"
                f"• Кэш изменений: {len(change_cache.l1_cache)} записей\n"
                f"• Кэш аватарок: {len(avatar_cache.l1_cache)} записей\n"
                f"• Очередь аватарок: {avatar_manager._pending.qsize()}\n"
                f"• Сессий в пуле: {len(session_pool.sessions)}"
            )

        await msg.reply(response, parse_mode='HTML')
    except Exception as e:
        await msg.reply(f"❌ Ошибка: {e}")


@auto_chat_router.message(F.text.regexp(r'^[!/.]проверить изменения$'))
async def force_check_changes(msg: Message):
    """Принудительная проверка изменений"""
    if msg.from_user.id != sanor_ID:
        return

    try:
        result = await force_check_now(msg.bot)
        if 'error' in result:
            await msg.reply(f"❌ {result['error']}")
        else:
            await msg.reply("✅ Проверка запущена")
    except Exception as e:
        await msg.reply(f"❌ Ошибка: {e}")


@auto_chat_router.message(F.text.regexp(r'^[!/.]тест изменения\s+\d+$'))
async def test_change(msg: Message):
    """Тестирует применение изменения"""
    if msg.from_user.id != sanor_ID:
        return

    try:
        change_id = int(msg.text.split()[-1])
        service = get_auto_chat_service(msg.bot)
        if not service:
            await msg.reply("❌ Сервис не инициализирован")
            return

        change = await get_change_by_id(change_id)
        if not change:
            await msg.reply(f"❌ Изменение {change_id} не найдено")
            return

        can_change, msg_text = await check_change_rate_limit(msg.chat.id, change['change_type'])
        if not can_change:
            await msg.reply(f"⚠️ {msg_text}")
            return

        success = await service.apply_change_now(change_id)
        if success:
            await update_change_time(msg.chat.id, change['change_type'])
            await msg.reply(f"✅ Изменение {change_id} применено")
        else:
            await msg.reply(f"❌ Ошибка применения")

    except Exception as e:
        await msg.reply(f"❌ Ошибка: {e}")


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def _check_chat_admin_callback(callback: CallbackQuery) -> bool:
    """Проверяет права для callback"""
    try:
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id

        agent_rang = await check_agent_access(user_id)
        if agent_rang >= 3:
            return True

        chat_member = await callback.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return False


# ==================== CALLBACK ОБРАБОТЧИКИ ДЛЯ ТЕКСТОВЫХ ИЗМЕНЕНИЙ ====================

@auto_chat_router.callback_query(lambda c: c.data.startswith(('page_', 'noop')))
@rate_limit_with_cleanup(limit=1)
async def handle_pagination(callback: CallbackQuery):
    """Обработка пагинации для текстовых изменений"""
    if callback.data == 'noop':
        await callback.answer()
        return

    if not await _check_chat_admin_callback(callback):
        await callback.answer("❌ Нет прав для просмотра", show_alert=True)
        return

    try:
        await callback.answer()

        _, page, change_type_str = callback.data.split('_')
        page = int(page)
        change_type = change_type_str if change_type_str != 'None' else None

        if page < 1:
            await callback.message.edit_text("📭 Нет изменений", reply_markup=None)
            return

        chat_id = callback.message.chat.id
        limit = 10

        if change_type:
            changes, total = await get_changes_by_type(chat_id, change_type, page, limit)
            type_display = TYPE_DISPLAY[change_type]
            title = f"{type_display['emoji']} {type_display['gen'].capitalize()}"
        else:
            changes = await get_all_active_changes(chat_id)
            total = len(changes)
            title = "📅 Все изменения"

        if not changes:
            await callback.message.edit_text("📭 Нет изменений", reply_markup=None)
            return

        max_page = (total + limit - 1) // limit
        if page > max_page and max_page > 0:
            page = max_page

        response = f"{title} (стр. {page}/{max_page if total > 0 else 1}):\n\n"

        for i, change in enumerate(changes, (page - 1) * limit + 1):
            type_info = TYPE_DISPLAY[change['change_type']]
            time_str = change['scheduled_time'].strftime("%d.%m.%Y %H:%M")

            response += (f"{i}. {type_info['emoji']} <b>ID:{change['id']}</b>\n"
                         f"   ⏰ {time_str} ({REPEAT_TYPE_DISPLAY[change['repeat_type']]})\n"
                         f"   📋 {change['new_value']}\n\n")

        keyboard = None
        if total > limit:
            keyboard_buttons = []

            if page > 1:
                keyboard_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}_{change_type}"))
            else:
                keyboard_buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))

            keyboard_buttons.append(InlineKeyboardButton(text=f"{page}/{max_page}", callback_data="noop"))

            if page < max_page:
                keyboard_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}_{change_type}"))
            else:
                keyboard_buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))

            keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
            refresh_button = InlineKeyboardButton(text="🔄 Обновить", callback_data=f"page_{page}_{change_type}")
            keyboard.inline_keyboard.append([refresh_button])

        await callback.message.edit_text(response, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}", exc_info=True)
        try:
            await callback.message.edit_text("❌ Произошла ошибка", reply_markup=None)
        except:
            pass


# ==================== ИНИЦИАЛИЗАЦИЯ И ЗАВЕРШЕНИЕ ====================

@auto_chat_router.startup()
async def on_startup():
    """Инициализация при старте"""
    await create_scheduled_changes_table()
    await avatar_manager.start()
    await change_cache.start_cleanup_task()

    for cfg in MultiBotConfig.BOTS:
        bot = get_bot_by_token(cfg["TOKEN"])
        if bot:
            await init_auto_chat_service(bot)

    logger.info("Модуль автоматических изменений инициализирован")


@auto_chat_router.shutdown()
async def on_shutdown():
    """Завершение работы"""
    await avatar_manager.stop()
    await session_pool.close_all()

    change_cache.clear()
    avatar_cache.clear()
    user_rate_cache.clear()

    await shutdown_auto_chat_service()

    logger.info("Модуль автоматических изменений остановлен")