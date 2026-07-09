import re
from typing import List, Dict, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def contains_links(text: str) -> bool:
    """Проверяет, содержит ли текст ссылки, игнорируя t.me/c/"""
    if not text:
        return False

    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|'
        r'www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|'
        r't\.me/[a-zA-Z0-9_]+|'
        r'@[a-zA-Z0-9_]{5,}'
    )

    all_links = url_pattern.findall(text)
    if not all_links:
        return False

    filtered_links = [link for link in all_links if 't.me/c/' not in link]
    return len(filtered_links) > 0


def get_moderation_keyboard(chat_id: int, user_id: int, content_type: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для модерации правил/приветствий.
    Формат: approve_rule:chat_id:user_id
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"approve_{content_type}:{chat_id}:{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_{content_type}:{chat_id}:{user_id}"
            )
        ]
    ])


def get_note_moderation_keyboard(chat_id: int, user_id: int, note_name: str, is_edit: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для модерации заметки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve_note:{chat_id}:{user_id}:{note_name}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_note:{chat_id}:{user_id}:{note_name}")
    builder.adjust(2)
    return builder.as_markup()


def get_first_comment_moderation_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для модерации первого комментария"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve_first_comment:{chat_id}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_first_comment:{chat_id}:{user_id}")
    builder.adjust(2)
    return builder.as_markup()


def extract_urls_from_buttons(buttons: Optional[List[Dict[str, str]]]) -> List[str]:
    """Извлекает все URL из кнопок"""
    if not buttons:
        return []
    return [btn['url'] for btn in buttons if btn.get('url')]