import re
from typing import List, Dict

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def contains_links(text: str) -> bool:
    """Проверяет, содержит ли текст ссылки, игнорируя ссылки на приватные чаты t.me/c/"""
    if not text:
        return False

    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|'
        r'www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|'
        r't\.me/[a-zA-Z0-9_]+|'
        r'@[a-zA-Z0-9_]{5,}'
    )

    # Ищем все ссылки в тексте
    all_links = url_pattern.findall(text)
    if not all_links:
        return False

    # Фильтруем ссылки на приватные чаты (t.me/c/)
    filtered_links = []

    for link in all_links:
        # Игнорируем все ссылки типа t.me/c/ (приватные чаты)
        if 't.me/c/' in link:
            continue

        # Если ссылка не является ссылкой на приватный чат, добавляем в список
        filtered_links.append(link)

    # Возвращаем True только если остались ссылки не на приватные чаты
    return len(filtered_links) > 0

def get_moderation_keyboard(chat_id: int, user_id: int, content_type: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"approve_{content_type}_{chat_id}_{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_{content_type}_{chat_id}_{user_id}"
            )
        ]
    ])


def get_note_moderation_keyboard(chat_id: int, user_id: int, note_name: str, is_edit: bool = False):
    """Создает клавиатуру для модерации заметки"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Одобрить",
        callback_data=f"approve_note:{chat_id}:{user_id}:{note_name}"
    )
    builder.button(
        text="❌ Отклонить",
        callback_data=f"reject_note:{chat_id}:{user_id}:{note_name}"
    )

    builder.adjust(2)
    return builder.as_markup()


def get_first_comment_moderation_keyboard(channel_id: int, user_id: int):
    """Создает клавиатуру для модерации первого комментария"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Одобрить",
        callback_data=f"approve_first_comment:{channel_id}:{user_id}"
    )
    builder.button(
        text="❌ Отклонить",
        callback_data=f"reject_first_comment:{channel_id}:{user_id}"
    )

    builder.adjust(2)
    return builder.as_markup()


def extract_urls_from_buttons(buttons: List[Dict[str, str]]) -> List[str]:
    """Извлекает все URL из кнопок"""
    return [btn['url'] for btn in buttons]