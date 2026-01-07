import logging
from typing import Optional
import unicodedata, re

logger = logging.getLogger(__name__)

def clean_name(name: Optional[str]) -> str:
    if not name:
        return ""

    try:
        # Нормализация Unicode
        normalized = unicodedata.normalize('NFKC', name)
        # Удаление нежелательных символов
        cleaned = re.sub(r'[^\w\s\-\.]', '', normalized)
        # Удаление лишних пробелов
        return ' '.join(cleaned.split())
    except Exception as e:
        logger.error(e, exc_info=True)
        return name