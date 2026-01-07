import logging
import re
from typing import Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs, parse_qsl

from handlers.BotAutomaticWork.users.checks.check_user_idDB import check_username
from handlers.BotAutomaticWork.users.links.users_global_linkDB import user_exists_in_db

logger = logging.getLogger(__name__)

# Константы для ссылок
TG_PROFILE_URL = "https://t.me/{}"
TG_DEEP_LINK = "tg://openmessage?user_id={}"

# Расширенное регулярное выражение для ВСЕХ форматов Telegram
TELEGRAM_FORMATS = re.compile(
    r'^'  # Начало строки
    r'(?:'  # Группа вариантов
    # 1. Простые упоминания
    r'@(\d+)|'  # @12345 → группа 1
    r'@([a-zA-Z0-9_]{5,32})|'  # @username → группа 2 (5-32 символа как в ТГ)

    # 2. t.me ссылки (все варианты)
    r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]{5,32})/?|'  # t.me/username → группа 3
    r'(?:https?://)?(?:www\.)?t\.me/(\+[0-9A-Za-z]+)/?|'  # t.me/+invite → группа 4 (не пользователь)
    r'(?:https?://)?(?:www\.)?t\.me/joinchat/([a-zA-Z0-9_\-]+)/?|'  # t.me/joinchat/invite → группа 5

    # 3. telegram.me ссылки
    r'(?:https?://)?(?:www\.)?telegram\.me/([a-zA-Z0-9_]{5,32})/?|'  # telegram.me/username → группа 6
    r'(?:https?://)?(?:www\.)?telegram\.me/(\+[0-9A-Za-z]+)/?|'  # telegram.me/+invite → группа 7

    # 4. telegram.dog ссылки (альтернативный домен)
    r'(?:https?://)?(?:www\.)?telegram\.dog/([a-zA-Z0-9_]{5,32})/?|'  # telegram.dog/username → группа 8

    # 5. Прямые deep links (уже существующие)
    r'tg://openmessage\?user_id=(\d+)|'  # tg://openmessage?user_id=12345 → группа 9
    r'tg://user\?id=(\d+)|'  # tg://user?id=12345 → группа 10

    # 6. Resolve ссылки для открытия чата
    r'tg://resolve\?(?:domain=([a-zA-Z0-9_]{5,32})|phone=(\+\d+))|'  # tg://resolve?domain=username или phone=+7... → группы 11,12

    # 7. Private invite ссылки
    r'tg://join\?invite=([a-zA-Z0-9_\-]+)|'  # tg://join?invite=xxx → группа 13

    # 8. Ссылки с параметром start (чат с ботом)
    r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]{5,32})\?start=([a-zA-Z0-9_\-]+)|'  # t.me/bot?start=xxx → группы 14,15

    # 9. Ссылки на конкретное сообщение
    r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]{5,32})/(\d+)/?|'  # t.me/username/123 → группы 16,17

    # 10. Ссылки на комментарии в каналах
    r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]{5,32})/(\d+)\?comment=(\d+)|'  # t.me/channel/123?comment=456 → группы 18,19,20

    # 11. Ссылки с thread (ветки)
    r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]{5,32})/(\d+)\?thread=(\d+)'  # t.me/channel/123?thread=456 → группы 21,22,23
    r')'  # Конец группы вариантов
    r'$'  # Конец строки
)

# Регулярное выражение для извлечения username из произвольных ссылок
USERNAME_EXTRACTOR = re.compile(
    r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]{5,32})'
)

# Регулярное выражение для извлечения ID из tg:// ссылок
TG_ID_EXTRACTOR = re.compile(
    r'tg://(?:openmessage|user)\?(?:user_)?id=(\d+)'
)


async def _parse_tg_deeplink(url: str) -> Optional[Tuple[Optional[int], Optional[str]]]:
    """Парсит tg:// ссылки и извлекает информацию о пользователе."""
    try:
        parsed = urlparse(url)
        params = dict(parse_qsl(parsed.query))

        # tg://openmessage?user_id=123
        if parsed.path == '/openmessage' or 'openmessage' in parsed.path:
            user_id = params.get('user_id')
            if user_id and user_id.isdigit():
                return int(user_id), None

        # tg://user?id=123
        elif parsed.path == '/user' or 'user' in parsed.path:
            user_id = params.get('id')
            if user_id and user_id.isdigit():
                return int(user_id), None

        # tg://resolve?domain=username или phone=+7...
        elif parsed.path == '/resolve' or 'resolve' in parsed.path:
            domain = params.get('domain')
            phone = params.get('phone')

            if domain:
                # domain может быть числовым ID, если пользователь скрыл username
                if domain.isdigit():
                    return int(domain), None
                return None, domain
            elif phone:
                # Телефонный номер - ищем в БД по другому полю
                # Здесь нужно добавить логику поиска по телефону
                logger.debug(f"Phone number found: {phone}")
                return None, None

        # tg://join?invite=xxx - не пользователь, а инвайт в группу
        elif parsed.path == '/join' or 'join' in parsed.path:
            logger.debug(f"Group invite link: {url}")
            return None, None

        # tg://msg?to=123 - отправка сообщения
        elif parsed.path == '/msg' or 'msg' in parsed.path:
            user_id = params.get('to')
            if user_id and user_id.isdigit():
                return int(user_id), None

        # tg://addcontact?phone=+7...&first_name=...
        elif parsed.path == '/addcontact' or 'addcontact' in parsed.path:
            phone = params.get('phone')
            # Обработка телефонного номера
            logger.debug(f"Add contact link with phone: {phone}")
            return None, None

        # tg://voicechat?invite=xxx - голосовой чат
        # tg://login?token=xxx - авторизация
        # Эти ссылки не относятся к пользователям

        return None, None

    except Exception as e:
        logger.error(f"Error parsing tg:// link {url}: {e}")
        return None, None


async def _extract_user_info_from_mention(mention: str) -> Optional[Tuple[Optional[int], Optional[str]]]:
    """Извлекает информацию о пользователе из ВСЕХ возможных форматов Telegram."""
    if not mention or not mention.strip():
        return None, None

    mention = mention.strip()

    # 1. Проверка на tg:// ссылки (deep links)
    if mention.startswith('tg://'):
        return await _parse_tg_deeplink(mention)

    # 2. Проверка через расширенное регулярное выражение
    if match := TELEGRAM_FORMATS.fullmatch(mention):
        groups = match.groups()

        # Определяем, какая группа совпала
        for i, group in enumerate(groups, 1):
            if group is not None:
                # Группы с числовыми ID: 1, 9, 10
                if i in (1, 9, 10):
                    try:
                        return int(group), None
                    except (ValueError, TypeError):
                        continue

                # Группы с username: 2, 3, 6, 8, 11, 14, 16, 18, 21
                elif i in (2, 3, 6, 8, 11, 14, 16, 18, 21):
                    # Если username состоит только из цифр, это может быть ID
                    if group.isdigit():
                        try:
                            return int(group), None
                        except (ValueError, TypeError):
                            return None, group
                    return None, group

                # Группа с телефоном: 12
                elif i == 12:
                    # Телефонный номер
                    logger.debug(f"Phone number in mention: {group}")
                    # Здесь можно добавить поиск по телефону в БД
                    return None, None

        return None, None

    # 3. Дополнительные проверки для нестандартных форматов
    # Извлечение username из любой строки, содержащей t.me/...
    if 't.me/' in mention or 'telegram.me/' in mention or 'telegram.dog/' in mention:
        if username_match := USERNAME_EXTRACTOR.search(mention):
            username = username_match.group(1)
            if username.isdigit():
                try:
                    return int(username), None
                except (ValueError, TypeError):
                    return None, username
            return None, username

    # 4. Извлечение ID из любой строки, содержащей tg:// ссылку
    if 'tg://' in mention:
        if id_match := TG_ID_EXTRACTOR.search(mention):
            user_id = id_match.group(1)
            if user_id.isdigit():
                return int(user_id), None

    return None, None


async def _get_user_id_from_username(username: str) -> Optional[int]:
    """Получает user_id по username с проверкой в БД."""
    if not username:
        return None

    user_id = await check_username(username)
    if user_id and await user_exists_in_db(user_id):
        return user_id
    return None


async def _get_user_id_from_id(user_id: int) -> Optional[int]:
    """Проверяет существование user_id в БД."""
    if user_id and await user_exists_in_db(user_id):
        return user_id
    return None


async def resolve_id(
        msg: Optional[Union[dict, object]] = None,
        mention: Optional[str] = None,
        allow_phone_lookup: bool = False
) -> Optional[int]:
    """Извлекает user_id из ВСЕХ возможных источников Telegram.

    Поддерживаемые форматы:
    1. Упоминания: @username, @12345
    2. Веб-ссылки:
       - t.me/username
       - telegram.me/username
       - telegram.dog/username
       - https://t.me/username
       - https://t.me/username/123 (пост)
       - https://t.me/username?start=xxx (бот)
    3. Deep Links:
       - tg://user?id=123
       - tg://openmessage?user_id=123
       - tg://resolve?domain=username
       - tg://resolve?phone=+71234567890
       - tg://msg?to=123
       - tg://addcontact?phone=+7...
    4. Entities сообщения
    5. Ответ на сообщение (reply)

    Args:
        msg: Объект сообщения с entities/reply_to_message
        mention: Текстовое упоминание в любом формате
        allow_phone_lookup: Разрешить поиск по номеру телефона

    Returns:
        Optional[int]: user_id или None, если не найден или нет в БД
    """
    try:
        # 1. Обработка mention (имеет приоритет, если передан)
        if mention:
            user_id, username = await _extract_user_info_from_mention(mention)

            if user_id:
                # Если нашли числовой ID
                return await _get_user_id_from_id(user_id)
            elif username:
                # Если нашли username
                return await _get_user_id_from_username(username)

            # Дополнительная проверка для телефонных номеров
            if allow_phone_lookup and mention.startswith('+'):
                # Здесь можно добавить логику поиска по телефону
                # Например: await _get_user_id_from_phone(mention)
                logger.debug(f"Phone lookup requested for: {mention}")

        # 2. Проверка reply (если передан msg)
        if msg and msg.reply_to_message and msg.reply_to_message.from_user:
            user_id = msg.reply_to_message.from_user.id
            if user_id and await user_exists_in_db(user_id):
                return user_id

        # 3. Проверка entities (если передан msg)
        if msg and hasattr(msg, 'entities') and msg.entities:
            full_text = getattr(msg, 'text', '') or getattr(msg, 'caption', '') or ""

            for entity in msg.entities:
                if entity.type == "text_mention" and hasattr(entity, 'user'):
                    user_id = entity.user.id
                    if result := await _get_user_id_from_id(user_id):
                        return result

                elif entity.type == "mention":
                    # Извлекаем username из текста
                    start = entity.offset
                    end = entity.offset + entity.length
                    if start < len(full_text) and end <= len(full_text):
                        username = full_text[start:end].lstrip('@')
                        if result := await _get_user_id_from_username(username):
                            return result

                elif entity.type == "url":
                    # Обработка ссылок в тексте
                    start = entity.offset
                    end = entity.offset + entity.length
                    if start < len(full_text) and end <= len(full_text):
                        url = full_text[start:end]
                        # Пытаемся извлечь user_id из ссылки
                        extracted_id, extracted_username = await _extract_user_info_from_mention(url)

                        if extracted_id:
                            if result := await _get_user_id_from_id(extracted_id):
                                return result
                        elif extracted_username:
                            if result := await _get_user_id_from_username(extracted_username):
                                return result

        # 4. Проверка text_entities (для некоторых библиотек)
        if msg and hasattr(msg, 'text_entities') and msg.text_entities:
            full_text = getattr(msg, 'text', '') or getattr(msg, 'caption', '') or ""

            for entity in msg.text_entities:
                if entity.type == "text_mention" and hasattr(entity, 'user'):
                    user_id = entity.user.id
                    if result := await _get_user_id_from_id(user_id):
                        return result

        return None

    except Exception as e:
        logger.error(f"Error in resolve_id: {e}", exc_info=True)
        return None


async def resolve_id_legacy(msg, mention: Optional[str] = None) -> Optional[int]:
    """Совместимая версия функции для обратной совместимости."""
    print('{mention},\n\n\n{msg}')
    return await resolve_id(msg, mention)


async def extract_all_mentions(text: str) -> list:
    """Извлекает ВСЕ упоминания пользователей из текста.

    Возвращает список кортежей (type, value):
    - ('id', 12345)
    - ('username', 'username')
    - ('phone', '+71234567890')
    - ('url', 'https://t.me/username')
    """
    if not text:
        return []

    mentions = []

    # Поиск простых @упоминаний
    simple_mentions = re.finditer(r'@([a-zA-Z0-9_]{5,32})', text)
    for match in simple_mentions:
        mentions.append(('username', match.group(1)))

    # Поиск @12345 (числовых ID)
    id_mentions = re.finditer(r'@(\d{5,})', text)
    for match in id_mentions:
        mentions.append(('id', int(match.group(1))))

    # Поиск всех Telegram URL
    telegram_urls = re.finditer(
        r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]{5,32})',
        text
    )
    for match in telegram_urls:
        username = match.group(1)
        if username.isdigit():
            mentions.append(('id', int(username)))
        else:
            mentions.append(('username', username))

    # Поиск tg:// ссылок
    tg_links = re.finditer(r'tg://(?:openmessage|user)\?(?:user_)?id=(\d+)', text)
    for match in tg_links:
        mentions.append(('id', int(match.group(1))))

    # Поиск телефонных номеров в Telegram формате
    phone_links = re.finditer(r'tg://resolve\?phone=(\+\d+)', text)
    for match in phone_links:
        mentions.append(('phone', match.group(1)))

    print(mentions)
    return mentions


async def normalize_telegram_link(identifier: str) -> dict:
    """Нормализует идентификатор Telegram в стандартный формат.

    Returns:
        dict: {
            'type': 'id' | 'username' | 'phone' | 'unknown',
            'value': значение,
            't.me_url': https://t.me/... (если применимо),
            'tg_url': tg://... (если применимо)
        }
    """
    result = {
        'type': 'unknown',
        'value': identifier,
        't.me_url': None,
        'tg_url': None
    }

    user_id, username = await _extract_user_info_from_mention(identifier)

    if user_id:
        result['type'] = 'id'
        result['value'] = user_id
        result['t.me_url'] = None  # Нет прямого URL для ID
        result['tg_url'] = f'tg://user?id={user_id}'

    elif username:
        result['type'] = 'username'
        result['value'] = username
        result['t.me_url'] = f'https://t.me/{username}'
        result['tg_url'] = f'tg://resolve?domain={username}'

    # Проверка на телефонный номер
    elif identifier.startswith('+') and re.match(r'^\+\d{10,15}$', identifier):
        result['type'] = 'phone'
        result['value'] = identifier
        result['tg_url'] = f'tg://resolve?phone={identifier}'

    print(result)
    return result