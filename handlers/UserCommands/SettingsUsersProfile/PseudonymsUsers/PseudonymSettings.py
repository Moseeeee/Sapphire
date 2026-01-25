from typing import Union
import unicodedata
import re
import logging
from typing import Tuple
import html


from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsUtils import contains_links
# Импорт для базы данных вынесен наверх
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_with_pseudonym
from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettingsDB import (
    validate_pseudonym,
    update_user_pseudonym, delete_user_pseudonym, get_user_pseudonym
)

PseudonymRouter = Router()

import unicodedata
import re
import logging
from typing import Tuple
import html

# Константы для невидимых символов
INVISIBLE_CHARS = {
    # Zero-width characters
    0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF,
    # Zero-width joiner/non-joiner
    0x200C, 0x200D,
    # Invisible operators
    0x2061, 0x2062, 0x2063, 0x2064,
    # Bidirectional text control
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    # Variation selectors
    0xFE00, 0xFE01, 0xFE02, 0xFE03, 0xFE04, 0xFE05, 0xFE06, 0xFE07,
    0xFE08, 0xFE09, 0xFE0A, 0xFE0B, 0xFE0C, 0xFE0D, 0xFE0E, 0xFE0F,
    # Other invisible characters
    0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
    0x180E, 0x3164, 0xFFA0,
}

# Deprecated и discouraged символы
DEPRECATED_CHARS = {
    0x1FFFE, 0x1FFFF, 0x2FFFE, 0x2FFFF, 0x3FFFE, 0x3FFFF,
    0x4FFFE, 0x4FFFF, 0x5FFFE, 0x5FFFF, 0x6FFFE, 0x6FFFF,
    0x7FFFE, 0x7FFFF, 0x8FFFE, 0x8FFFF, 0x9FFFE, 0x9FFFF,
    0xAFFFE, 0xAFFFF, 0xBFFFE, 0xBFFFF, 0xCFFFE, 0xCFFFF,
    0xDFFFE, 0xDFFFF, 0xEFFFE, 0xEFFFF, 0xFFFFE, 0xFFFFF,
    0x10FFFE, 0x10FFFF,
}

# Символы, ломающие отображение
BREAKING_CHARS = {
    0x2028,  # Line separator
    0x2029,  # Paragraph separator
    0x000B,  # Vertical tab
    0x000C,  # Form feed
    0x0085,  # Next line
}


def validate_pseudonym(pseudonym: str) -> Tuple[bool, str]:
    """
    Улучшенная валидация псевдонима с расширенной защитой
    """
    if not pseudonym or not isinstance(pseudonym, str):
        return False, "Псевдоним должен быть строкой"

    # 1. Сохраняем оригинал для сравнения
    original = pseudonym

    # 2. Нормализация Unicode (NFKC для объединения символов)
    normalized = unicodedata.normalize('NFKC', pseudonym)

    # 3. Удаление всех невидимых и управляющих символов
    cleaned_chars = []
    for char in normalized:
        category = unicodedata.category(char)
        char_ord = ord(char)

        # Удаляем все управляющие символы
        if category in ('Cc', 'Cf', 'Co', 'Cn'):
            continue

        # Удаляем невидимые символы
        if char_ord in INVISIBLE_CHARS:
            continue

        # Проверяем на surrogate pairs
        if 0xD800 <= char_ord <= 0xDFFF:
            continue

        # Проверяем на deprecated символы
        if char_ord in DEPRECATED_CHARS:
            continue

        # Проверяем на символы, которые ломают отображение
        if char_ord in BREAKING_CHARS:
            continue

        cleaned_chars.append(char)

    cleaned = ''.join(cleaned_chars)

    # 4. Проверка на пустоту после очистки
    if not cleaned or not cleaned.strip():
        return False, "Псевдоним не может быть пустым или состоять только из невидимых символов"

    # 5. Удаление символов изменения направления текста
    cleaned = remove_bidi_chars(cleaned)

    # 6. Проверка длины
    if len(cleaned) > 64:
        return False, "Псевдоним слишком длинный (максимум 64 символа)"

    if len(cleaned) < 1:
        return False, "Псевдоним слишком короткий (минимум 1 символ)"

    # 7. Проверка размера в байтах
    try:
        byte_size = len(cleaned.encode('utf-8'))
        if byte_size > 128:
            return False, "Псевдоним слишком большой"
    except UnicodeError:
        return False, "Некорректная кодировка символов"

    # 8. Проверка на ссылки и упоминания
    if contains_links(cleaned):
        return False, "Псевдоним не может содержать ссылки или упоминания"

    # 9. Проверка на опасные паттерны
    dangerous_patterns = [
        r'[<>{}|\\^~\[\]]',  # HTML/специальные символы
        r'[\x00-\x1F\x7F]',  # Управляющие символы ASCII
        r'[\uD800-\uDFFF]',  # Суррогатные пары
        r'[\uE000-\uF8FF]',  # Приватная область Unicode
        r'[\uFFF0-\uFFFF]',  # Специальные символы Unicode
        r'^[_\-.]+$',  # Только специальные символы
        r'[\u0000-\u0008\u000B\u000C\u000E-\u001F]',  # Доп. управляющие
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, cleaned):
            return False, "Псевдоним содержит запрещенные символы"

    # 10. Проверка на эмодзи
    emoji_info = count_emojis(cleaned)
    if emoji_info['total'] > 2:
        return False, "Слишком много эмодзи (максимум 2)"

    # 11. Проверка на повторяющиеся специальные символы
    if re.search(r'[-_\.!?,:;+*%$#@&\(\)"\']{3,}', cleaned):
        return False, "Слишком много повторяющихся специальных символов"

    # 12. Проверка на начало/конец специальными символами
    special_chars = set('-_.,!?:;+*%$#@&()"\'')
    if cleaned and (cleaned[0] in special_chars or cleaned[-1] in special_chars):
        return False, "Псевдоним не может начинаться или заканчиваться специальными символами"

    # 13. Проверка на допустимые символы (расширенная версия)
    invalid_chars = []
    for char in cleaned:
        char_ord = ord(char)

        # Разрешаем: обычные буквы, цифры, пробелы, разрешенные специальные символы
        # И ТАКЖЕ стилизованные буквы (математические и др.)

        # 1. Обычные латинские буквы (a-z, A-Z)
        is_latin = ('a' <= char <= 'z' or 'A' <= char <= 'Z')

        # 2. Обычные кириллические буквы
        is_cyrillic = ('а' <= char <= 'я' or 'А' <= char <= 'Я' or char in ('ё', 'Ё'))

        # 3. Цифры
        is_digit = ('0' <= char <= '9')

        # 4. Разрешенные специальные символы
        is_special = (char in ' -_.,!?:;+*%$#@&()"\'')

        # 5. Пробельные символы
        is_space = char.isspace()

        # 6. Стилизованные латинские буквы (математические и др.)
        is_styled_latin = (
            # Математические курсивные буквы
                (0x1D434 <= char_ord <= 0x1D467) or  # Mathematical Italic
                (0x1D468 <= char_ord <= 0x1D49B) or  # Mathematical Bold Italic
                (0x1D49C <= char_ord <= 0x1D4CF) or  # Mathematical Script
                (0x1D4D0 <= char_ord <= 0x1D503) or  # Mathematical Bold Script
                (0x1D504 <= char_ord <= 0x1D537) or  # Mathematical Fraktur
                (0x1D538 <= char_ord <= 0x1D56B) or  # Mathematical Double-struck
                (0x1D56C <= char_ord <= 0x1D59F) or  # Mathematical Bold Fraktur
                (0x1D5A0 <= char_ord <= 0x1D5D3) or  # Mathematical Sans-serif
                (0x1D5D4 <= char_ord <= 0x1D607) or  # Mathematical Sans-serif Bold
                (0x1D608 <= char_ord <= 0x1D63B) or  # Mathematical Sans-serif Italic
                (0x1D63C <= char_ord <= 0x1D66F) or  # Mathematical Sans-serif Bold Italic
                (0x1D670 <= char_ord <= 0x1D6A3) or  # Mathematical Monospace
                # Дополнительные стилизованные символы
                (0x1D400 <= char_ord <= 0x1D433) or  # Mathematical Bold
                (0x1D6A8 <= char_ord <= 0x1D6E1) or  # Mathematical Bold Greek
                (0x1D7CE <= char_ord <= 0x1D7FF)  # Mathematical Bold Digit
        )

        # 7. Стилизованные кириллические буквы (если есть)
        is_styled_cyrillic = (
            # Кириллица в расширенном диапазоне
                (0x0400 <= char_ord <= 0x04FF) or  # Основная кириллица
                (0x0500 <= char_ord <= 0x052F) or  # Расширенная кириллица
                (0x2DE0 <= char_ord <= 0x2DFF) or  # Расширенная кириллица-A
                (0xA640 <= char_ord <= 0xA69F)  # Расширенная кириллица-B
        )

        # Комбинируем все условия
        is_valid = (
                is_latin or
                is_cyrillic or
                is_digit or
                is_special or
                is_space or
                is_styled_latin or
                is_styled_cyrillic
        )

        if not is_valid:
            # Проверяем, может быть это допустимая буква из других алфавитов
            category = unicodedata.category(char)
            if category.startswith('L'):  # Любая буква
                is_valid = True
            elif category in ('Nd', 'Nl', 'No'):  # Числа
                is_valid = True
            elif category in ('Zs', 'Zl', 'Zp'):  # Пробельные символы
                is_valid = True

        if not is_valid:
            invalid_chars.append(char)
            if len(invalid_chars) >= 3:
                break

    if invalid_chars:
        invalid_chars_str = ', '.join([f"U+{ord(c):04X}" for c in invalid_chars[:3]])
        return False, f"Содержит недопустимые символы: {invalid_chars_str}"

    # 14. Проверка на моно-символы
    chars_without_spaces = re.sub(r'\s', '', cleaned)
    if len(chars_without_spaces) > 1 and len(set(chars_without_spaces)) == 1:
        return False, "Псевдоним не может состоять из одного повторяющегося символа"

    # 15. Очистка пробелов
    cleaned = clean_whitespace(cleaned)

    # 16. Проверка на запрещенные слова
    if contains_forbidden_words(cleaned):
        return False, "Псевдоним содержит запрещенные слова"

    # 17. Проверка на валидность UTF-8
    try:
        cleaned.encode('utf-8')
    except UnicodeError:
        return False, "Некорректная кодировка символов"

    # 18. Проверка, что очищенный псевдоним не пустой
    if not cleaned or len(cleaned.strip()) < 1:
        return False, "Псевдоним слишком короткий после очистки"

    # 19. Проверка на слишком много специальных символов
    special_count = sum(1 for c in cleaned if c in special_chars)
    if special_count > len(cleaned) * 0.3:  # Не более 30% специальных символов
        return False, "Слишком много специальных символов"

    return True, cleaned


def remove_bidi_chars(text: str) -> str:
    """Удаляет символы изменения направления текста"""
    bidi_chars = [
        '\u202A', '\u202B', '\u202C', '\u202D', '\u202E',
        '\u2066', '\u2067', '\u2068', '\u2069', '\u200F', '\u200E'
    ]
    for char in bidi_chars:
        text = text.replace(char, '')
    return text


def count_emojis(text: str) -> dict:
    """Считает эмодзи в тексте"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # эмоции
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и карты
        "\U0001F1E0-\U0001F1FF"  # флаги
        "\U00002702-\U000027B0"  # другие символы
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )

    emojis = emoji_pattern.findall(text)
    return {
        'total': len(emojis),
        'emojis': emojis
    }


def clean_whitespace(text: str) -> str:
    """Очищает пробелы в тексте"""
    # Удаляем пробелы в начале и конце
    text = text.strip()

    # Заменяем множественные пробелы на один
    text = re.sub(r'\s{2,}', ' ', text)

    # Удаляем пробелы вокруг некоторых специальных символов
    text = re.sub(r'\s*([\-_\.!?,:;+*%$#@&\(\)"\'])\s*', r'\1', text)

    return text


def contains_forbidden_words(text: str) -> bool:
    """Проверяет наличие запрещенных слов"""
    # Транслитерация стилизованных символов в обычные для проверки
    import unicodedata

    # Нормализуем и преобразуем стилизованные символы в обычные
    normalized = unicodedata.normalize('NFKD', text)
    # Удаляем комбинирующие диакритические знаки
    ascii_text = ''.join(c for c in normalized if not unicodedata.combining(c))

    # Приводим к нижнему регистру для проверки
    lower_text = ascii_text.lower()

    # Список запрещенных слов (можно расширить)
    forbidden_words = [
        'admin', 'administrator', 'root', 'system', 'null', 'undefined',
        'support', 'help', 'official', 'moderator', 'mod',
        'http:', 'https:', 'www.', '.com', '.ru', '.org', '.net',
        '@everyone', '@here', '@channel', '@all'
    ]

    for word in forbidden_words:
        if word in lower_text:
            return True

    return False


def contains_links(text: str) -> bool:
    """Проверяет наличие ссылок в тексте"""
    # Транслитерация стилизованных символов в обычные для проверки
    import unicodedata

    # Нормализуем и преобразуем стилизованные символы в обычные
    normalized = unicodedata.normalize('NFKD', text)
    # Удаляем комбинирующие диакритические знаки
    ascii_text = ''.join(c for c in normalized if not unicodedata.combining(c))

    lower_text = ascii_text.lower()

    link_patterns = [
        r'https?://',
        r'www\.',
        r't\.me/',
        r'@[\w]{5,}',
        r'bit\.ly/',
        r'tinyurl\.com/',
        r'\.(com|ru|org|net|info|biz|xyz)',
    ]

    for pattern in link_patterns:
        if re.search(pattern, lower_text):
            return True
    return False


# Улучшенная функция для обработки команды
@PseudonymRouter.message(F.text.lower().startswith('+псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('+ник'))
@PseudonymRouter.message(F.text.lower().startswith('+nick'))
async def set_pseudonym_command(message: Message):
    """Установка псевдонима в чате"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == 'private':
        return

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 68):
        await message.reply("❌ У вас недостаточно прав для использования этой команды")
        return

    # Получаем псевдоним из сообщения
    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)

    if len(parts) < 2:
        await message.reply(
            "ℹ️ Использование: <code>+псевдоним [ваш псевдоним]</code>\n"
            "Пример: <code>+псевдоним Нео</code>",
            parse_mode='HTML'
        )
        return

    pseudonym = parts[1].strip()

    # Валидация псевдонима
    is_valid, result = validate_pseudonym(pseudonym)

    if not is_valid:
        await message.reply(f"❌ {result}", parse_mode='HTML')
        return

    # Проверяем, были ли изменения после валидации
    original_clean = re.sub(r'\s+', '', pseudonym)
    result_clean = re.sub(r'\s+', '', result)

    if original_clean != result_clean:
        # Показываем разницу
        await message.reply(
            "⚠️ Псевдоним был автоматически очищен:\n"
            f"Было: <code>{html.escape(pseudonym[:50])}</code>\n"
            f"Стало: <code>{html.escape(result)}</code>",
            parse_mode='HTML'
        )

    # Сохраняем псевдоним
    try:
        await update_user_pseudonym(chat_id, user_id, result)
        await message.reply(
            f"✅ Псевдоним успешно установлен!\n",
            parse_mode='HTML'
        )

    except Exception as e:
        logging.error(f"Ошибка при сохранении псевдонима: {e}", exc_info=True)
        await message.reply(
            "❌ Произошла ошибка при сохранении псевдонима. "
        )




@PseudonymRouter.message(F.text.lower().startswith('-псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('-ник'))
@PseudonymRouter.message(F.text.lower().startswith('-nick'))
@PseudonymRouter.message(F.text.lower().startswith('!сбросить псевдоним'))
async def remove_pseudonym_command(message: Message):
    """Удаление псевдонима"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == 'private':
        return

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 68):
            return

    # Пытаемся удалить псевдоним
    success = await delete_user_pseudonym(chat_id, user_id)

    if success:
        await message.reply("✅ Псевдоним сброшен!", parse_mode='HTML')
    else:
        await message.reply("ℹ️ У вас не установлен псевдоним.", parse_mode='HTML')


@PseudonymRouter.message(F.text.lower().startswith('!мой псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('.мой псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('/мой псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('мой псевдоним'))

@PseudonymRouter.message(F.text.lower().startswith('мой ник'))
@PseudonymRouter.message(F.text.lower().startswith('!мой ник'))
@PseudonymRouter.message(F.text.lower().startswith('.мой ник'))
@PseudonymRouter.message(F.text.lower().startswith('/мой ник'))
async def get_my_pseudonym_command(message: Message):
    """Просмотр своего псевдонима"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == 'private':
        return

    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 68):
        return

    pseudonym = await get_user_pseudonym(chat_id, user_id)

    if pseudonym:
        await message.reply(
            f"👁️‍🗨️ Ваш псевдоним: <b>{pseudonym}</b>",
            parse_mode='HTML'
        )
    else:
        await message.reply(
            "ℹ️ <b>У вас не установлен псевдоним.</b>\n\n"
            "Установить: <code>+псевдоним [ваше_имя]</code>",
            parse_mode='HTML'
        )


@PseudonymRouter.message(F.text.lower().startswith('!псевдонимы'))
@PseudonymRouter.message(F.text.lower().startswith('/псевдонимы'))
@PseudonymRouter.message(F.text.lower().startswith('.псевдонимы'))
@PseudonymRouter.message(F.text.lower().startswith('псевдонимы'))
@PseudonymRouter.message(F.text.lower().startswith('!ники'))
@PseudonymRouter.message(F.text.lower().startswith('/ники'))
@PseudonymRouter.message(F.text.lower().startswith('.ники'))
@PseudonymRouter.message(F.text.lower().startswith('ники'))
@PseudonymRouter.message(Command("pseudonyms"))
async def list_pseudonyms_command(message: Message):
    """Список всех псевдонимов в чате (только для админов)"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type == 'private':
        return

    # Проверяем, что это группа или супергруппа
    if message.chat.type in ['private', 'channel']:
        await message.reply("❌ Эта команда работает только в группах и супергруппах")
        return

    # Проверяем права администратора
    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 69):
        return

    # Загружаем список псевдонимов (начинаем с 1 страницы)
    await show_pseudonyms_page(message, chat_id, page=1)






async def show_pseudonyms_page(
        message: Union[Message, CallbackQuery],
        chat_id: int,
        page: int = 1,
        items_per_page: int = 20
):
    """Показать страницу с псевдонимами"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем общее количество псевдонимов
            total_count = await conn.fetchval(
                'SELECT COUNT(*) FROM users_chats WHERE chat_id = $1 AND pseudonym IS NOT NULL',
                chat_id
            )

            if total_count == 0:
                if isinstance(message, Message):
                    await message.reply("📝 В этом чате никто не установил псевдоним")
                else:
                    # Это CallbackQuery
                    await message.answer("📝 В этом чате никто не установил псевдоним", show_alert=True)
                    try:
                        await message.message.edit_text("📝 В этом чате никто не установил псевдоним")
                    except:
                        pass
                return

            # Определяем нужна ли пагинация
            needs_pagination = total_count > items_per_page
            total_pages = max(1, (total_count + items_per_page - 1) // items_per_page) if needs_pagination else 1
            page = max(1, min(page, total_pages))

            # Если записей много и нужна пагинация, получаем данные для текущей страницы
            if needs_pagination:
                offset = (page - 1) * items_per_page
                rows = await conn.fetch('''
                    SELECT uc.user_id, uc.pseudonym, u.username 
                    FROM users_chats uc
                    LEFT JOIN users u ON uc.user_id = u.user_id
                    WHERE uc.chat_id = $1 AND uc.pseudonym IS NOT NULL
                    ORDER BY uc.pseudonym
                    LIMIT $2 OFFSET $3
                ''', chat_id, items_per_page, offset)
            else:
                # Если записей мало, получаем все сразу
                rows = await conn.fetch('''
                    SELECT uc.user_id, uc.pseudonym, u.username 
                    FROM users_chats uc
                    LEFT JOIN users u ON uc.user_id = u.user_id
                    WHERE uc.chat_id = $1 AND uc.pseudonym IS NOT NULL
                    ORDER BY uc.pseudonym
                ''', chat_id)

            # Формируем список
            pseudonyms_list = []
            start_num = ((page - 1) * items_per_page) + 1 if needs_pagination else 1

            for i, row in enumerate(rows, start=start_num):
                user_id = row['user_id']
                # Используем user_link_with_pseudonym для создания ссылки на пользователя
                user_link = await user_link_with_pseudonym(user_id, chat_id)
                pseudonyms_list.append(f"{i}. {user_link}")

            # Формируем текст сообщения
            if needs_pagination:
                response_text = (
                        f"📋 <b>Список псевдонимов в этом чате:</b>\n"
                        f"Страница {page}/{total_pages} (всего: {total_count})\n\n" +
                        "\n".join(pseudonyms_list)
                )
            else:
                response_text = (
                        f"📋 <b>Список псевдонимов в этом чате:</b>\n"
                        f"Всего: {total_count}\n\n" +
                        "\n".join(pseudonyms_list)
                )

            # Создаем клавиатуру только если нужна пагинация
            reply_markup = None
            if needs_pagination:
                keyboard = []

                # Кнопки навигации
                nav_buttons = []
                if page > 1:
                    nav_buttons.append(InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=f"pseudos:{chat_id}:{page - 1}"
                    ))

                nav_buttons.append(InlineKeyboardButton(
                    text=f"{page}/{total_pages}",
                    callback_data="pseudos:current"
                ))

                if page < total_pages:
                    nav_buttons.append(InlineKeyboardButton(
                        text="Вперед ▶️",
                        callback_data=f"pseudos:{chat_id}:{page + 1}"
                    ))

                if nav_buttons:
                    keyboard.append(nav_buttons)

                # Кнопка обновления
                keyboard.append([InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=f"pseudos:{chat_id}:{page}"
                )])

                reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

            # Определяем, как отправлять/редактировать сообщение
            if isinstance(message, CallbackQuery):
                # Если это колбэк от кнопки
                try:
                    await message.message.edit_text(
                        response_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True,
                        reply_markup=reply_markup
                    )
                    await message.answer()  # Сбрасываем индикатор загрузки
                except Exception as e:
                    # Если нельзя отредактировать, отправляем новое сообщение
                    logging.warning(f"Не удалось отредактировать сообщение: {e}")
                    await message.message.reply(
                        response_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True,
                        reply_markup=reply_markup
                    )

            elif isinstance(message, Message):
                # Если это новая команда из сообщения
                if hasattr(message, 'edit_text') and message.reply_to_message:
                    # Пытаемся отредактировать предыдущее сообщение
                    try:
                        await message.edit_text(
                            response_text,
                            parse_mode='HTML',
                            disable_web_page_preview=True,
                            reply_markup=reply_markup
                        )
                    except:
                        # Если не получается, отправляем новое
                        await message.reply(
                            response_text,
                            parse_mode='HTML',
                            disable_web_page_preview=True,
                            reply_markup=reply_markup
                        )
                else:
                    # Просто отправляем новое сообщение
                    await message.reply(
                        response_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True,
                        reply_markup=reply_markup
                    )
            else:
                # На всякий случай
                logging.error(f"Неизвестный тип message: {type(message)}")

    except Exception as e:
        error_msg = f"❌ Ошибка при получении списка: {str(e)}"
        logging.error(f"Ошибка в show_pseudonyms_page: {e}", exc_info=True)

        if isinstance(message, CallbackQuery):
            try:
                await message.message.edit_text(error_msg)
            except:
                await message.answer(error_msg, show_alert=True)
        elif isinstance(message, Message):
            await message.reply(error_msg)


@PseudonymRouter.callback_query(F.data.startswith("pseudos:"))
@rate_limit_with_cleanup(limit=1)
async def handle_pseudonyms_pagination(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    """Обработка нажатий на кнопки пагинации"""
    try:
        # Разбираем callback_data: pseudos:chat_id:page
        parts = callback.data.split(":")

        if parts[1] == "current":
            await callback.answer("Текущая страница")
            return

        if len(parts) < 3:
            await callback.answer("Ошибка формата данных")
            return

        chat_id = int(parts[1])
        page = int(parts[2])

        # Проверяем права администратора
        if not await auto_check_AccessLevel_for_rang(callback.from_user.id, chat_id, 58):
            await callback.answer("❌ Эта команда доступна только администраторам", show_alert=True)
            return

        # Проверяем, что сообщение существует
        if not callback.message:
            await callback.answer("Сообщение не найдено")
            return

        # Обновляем сообщение через callback
        await show_pseudonyms_page(callback, chat_id, page)

    except ValueError as ve:
        logging.error(f"ValueError в handle_pseudonyms_pagination: {ve}")
        await callback.answer("Ошибка в данных", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка в handle_pseudonyms_pagination: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)