import re
import html
from typing import Union
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from handlers.AdminsTools.ChatSettings.reports.reportsDB import search_user_name
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name
from handlers.BotAutomaticWork.users.links.usersLinksUtils.emoji_utils import format_pseudonym_for_display
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_linkDB import search_username
from handlers.UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettingsDB import (
    validate_pseudonym,
    update_user_pseudonym, delete_user_pseudonym, get_user_pseudonym
)


PseudonymRouter = Router()

# Паттерны для проверки ссылок и юзернеймов
URL_PATTERN = re.compile(
    r'https?://(?:[-\w.]|%[\da-fA-F]{2})+|'  # http/https URLs
    r'www\.[-\w.]+|'  # www URLs
    r't\.me/[-\w.]+|'  # t.me links
    r'@[a-zA-Z0-9_]{5,}'  # юзернеймы (@username)
)

# Символы, которые могут сломать HTML
HTML_DANGEROUS_CHARS = ['<', '>', '"', "'", '&', '`']

# Символы, которые могут сломать систему или вызвать проблемы
BREAKING_SYMBOLS = [
    '\x00',  # Null char
    '\x07',  # Bell
    '\x08',  # Backspace
    '\x0b',  # Vertical tab
    '\x0c',  # Form feed
    '\x1b',  # Escape
    '\x7f',  # Delete
    '\u200b',  # Zero-width space
    '\u200c',  # Zero-width non-joiner
    '\u200d',  # Zero-width joiner
    '\u202e',  # Right-to-left override
    '\u202d',  # Left-to-right override
    '\u2066',  # Left-to-right isolate
    '\u2067',  # Right-to-left isolate
    '\u2068',  # First strong isolate
    '\u2069',  # Pop directional isolate
    '\ufeff',  # Byte order mark
]


def sanitize_text_for_storage(text: str) -> str:
    """
    Подготавливает текст для безопасного хранения.
    Сохраняет премиум эмодзи, но экранирует опасные символы вне тегов эмодзи.
    """
    # Сначала защищаем теги эмодзи
    emoji_tags = []

    # Находим и временно заменяем теги эмодзи
    def protect_emoji(match):
        emoji_tags.append(match.group(0))
        return f'__EMOJI_TAG_{len(emoji_tags) - 1}__'

    # Защищаем теги эмодзи
    protected_text = re.sub(
        r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>',
        protect_emoji,
        text
    )

    # Экранируем HTML символы в оставшемся тексте
    protected_text = html.escape(protected_text)

    # Восстанавливаем теги эмодзи
    for i, tag in enumerate(emoji_tags):
        protected_text = protected_text.replace(f'__EMOJI_TAG_{i}__', tag)

    return protected_text


def check_breaking_symbols(text: str) -> tuple[bool, str]:
    """Проверяет наличие ломающих символов"""
    # Проверяем только текст вне тегов эмодзи
    clean_text = re.sub(r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>', '', text)

    for symbol in BREAKING_SYMBOLS:
        if symbol in clean_text:
            return False, f"Обнаружен запрещенный символ: {repr(symbol)}"
    return True, ""


def check_links_and_mentions(text: str) -> tuple[bool, str]:
    """Проверяет наличие ссылок и упоминаний"""
    # Удаляем теги эмодзи для проверки
    clean_text = re.sub(r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>', '', text)

    if URL_PATTERN.search(clean_text):
        return False, "Обнаружены ссылки или упоминания (@username)"
    return True, ""


def extract_pseudonym_with_emoji(html_text: str) -> tuple[str, bool]:
    """
    Извлекает псевдоним из сообщения, сохраняя премиум эмодзи.

    Returns:
        tuple: (псевдоним_с_эмодзи, содержит_ли_эмодзи)
    """
    # Разделяем на команду и псевдоним
    parts = html_text.split(maxsplit=1)
    if len(parts) < 2:
        return "", False

    pseudonym = parts[1].strip()

    # Проверяем, содержит ли псевдоним эмодзи
    has_emoji = bool(re.search(r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>', pseudonym))

    return pseudonym, has_emoji


def get_text_length_without_premium_emoji(text: str) -> int:
    """Возвращает длину текста без учета премиум эмодзи"""
    # Удаляем теги премиум эмодзи
    clean_text = re.sub(r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>', '', text)
    # Убираем пробелы для точного подсчета
    return len(clean_text.strip())

async def user_link_global(UserId: int) -> str:
    try:
        username = await search_username(UserId)
        UserName = await search_user_name(UserId)
        CleanName = clean_name(UserName)

        # Определяем отображаемое имя с приоритетами
        display_name = CleanName

        if username:
            return f"<a href='https://t.me/{username}'>{display_name}</a>"
        else:
            return f"<a href='tg://openmessage?user_id={UserId}'>{display_name}</a>"

    except Exception as e:
        return f"<a href='tg://openmessage?user_id={UserId}'>{UserId}</a>"


async def user_link_with_pseudonym(user_id: int, chat_id: int) -> str:
    """
    Создает ссылку на пользователя с учетом псевдонима.
    Извлекает премиум эмодзи, создает ссылку на оставшийся текст,
    затем вставляет эмодзи обратно на их оригинальные позиции.
    """
    try:
        # Получаем псевдоним пользователя в этом чате
        pseudonym = await get_user_pseudonym(chat_id, user_id)

        if pseudonym:
            # Форматируем псевдоним с поддержкой эмодзи
            display_text = format_pseudonym_for_display(pseudonym)
            username = await search_username(user_id)

            # Если есть премиум эмодзи
            if '<tg-emoji' in display_text:
                import re

                # Находим все эмодзи и их позиции
                emoji_pattern = r'(<tg-emoji[^>]*>.*?</tg-emoji>)'

                # Разделяем текст на части: текст и эмодзи
                parts = re.split(emoji_pattern, display_text)

                # Собираем результат
                result_parts = []

                for part in parts:
                    if not part:
                        continue

                    if part.startswith('<tg-emoji'):
                        # Это эмодзи - добавляем как есть
                        result_parts.append(part)
                    else:
                        # Это текст - делаем ссылку (если текст не пустой)
                        if part.strip():
                            if username:
                                linked_text = f"<a href='https://t.me/{username}'>{part}</a>"
                            else:
                                linked_text = f"<a href='tg://openmessage?user_id={user_id}'>{part}</a>"
                            result_parts.append(linked_text)
                        else:
                            # Пустой текст (пробелы между эмодзи)
                            result_parts.append(part)

                return ''.join(result_parts)
            else:
                # Нет эмодзи - обычная ссылка
                if username:
                    return f"<a href='https://t.me/{username}'>{display_text}</a>"
                else:
                    return f"<a href='tg://openmessage?user_id={user_id}'>{display_text}</a>"
        else:
            # Если нет псевдонима, используем стандартную функцию
            return await user_link_global(user_id)

    except Exception as e:
        return await user_link_global(user_id)


@PseudonymRouter.message(F.text.lower().startswith('+псевдоним'))
@PseudonymRouter.message(F.text.lower().startswith('+ник'))
@PseudonymRouter.message(F.text.lower().startswith('+nick'))
async def set_pseudonym_command(message: Message):
    """Установка псевдонима в чате с сохранением премиум эмодзи"""
    # Убираем выполнение в личных сообщениях на самом начале
    if message.chat.type == 'private':
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверка прав доступа
    if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 68):
        return

    # Получаем текст сообщения с HTML разметкой
    html_text = message.html_text or ""

    # Извлекаем псевдоним с сохранением эмодзи
    pseudonym_html, has_emoji = extract_pseudonym_with_emoji(html_text)

    # Валидация пустого псевдонима
    if not pseudonym_html or pseudonym_html.strip() == "":
        await message.reply(
            f"Пример: <code>+псевдоним Нео</code> или с премиум эмодзи: <code>+псевдоним <tg-emoji emoji-id='5271552643322355356'>😀</tg-emoji>Нео</code>",
            parse_mode='HTML'
        )
        return

    # Получаем чистый текст без эмодзи для валидаций
    clean_text = re.sub(r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>', '', pseudonym_html).strip()

    # Валидации с ранним возвратом
    validation_checks = [
        # 1. Проверка на ломающие символы
        (lambda: check_breaking_symbols(pseudonym_html),
         lambda result: result[0],
         lambda result: f"❌ {result[1]}"),

        # 2. Проверка на ссылки и @юзернеймы
        (lambda: check_links_and_mentions(pseudonym_html),
         lambda result: result[0],
         lambda result: f"❌ {result[1]}"),

        # 3. Проверка длины текста без учета премиум эмодзи
        (lambda: get_text_length_without_premium_emoji(pseudonym_html),
         lambda length: length > 0,
         lambda
             length: "❌ Псевдоним не может быть пустым" if length == 0 else f"❌ Псевдоним слишком длинный (максимум 32 символа без эмодзи, у вас {length})"),

        # 4. Проверка максимальной длины
        (lambda: get_text_length_without_premium_emoji(pseudonym_html),
         lambda length: length <= 32,
         lambda length: None),  # Сообщение уже в предыдущей проверке

        # 5. Базовая валидация символов
        (lambda: validate_pseudonym(clean_text),
         lambda result: result[0],
         lambda result: f"❌ {result[1]}")
    ]

    # Выполняем все проверки
    for check_func, condition_func, error_func in validation_checks:
        result = check_func()
        if not condition_func(result):
            error_msg = error_func(result)
            if error_msg:
                await message.reply(error_msg, parse_mode='HTML')
            return

    # Проверка на занятость псевдонима
    pool = get_db_pool()
    async with pool.acquire() as conn:
        existing_user = await conn.fetchrow(
            '''
            SELECT user_id FROM users_chats 
            WHERE chat_id = $1 
            AND pseudonym = $2 
            AND user_id != $3
            ''',
            chat_id, pseudonym_html, user_id
        )

        if existing_user:
            display_name = await user_link_with_pseudonym(existing_user['user_id'], chat_id)
            await message.reply(
                f"❌ Псевдоним «{html.escape(clean_text)}» уже используется пользователем {display_name}",
                parse_mode='HTML'
            )
            return

    # Подготавливаем текст для хранения (сохраняем эмодзи, экранируем остальное)
    safe_pseudonym = sanitize_text_for_storage(pseudonym_html)

    # Сохраняем псевдоним
    try:
        success = await update_user_pseudonym(chat_id, user_id, safe_pseudonym)

        if not success:
            await message.reply(
                f"❌ Псевдоним «{html.escape(clean_text)}» уже используется другим пользователем",
                parse_mode='HTML'
            )
            return

        # Формируем ответ
        if has_emoji:
            # Показываем псевдоним с эмодзи
            response = f"✅ Псевдоним «{safe_pseudonym}» установлен."
        else:
            response = f"✅ Псевдоним «{html.escape(clean_text)}» установлен."

        await message.reply(response, parse_mode='HTML')

    except Exception as e:
        logging.error(f"Ошибка при сохранении псевдонима для user_id={user_id}, chat_id={chat_id}: {e}",
                      exc_info=True)
        await message.reply("❌ Произошла ошибка при сохранении псевдонима", parse_mode='HTML')


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
        # Используем user_link_with_pseudonym для форматирования отображения
        user_link = await user_link_with_pseudonym(user_id, chat_id)
        await message.reply(
            f"👁️‍🗨️ Ваш псевдоним: {user_link}",
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
                # Используем функцию user_link_with_pseudonym для создания ссылки
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