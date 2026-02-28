# handlers/UserCommands/SettingsUsersProfile/PseudonymsUsers/emoji_utils.py
import re
import html


def protect_emoji_tags_for_escape(text: str) -> tuple[str, list]:
    """
    Защищает теги эмодзи от HTML-экранирования.
    Возвращает текст с временными маркерами и список оригинальных тегов.
    """
    if not text:
        return text, []

    emoji_tags = []

    def replace_tag(match):
        emoji_tags.append(match.group(0))
        return f'__EMOJI_PROTECTED_{len(emoji_tags) - 1}__'

    # Заменяем теги эмодзи на маркеры
    protected = re.sub(
        r'<tg-emoji emoji-id="\d+">[^<]*</tg-emoji>',
        replace_tag,
        text
    )

    return protected, emoji_tags


def restore_emoji_tags(text: str, emoji_tags: list) -> str:
    """Восстанавливает теги эмодзи из маркеров"""
    if not text or not emoji_tags:
        return text

    for i, tag in enumerate(emoji_tags):
        text = text.replace(f'__EMOJI_PROTECTED_{i}__', tag)
    return text


def format_pseudonym_for_display(pseudonym: str) -> str:
    """
    Форматирует псевдоним для отображения с поддержкой премиум эмодзи.

    Returns:
        str: HTML-строка с псевдонимом (без ссылки)
    """
    if not pseudonym:
        return ""

    # Если есть теги эмодзи, сохраняем их
    if '<tg-emoji' in pseudonym:
        # Защищаем теги эмодзи
        protected_text, emoji_tags = protect_emoji_tags_for_escape(pseudonym)

        # Экранируем остальной текст
        safe_text = html.escape(protected_text)

        # Восстанавливаем теги эмодзи
        return restore_emoji_tags(safe_text, emoji_tags)
    else:
        # Обычный текст без эмодзи
        return html.escape(pseudonym)



