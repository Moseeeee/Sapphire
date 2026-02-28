
import asyncio
import datetime
import hashlib
import logging
import re
from typing import Dict, Tuple
from urllib.parse import urlparse, quote

import aiohttp
from aiogram import Router, F
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from handlers.AdminsTools.ChatSettings.settings_link_filter.links_filterDB import (
    get_effective_filter_settings, is_link_allowed,
    get_link_action, toggle_link_filter, set_link_action, add_to_whitelist,
    remove_from_whitelist, get_whitelist, get_whitelisted_links_count,
    clear_chat_whitelist, get_link_filter_status
)
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AdminsTools.CommandsModerations.bans.banDB import get_default_ban_duration
from handlers.AdminsTools.CommandsModerations.mute.mute import perform_mute
from handlers.AdminsTools.CommandsModerations.mute.muteDB import get_default_mute_duration
from handlers.AdminsTools.CommandsModerations.warns.warns import perform_warn_action
from handlers.AdminsTools.CommandsModerations.warns.warnsDB import get_warn_limit, get_warn_action
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.SeasonsEmojiUtils import get_emoji
from handlers.BotAutomaticWork.parse_time_auto import format_duration
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import get_random_text, rate_limit_with_cleanup
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)
link_filter = Router()
VT_API_KEY = "bbb2b6ba9aeaee72547a89909cbd89adf49af8541cbb227454aad1ca875c2233"


# Улучшенные регулярные выражения для разных типов ссылок
URL_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z]{2,})+[^\s]*|'
    r'(?:https?://)?(?:t\.me|telegram\.me)/[^\s]+|'
    r'(?:https?://)?chat\.whatsapp\.com/[^\s]+|'
    r'(?:https?://)?discord\.(?:gg|com/invite)/[^\s]+'
)

REFERRAL_PARAM_REGEX = re.compile(
    r'[?&](?:ref|invite|referral|promo|code|gift|partner|aff|inviteCode|startapp)=[^&\s]+',
    re.IGNORECASE
)

TELEGRAM_SPECIFIC_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|c/|chat/|channel/|s/)',
    re.IGNORECASE
)

DOMAIN_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)'
)


# Кэш для пагинации с ограничением размера
class PaginationCache:
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, Tuple[int, int, int]] = {}  # key: (chat_id, user_id) -> (message_id, page, timestamp)
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}

    def set(self, chat_id: int, user_id: int, message_id: int, page: int):
        """Сохраняет информацию о сообщении пагинации"""
        key = f"{chat_id}_{user_id}"
        self.cache[key] = (message_id, page, int(datetime.datetime.now().timestamp()))
        self.access_times[key] = datetime.datetime.now().timestamp()

        # Очищаем старые записи если кэш переполнен
        if len(self.cache) > self.max_size:
            self._cleanup_old_entries()

    def get(self, chat_id: int, user_id: int) -> Tuple[int, int, int]:
        """Получает информацию о сообщении пагинации"""
        key = f"{chat_id}_{user_id}"
        if key in self.cache:
            self.access_times[key] = datetime.datetime.now().timestamp()
            return self.cache[key]
        return None

    def delete(self, chat_id: int, user_id: int):
        """Удаляет информацию о сообщении пагинации"""
        key = f"{chat_id}_{user_id}"
        if key in self.cache:
            del self.cache[key]
        if key in self.access_times:
            del self.access_times[key]

    def _cleanup_old_entries(self):
        """Очищает старые записи из кэша"""
        if not self.access_times:
            return

        # Находим самые старые записи (половину от максимального размера)
        sorted_keys = sorted(self.access_times.items(), key=lambda x: x[1])
        keys_to_remove = [key for key, _ in sorted_keys[:self.max_size // 2]]

        for key in keys_to_remove:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]

        logger.debug(f"Pagination cache cleanup: removed {len(keys_to_remove)} old entries")


# Глобальный кэш пагинации с ограничением 1000 записей
pagination_cache = PaginationCache(max_size=1000)


async def check_url_virustotal(url: str) -> dict:
    """
    Проверка URL через VirusTotal API v3.
    """
    headers = {
        "x-apikey": VT_API_KEY,
        "Accept": "application/json"
    }

    try:
        # Валидация URL
        parsed = urlparse(url)
        if not parsed.netloc:  # Упрощенная проверка
            return {
                "success": False,
                "error": "Неверный формат URL"
            }

        # Кодируем URL для POST запроса
        encoded_url = quote(url, safe='')

        async with aiohttp.ClientSession() as session:
            # Проверяем существующий анализ
            url_id = hashlib.sha256(url.encode()).hexdigest()

            try:
                async with session.get(
                        f"https://www.virustotal.com/api/v3/urls/{url_id}",
                        headers=headers,
                        timeout=30
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": data.get("data", {}),
                            "is_new": False
                        }
                    elif response.status == 404:
                        # Отправляем на анализ
                        post_data = aiohttp.FormData()
                        post_data.add_field('url', url)

                        async with session.post(
                                "https://www.virustotal.com/api/v3/urls",
                                headers=headers,
                                data=post_data,
                                timeout=30
                        ) as post_response:

                            if post_response.status == 200:
                                submit_data = await post_response.json()
                                analysis_id = submit_data.get("data", {}).get("id")

                                if analysis_id:
                                    # Ждем и получаем результат
                                    await asyncio.sleep(3)

                                    async with session.get(
                                            f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                                            headers=headers,
                                            timeout=30
                                    ) as analysis_response:

                                        if analysis_response.status == 200:
                                            analysis_data = await analysis_response.json()
                                            return {
                                                "success": True,
                                                "data": analysis_data.get("data", {}),
                                                "is_new": True
                                            }

                            return {
                                "success": False,
                                "error": f"Ошибка отправки: {post_response.status}"
                            }
                    else:
                        return {
                            "success": False,
                            "error": f"Ошибка API: {response.status}"
                        }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": "Таймаут запроса к VirusTotal"
                }

    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Сетевая ошибка: {str(e)}"
        }
    except Exception as e:
        logger.error(f"VirusTotal error: {e}")
        return {
            "success": False,
            "error": f"Ошибка: {str(e)}"
        }


def normalize_url_for_check(url: str) -> dict:
    """
    Нормализует URL для проверки в вайтлисте.
    Возвращает словарь с различными вариантами нормализации.
    """
    if not url:
        return {}

    result = {}

    # Оригинальная ссылка
    original = url.strip()
    result['original'] = original

    # Приводим к нижнему регистру
    url_lower = original.lower()
    result['lower'] = url_lower

    # Вариант с https://
    if not url_lower.startswith(('http://', 'https://')):
        result['with_https'] = 'https://' + url_lower
    else:
        result['with_https'] = url_lower

    # Без протокола
    no_protocol = re.sub(r'^https?://', '', url_lower)
    result['no_protocol'] = no_protocol

    # Без www.
    no_www = re.sub(r'^www\.', '', no_protocol)
    result['no_www'] = no_www

    # Для Telegram ссылок - нормализуем t.me/telegram.me
    telegram_normalized = no_www
    if telegram_normalized.startswith('telegram.me/'):
        telegram_normalized = telegram_normalized.replace('telegram.me/', 't.me/', 1)
    elif telegram_normalized.startswith('t.me/'):
        # Убираем возможные дубли протокола
        telegram_normalized = telegram_normalized.replace('https://t.me/', 't.me/')
        telegram_normalized = telegram_normalized.replace('http://t.me/', 't.me/')
    result['telegram_normalized'] = telegram_normalized

    # Для других платформ тоже нормализуем
    # WhatsApp
    if 'chat.whatsapp.com/' in telegram_normalized:
        result['whatsapp_normalized'] = 'chat.whatsapp.com/' + \
                                        telegram_normalized.split('chat.whatsapp.com/')[1].split('?')[0]

    # Discord
    if 'discord.gg/' in telegram_normalized or 'discord.com/invite/' in telegram_normalized:
        discord_part = telegram_normalized.split('/')[-1].split('?')[0]
        result['discord_normalized'] = f'discord.gg/{discord_part}'

    # YouTube
    if 'youtube.com/' in telegram_normalized or 'youtu.be/' in telegram_normalized:
        youtube_id = None
        if 'youtu.be/' in telegram_normalized:
            youtube_id = telegram_normalized.split('youtu.be/')[1].split('?')[0]
        elif 'youtube.com/watch?v=' in telegram_normalized:
            match = re.search(r'v=([a-zA-Z0-9_-]+)', telegram_normalized)
            youtube_id = match.group(1) if match else None

        if youtube_id:
            result['youtube_normalized'] = f'youtu.be/{youtube_id}'

    # Без параметров запроса (для всех ссылок)
    no_params = telegram_normalized.split('?')[0]
    if no_params != telegram_normalized:
        result['no_params'] = no_params

    # Доменная часть (для частичного совпадения)
    if 't.me/' in telegram_normalized:
        result['domain_part'] = 't.me'
    elif 'telegram.me/' in url_lower:
        result['domain_part'] = 'telegram.me'
    elif 'whatsapp.com' in url_lower:
        result['domain_part'] = 'whatsapp.com'
    elif 'discord.gg' in url_lower or 'discord.com' in url_lower:
        result['domain_part'] = 'discord'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        result['domain_part'] = 'youtube'
    elif 'vk.com' in url_lower:
        result['domain_part'] = 'vk.com'
    elif 'facebook.com' in url_lower:
        result['domain_part'] = 'facebook.com'
    elif 'instagram.com' in url_lower:
        result['domain_part'] = 'instagram.com'
    else:
        # Извлекаем домен для других сайтов
        domain_match = re.match(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', no_www)
        if domain_match:
            result['domain_part'] = domain_match.group(1)

    return result


def detect_links(text: str, effective_settings: dict) -> dict:
    """
    Обнаруживает все типы ссылок в тексте.
    Теперь включает ВСЕ ссылки, даже мессенджеры и платформы.
    """
    result = {
        'websites': [],
        'chats': [],
        'referrals': []
    }

    if not text or len(text.strip()) < 5:
        return result

    # Находим все потенциальные URL в тексте
    url_matches = URL_REGEX.finditer(text)

    for match in url_matches:
        url = match.group(0).strip()
        if not url:
            continue

        # Нормализуем URL (добавляем протокол если нужно)
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Флаги для определения типа ссылки
        is_referral = False
        is_telegram_chat = False
        is_website = False

        # 1. Проверяем на реферальные ссылки (ВСЕГДА определяем)
        if REFERRAL_PARAM_REGEX.search(url):
            result['referrals'].append(url)
            is_referral = True
            logger.debug(f"Detected referral link: {url}")

        # 2. Проверяем на Telegram чаты/каналы (ВСЕГДА определяем)
        telegram_match = TELEGRAM_SPECIFIC_REGEX.search(url)
        if telegram_match:
            # Это Telegram чат, канал или группа
            result['chats'].append(url)
            is_telegram_chat = True
            logger.debug(f"Detected Telegram chat/channel: {url}")
        elif ('t.me/' in url.lower() or 'telegram.me/' in url.lower()) and not is_referral:
            # Проверяем, это ссылка на пользователя или на чат
            # Если в ссылке есть параметры или это явно не username
            path_part = url.split('/')[-1].split('?')[0]
            if '?' in url or not re.match(r'^[a-zA-Z0-9_]{5,}$', path_part):
                result['chats'].append(url)
                is_telegram_chat = True
                logger.debug(f"Detected Telegram link (probable chat): {url}")

        # 3. Проверяем на обычные сайты (ВСЕГДА определяем, даже если это мессенджер)
        domain_match = DOMAIN_REGEX.search(url)
        if domain_match:
            domain = domain_match.group(1).lower()

            # Обрабатываем ВСЕ домены, включая мессенджеры
            # Если это не реферальная и не Telegram чат ссылка, добавляем в websites
            if not is_referral and not is_telegram_chat:
                result['websites'].append(url)
                is_website = True
                logger.debug(f"Detected website link: {url}")
            # Если это мессенджер, но не определен как чат или рефералка, все равно обрабатываем
            elif any(domain_part in domain for domain_part in
                     ['whatsapp.com', 'discord.gg', 'discord.com',
                      'play.google.com', 'apps.apple.com', 'vk.com',
                      'youtube.com', 'youtu.be', 'facebook.com', 'instagram.com']):
                result['websites'].append(url)
                is_website = True
                logger.debug(f"Detected platform link: {url}")

        # 4. Если ссылка не попала ни в одну категорию, но похожа на URL
        if not is_referral and not is_telegram_chat and not is_website:
            # Проверяем общий паттерн URL
            url_pattern = re.compile(
                r'https?://[^\s<>"\']+',
                re.IGNORECASE
            )
            if url_pattern.search(url):
                result['websites'].append(url)
                logger.debug(f"Detected generic URL: {url}")

    # Убираем дубликаты и удаляем пустые списки
    for key in result:
        result[key] = list(set(result[key]))

    return {k: v for k, v in result.items() if v}


# Улучшенный should_block_links для обработки всех типов ссылок
async def should_block_links(detected_links: dict, effective_settings: dict, chat_id: int) -> list:
    """
    Проверяет, какие ссылки нужно заблокировать.
    Теперь обрабатывает ВСЕ типы ссылок.
    Возвращает список ссылок для блокировки в формате [(тип, ссылка), ...]
    """
    blocked_links = []

    # Если включен режим "все ссылки", блокируем все найденные ссылки
    if effective_settings.get('filter_all', False):
        for link_type, links in detected_links.items():
            for link in links:
                is_allowed, found_variant = await check_link_in_whitelist(chat_id, link)
                logger.debug(f"Checking '{link}' in 'all links' mode: allowed={is_allowed}")
                if not is_allowed:
                    blocked_links.append((link_type, link))
        return blocked_links

    # Проверяем каждый тип ссылок отдельно
    for link_type, links in detected_links.items():
        # Проверяем, включен ли этот тип фильтрации
        filter_key = f'filter_{link_type}'
        if effective_settings.get(filter_key, False):
            for link in links:
                is_allowed, found_variant = await check_link_in_whitelist(chat_id, link)
                logger.debug(
                    f"Checking '{link}' of type {link_type}: allowed={is_allowed}, filter_enabled={effective_settings.get(filter_key, False)}")

                if not is_allowed:
                    blocked_links.append((link_type, link))

    logger.info(f"Total blocked links found: {len(blocked_links)}")
    return blocked_links


async def get_bot_id_int() -> int:
    """Получает числовой ID бота"""
    try:
        me = await bot.get_me()
        return me.id
    except Exception as e:
        logger.error(f"Error getting bot ID via get_me(): {e}")
        from handlers.BotAutomaticWork.Gonfig.config import bot_id as config_bot_id
        return config_bot_id if config_bot_id else 8020015583


async def handle_blocked_links(message: Message, blocked_links: list):
    """Обрабатывает обнаруженные запрещенные ссылки"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Формируем сообщение о нарушении
    link_types = {
        'websites': 'сайт',
        'chats': 'чат/канал Telegram',
        'referrals': 'реферальная ссылка'
    }

    violation_text = []
    for link_type, link in blocked_links:
        violation_text.append(f"• {link_types.get(link_type, 'ссылка')}: {link}")

    # Получаем действие для применения
    action = await get_link_action(chat_id)

    # Получаем ID бота как число
    bot_id_int = await get_bot_id_int()

    # Получаем информацию о пользователе
    user_link = await user_link_global(user_id)

    # Удаляем сообщение с запрещенными ссылками ПЕРЕД отправкой ответа
    delete_success = False
    try:
        await message.delete()
        delete_success = True
        logger.info(f"Successfully deleted message with blocked links from user {user_id}")
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.error(f"Error deleting message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting message: {e}")

    # Применяем действие
    if action == 'warn':
        # Выдаем варн через существующую систему
        warn_count = await add_warn_for_links(chat_id, user_id, bot_id_int, "\n".join(violation_text))
        warn_limit = await get_warn_limit(chat_id)

        if warn_count >= warn_limit:
            # Достигнут лимит варнов, применяем действие
            action_result = await perform_warn_action(chat_id, user_id, await get_warn_action(chat_id), bot_id_int)
            response_text = (
                f"{get_emoji('warn_emoji')} {user_link} получ{g('ил', await get_user_gender(user_id))} "
                f"варн за запрещенные ссылки ({warn_count}/{warn_limit})\n"
                f"⚠️ Достигнут лимит варнов! {action_result}"
            )
        else:
            response_text = (
                f"{get_emoji('warn_emoji')} {user_link} получ{g('ил', await get_user_gender(user_id))} "
                f"варн за запрещенные ссылки ({warn_count}/{warn_limit})\n\n"
                f"Снять наказание: <code>-варн @{user_id}</code>"
            )

    elif action == 'mute':
        duration = await get_default_mute_duration(chat_id)
        if duration is None:
            duration_str = "навсегда"
        else:
            duration_str = format_duration(duration)

        success, result = await perform_mute(
            chat_id=chat_id,
            user_id=user_id,
            duration=duration,
            admin_id=bot_id_int,
            reason="Запрещенные ссылки"
        )

        response_text = (
            f"🔇 {user_link} был{g('', await get_user_gender(user_id))} замьючен {duration_str} "
            f"за размещение запрещенных ссылок\n"
            f"Снять наказание: <code>.размут @{user_id}</code>"
        )

    elif action == 'ban':
        duration = await get_default_ban_duration(chat_id)
        if duration is None:
            duration_str = "навсегда"
        else:
            duration_str = format_duration(duration)

        success, result = await perform_ban(
            chat_id=chat_id,
            user_id=user_id,
            duration=duration,
            admin_id=bot_id_int,
            reason="Запрещенные ссылки"
        )

        response_text = (
            f"🚫 {user_link} был{g('', await get_user_gender(user_id))} забанен {duration_str} "
            f"за размещение запрещенных ссылки\n\n"
            f"Снять наказание: <code>.разбан @{user_id}</code>"
        )

    elif action == 'kick':
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await asyncio.sleep(1)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            response_text = (
                f"👢 {user_link} был{g('', await get_user_gender(user_id))} кикнут "
                f"за размещение запрещенных ссылок\n"
            )
        except Exception as e:
            logger.error(f"Error kicking user: {e}")
            response_text = (
                f"⚠️ Не удалось кикнуть {user_link} за запрещенные ссылки\n"
            )
    else:
        # Действие по умолчанию - варн
        response_text = (
            f"⚠️ {user_link}, обнаружены запрещенные ссылки в вашем сообщении!\n"
        )

    # Отправляем сообщение о нарушении только если сообщение было удалено
    if delete_success:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=response_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            logger.info(f"Sent violation message for user {user_id}")
        except Exception as e:
            logger.error(f"Error sending violation message: {e}")
    else:
        logger.warning(f"Could not send violation message because original message was not deleted for user {user_id}")


async def add_warn_for_links(chat_id: int, user_id: int, admin_id: int, reason: str) -> int:
    """Добавляет варн за запрещенные ссылки"""
    from handlers.AdminsTools.CommandsModerations.warns.warnsDB import add_warn
    from handlers.AdminsTools.CommandsModerations.warns.warnsDB import get_default_warn_duration

    # Получаем длительность варна по умолчанию
    duration_str = await get_default_warn_duration(chat_id)

    # Проверяем тип duration_str
    duration = None
    if duration_str:
        if isinstance(duration_str, str):
            from handlers.BotAutomaticWork.parse_time_auto import parse_time_string
            try:
                duration = parse_time_string(duration_str)
            except Exception as e:
                logger.error(f"Error parsing warn duration: {e}")
                duration = None
        elif isinstance(duration_str, datetime.timedelta):
            duration = duration_str
        else:
            logger.warning(f"Unexpected duration type: {type(duration_str)}")

    # Добавляем варн
    return await add_warn(chat_id, user_id, admin_id, reason, duration)


async def check_link_in_whitelist(chat_id: int, url: str) -> tuple:
    """
    Проверяет, разрешена ли ссылка в вайтлисте.
    Возвращает (разрешено_ли, найденный_вариант)
    """
    if not url:
        return False, None

    # Нормализуем ссылку
    normalized_variants = normalize_url_for_check(url)

    # Проверяем все варианты
    for variant_name, variant_value in normalized_variants.items():
        is_allowed = await is_link_allowed(chat_id, variant_value)
        if is_allowed:
            logger.info(f"Link '{url}' allowed via variant '{variant_name}': '{variant_value}'")
            return True, (variant_name, variant_value)

    # Если ни один вариант не подошел
    logger.info(f"Link '{url}' not allowed. Variants checked: {list(normalized_variants.keys())}")
    return False, None


async def should_block_links(detected_links: dict, effective_settings: dict, chat_id: int) -> list:
    """
    Проверяет, какие ссылки нужно заблокировать.
    Возвращает список ссылок для блокировки в формате [(тип, ссылка), ...]
    """
    blocked_links = []

    # Если включен режим "все ссылки", блокируем все найденные ссылки
    if effective_settings.get('filter_all', False):
        for link_type, links in detected_links.items():
            for link in links:
                is_allowed, found_variant = await check_link_in_whitelist(chat_id, link)
                logger.info(f"Checking link '{link}' in 'all links' mode: allowed={is_allowed}")
                if not is_allowed:
                    blocked_links.append((link_type, link))
        return blocked_links

    # Проверяем каждый тип ссылок отдельно
    for link_type, links in detected_links.items():
        # Проверяем, включен ли этот тип фильтрации
        filter_key = f'filter_{link_type}'
        if effective_settings.get(filter_key, False):
            for link in links:
                is_allowed, found_variant = await check_link_in_whitelist(chat_id, link)
                logger.info(
                    f"Checking link '{link}' of type {link_type}: allowed={is_allowed}, filter_enabled={effective_settings.get(filter_key, False)}")

                if not is_allowed:
                    blocked_links.append((link_type, link))

    logger.info(f"Final blocked links: {blocked_links}")
    return blocked_links


# Команды управления фильтрацией ссылок
@link_filter.message(F.text.regexp(re.compile(r'^[-+]сайты(\s|$)', re.IGNORECASE)))
async def toggle_websites_filter(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command = message.text.strip().lower()
    enable = command.startswith('+')

    await toggle_link_filter(message.chat.id, 'filter_websites', enable)

    status = "включена" if enable else "отключена"
    status_emoji = "✅" if enable else "❌"

    await message.answer(
        f"{status_emoji} Фильтрация сайтов успешно {status}",
        parse_mode="HTML"
    )


@link_filter.message(F.text.regexp(re.compile(r'^[-+]чаты(\s|$)', re.IGNORECASE)))
async def toggle_chats_filter(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command = message.text.strip().lower()
    enable = command.startswith('+')

    await toggle_link_filter(message.chat.id, 'filter_chats', enable)

    status = "включена" if enable else "отключена"
    status_emoji = "✅" if enable else "❌"

    await message.answer(
        f"{status_emoji} Фильтрация чатов и каналов Telegram успешно {status}",
        parse_mode="HTML"
    )


@link_filter.message(F.text.regexp(re.compile(r'^[-+]рефералы(\s|$)', re.IGNORECASE)))
async def toggle_referrals_filter(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command = message.text.strip().lower()
    enable = command.startswith('+')

    await toggle_link_filter(message.chat.id, 'filter_referrals', enable)

    status = "включена" if enable else "отключена"
    status_emoji = "✅" if enable else "❌"

    await message.answer(
        f"{status_emoji} Фильтрация реферальных ссылок успешно {status}",
        parse_mode="HTML"
    )


@link_filter.message(F.text.regexp(re.compile(r'^[-+]все ссылки(\s|$)', re.IGNORECASE)))
async def toggle_all_links_filter(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command = message.text.strip().lower()
    enable = command.startswith('+')

    await toggle_link_filter(message.chat.id, 'filter_all', enable)

    status = "включена" if enable else "отключена"
    status_emoji = "✅" if enable else "❌"

    if enable:
        await message.answer(
            f"{status_emoji} Фильтрация ВСЕХ типов ссылок успешно {status}\n\n"
            f"⚠️ <b>Внимание:</b> В этом режиме все ссылки будут фильтроваться, "
            f"независимо от индивидуальных настроек.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"{status_emoji} Режим 'все ссылки' отключен\n\n"
            f"Теперь работают индивидуальные настройки фильтрации.",
            parse_mode="HTML"
        )


@link_filter.message(F.text.regexp(re.compile(r'^[+-]вайт ссылка(?:\s+|$)', re.IGNORECASE)))
async def manage_whitelist(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command_text = message.text.strip()
    command = command_text.lower()
    enable = command.startswith('+')

    # Проверяем, есть ли аргумент после команды
    if command.endswith('вайт ссылка') or command.endswith('вайт ссылка '):
        # Команда без аргумента - показываем справку
        help_text = (
            "🔧 <b>Управление вайтлистом ссылок</b>\n\n"
            "📚 <b>Формат команды:</b>\n"
            "<code>+вайт ссылка [ссылка]</code> - добавить ссылку в вайтлист\n"
            "<code>-вайт ссылка [ссылка]</code> - удалить ссылку из вайтлиста\n\n"
            "📝 <b>Примеры использования:</b>\n"
            "<code>+вайт ссылка example.com</code>\n"
            "<code>+вайт ссылка t.me/mychannel</code>\n"
            "<code>+вайт ссылка https://google.com</code>\n"
            "<code>-вайт ссылка badsite.com</code>\n\n"
            "ℹ️ <b>Особенности:</b>\n"
            "• Можно указывать ссылки с http/https или без\n"
            "• Можно использовать частичные совпадения\n"
            "• Для просмотра вайтлиста используйте <code>ссылки вайтлист</code>"
        )

        await message.answer(
            help_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return

    # Команда с аргументом
    url_match = re.search(r'^[+-]вайт ссылка\s+(\S+)', command_text, re.IGNORECASE)

    if not url_match:
        await message.answer(
            "❌ Неверный формат команды!\n"
            "Пример использования:\n"
            "<code>+вайт ссылка example.com</code> - разрешить ссылку\n"
            "<code>-вайт ссылка example.com</code> - запретить ссылку",
            parse_mode="HTML"
        )
        return

    url = url_match.group(1).strip()

    # Валидация ссылки
    if not url or len(url) < 3:
        await message.answer(
            "❌ Ссылка слишком короткая или пустая!",
            parse_mode="HTML"
        )
        return

    # Очищаем ссылку от лишних символов
    url = url.rstrip('.,;:!?')

    if enable:
        success = await add_to_whitelist(message.chat.id, url, message.from_user.id)
        if success:
            # Получаем текущее количество ссылок в вайтлисте
            count = await get_whitelisted_links_count(message.chat.id)
            # Показываем нормализованные варианты
            normalized = normalize_url_for_check(url)
            variants_text = "\n".join([f"<i>{k}:</i> <code>{v}</code>" for k, v in normalized.items()])

            await message.answer(
                f"✅ Ссылка успешно добавлена в вайтлист\n\n"
                f"🔗 <b>Оригинал:</b> <code>{url}</code>\n"
                f"📊 <b>Всего в вайтлисте:</b> {count} ссылок\n\n"
                f"🔍 <b>Нормализованные варианты:</b>\n{variants_text}\n\n"
                f"ℹ️ Для просмотра списка используйте <code>ссылки вайтлист</code>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                f"❌ Не удалось добавить ссылку в вайтлист\n"
                f"Возможно, она уже существует в списке.",
                parse_mode="HTML"
            )
    else:
        success = await remove_from_whitelist(message.chat.id, url)
        if success:
            count = await get_whitelisted_links_count(message.chat.id)
            await message.answer(
                f"✅ Ссылка успешно удалена из вайтлиста\n\n"
                f"🔗 <b>Ссылка:</b> <code>{url}</code>\n"
                f"📊 <b>Осталось в вайтлисте:</b> {count} ссылок",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                f"❌ Ссылка не найдена в вайтлисте\n"
                f"Проверьте правильность написания.",
                parse_mode="HTML"
            )


async def show_whitelist_page(chat_id: int, user_id: int, page: int, message: Message = None,
                              callback_query: CallbackQuery = None):
    """Показывает страницу вайтлиста с пагинацией"""
    whitelist = await get_whitelist(chat_id)
    count = await get_whitelisted_links_count(chat_id)

    if not whitelist:
        if message:
            await message.answer("📋 Вайтлист ссылок пуст.")
        elif callback_query:
            await callback_query.message.edit_text("📋 Вайтлист ссылок пуст.")
        return

    # Настройки пагинации
    ITEMS_PER_PAGE = 10
    total_pages = (count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    # Проверяем корректность номера страницы
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    # Вычисляем начало и конец для текущей страницы
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, count)

    # Формируем заголовок
    response = f"📋 <b>Вайтлист ссылок</b> (стр. {page}/{total_pages}, всего: {count})\n\n"

    # Добавляем ссылки для текущей страницы
    for i in range(start_idx, end_idx):
        item = whitelist[i]
        regex_icon = "🔤" if item['is_regex'] else "🔗"
        added_by = f"👤 {item['added_by']}" if item['added_by'] else ""

        # Показываем номер с учетом пагинации
        item_number = i + 1
        response += f"{item_number}. {regex_icon} <code>{item['pattern']}</code> {added_by}\n"

        # Показываем нормализованную версию для отладки (только для Telegram ссылок)
        normalized = normalize_url_for_check(item['pattern'])
        telegram_norm = normalized.get('telegram_normalized')
        if telegram_norm and telegram_norm != item['pattern'].lower():
            response += f"   ↳ <i>норм.:</i> <code>{telegram_norm}</code>\n"

        # Добавляем пустую строку между записями для читабельности
        if i < end_idx - 1:
            response += "\n"

    # Создаем клавиатуру с кнопками пагинации
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Кнопки навигации
    nav_buttons = []

    # Кнопка "Предыдущая"
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"whitelist_page_{chat_id}_{page - 1}")
        )

    # Информация о странице (только если больше 1 страницы)
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="whitelist_info")
        )

    # Кнопка "Следующая"
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"whitelist_page_{chat_id}_{page + 1}")
        )

    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)

    # Кнопки быстрого удаления (только для первой страницы)
    if page == 1 and count > 0:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🗑️ Очистить вайтлист", callback_data=f"whitelist_clear_{chat_id}")
        ])

    # Кнопка обновления
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"whitelist_page_{chat_id}_{page}")
    ])

    # Отправляем или редактируем сообщение
    if message:
        # Отправляем новое сообщение
        sent_message = await message.reply(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        # Сохраняем в кэш с ограничением
        pagination_cache.set(chat_id, user_id, sent_message.message_id, page)
    elif callback_query:
        # Редактируем существующее сообщение
        try:
            await callback_query.message.edit_text(
                response,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            # Обновляем кэш
            pagination_cache.set(chat_id, user_id, callback_query.message.message_id, page)
        except Exception as e:
            logger.error(f"Error editing whitelist message: {e}")
            # Если сообщение не изменилось, просто отвечаем на callback
            await callback_query.answer()


@link_filter.message(F.text.regexp(re.compile(r'^[!./]ссылки вайтлист(?:\s+|$)', re.IGNORECASE)))
async def show_whitelist_command(message: Message):
    """Обработчик команды для показа вайтлиста"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 66):
        return

    # Показываем первую страницу
    await show_whitelist_page(message.chat.id, message.from_user.id, 1, message)


# Обработчик callback-запросов для пагинации
@link_filter.callback_query(F.data.startswith("whitelist_page_"))
@rate_limit_with_cleanup(limit=1)
async def handle_whitelist_pagination(callback_query: CallbackQuery):
    """Обрабатывает нажатия кнопок пагинации"""
    if (not callback_query.message.reply_to_message or
            callback_query.from_user.id != callback_query.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback_query.answer(f"{random_text}", show_alert=True)
        return
    try:
        # Извлекаем данные из callback
        data_parts = callback_query.data.split("_")
        if len(data_parts) >= 4:
            chat_id = int(data_parts[2])
            page = int(data_parts[3])


            # Показываем запрошенную страницу
            await show_whitelist_page(chat_id, callback_query.from_user.id, page, callback_query=callback_query)
            await callback_query.answer()
        else:
            await callback_query.answer("❌ Ошибка пагинации", show_alert=True)
    except Exception as e:
        logger.error(f"Error in whitelist pagination: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


# Сначала обработчик для подтверждения (более специфичный фильтр)
@link_filter.callback_query(F.data.startswith("whitelist_clear_confirm_"))
@rate_limit_with_cleanup(limit=1)
async def handle_whitelist_clear_confirm(callback_query: CallbackQuery):
    """Подтверждение очистки вайтлиста"""

    if (not callback_query.message.reply_to_message or
            callback_query.from_user.id != callback_query.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback_query.answer(f"{random_text}", show_alert=True)
        return

    try:
        # Извлекаем chat_id из callback
        data_parts = callback_query.data.split("_")
        logger.info(f"whitelist_clear_confirm data parts: {data_parts}")

        if len(data_parts) >= 4:
            # Данные в формате: whitelist_clear_confirm_{chat_id}
            chat_id = int(data_parts[3])


            # Получаем количество ссылок до очистки
            count = await get_whitelisted_links_count(chat_id)

            # Очищаем вайтлист
            deleted_count = await clear_chat_whitelist(chat_id)

            # Удаляем из кэша
            pagination_cache.delete(chat_id, callback_query.from_user.id)

            # Обновляем сообщение
            await callback_query.message.edit_text(
                f"✅ <b>Вайтлист успешно очищен!</b>\n\n"
                f"🗑️ Удалено ссылок: {deleted_count}\n\n"
                f"Вайтлист теперь пуст.",
                parse_mode="HTML"
            )

            # Удаляем клавиатуру
            await callback_query.message.edit_reply_markup(reply_markup=None)
            await callback_query.answer(f"Очищено {deleted_count} ссылок")
        else:
            await callback_query.answer("❌ Ошибка в формате данных", show_alert=True)
    except ValueError as e:
        logger.error(f"Value error in whitelist clear confirm: {e}, data_parts: {data_parts}")
        await callback_query.answer("❌ Ошибка в формате данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error clearing whitelist: {e}")
        await callback_query.answer("❌ Произошла ошибка при очистке", show_alert=True)


# Затем обработчик для запроса очистки (менее специфичный фильтр)
@link_filter.callback_query(F.data.startswith("whitelist_clear_"))
@rate_limit_with_cleanup(limit=1)
async def handle_whitelist_clear(callback_query: CallbackQuery):
    """Обрабатывает запрос очистки вайтлиста (показывает подтверждение)"""

    if (not callback_query.message.reply_to_message or
            callback_query.from_user.id != callback_query.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback_query.answer(f"{random_text}", show_alert=True)
        return

    try:
        # Извлекаем chat_id из callback
        data_parts = callback_query.data.split("_")
        logger.info(f"whitelist_clear data parts: {data_parts}")

        # Проверяем, что это не подтверждение (этот случай уже обработан выше)
        if len(data_parts) >= 3 and data_parts[2] != "confirm":
            # Это обычный запрос очистки
            chat_id = int(data_parts[2])


            # Запрашиваем подтверждение
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, очистить", callback_data=f"whitelist_clear_confirm_{chat_id}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data=f"whitelist_page_{chat_id}_1")
                ]
            ])

            await callback_query.message.edit_text(
                "⚠️ <b>Подтверждение очистки вайтлиста</b>\n\n"
                "Вы уверены, что хотите очистить ВЕСЬ вайтлист ссылок?\n"
                "Это действие нельзя отменить!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await callback_query.answer()
        else:
            # Это подтверждение или неправильный формат, игнорируем
            # (подтверждение уже обработано в handle_whitelist_clear_confirm)
            pass
    except ValueError as e:
        logger.error(f"Value error in whitelist clear: {e}, data_parts: {data_parts}")
        await callback_query.answer("❌ Ошибка в формате данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error in whitelist clear confirmation: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


@link_filter.callback_query(F.data == "whitelist_info")
async def handle_whitelist_info(callback_query: CallbackQuery):
    """Обрабатывает нажатие на информационную кнопку"""
    await callback_query.answer("📖 Информация о странице", show_alert=False)


@link_filter.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?проверить ссылку(?:\s+|$)', re.IGNORECASE)))
async def check_link_virustotal_handler(message: Message):
    """
    Команда для проверки ссылок через VirusTotal.
    """
    # Проверка прав
    if message.chat.type != "private":
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 67):
            return

    # Извлекаем ссылку из команды
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "❌ <b>Неверный формат команды</b>\n\n"
            "📝 <b>Используйте:</b>\n"
            "<code>проверить ссылку [ваша_ссылка]</code>\n\n"
            "📌 <b>Пример:</b>\n"
            "<code>проверить ссылку https://example.com</code>",
            parse_mode="HTML"
        )
        return

    url_to_check = parts[2].strip()

    # Отправляем сообщение о начале проверки
    wait_msg = await message.answer(
        "🔍 <b>Проверяю ссылку...</b>\n"
        "⏳ <i>Запрашиваю данные с VirusTotal</i>",
        parse_mode="HTML"
    )

    # Проверяем ссылку
    result = await check_url_virustotal(url_to_check)

    # Формируем ответ
    if result["success"]:
        data = result["data"]
        attributes = data.get("attributes", {})
        stats = attributes.get("last_analysis_stats", {})
        total = sum(stats.values())

        malicious = stats.get('malicious', 0)
        suspicious = stats.get('suspicious', 0)

        # Определяем статус для первого предложения
        if total == 0:
            opening_phrase = "еще не проверена антивирусами"
            verdict_emoji = "🔍"
        elif malicious == 0 and suspicious == 0:
            opening_phrase = "безопасна"
            verdict_emoji = "✅"
        elif malicious == 0 and suspicious > 0:
            if suspicious <= 3:
                opening_phrase = "в целом безопасна, но есть подозрительные признаки"
                verdict_emoji = "⚠️"
            else:
                opening_phrase = "выглядит подозрительно"
                verdict_emoji = "⚠️"
        elif malicious == 1:
            opening_phrase = "имеет одно вредоносное обнаружение"
            verdict_emoji = "🚨"
        elif malicious == 2:
            opening_phrase = "имеет несколько вредоносных обнаружений"
            verdict_emoji = "🚨"
        elif malicious >= 3 and malicious < 10:
            opening_phrase = "опасна и содержит вредоносные элементы"
            verdict_emoji = "🚨"
        elif malicious >= 10:
            opening_phrase = "крайне опасна и содержит множество угроз"
            verdict_emoji = "⛔"
        else:
            opening_phrase = "требует осторожности"
            verdict_emoji = "⚠️"

        result_virus_check = f"{verdict_emoji} <b>Результат проверки выявил, что ссылка {opening_phrase}.</b>\n"


        check_link = f"🔗 <b>Ссылка:</b> <code>{url_to_check}</code>\n"

        # Форматируем дату
        last_analysis = attributes.get('last_analysis_date')
        if last_analysis:
            from datetime import datetime
            date_obj = datetime.fromtimestamp(last_analysis)
            formatted_date = date_obj.strftime("%d.%m.%Y %H:%M")
            last_data = f"📅 <b>Последняя проверка:</b> {formatted_date}\n\n"
        else:
            last_data = f"📅 <b>Последняя проверка:</b> Неизвестно\n\n"


        # Ссылка на полный отчет
        if "id" in data:
            check_id = f"\n⛓️ <a href='https://www.virustotal.com/gui/url/{data['id']}'>Полный отчет VirusTotal</a>\n"
        if result.get("is_new"):
            check_id = f"\n\n🆕 <i>Это первая проверка данной ссылки</i>"

    else:
        # Ошибка проверки
        response = f"❌ <b>Не удалось проверить ссылку</b>\n\n"
        response += f"<b>Ссылка:</b> <code>{url_to_check[:80]}</code>\n\n"
        response += f"<b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}\n\n"
        response += "📝 <b>Что можно сделать:</b>\n"
        response += "• Проверьте правильность ссылки\n"
        response += "• Попробуйте позже\n"
        response += "• Используйте другую ссылку"

    # Обновляем сообщение с результатами

    response = f'{result_virus_check}{check_link}{last_data}{check_id}'

    try:
        await wait_msg.edit_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except:
        await message.answer(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True
        )


@link_filter.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?ссылки исход(?:\s+|$)', re.IGNORECASE)))
async def set_link_action_cmd(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    command_text = message.text.strip()
    command = command_text.lower()

    # Пытаемся извлечь аргумент
    parts = command.split(maxsplit=2)

    if len(parts) < 3:  # ['ссылки', 'исход'] или ['!ссылки', 'исход']
        # Команда без аргумента - показываем справку с текущим статусом
        try:
            # Получаем текущее действие
            current_action = await get_link_action(message.chat.id)

            action_names = {
                'ban': 'бан',
                'kick': 'кик',
                'warn': 'варн',
                'mute': 'мут'
            }

            current_action_name = action_names.get(current_action, 'варн (по умолчанию)')

            await message.answer(
                f"🔧 <b>Управление действиями за ссылки</b>\n\n"
                f"📋 <b>Текущее действие:</b> {current_action_name}\n\n"
                f"📚 <b>Доступные действия:</b>\n"
                f"<code>бан</code> - забанить пользователя\n"
                f"<code>кик</code> - кикнуть пользователя\n"
                f"<code>варн</code> - выдать предупреждение\n"
                f"<code>мут</code> - замутить пользователя\n\n"
                f"📝 <b>Примеры использования:</b>\n"
                f"<code>ссылки исход бан</code>\n"
                f"<code>ссылки исход варн</code>\n"
                f"<code>ссылки исход мут</code>\n\n"
                f"ℹ️ Выберите действие для применения при обнаружении запрещенных ссылок.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error showing link action help: {e}")
            await message.answer(
                "❌ Неверный формат команды!\n"
                "Используйте: <code>ссылки исход бан|кик|варн|мут</code>",
                parse_mode="HTML"
            )
        return

    # Команда с аргументом (части: [префикс]ссылки исход [действие])
    action = parts[-1].lower()  # Последняя часть - действие
    action_map = {
        'бан': 'ban',
        'кик': 'kick',
        'варн': 'warn',
        'мут': 'mute'
    }

    if action not in action_map:
        await message.answer(
            "❌ Неверное действие!\n\n"
            "📚 <b>Доступные действия:</b>\n"
            "<code>бан</code> - забанить пользователя\n"
            "<code>кик</code> - кикнуть пользователя\n"
            "<code>варн</code> - выдать предупреждение\n"
            "<code>мут</code> - замутить пользователя",
            parse_mode="HTML"
        )
        return

    await set_link_action(message.chat.id, action_map[action])

    # Формируем понятное название действия
    action_names = {
        'ban': 'бан',
        'kick': 'кик',
        'warn': 'варн',
        'mute': 'мут'
    }

    await message.answer(
        f"✅ <b>Действие обновлено!</b>\n\n"
        f"При обнаружении запрещенных ссылок будет применяться: <b>{action_names[action_map[action]]}</b>\n\n"
        f"ℹ️ Чтобы изменить действие, используйте команду снова.",
        parse_mode="HTML"
    )


@link_filter.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?ссылки очистить вайтлист(\s|$)', re.IGNORECASE)))
async def clear_whitelist_cmd(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 65):
        return

    count = await get_whitelisted_links_count(message.chat.id)
    if count == 0:
        await message.answer("📋 Вайтлист ссылок уже пуст.")
        return

    deleted_count = await clear_chat_whitelist(message.chat.id)

    await message.answer(
        f"✅ Вайтлист ссылок успешно очищен (удалено {deleted_count} ссылок)",
        parse_mode="HTML"
    )


@link_filter.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?ссылки статус(\s|$)', re.IGNORECASE)))
async def show_link_settings(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 66):
        return

    status = await get_link_filter_status(message.chat.id)
    effective_settings = status['effective_settings']

    # Формируем понятное название действия
    action_names = {
        'ban': 'бан',
        'kick': 'кик',
        'warn': 'варн',
        'mute': 'мут'
    }

    status_emoji = {
        True: "✅",
        False: "❌"
    }

    response = "🔍 <b>Статус фильтрации ссылок:</b>\n\n"

    if effective_settings['filter_all']:
        response += f"🎯 <b>Режим:</b> Все ссылки\n"
        response += f"{status_emoji[True]} Сайты\n"
        response += f"{status_emoji[True]} Чаты и каналы Telegram\n"
        response += f"{status_emoji[True]} Реферальные ссылки\n\n"
        response += f"⚠️ <i>В этом режиме все ссылки фильтруются</i>\n\n"
    else:
        response += f"🎯 <b>Режим:</b> Индивидуальные настройки\n"
        response += f"{status_emoji[effective_settings['filter_websites']]} Сайты\n"
        response += f"{status_emoji[effective_settings['filter_chats']]} Чаты и каналы Telegram\n"
        response += f"{status_emoji[effective_settings['filter_referrals']]} Реферальные ссылки\n\n"

    response += f"🛡️ <b>Действие при нарушении:</b> {action_names.get(effective_settings['action'], 'варн')}\n\n"

    whitelist_count = status['whitelist_count']
    response += f"📋 <b>Вайтлист:</b> {whitelist_count} разрешенных ссылок"

    await message.answer(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# Хендлер для обработки сообщений с ссылками
async def check_links_in_message(message: Message) -> bool:
    """
    Проверяет сообщение на наличие запрещенных ссылок.
    Возвращает True если сообщение было заблокировано.
    """

    # Быстрая проверка приватного чата
    if message.chat.type == 'private':
        return False

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Пропускаем владельца бота
        if user_id in boss_agent:
            return False

        # Проверяем, является ли отправитель администратором
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                return False
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")

        # Получаем эффективные настройки фильтрации для чата
        effective_settings = await get_effective_filter_settings(chat_id)

        # Проверяем, активен ли какой-либо фильтр
        if not effective_settings.get('filter_all', False) and \
                not any([effective_settings.get('filter_websites', False),
                         effective_settings.get('filter_chats', False),
                         effective_settings.get('filter_referrals', False)]):
            #logger.info(f"No link filtering active for chat {chat_id}")
            return False

        # Извлекаем текст для проверки
        text_to_check = message.text or message.caption or ""

        # Быстрая проверка на наличие URL в тексте
        if not URL_REGEX.search(text_to_check):
            #logger.info(f"No URLs found in message from user {user_id}")
            return False

        # Обнаруживаем все типы ссылок (независимо от настройки)
        detected_links = detect_links(text_to_check, effective_settings)

        # Логирование для отладки
        #logger.info(f"Detected links for user {user_id} in chat {chat_id}: {detected_links}")
        #logger.info(f"Effective settings for chat {chat_id}: {effective_settings}")

        # Проверяем, есть ли вообще ссылки
        if not any(detected_links.values()):
            logger.info(f"No links detected for user {user_id}")
            return False

        # Проверяем, какие ссылки нужно заблокировать
        blocked_links = await should_block_links(detected_links, effective_settings, chat_id)

        #logger.info(f"Should block links result: {blocked_links}")

        if not blocked_links:
            #logger.info(f"No links to block for user {user_id}")
            return False

        # Логирование заблокированных ссылок
        #logger.info(f"Blocked links for user {user_id}: {blocked_links}")

        # Если найдены запрещенные ссылки, применяем действие
        await handle_blocked_links(message, blocked_links)
        return True

    except Exception as e:
        logger.error(f"Error in link filter: {e}", exc_info=True)
        return False