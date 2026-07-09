import logging
import re

from aiogram import Router, F, types
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.AdminsTools.ChatSettings.notes.notesDB import add_note, delete_note, get_note, get_all_notes, \
    search_notes, get_note_by_name, update_note_text, rename_note
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsUtils import contains_links, \
    get_note_moderation_keyboard
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsDB import get_pending_moderation_note, \
    add_pending_moderation_note
from handlers.BotAutomaticWork.Gonfig.config import AGENT_CHAT_ID_CheckTextApprovals
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

notes_router = Router()

logger = logging.getLogger(__name__)


def parse_note_args(text: str) -> tuple[str, str]:
    """Парсинг аргументов для команды заметки"""
    # Убираем команду
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return "", ""

    # Получаем всё после команды
    content = parts[1]

    # Ищем первое вхождение перевода строки после команды
    first_newline = content.find('\n')

    if first_newline == -1:
        # Если нет перевода строки - всё это название
        return content.strip(), ""
    else:
        # Всё до первого перевода строки - название
        # Всё после первого перевода строки - текст заметки
        note_name = content[:first_newline].strip()
        note_text = content[first_newline + 1:].strip()
        return note_name, note_text


def get_command_args(text: str, command: str) -> str:
    """Извлечение аргументов после команды"""
    # Удаляем команду и пробелы в начале
    return text[len(command):].strip()


def extract_note_identifier(text: str) -> str:
    # Убираем все возможные префиксы в начале
    prefixes = ["/заметка", ".заметка", "!заметка", "заметка"]

    for prefix in prefixes:
        if text.lower().startswith(prefix):
            # Убираем префикс и лишние пробелы
            identifier = text[len(prefix):].strip()
            return identifier

    return ""


@notes_router.message(lambda m: m.text and m.text.lower().startswith("+заметка"))
async def add_note_handler(message: Message):
    """Добавление новой заметки: +заметка название\nтекст"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 51):
        return

    try:
        # Парсим аргументы
        note_name, note_text = parse_note_args(message.text)

        # Валидация
        if not note_name:
            await message.reply("Укажите название заметки после команды")
            return

        if not note_text:
            await message.reply('Укажите текст заметки после названия, начиная с новой строки.')
            return

        # Получаем HTML-текст для сохранения форматирования
        if message.html_text:
            html_text = message.html_text
            # Ищем перенос строки после команды
            lines = html_text.split('\n', 1)
            if len(lines) > 1:
                html_note_text = lines[1].strip()
            else:
                html_note_text = ""
        else:
            html_note_text = message.text.split('\n', 1)[1].strip() if '\n' in message.text else ""

        # Проверяем, существует ли уже заметка с таким названием
        existing_note = await get_note_by_name(message.chat.id, note_name)
        if existing_note:
            await message.reply("Заметка с таким названием уже существует")
            return

        # Проверка на ссылки
        if contains_links(html_note_text):
            # Если есть ссылки - отправляем на модерацию
            chat_id = message.chat.id
            user_id = message.from_user.id

            chat_link = await chat_global_link(chat_id)
            user_link = await user_link_global(user_id)

            try:
                admin_message = await message.bot.send_message(
                    AGENT_CHAT_ID_CheckTextApprovals,
                    f"📋 <b>Новая заметка на проверку</b>\n"
                    f"<b>Название:</b> {note_name}\n\n"
                    f"<b>💬 Текст заметки:</b>\n{html_note_text}\n\n"
                    f"<b>Чат:</b> {chat_link}\n"
                    f"<b>Пользователь:</b> {user_link}",
                    reply_markup=get_note_moderation_keyboard(chat_id, user_id, note_name, is_edit=False),
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

                await message.reply('Заметка отправлена на проверку, ожидайте.')

                # Проверяем существующую запись модерации
                existing = await get_pending_moderation_note(chat_id, note_name)

                if existing:
                    try:
                        await message.bot.delete_message(AGENT_CHAT_ID_CheckTextApprovals, existing['admin_message_id'])
                    except Exception:
                        pass  # Игнорируем ошибки удаления старого сообщения

                # Создаем или обновляем запись
                await add_pending_moderation_note(
                    chat_id,
                    note_name,
                    html_note_text,  # Сохраняем HTML-текст
                    message.message_id,
                    admin_message.message_id,
                    user_id,
                    is_edit=False
                )

            except Exception as e:
                await message.reply('❌ Ошибка при отправке на модерацию.')
                logger.error(f"Ошибка при отправке на модерацию: {e}", exc_info=True)
                return

        else:
            # Если ссылок нет - сразу сохраняем
            result = await add_note(message.chat.id, note_name, html_note_text)

            if result.get('success', False):
                await message.reply(f"✅ Заметка «{note_name}» добавлена")
            else:
                await message.reply(f"Ошибка при добавлении заметки: {result.get('error', 'Неизвестная ошибка')}")

    except Exception as e:
        logger.error(f"Ошибка в add_note_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при добавлении заметки")


@notes_router.message(lambda m: m.text and m.text.lower().startswith("-заметка"))
async def delete_note_handler(message: Message):
    """Удаление заметки: -заметка название_или_номер"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 51):
        return

    try:
        # Получаем аргумент (идентификатор)
        identifier = get_command_args(message.text, "-заметка")

        if not identifier:
            await message.reply("Укажите название или номер заметки для удаления")
            return

        # Получаем заметку перед удалением, чтобы показать название
        note = await get_note(message.chat.id, identifier)
        if not note:
            await message.reply("Заметка не найдена")
            return

        # Удаляем заметку
        success = await delete_note(message.chat.id, identifier)

        if success:
            await message.reply(f"✅ Заметка «{note['notes_name']}» удалена")
        else:
            await message.reply("Ошибка при удалении заметки")

    except Exception as e:
        logger.error(f"Ошибка в delete_note_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при удалении заметки")


@notes_router.message(lambda m: m.text and m.text.lower().startswith("~заметка"))
async def edit_note_content_handler(message: Message):
    """Редактирование содержимого заметки: ~заметка название_или_номер\nновый_текст"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 51):
        return

    try:
        # Парсим аргументы
        note_identifier, note_text = parse_note_args(message.text)

        # Валидация
        if not note_identifier:
            await message.reply("Укажите название или номер заметки для редактирования")
            return

        if not note_text:
            await message.reply('Укажите новый текст заметки после названия/номера, начиная с новой строки.')
            return

        # Проверяем существование заметки
        current_note = await get_note(message.chat.id, note_identifier)
        if not current_note:
            await message.reply("Заметка не найдена")
            return

        note_name = current_note['notes_name']

        # Получаем HTML-текст
        if message.html_text:
            html_text = message.html_text
            lines = html_text.split('\n', 1)
            if len(lines) > 1:
                html_note_text = lines[1].strip()
            else:
                html_note_text = ""
        else:
            html_note_text = message.text.split('\n', 1)[1].strip() if '\n' in message.text else ""

        # Проверка на ссылки
        if contains_links(html_note_text):
            # Если есть ссылки - отправляем на модерацию
            chat_id = message.chat.id
            user_id = message.from_user.id

            chat_link = await chat_global_link(chat_id)
            user_link = await user_link_global(user_id)

            try:
                admin_message = await message.bot.send_message(
                    AGENT_CHAT_ID_CheckTextApprovals,
                    f"📝 <b>Редактирование заметки на проверку</b>\n"
                    f"<b>Название:</b> {note_name}\n\n"
                    f"<b>💬 Новый текст заметки:</b>\n{html_note_text}\n\n"
                    f"<b>Чат:</b> {chat_link}\n"
                    f"<b>Пользователь:</b> {user_link}",
                    reply_markup=get_note_moderation_keyboard(chat_id, user_id, note_name, is_edit=True),
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

                await message.reply('Изменения отправлены на проверку, ожидайте.')

                # Сохраняем в БД модерации с is_edit=True
                await add_pending_moderation_note(
                    chat_id,
                    note_name,
                    html_note_text,
                    message.message_id,
                    admin_message.message_id,
                    user_id,
                    is_edit=True  # Важно!
                )

            except Exception as e:
                await message.reply('Ошибка при отправке на модерацию.')
                logger.error(f"Ошибка при отправке на модерацию: {e}", exc_info=True)
                return

        else:
            # Если ссылок нет - сразу обновляем
            success = await update_note_text(message.chat.id, note_identifier, html_note_text)

            if success:
                await message.reply(f"✅ Заметка «{note_name}» обновлена")
            else:
                await message.reply("Ошибка при обновлении заметки")

    except Exception as e:
        logger.error(f"Ошибка в edit_note_content_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при редактировании заметки")


@notes_router.message(lambda m: m.text and m.text.lower().startswith("~название заметки"))
async def rename_note_handler(message: Message):
    """Переименование заметки: ~название заметки старое_название/номер новое_название"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 51):
        return

    try:
        # Получаем аргументы
        args = message.text.split(maxsplit=3)
        if len(args) < 4:
            await message.reply("Формат команды: ~название заметки {старое_название/номер} {новое_название}")
            return

        old_identifier = args[2].strip()
        new_name = args[3].strip()

        # Валидация
        if not new_name:
            await message.reply("Укажите новое название заметки")
            return

        if len(new_name) > 100:
            await message.reply("Название заметки не должно превышать 100 символов")
            return

        # Получаем текущую заметку
        current_note = await get_note(message.chat.id, old_identifier)
        if not current_note:
            await message.reply("Заметка не найдена")
            return

        # Проверяем, не существует ли уже заметка с таким названием
        existing_note = await get_note_by_name(message.chat.id, new_name)
        if existing_note and existing_note['notes_name'] != current_note['notes_name']:
            await message.reply("Заметка с таким названием уже существует")
            return

        # Переименовываем
        success = await rename_note(message.chat.id, old_identifier, new_name)

        if success:
            await message.reply(f"✅ Заметка «{current_note['notes_name']}» переименована в «{new_name}»")
        else:
            await message.reply("Ошибка при переименовании заметки")

    except Exception as e:
        logger.error(f"Ошибка в rename_note_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при переименовании заметки")


@notes_router.message(lambda m: m.text and m.text.lower().startswith("/заметка"))
@notes_router.message(lambda m: m.text and m.text.lower().startswith(".заметка"))
@notes_router.message(lambda m: m.text and m.text.lower().startswith("!заметка"))
@notes_router.message(lambda m: m.text and m.text.lower().startswith("заметка"))
async def show_note_handler(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 52):
        return

    """Показать заметку: заметка название_или_номер"""
    try:
        # Извлекаем идентификатор заметки
        identifier = extract_note_identifier(message.text)

        if not identifier:
            await message.reply("❌ Укажите название или номер заметки")
            return

        # Получаем заметку
        note = await get_note(message.chat.id, identifier)

        if note:
            # Проверяем наличие HTML-разметки в тексте
            note_text = note['notes_text']
            parse_mode = 'HTML' if '<' in note_text and '>' in note_text else None

            response = (f"📝 Заметка «{note['notes_name']}»\n\n"
                        f"{note_text}")

            # Определяем, на какое сообщение отвечать
            reply_to_message_id = None
            if message.reply_to_message:
                # Если команда была отправлена в ответ на другое сообщение
                reply_to_message_id = message.reply_to_message.message_id

            await bot.send_message(
                chat_id=message.chat.id,
                text=response,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
                reply_to_message_id=reply_to_message_id  # Передаем ID сообщения для ответа
            )
        else:
            await message.reply("Заметка не найдена")

    except Exception as e:
        logger.error(f"Ошибка в show_note_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при поиске заметки")


# Константы для пагинации
NOTES_PER_PAGE = 10


@notes_router.message(F.text.regexp(re.compile(r'^[!/.]заметки(\s|$)', re.IGNORECASE)))
@notes_router.message(lambda m: m.text and m.text.lower().startswith("заметки"))
async def list_notes_handler(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 52):
        return

    """Показать все заметки чата с пагинацией"""
    try:
        await show_notes_page(message, page=1)

    except Exception as e:
        logger.error(f"Ошибка в list_notes_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при получении списка заметок")



async def show_notes_page(message: Message, page: int, search_term: str = None, edit_message: bool = False):
    """Показать страницу с заметками"""
    try:
        chat_id = message.chat.id
        if search_term:
            notes = await search_notes(chat_id, search_term)
            title = f"🔍 Результаты поиска \"{search_term}\""
        else:
            notes = await get_all_notes(chat_id)
            title = "📋 Список заметок"

        if not notes:
            if search_term:
                response = "Заметка не найдена"
            else:
                response = "В этом чате нет заметок"

            if edit_message:
                await message.edit_text(response)
            else:
                await message.reply(response)
            return

        # Рассчитываем пагинацию
        total_notes = len(notes)
        total_pages = (total_notes + NOTES_PER_PAGE - 1) // NOTES_PER_PAGE
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * NOTES_PER_PAGE
        end_idx = min(start_idx + NOTES_PER_PAGE, total_notes)
        page_notes = notes[start_idx:end_idx]

        # Формируем сообщение
        response = f"{title} (стр. {page}/{total_pages}):\n\n"
        for i, note in enumerate(page_notes, start=start_idx + 1):
            response += f"{note.get('notes_id', i)}. {note['notes_name']}\n"

        # Создаем клавиатуру для пагинации
        keyboard = create_pagination_keyboard(page, total_pages, search_term)

        if edit_message:
            await message.edit_text(response, reply_markup=keyboard)
        elif message.reply_to_message:
            await message.reply_to_message.reply(response, reply_markup=keyboard)
        else:
            await message.reply(response, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в show_notes_page: {e}", exc_info=True)
        if not edit_message:
            await message.reply("Произошла ошибка при отображении заметок")


def create_pagination_keyboard(current_page: int, total_pages: int, search_term: str = None):
    """Создает клавиатуру для пагинации"""
    builder = InlineKeyboardBuilder()

    # Добавляем кнопки для навигации
    if current_page > 1:
        builder.button(
            text="⬅️ Назад",
            callback_data=f"notes_prev:{current_page - 1}:{search_term or ''}"
        )

    if current_page < total_pages:
        builder.button(
            text="Вперед ➡️",
            callback_data=f"notes_next:{current_page + 1}:{search_term or ''}"
        )

    # Настраиваем расположение кнопок
    if current_page > 1 and current_page < total_pages:
        builder.adjust(2)  # обе кнопки в одном ряду
    else:
        builder.adjust(1)  # одна кнопка в ряду

    return builder.as_markup()


# @notes_router.message(lambda m: m.text and m.text.lower().startswith("поиск заметки"))
async def search_notes_handler(message: Message):
    """Поиск заметок: поиск заметки текст_для_поиска"""
    try:
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 52):
            return

        # Получаем аргумент (поисковый запрос)
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.reply("Укажите текст для поиска")
            return

        search_term = args[2].strip()
        await show_notes_page(message, page=1, search_term=search_term)

    except Exception as e:
        logger.error(f"Ошибка в search_notes_handler: {e}", exc_info=True)
        await message.reply("Произошла ошибка при поиске заметок")


# Обработчики callback-запросов для пагинации
@notes_router.callback_query(F.data.startswith("notes_"))
@rate_limit_with_cleanup(limit=1)
async def handle_notes_pagination(callback: types.CallbackQuery):
    """Обработка пагинации заметок"""
    try:
        # Проверяем права пользователя
        if not await auto_check_AccessLevel_for_rang(callback.from_user.id, callback.message.chat.id, 52):
            await callback.answer("У вас недостаточно прав", show_alert=True)
            return

        # Проверяем, что пользователь является отправителем исходного сообщения
        if callback.message.reply_to_message:
            if callback.from_user.id != callback.message.reply_to_message.from_user.id:
                random_text = get_random_text()
                await callback.answer(f"{random_text}", show_alert=True)
                return
        else:
            # Если нет reply_to_message, проверяем чат
            if callback.from_user.id != callback.message.chat.id:
                await callback.answer("Эта кнопка не для вас", show_alert=True)
                return

        data = callback.data.split(":")
        if len(data) < 2:
            await callback.answer("Неверный формат данных", show_alert=True)
            return

        action = data[0]
        current_page = int(data[1]) if len(data) > 1 else 1
        search_term = data[2] if len(data) > 2 and data[2] else None

        if action == "notes_prev":
            new_page = max(1, current_page - 1)
        elif action == "notes_next":
            new_page = current_page + 1
        else:
            await callback.answer()
            return

        # Редактируем существующее сообщение вместо отправки нового
        await show_notes_page(callback.message, new_page, search_term, edit_message=True)
        await callback.answer()

    except ValueError:
        await callback.answer("Ошибка в данных пагинации", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в handle_notes_pagination: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при переключении страницы", show_alert=True)