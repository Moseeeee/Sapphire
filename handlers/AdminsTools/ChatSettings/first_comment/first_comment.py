import logging
import re
from typing import List, Dict

from aiogram import Router, F
from aiogram.types import Message

from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import (
    set_first_comment, get_first_comment, delete_first_comment
)
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

first_comment_commands_router = Router()
logger = logging.getLogger(__name__)


def parse_first_comment_html_command(message: Message) -> tuple[str, List[Dict[str, str]]]:
    """Парсинг команды первого комментария из HTML текста"""
    # Получаем HTML текст сообщения
    html_text = message.html_text or ""

    if not html_text:
        return "", []

    # Удаляем саму команду из начала
    html_lines = html_text.strip().split('\n')

    # Пропускаем первую строку с командой
    if html_lines and html_lines[0].lower().startswith("+первый комментарий"):
        html_lines = html_lines[1:]

    content_text = '\n'.join(html_lines).strip()
    if not content_text:
        return "", []

    # Разделяем на строки для парсинга кнопок
    lines = content_text.split('\n')
    comment_lines = []
    buttons = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Проверяем формат кнопки: [текст](ссылка)
        # Используем регулярку для поиска в HTML
        match = re.search(r'\[(.+?)\]\((.+?)\)', line)
        if match and len(buttons) < 5:
            button_text = match.group(1).strip()
            button_url = match.group(2).strip()

            # Удаляем HTML теги из текста кнопки
            button_text = re.sub(r'<[^>]+>', '', button_text)

            # Добавляем https:// если нет
            if not button_url.startswith(('http://', 'https://')):
                button_url = f'https://{button_url}'

            buttons.append({
                'text': button_text[:50],
                'url': button_url[:500]
            })

            # Удаляем кнопку из строки
            line = re.sub(r'\[.+?\]\(.+?\)', '', line).strip()

        if line:
            comment_lines.append(line)

    comment_html = '\n'.join(comment_lines).strip()
    return comment_html, buttons


def parse_first_comment_command_text(text: str) -> tuple[str, List[Dict[str, str]]]:
    """Парсинг команды первого комментария из обычного текста"""
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return "", []

    # Пропускаем команду
    content_lines = lines[1:]
    comment_lines = []
    buttons = []

    for line in content_lines:
        line = line.strip()
        if not line:
            continue

        # Проверяем формат кнопки: [текст](ссылка)
        match = re.match(r'^\[(.+?)\]\((.+?)\)$', line)
        if match and len(buttons) < 5:
            button_text = match.group(1).strip()
            button_url = match.group(2).strip()

            # Добавляем https:// если нет
            if not button_url.startswith(('http://', 'https://')):
                button_url = f'https://{button_url}'

            buttons.append({
                'text': button_text[:50],
                'url': button_url[:500]
            })
        else:
            comment_lines.append(line)

    comment_text = '\n'.join(comment_lines)
    return comment_text, buttons


@first_comment_commands_router.message(F.text.startswith("+первый комментарий"))
async def add_first_comment_handler(message: Message):
    """Добавление первого комментария для привязанного канала"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 74):
        return

    try:
        # Парсим команду - сначала пробуем получить HTML
        if message.html_text:
            comment_html, buttons = parse_first_comment_html_command(message)
        else:
            comment_html, buttons = parse_first_comment_command_text(message.text or "")

        # Валидация
        if not comment_html:
            await message.reply("❌ Укажите текст комментария после команды")
            return

        # Убираем лишние пробелы и переносы
        comment_html = comment_html.strip()

        if len(comment_html) > 4000:
            await message.reply("❌ Текст комментария слишком длинный (макс. 4000 символов)")
            return

        # Получаем привязанный канал
        linked_chat_id = None
        if message.chat.is_forum or message.chat.type in ['group', 'supergroup']:
            try:
                chat_info = await message.bot.get_chat(message.chat.id)
                linked_chat_id = chat_info.linked_chat_id
            except Exception as e:
                logger.error(f"Ошибка получения linked_chat_id: {e}")

        if not linked_chat_id:
            await message.reply("❌ У этой группы нет привязанного канала")
            return

        # Сохраняем в БД с HTML
        success = await set_first_comment(linked_chat_id, comment_html, buttons)

        if success:
            response = f"✅ Первый комментарий установлен для канала\n\n"

            # Показываем предпросмотр текста
            preview_text = comment_html


            response += f"📝 <b>Текст:</b>\n<code>{preview_text}</code>\n\n"

            if buttons:
                response += f"🔘 <b>Кнопки:</b> {len(buttons)} шт.\n"
                for i, btn in enumerate(buttons, 1):
                    response += f"{i}. {btn['text']}\n"

            await message.reply(response, parse_mode='HTML')
        else:
            await message.reply("❌ Ошибка при сохранении первого комментария")

    except Exception as e:
        logger.error(f"Ошибка в add_first_comment_handler: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при установке первого комментария")


@first_comment_commands_router.message(F.text.startswith("-первый комментарий"))
async def delete_first_comment_handler(message: Message):
    """Удаление первого комментария для привязанного канала"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 74):
        return

    try:
        # Получаем привязанный канал
        linked_chat_id = None
        if message.chat.is_forum or message.chat.type in ['group', 'supergroup']:
            try:
                chat_info = await message.bot.get_chat(message.chat.id)
                linked_chat_id = chat_info.linked_chat_id
            except Exception as e:
                logger.error(f"Ошибка получения linked_chat_id: {e}")

        if not linked_chat_id:
            await message.reply("❌ У этой группы нет привязанного канала")
            return

        # Удаляем из БД
        success = await delete_first_comment(linked_chat_id)

        if success:
            await message.reply("✅ Первый комментарий удален для привязанного канала")
        else:
            await message.reply("❌ Первый комментарий не найден или ошибка удаления")

    except Exception as e:
        logger.error(f"Ошибка в delete_first_comment_handler: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при удалении первого комментария")


@first_comment_commands_router.message(F.text.startswith(".первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("!первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("/первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("первый комментарий"))
async def show_first_comment_handler(message: Message):
    """Показать первый комментарий для привязанного канала"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 75):
        return

    try:
        # Получаем привязанный канал
        linked_chat_id = None
        if message.chat.is_forum or message.chat.type in ['group', 'supergroup']:
            try:
                chat_info = await message.bot.get_chat(message.chat.id)
                linked_chat_id = chat_info.linked_chat_id
            except Exception as e:
                logger.error(f"Ошибка получения linked_chat_id: {e}")

        if not linked_chat_id:
            await message.reply("❌ У этой группы нет привязанного канала")
            return

        # Получаем из БД
        first_comment = await get_first_comment(linked_chat_id)

        if not first_comment:
            await message.reply("📭 Первый комментарий не установлен для привязанного канала")
            return

        comment_html = first_comment['comment_text']
        buttons = first_comment['buttons']

        # Показываем HTML как есть
        response = f"📍 <b>Первый комментарий для канала:</b>\n\n"
        response += comment_html[:1000]

        if len(comment_html) > 1000:
            response += "\n\n<i>... (текст сокращен, полный текст сохранен в БД)</i>"

        if buttons:
            response += f"\n\n🔘 <b>Кнопки ({len(buttons)}):</b>"
            for i, btn in enumerate(buttons, 1):
                response += f"\n{i}. {btn['text']}"
                if len(btn['url']) > 30:
                    response += f"\n   → <code>{btn['url']}</code>"
                else:
                    response += f"\n   → <code>{btn['url']}</code>"


        await message.reply(response, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка в show_first_comment_handler: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при получении первого комментария")


# Для отладки
#@first_comment_commands_router.message(F.text == "/debug_html")
async def debug_html_handler(message: Message):
    """Отладка HTML текста"""
    try:
        debug_info = f"""
📊 <b>Информация о сообщении:</b>

<b>message.text:</b>
<code>{str(message.text)}</code>

<b>message.html_text:</b>
<code>{message.html_text}</code>

<b>Есть ли html_text:</b> {bool(message.html_text)}
<b>Тип сообщения:</b> {message.content_type}
"""

        if message.html_text:
            debug_info += f"\n\n<b>Длина html_text:</b> {len(message.html_text)} символов"
            debug_info += f"\n<b>Пример html_text:</b>\n<code>{message.html_text}</code>"

        await message.reply(debug_info, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка в debug_html_handler: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {str(e)}")