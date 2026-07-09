from aiogram import Router, F
from aiogram.types import Message
import re
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsUtils import contains_links, \
    extract_urls_from_buttons, get_first_comment_moderation_keyboard
from handlers.BotAutomaticWork.Gonfig.config import AGENT_CHAT_ID_CheckTextApprovals
from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import (
    set_first_comment, add_pending_first_comment, delete_first_comment, get_first_comment
)
import logging

logger = logging.getLogger(__name__)
first_comment_commands_router = Router()


def parse_buttons_from_text(text: str) -> tuple[str, list]:
    """
    Парсинг текста и извлечение кнопок в формате [текст](ссылка)
    Возвращает (очищенный_текст, список_кнопок)
    """
    buttons = []

    # Паттерн для поиска [текст](ссылка)
    # Ищем все вхождения, где текст в квадратных скобках, а ссылка в круглых
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'

    # Находим все совпадения
    matches = re.findall(pattern, text)

    for match in matches:
        button_text = match[0].strip()
        button_url = match[1].strip()

        # Проверяем, что URL начинается с http:// или https://
        if button_url.startswith(('http://', 'https://')):
            buttons.append({
                'text': button_text,
                'url': button_url
            })
            logger.debug(f"🔘 Найдена кнопка: {button_text} -> {button_url}")

    # Удаляем все найденные конструкции [текст](ссылка) из текста
    clean_text = re.sub(pattern, '', text)

    # Очищаем лишние переносы строк
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
    clean_text = clean_text.strip()

    return clean_text, buttons


def parse_first_comment_command_text(text: str):
    """Парсинг команды из обычного текста"""
    parts = text.split("\n", 1)
    if len(parts) < 2:
        return "", []

    raw_text = parts[1].strip()
    # Парсим кнопки из текста
    comment_text, buttons = parse_buttons_from_text(raw_text)
    return comment_text, buttons


def parse_first_comment_html_command(message: Message):
    """Парсинг команды из HTML-текста"""
    parts = message.html_text.split("\n", 1)
    if len(parts) < 2:
        return "", []

    raw_text = parts[1].strip()
    # Парсим кнопки из текста
    comment_text, buttons = parse_buttons_from_text(raw_text)
    return comment_text, buttons


@first_comment_commands_router.message(F.text.startswith("+первый комментарий"))
async def add_first_comment_handler(message: Message):
    """Добавление первого комментария с автоматическим созданием кнопок из [текст](ссылка)"""
    try:

        has_access = await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 74)
        if not has_access:
            return

        if message.html_text:
            comment_html, buttons = parse_first_comment_html_command(message)
        else:
            comment_html, buttons = parse_first_comment_command_text(message.text or "")

        if not comment_html:
            await message.reply("Укажите текст комментария после команды")
            return

        comment_html = comment_html.strip()
        if len(comment_html) > 4000:
            await message.reply("Текст комментария слишком длинный (макс. 4000 символов)")
            return

        # Сохраняем ID чата, где введена команда (ГРУППА)
        chat_id = message.chat.id


        # Проверяем наличие ссылок в тексте
        has_links = contains_links(comment_html)
        if buttons:
            button_urls = extract_urls_from_buttons(buttons)
            if button_urls:
                has_links = True



        # Если есть ссылки - отправляем на модерацию
        if has_links:
            try:
                chat_link = await chat_global_link(chat_id)
                user_link = await user_link_global(message.from_user.id)

                # Формируем предпросмотр с кнопками
                preview = comment_html[:300] + ('...' if len(comment_html) > 300 else '')
                buttons_preview = ""
                if buttons:
                    buttons_preview = f"\n\n🔘 <b>Кнопки ({len(buttons)}):</b>\n"
                    for i, btn in enumerate(buttons[:3], 1):
                        buttons_preview += f"{i}. {btn['text']} → {btn['url'][:50]}...\n"
                    if len(buttons) > 3:
                        buttons_preview += f"... и еще {len(buttons) - 3}"

                admin_message = await message.bot.send_message(
                    AGENT_CHAT_ID_CheckTextApprovals,
                    f"📌 <b>Первый комментарий на проверку</b>\n\n"
                    f"💬 <b>Текст:</b>\n{preview}{buttons_preview}\n\n"
                    f"ℹ️ Некая информация:\n"
                    f"<b>Чат:</b> {chat_link}\n"
                    f"<b>Пользователь:</b> {user_link}",
                    reply_markup=get_first_comment_moderation_keyboard(chat_id, message.from_user.id),
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

                await message.reply('Комментарий отправлен на проверку, ожидайте.')

                await add_pending_first_comment(
                    chat_id,
                    comment_html,
                    message.message_id,
                    admin_message.message_id,
                    message.from_user.id,
                    buttons
                )

            except Exception as e:
                logger.error(f"❌ Ошибка отправки на модерацию: {e}", exc_info=True)
                await message.reply('Ошибка при отправке на модерацию')
            return

        # Если ссылок нет - сохраняем сразу
        try:
            success = await set_first_comment(chat_id, comment_html, buttons)
            if success:
                preview = comment_html[:200] + ('...' if len(comment_html) > 200 else '')
                response = f"✅ Первый комментарий установлен"
                if buttons:
                    response += f"\n\n🔘 <b>Кнопки ({len(buttons)}):</b>"
                    for i, btn in enumerate(buttons, 1):
                        response += f"\n{i}. {btn['text']} → <code>{btn['url']}</code>"
                await message.reply(response, parse_mode='HTML')
            else:
                await message.reply("Ошибка при сохранении")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения: {e}", exc_info=True)
            await message.reply("Ошибка при сохранении")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в add_first_comment_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при установке первого комментария")


@first_comment_commands_router.message(F.text.startswith("-первый комментарий"))
async def delete_first_comment_handler(message: Message):
    """Удаление первого комментария"""
    try:
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 74):
            return

        chat_id = message.chat.id
        success = await delete_first_comment(chat_id)

        if success:
            await message.reply("✅ Первый комментарий удален")
        else:
            await message.reply("Первый комментарий не найден")

    except Exception as e:
        logger.error(f"Ошибка в delete_first_comment_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при удалении первого комментария")


@first_comment_commands_router.message(F.text.startswith(".первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("!первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("/первый комментарий"))
@first_comment_commands_router.message(F.text.startswith("первый комментарий"))
async def show_first_comment_handler(message: Message):
    """Показать первый комментарий"""
    try:
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 75):
            return

        chat_id = message.chat.id
        first_comment = await get_first_comment(chat_id)

        if not first_comment:
            await message.reply("Первый комментарий не установлен для этой группы")
            return

        comment_html = first_comment['comment_text']
        buttons = first_comment['buttons']

        response = f"📍 <b>Первый комментарий:</b>\n\n"
        response += comment_html

        if buttons:
            response += f"\n\n🔘 <b>Кнопки ({len(buttons)}):</b>"
            for i, btn in enumerate(buttons, 1):
                response += f"\n{i}. {btn['text']} → <code>{btn['url']}</code>"

        await message.reply(response, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка в show_first_comment_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при получении первого комментария")